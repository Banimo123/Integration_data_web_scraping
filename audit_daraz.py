"""Compare CSV values to the saved product blocks, without contacting Daraz."""
import argparse
import os
from functools import lru_cache
import csv
import hashlib
import json
import re
from pathlib import Path
from bs4 import BeautifulSoup
from utils import clean_text, host_currency, parse_price
from scrapers.daraz_scraper import _gallery_images


@lru_cache(maxsize=8)
def index_captures(directory):
    """Index once; Windows directory entries already contain modification times."""
    selected = {}
    times = {}
    with os.scandir(directory) as entries:
        for entry in entries:
            parts = entry.name.split("_", 2)
            if len(parts) != 3 or parts[1] not in {"http", "browser"} or not entry.is_file():
                continue
            key = (parts[0], parts[1], Path(entry.name).suffix)
            modified = entry.stat().st_mtime_ns
            if modified >= times.get(key, -1):
                selected[key] = Path(entry.path)
                times[key] = modified
    return selected


def audit(directory):
    directory = Path(directory)
    report = json.loads((directory / "rapport.json").read_text(encoding="utf-8-sig"))
    captures = Path(report.get("captures", directory / "captures"))
    with (directory / "produits_daraz.csv").open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file, delimiter=";"))
    capture_index = index_captures(captures)
    results = []
    for row in rows:
        key = hashlib.sha256(row["lien"].encode()).hexdigest()[:12]
        capture = capture_index.get((key, "browser", ".html")) or capture_index.get((key, "http", ".html"))
        item = {"id": row["id"], "url": row["lien"], "statut_csv": row["statut_scraping"], "ecarts": []}
        if capture is None:
            item["ecarts"].append("Aucune capture HTML disponible")
            results.append(item)
            continue
        soup = BeautifulSoup(capture.read_text(encoding="utf-8"), "lxml")
        item["capture"] = str(capture)
        text = clean_text(soup.get_text(" ", strip=True))
        invalid = any(message in text.lower() for message in ("we seem to have lost this page", "page not found"))
        proof_path = directory / ("preuve_" + row["id"] + ".json")
        if proof_path.exists():
            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            if proof.get("url") == row["lien"] and proof.get("http_status") in {404, 410}:
                invalid = True
                item["preuve_http"] = str(proof_path)
                item["http_status"] = proof["http_status"]
        item["page_invalide"] = invalid
        if invalid:
            if not row["statut_scraping"].startswith("erreur"):
                item["ecarts"].append("Page invalide acceptee")
            results.append(item)
            continue
        price_tag = soup.select_one(".pdp-price_type_normal")
        displayed_price = parse_price(price_tag.get_text(" ", strip=True)) if price_tag else ""
        item["prix_affiche"] = displayed_price
        item["prix_csv"] = row["prix"]
        if displayed_price and row["prix"] != displayed_price:
            item["ecarts"].append("Prix CSV different du prix affiche")
        quantity = soup.select_one("#module_quantity-input")
        cart = soup.select_one("#module_add_to_cart")
        quantity_text = clean_text(quantity.get_text(" ", strip=True)) if quantity else ""
        cart_text = clean_text(cart.get_text(" ", strip=True)) if cart else ""
        item["preuve_stock"] = quantity_text + " | " + cart_text
        if re.search(r"out of stock|currently unavailable|^sold out$", quantity_text, re.I):
            expected = "hors_stock"
        elif cart and any(
            re.search(r"buy now|add to cart", button.get_text(" ", strip=True), re.I)
            and not button.has_attr("disabled") and button.get("aria-disabled") != "true"
            and "disabled" not in " ".join(button.get("class", []))
            for button in cart.select("button")
        ):
            expected = "ok"
        else:
            expected = "indetermine"
        item["stock_page"] = expected
        if expected in {"ok", "hors_stock"} and row["statut_scraping"] != expected:
            item["ecarts"].append("Statut CSV different des commandes produit")
        if expected == "indetermine" and row["statut_scraping"] in {"ok", "hors_stock"}:
            item["ecarts"].append("Disponibilite sans preuve")
        if row["devise"] != host_currency(row["lien"]):
            item["ecarts"].append("Devise incorrecte")
        gallery = _gallery_images(soup)
        images = row["liens_images"].split("|") if row["liens_images"] else []
        item["images_galerie"] = len(gallery)
        if gallery and set(images) != set(gallery):
            item["ecarts"].append("Images differentes de la galerie selectionnee")
        for field, selector in [("titre", "h1.pdp-mod-product-badge-title"), ("marque", ".pdp-product-brand__brand-link"), ("description", ".pdp-product-desc, .pdp-mod-product-desc")]:
            tag = soup.select_one(selector)
            item[field + "_page_present"] = bool(tag and clean_text(tag.get_text(" ", strip=True)))
            if item[field + "_page_present"] and not row[field]:
                item["ecarts"].append(field + " present sur la page mais absent du CSV")
        results.append(item)
    result = {"fiches": len(results), "pages_invalides": sum(r.get("page_invalide", False) for r in results), "fiches_avec_ecarts": sum(bool(r["ecarts"]) for r in results), "details": results}
    (directory / "audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", nargs="?", type=Path, default=Path("output/validation/complet"))
    args = parser.parse_args()
    print(json.dumps(audit(args.directory), ensure_ascii=True, indent=2))
