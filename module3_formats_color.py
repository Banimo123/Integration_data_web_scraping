"""Module 3 — Analyse des formats et caractéristiques colorimétriques.

Entrées : images_inventory.json et module2_integrity.json
Sorties :
- output/validation/module3_formats_color.json
- output/validation/module3_formats_color_summary.json
- output/validation/module3_formats_color_errors.json (si nécessaire)

Aucune conversion ou modification des images originales n'est effectuée.
"""
from __future__ import annotations

import argparse
import io
from collections import Counter
from pathlib import Path

from PIL import Image, ImageCms

from audit_common import (
    PROJECT_ROOT,
    image_path_from_record,
    load_integrity_map,
    load_inventory,
    print_input_summary,
    valid_inventory_records,
    write_json,
)


def detect_transparency(image: Image.Image) -> bool:
    """Détecte des pixels réellement transparents, y compris certains PNG/GIF palette."""
    bands = image.getbands()

    if "A" in bands:
        try:
            alpha = image.getchannel("A")
            minimum, _maximum = alpha.getextrema()
            return minimum < 255
        except Exception:
            return False

    transparency = image.info.get("transparency")
    if transparency is None:
        return False

    # PNG/GIF en mode palette : l'index transparent doit être réellement utilisé.
    if isinstance(transparency, int):
        try:
            return any(pixel == transparency for pixel in image.getdata())
        except Exception:
            return False

    # Une table d'alpha peut être stockée sous forme de bytes ou de liste.
    if isinstance(transparency, (bytes, bytearray, list, tuple)):
        try:
            used_indices = set(image.getdata())
            return any(
                index < len(transparency) and transparency[index] < 255
                for index in used_indices
                if isinstance(index, int)
            )
        except Exception:
            # Cas d'une couleur transparente RGB (clé de transparence).
            try:
                return any(pixel == transparency for pixel in image.getdata())
            except Exception:
                return False

    return False


def detect_color_profile(image: Image.Image):
    icc_data = image.info.get("icc_profile")
    if not icc_data:
        return None

    try:
        profile = ImageCms.getOpenProfile(io.BytesIO(icc_data))
        name = ImageCms.getProfileName(profile).strip()
        return name if name else "Profil ICC présent (nom non disponible)"
    except Exception:
        return "Profil ICC présent (non interprétable)"


def main() -> None:
    parser = argparse.ArgumentParser(description="Module 3 : formats et caractéristiques couleur.")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT))
    parser.add_argument("--inventory", default="images_inventory.json")
    parser.add_argument("--integrity", default="output/validation/module2_integrity.json")
    parser.add_argument("--output", default="output/validation/module3_formats_color.json")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    inventory, inventory_path = load_inventory(root, args.inventory)
    integrity = load_integrity_map(root, args.integrity)
    valid_records = valid_inventory_records(inventory, integrity)
    print_input_summary(inventory_path, len(inventory))
    print(f"Images techniquement valides à analyser : {len(valid_records)}")

    results = []
    errors = []

    for index, record in enumerate(valid_records, start=1):
        path = image_path_from_record(root, record)
        try:
            with Image.open(path) as image:
                image_format = image.format
                color_mode = image.mode
                bands = image.getbands()
                has_alpha = "A" in bands
                has_transparency = detect_transparency(image)
                color_profile = detect_color_profile(image)

            extension_source = record.get("image_name") or str(record["file_path"])
            file_extension = Path(extension_source).suffix

            results.append({
                "image_id": record["image_id"],
                "file_path": str(record["file_path"]),
                "image_format": image_format,
                "file_extension": file_extension,
                "color_mode": color_mode,
                "has_alpha_channel": has_alpha,
                "has_transparency": has_transparency,
                "color_profile": color_profile,
            })
        except Exception as exc:
            errors.append({
                "image_id": record["image_id"],
                "file_path": str(record["file_path"]),
                "error_message": f"{type(exc).__name__}: {exc}"[:500],
            })

        if index % 100 == 0 or index == len(valid_records):
            print(f"Analyse : {index}/{len(valid_records)}")

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = root / output_path
    write_json(output_path, results)

    summary = {
        "total_valid_images_received": len(valid_records),
        "total_images_analyzed": len(results),
        "total_errors": len(errors),
        "format_distribution": dict(Counter(str(row["image_format"]) for row in results)),
        "color_mode_distribution": dict(Counter(str(row["color_mode"]) for row in results)),
        "images_with_alpha_channel": sum(row["has_alpha_channel"] for row in results),
        "images_with_transparency": sum(row["has_transparency"] for row in results),
        "images_with_color_profile": sum(row["color_profile"] is not None for row in results),
    }
    summary_path = output_path.with_name("module3_formats_color_summary.json")
    write_json(summary_path, summary)

    if errors:
        write_json(output_path.with_name("module3_formats_color_errors.json"), errors)

    print(f"\nRapport créé : {output_path}")
    print(f"Résumé créé : {summary_path}")
    print("Bilan :", summary)


if __name__ == "__main__":
    main()
