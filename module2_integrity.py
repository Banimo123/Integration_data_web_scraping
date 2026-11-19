"""Module 2 — Vérification de l'intégrité technique des images.

Entrée : images_inventory.json
Sortie : output/validation/module2_integrity.json

Aucun fichier image n'est modifié, déplacé ou supprimé.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, UnidentifiedImageError, ImageSequence

from audit_common import (
    PROJECT_ROOT,
    default_output_path,
    image_path_from_record,
    load_inventory,
    print_input_summary,
    write_json,
)


def inspect_image(path: Path) -> dict:
    if not path.exists():
        return {
            "file_exists": False,
            "file_size_bytes": None,
            "is_empty": False,
            "is_readable": False,
            "integrity_status": "missing",
            "error_message": "Fichier absent à l'emplacement indiqué dans l'inventaire.",
        }

    try:
        size = path.stat().st_size
    except PermissionError as exc:
        return {
            "file_exists": True,
            "file_size_bytes": None,
            "is_empty": False,
            "is_readable": False,
            "integrity_status": "unreadable",
            "error_message": f"{type(exc).__name__}: {exc}",
        }
    except OSError as exc:
        return {
            "file_exists": True,
            "file_size_bytes": None,
            "is_empty": False,
            "is_readable": False,
            "integrity_status": "unreadable",
            "error_message": f"{type(exc).__name__}: {exc}",
        }

    if size == 0:
        return {
            "file_exists": True,
            "file_size_bytes": 0,
            "is_empty": True,
            "is_readable": False,
            "integrity_status": "empty",
            "error_message": "Le fichier existe mais sa taille est égale à zéro octet.",
        }

    try:
        # verify() contrôle la structure du fichier. L'image doit ensuite être
        # rouverte, car verify() invalide l'objet Image pour un décodage ultérieur.
        with Image.open(path) as image:
            image.verify()

        # load() force le décodage des pixels. Pour les formats multi-images,
        # chaque frame est parcourue sans enregistrer ni modifier l'original.
        with Image.open(path) as image:
            frame_count = getattr(image, "n_frames", 1)
            for frame_index in range(frame_count):
                image.seek(frame_index)
                image.load()

        return {
            "file_exists": True,
            "file_size_bytes": size,
            "is_empty": False,
            "is_readable": True,
            "integrity_status": "valid",
            "error_message": None,
        }

    except PermissionError as exc:
        status = "unreadable"
        error_message = f"{type(exc).__name__}: {exc}"
    except (UnidentifiedImageError, OSError, EOFError, SyntaxError, ValueError) as exc:
        status = "corrupted"
        error_message = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        status = "unreadable"
        error_message = f"{type(exc).__name__}: {exc}"

    return {
        "file_exists": True,
        "file_size_bytes": size,
        "is_empty": False,
        "is_readable": False,
        "integrity_status": status,
        "error_message": error_message[:500],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Module 2 : audit d'intégrité des images.")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT), help="Racine du projet.")
    parser.add_argument("--inventory", default="images_inventory.json", help="Chemin de l'inventaire du Module 1.")
    parser.add_argument(
        "--output",
        default="output/validation/module2_integrity.json",
        help="Chemin du JSON de sortie.",
    )
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    inventory, inventory_path = load_inventory(root, args.inventory)
    print_input_summary(inventory_path, len(inventory))

    results = []
    for index, record in enumerate(inventory, start=1):
        path = image_path_from_record(root, record)
        check = inspect_image(path)
        results.append({
            "image_id": record["image_id"],
            "file_path": str(record["file_path"]),
            **check,
        })

        if index % 100 == 0 or index == len(inventory):
            print(f"Contrôle : {index}/{len(inventory)}")

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = root / output_path
    write_json(output_path, results)

    counts = {}
    for row in results:
        status = row["integrity_status"]
        counts[status] = counts.get(status, 0) + 1

    print(f"\nRapport créé : {output_path}")
    print("Bilan :", counts)


if __name__ == "__main__":
    main()
