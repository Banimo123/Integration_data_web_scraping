"""Module 5 — Détection des doublons visuels intra-dossier produit.

Entrées : images_inventory.json et module2_integrity.json
Sorties :
- output/validation/module5_visual_duplicates.json
- output/validation/module5_visual_duplicates_errors.json (si nécessaire)

Les comparaisons sont limitées au même couple (platform, entity_id).
Aucun fichier n'est supprimé, déplacé ou modifié.
"""
from __future__ import annotations

import argparse
import hashlib
from itertools import combinations
from pathlib import Path

from PIL import Image

try:
    import imagehash
except ImportError as exc:
    raise SystemExit(
        "La bibliothèque ImageHash est absente. Installe-la avec : "
        "python -m pip install ImageHash"
    ) from exc

from audit_common import (
    PROJECT_ROOT,
    image_path_from_record,
    load_integrity_map,
    load_inventory,
    print_input_summary,
    valid_inventory_records,
    write_json,
)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Module 5 : doublons exacts et visuels.")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT))
    parser.add_argument("--inventory", default="images_inventory.json")
    parser.add_argument("--integrity", default="output/validation/module2_integrity.json")
    parser.add_argument("--output", default="output/validation/module5_visual_duplicates.json")
    parser.add_argument(
        "--max-phash-distance",
        type=int,
        default=6,
        help="Distance de Hamming pHash maximale (sur 64 bits). Seuil initial à valider.",
    )
    args = parser.parse_args()

    if not 0 <= args.max_phash_distance <= 64:
        raise SystemExit("--max-phash-distance doit être compris entre 0 et 64.")

    root = Path(args.project_root).resolve()
    inventory, inventory_path = load_inventory(root, args.inventory)
    integrity = load_integrity_map(root, args.integrity)
    valid_records = valid_inventory_records(inventory, integrity)
    print_input_summary(inventory_path, len(inventory))
    print(f"Images valides candidates à la comparaison : {len(valid_records)}")
    print("Périmètre : comparaisons uniquement dans le même dossier (platform, entity_id).")

    groups = {}
    for record in valid_records:
        key = (str(record["platform"]), str(record["entity_id"]))
        groups.setdefault(key, []).append(record)

    results = []
    errors = []
    total_groups = len(groups)
    hash_bits = 64  # pHash 8x8 par défaut avec ImageHash.

    for group_index, (group_key, records) in enumerate(sorted(groups.items()), start=1):
        if len(records) < 2:
            continue

        prepared = []
        for record in records:
            path = image_path_from_record(root, record)
            try:
                sha = sha256_file(path)
                with Image.open(path) as image:
                    perceptual_hash = imagehash.phash(image, hash_size=8)
                prepared.append((record, path, sha, perceptual_hash))
            except Exception as exc:
                errors.append({
                    "image_id": record["image_id"],
                    "file_path": str(record["file_path"]),
                    "error_message": f"{type(exc).__name__}: {exc}"[:500],
                })

        for left, right in combinations(prepared, 2):
            record_1, _path_1, sha_1, phash_1 = left
            record_2, _path_2, sha_2, phash_2 = right

            common = {
                "platform": record_1["platform"],
                "entity_id": record_1["entity_id"],
                "image_id_1": record_1["image_id"],
                "image_id_2": record_2["image_id"],
                "file_path_1": str(record_1["file_path"]),
                "file_path_2": str(record_2["file_path"]),
            }

            if sha_1 == sha_2:
                results.append({
                    **common,
                    "duplicate_type": "exact_duplicate",
                    "comparison_method": "SHA-256",
                    "similarity_score": 1.0,
                    "threshold": None,
                    "cleaning_recommendation": "remove_one_copy",
                    "review_status": "pending",
                })
                continue

            distance = phash_1 - phash_2
            if distance <= args.max_phash_distance:
                similarity = 1.0 - (distance / hash_bits)
                threshold = 1.0 - (args.max_phash_distance / hash_bits)
                results.append({
                    **common,
                    "duplicate_type": "near_duplicate",
                    "comparison_method": "pHash",
                    "similarity_score": round(similarity, 6),
                    "threshold": round(threshold, 6),
                    "cleaning_recommendation": "manual_review",
                    "review_status": "pending",
                })

        if group_index % 50 == 0 or group_index == total_groups:
            print(f"Groupes produits examinés : {group_index}/{total_groups}")

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = root / output_path
    write_json(output_path, results)

    if errors:
        write_json(output_path.with_name("module5_visual_duplicates_errors.json"), errors)

    exact_count = sum(row["duplicate_type"] == "exact_duplicate" for row in results)
    near_count = sum(row["duplicate_type"] == "near_duplicate" for row in results)

    print(f"\nRapport créé : {output_path}")
    print(f"Doublons exacts : {exact_count}")
    print(f"Doublons visuellement similaires : {near_count}")
    print(f"Erreurs de lecture/hash : {len(errors)}")
    print(
        f"Seuil pHash utilisé : distance <= {args.max_phash_distance}/64 "
        f"(similarité >= {1 - args.max_phash_distance / 64:.4f})"
    )
    print("Aucune image n'a été supprimée ou modifiée.")


if __name__ == "__main__":
    main()
