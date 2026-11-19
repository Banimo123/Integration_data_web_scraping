"""
Scraping Daraz à partir du fichier fusionné du groupe.

Entrée :
    input/scp_groupe_400.xlsx

Sortie :
    output/produits_daraz.csv
"""

import argparse
import csv
from pathlib import Path

from openpyxl import load_workbook

from scrapers import daraz_scraper, playwright_manager
from utils import get_session, polite_delay, host_currency

INPUT_XLSX = Path("input/scp_groupe_400.xlsx")
OUTPUT_CSV = Path("output/produits_daraz.csv")

CSV_FIELDNAMES = [
    "id",
    "site",
    "row_id",
    "lien",
    "titre",
    "marque",
    "categorie",
    "sous_categorie",
    "prix",
    "devise",
    "description",
    "liens_images",
    "nb_images",
    "statut_scraping",
]


def read_products(path):
    wb = load_workbook(path, data_only=True, read_only=True)
    ws = wb["produits"]

    header = [
        cell.value
        for cell in next(ws.iter_rows(min_row=1, max_row=1))
    ]
    pos = {
        str(value).strip(): index
        for index, value in enumerate(header)
        if value is not None
    }

    required = {"id", "categorie", "sous_categorie", "daraz"}
    missing = required - set(pos)

    if missing:
        raise ValueError(
            f"Colonnes manquantes : {sorted(missing)}"
        )

    for row in ws.iter_rows(min_row=2, values_only=True):
        url = row[pos["daraz"]]

        if not isinstance(url, str):
            continue

        url = url.strip()

        if not url.startswith(("http://", "https://")):
            continue

        yield {
            "id": row[pos["id"]],
            "categorie": row[pos["categorie"]] or "",
            "sous_categorie": row[pos["sous_categorie"]] or "",
            "url": url,
        }


def load_completed_rows(path):
    done = set()
    rows = []

    if not path.exists():
        return done, rows

    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file, delimiter=";")

        for row in reader:
            if row.get("statut_scraping") in {"ok", "hors_stock"}:
                done.add(row.get("row_id"))
                rows.append(dict(row))

    return done, rows


def run(limit=None, start_id=None, end_id=None, no_resume=False, product_ids=None, output=None):
    output_csv = Path(output) if output is not None else OUTPUT_CSV
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    if no_resume:
        completed, old_rows = set(), []
    else:
        completed, old_rows = load_completed_rows(output_csv)

    products = list(read_products(INPUT_XLSX))

    if product_ids is not None:
        selected = {str(pid) for pid in product_ids}
        products = [p for p in products if str(p["id"]) in selected]

    if start_id is not None:
        products = [
            p for p in products
            if int(p["id"]) >= start_id
        ]

    if end_id is not None:
        products = [
            p for p in products
            if int(p["id"]) <= end_id
        ]

    if limit is not None:
        products = products[:limit]

    print(f"[INFO] URLs Daraz : {len(products)}")
    print(f"[INFO] Déjà terminées : {len(completed)}")

    session = get_session()

    try:
        with output_csv.open(
            "w",
            newline="",
            encoding="utf-8-sig"
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=CSV_FIELDNAMES,
                delimiter=";",
                quoting=csv.QUOTE_MINIMAL,
            )

            writer.writeheader()

            for old_row in old_rows:
                writer.writerow(old_row)

            for index, product in enumerate(products, start=1):
                pid = product["id"]
                row_id = f"{pid}_daraz"

                if row_id in completed:
                    print(f"[SKIP] {row_id}")
                    continue

                print(
                    f"[{index}/{len(products)}] "
                    f"{row_id} -> {product['url']}"
                )

                row = {
                    "id": pid,
                    "site": "daraz",
                    "row_id": row_id,
                    "lien": product["url"],
                    "titre": "",
                    "marque": "",
                    "categorie": product["categorie"],
                    "sous_categorie": product["sous_categorie"],
                    "prix": "",
                    "devise": host_currency(product["url"]),
                    "description": "",
                    "liens_images": "",
                    "nb_images": 0,
                    "statut_scraping": "erreur",
                }

                try:
                    data = daraz_scraper.scrape(
                        product["url"],
                        session
                    )

                    images = [
                        str(url_img)
                        for url_img in data.get("liens_images", [])
                        if isinstance(url_img, str) and url_img
                    ]

                    row.update({
                        "titre": data.get("titre", ""),
                        "marque": data.get("marque", ""),
                        "prix": data.get("prix", ""),
                        "devise": data.get("devise", ""),
                        "description": data.get("description", ""),
                        "liens_images": "|".join(images),
                        "nb_images": len(images),
                        "statut_scraping": (
                            "erreur: disponibilite indeterminee"
                            if data.get("stock_indetermine")
                            else "hors_stock"
                            if data.get("hors_stock")
                            else "ok"
                        ),
                    })

                except Exception as exc:
                    row["statut_scraping"] = (
                        f"erreur: {type(exc).__name__}: {exc}"
                    )
                    print("   ->", row["statut_scraping"])

                writer.writerow(row)
                file.flush()

                polite_delay()

    finally:
        playwright_manager.close_all()

    print(f"[TERMINE] {output_csv}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--ids", help="IDs separes par des virgules")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--start-id", type=int, default=None)
    parser.add_argument("--end-id", type=int, default=None)
    parser.add_argument("--no-resume", action="store_true")

    args = parser.parse_args()

    run(
        product_ids=args.ids.split(",") if args.ids else None,
        output=args.output,
        limit=args.limit,
        start_id=args.start_id,
        end_id=args.end_id,
        no_resume=args.no_resume,
    )
