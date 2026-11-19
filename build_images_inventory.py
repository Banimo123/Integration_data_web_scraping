from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("L'inventaire source doit être une liste JSON.")
    return data


def load_products_csv(path: Path):
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        rows = list(reader)
    return rows


def basename_from_url(url: str) -> str:
    return Path(urlparse(url).path).name


def main():
    parser = argparse.ArgumentParser(
        description="Construit l'inventaire physique final des images Daraz."
    )
    parser.add_argument("--root", default=".", help="Racine du projet Daraz.")
    parser.add_argument("--source", default="images_inventory_csv_test.json")
    parser.add_argument("--products", default="output/produits_daraz.csv")
    parser.add_argument("--images-dir", default="output/images/daraz")
    parser.add_argument("--output", default="images_inventory.json")
    parser.add_argument(
        "--report",
        default="output/validation/module1_inventory_build_report.json"
    )
    args = parser.parse_args()

    project_root = Path(args.root).resolve()
    source_path = project_root / args.source
    products_path = project_root / args.products
    images_root = project_root / args.images_dir
    output_path = project_root / args.output
    report_path = project_root / args.report

    if not source_path.exists():
        raise FileNotFoundError(f"Inventaire source introuvable : {source_path}")
    if not images_root.exists():
        raise FileNotFoundError(f"Dossier d'images introuvable : {images_root}")

    records = load_json(source_path)
    product_rows = load_products_csv(products_path)

    # Index physique : (nom du dossier produit, nom du fichier en minuscules).
    physical_index = defaultdict(list)
    all_physical_files = []
    for path in images_root.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            all_physical_files.append(path)
            physical_index[(path.parent.name, path.name.lower())].append(path)

    output_records = []
    missing = []
    ambiguous = []
    matched_paths = set()
    folder_ids = {p.name for p in images_root.iterdir() if p.is_dir()}

    for rec in records:
        entity_id = str(rec["entity_id"])
        image_name = str(rec["image_name"])
        candidates = physical_index.get((entity_id, image_name.lower()), [])

        # Si l'image est rangée dans un sous-dossier du dossier produit,
        # rechercher également dans tout l'arbre du produit.
        if not candidates:
            product_folder = images_root / entity_id
            if product_folder.exists():
                candidates = [
                    p for p in product_folder.rglob("*")
                    if p.is_file() and p.name.lower() == image_name.lower()
                ]

        new_rec = dict(rec)
        if len(candidates) == 1:
            actual_path = candidates[0]
            new_rec["file_path"] = actual_path.relative_to(project_root).as_posix()
            new_rec["file_size_bytes"] = actual_path.stat().st_size
            new_rec["physical_file_exists"] = True
            matched_paths.add(actual_path.resolve())
        elif len(candidates) > 1:
            expected = images_root / entity_id / image_name
            new_rec["file_path"] = expected.relative_to(project_root).as_posix()
            new_rec["file_size_bytes"] = None
            new_rec["physical_file_exists"] = False
            ambiguous.append({
                "image_id": rec["image_id"],
                "entity_id": entity_id,
                "image_name": image_name,
                "candidate_paths": [
                    p.relative_to(project_root).as_posix() for p in candidates
                ],
            })
        else:
            expected = images_root / entity_id / image_name
            new_rec["file_path"] = expected.relative_to(project_root).as_posix()
            new_rec["file_size_bytes"] = None
            new_rec["physical_file_exists"] = False
            missing.append({
                "image_id": rec["image_id"],
                "entity_id": entity_id,
                "image_name": image_name,
                "expected_path": expected.relative_to(project_root).as_posix(),
                "product_folder_exists": entity_id in folder_ids,
            })

        output_records.append(new_rec)

    # Contrôles croisés avec le CSV produit, s'il est présent.
    csv_check = {
        "csv_found": product_rows is not None,
        "product_rows": len(product_rows) if product_rows is not None else None,
        "sum_nb_images": None,
        "products_with_images": None,
        "products_without_images": None,
        "image_count_mismatches": [],
        "image_url_order_mismatches": [],
    }

    if product_rows is not None:
        csv_image_counts = {}
        csv_urls_by_id = {}
        for row in product_rows:
            product_id = str(row.get("id", "")).strip()
            urls = [u for u in str(row.get("liens_images", "")).split("|") if u.strip()]
            try:
                declared_count = int(row.get("nb_images", "0") or 0)
            except ValueError:
                declared_count = -1

            csv_image_counts[product_id] = declared_count
            csv_urls_by_id[product_id] = urls

            if declared_count != len(urls):
                csv_check["image_count_mismatches"].append({
                    "entity_id": product_id,
                    "nb_images": declared_count,
                    "number_of_urls": len(urls),
                })

        inv_by_entity = defaultdict(list)
        for row in output_records:
            inv_by_entity[str(row["entity_id"])].append(row)

        csv_check["sum_nb_images"] = sum(
            max(0, n) for n in csv_image_counts.values()
        )
        csv_check["products_with_images"] = sum(n > 0 for n in csv_image_counts.values())
        csv_check["products_without_images"] = sum(n == 0 for n in csv_image_counts.values())

        for product_id, declared_count in csv_image_counts.items():
            inventory_rows = inv_by_entity.get(product_id, [])
            if len(inventory_rows) != max(0, declared_count):
                csv_check["image_count_mismatches"].append({
                    "entity_id": product_id,
                    "csv_nb_images": declared_count,
                    "inventory_records": len(inventory_rows),
                })

            inv_urls = [str(row.get("image_url", "")) for row in inventory_rows]
            csv_urls = csv_urls_by_id.get(product_id, [])
            if inv_urls != csv_urls:
                csv_check["image_url_order_mismatches"].append({
                    "entity_id": product_id,
                    "csv_urls": len(csv_urls),
                    "inventory_urls": len(inv_urls),
                })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(output_records, f, ensure_ascii=False, indent=2)

    orphan_files = [
        p for p in all_physical_files if p.resolve() not in matched_paths
    ]

    report = {
        "module": 1,
        "platform": "daraz",
        "source_inventory": args.source,
        "physical_images_root": args.images_dir,
        "total_metadata_records": len(records),
        "unique_product_ids_in_inventory": len({str(r["entity_id"]) for r in records}),
        "physical_image_files_found": len(all_physical_files),
        "matched_physical_images": len(matched_paths),
        "missing_or_unmatched_metadata_images": len(missing),
        "ambiguous_image_matches": len(ambiguous),
        "orphan_physical_images_not_in_inventory": len(orphan_files),
        "product_folders_found": len(folder_ids),
        "product_folders_with_inventory_images": len({
            str(r["entity_id"]) for r in records
        } & folder_ids),
        "csv_cross_check": csv_check,
        "missing_images": missing,
        "ambiguous_matches": ambiguous,
        "orphan_files_sample": [
            p.relative_to(project_root).as_posix() for p in orphan_files[:100]
        ],
        "notes": [
            "Aucun fichier image n'a été modifié, déplacé ou supprimé.",
            "Les correspondances sont faites par entity_id (dossier produit) et image_name.",
            "Les chemins attendus des images absentes sont conservés afin que le Module 2 puisse les signaler.",
            "Les images ambiguës ne sont pas choisies automatiquement."
        ],
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("=== INVENTAIRE PHYSIQUE DARAZ ===")
    print(f"Enregistrements metadata : {len(records)}")
    print(f"Fichiers image physiques trouvés : {len(all_physical_files)}")
    print(f"Images associées : {len(matched_paths)}")
    print(f"Images non trouvées : {len(missing)}")
    print(f"Correspondances ambiguës : {len(ambiguous)}")
    print(f"Images physiques orphelines : {len(orphan_files)}")
    print(f"Inventaire créé : {output_path}")
    print(f"Rapport créé : {report_path}")

    if csv_check["csv_found"]:
        print("\n=== CONTRÔLE CROISÉ CSV ===")
        print(f"Lignes produits : {csv_check['product_rows']}")
        print(f"Somme nb_images : {csv_check['sum_nb_images']}")
        print(f"Produits avec images : {csv_check['products_with_images']}")
        print(f"Produits sans images : {csv_check['products_without_images']}")
        print(f"Écarts de comptage : {len(csv_check['image_count_mismatches'])}")
        print(f"Écarts d'URL/ordre : {len(csv_check['image_url_order_mismatches'])}")

    if missing or ambiguous:
        print(
            "\nATTENTION : consulte le rapport avant les modules 2 à 5. "
            "Les images non trouvées ou ambiguës devront être expliquées."
        )


if __name__ == "__main__":
    main()
