"""Module 4 — Analyse de l'orientation EXIF.

Entrées : images_inventory.json et module2_integrity.json
Sortie : output/validation/module4_exif_orientation.json

Le script lit la balise EXIF Orientation (274) et ne tourne/modifie aucune image.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

from audit_common import (
    PROJECT_ROOT,
    image_path_from_record,
    load_integrity_map,
    load_inventory,
    print_input_summary,
    valid_inventory_records,
    write_json,
)


ORIENTATION_TAG = 274


def inspect_exif_orientation(path: Path) -> dict:
    try:
        with Image.open(path) as image:
            exif = image.getexif()
            exif_raw = image.info.get("exif")
            has_exif = bool(exif_raw) or len(exif) > 0

            value = exif.get(ORIENTATION_TAG)
            if value is None:
                status = "not_available"
                orientation_value = None
            else:
                try:
                    orientation_value = int(value)
                except (TypeError, ValueError):
                    orientation_value = None
                    status = "unknown"
                else:
                    if orientation_value == 1:
                        status = "normal"
                    elif 2 <= orientation_value <= 8:
                        status = "requires_correction"
                    else:
                        status = "unknown"

            return {
                "has_exif": has_exif,
                "exif_orientation": orientation_value,
                "orientation_status": status,
            }

    except Exception:
        return {
            "has_exif": False,
            "exif_orientation": None,
            "orientation_status": "unknown",
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Module 4 : lecture de l'orientation EXIF.")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT))
    parser.add_argument("--inventory", default="images_inventory.json")
    parser.add_argument("--integrity", default="output/validation/module2_integrity.json")
    parser.add_argument("--output", default="output/validation/module4_exif_orientation.json")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    inventory, inventory_path = load_inventory(root, args.inventory)
    integrity = load_integrity_map(root, args.integrity)
    valid_records = valid_inventory_records(inventory, integrity)
    print_input_summary(inventory_path, len(inventory))
    print(f"Images techniquement valides à examiner : {len(valid_records)}")

    results = []
    for index, record in enumerate(valid_records, start=1):
        path = image_path_from_record(root, record)
        exif_info = inspect_exif_orientation(path)
        results.append({
            "image_id": record["image_id"],
            "file_path": str(record["file_path"]),
            **exif_info,
        })

        if index % 100 == 0 or index == len(valid_records):
            print(f"Analyse EXIF : {index}/{len(valid_records)}")

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = root / output_path
    write_json(output_path, results)

    counts = {}
    for row in results:
        status = row["orientation_status"]
        counts[status] = counts.get(status, 0) + 1

    print(f"\nRapport créé : {output_path}")
    print("Bilan :", counts)


if __name__ == "__main__":
    main()
