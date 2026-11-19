"""Controle du CSV brut Daraz, sans modification des 14 colonnes."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from utils import host_currency, parse_price


def analyse(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file, delimiter=";")
        columns = reader.fieldnames
        rows = list(reader)
    from main_daraz import CSV_FIELDNAMES
    anomalies = []
    for row in rows:
        issues = []
        for field in ("titre", "marque", "prix", "description"):
            if not (row.get(field) or "").strip():
                issues.append(field + " vide")
        images = [u for u in (row.get("liens_images") or "").split("|") if u]
        try:
            count = int(row.get("nb_images") or 0)
        except ValueError:
            count = -1
        if not images or count == 0:
            issues.append("sans image")
        if count != len(images):
            issues.append("compte images incoherent")
        status = row.get("statut_scraping", "")
        if status not in {"ok", "hors_stock"}:
            issues.append(status or "statut vide")
        if row.get("devise") != host_currency(row.get("lien", "")):
            issues.append("devise incoherente")
        if row.get("prix") and (not parse_price(row["prix"]) or float(parse_price(row["prix"])) <= 0):
            issues.append("prix invalide")
        if issues:
            anomalies.append({"id": row.get("id"), "url": row.get("lien"), "problemes": issues})
    statuses = Counter(row.get("statut_scraping", "") for row in rows)
    report = {
        "lignes": len(rows), "colonnes_conformes": columns == CSV_FIELDNAMES,
        "ok": statuses["ok"], "hors_stock": statuses["hors_stock"],
        "erreurs": sum(n for status, n in statuses.items() if status not in {"ok", "hors_stock"}),
        "titres_vides": sum(not (r.get("titre") or "").strip() for r in rows),
        "prix_vides": sum(not (r.get("prix") or "").strip() for r in rows),
        "marques_vides": sum(not (r.get("marque") or "").strip() for r in rows),
        "descriptions_vides": sum(not (r.get("description") or "").strip() for r in rows),
        "sans_images": sum(not r.get("liens_images") or r.get("nb_images") == "0" for r in rows),
        "ok_prix_vide": sum(r.get("statut_scraping") == "ok" and not r.get("prix") for r in rows),
        "disponibilites_indeterminees": sum("indeterminee" in r.get("statut_scraping", "") for r in rows),
        "devises_incoherentes": sum(r.get("devise") != host_currency(r.get("lien", "")) for r in rows),
        "devises": dict(Counter(r.get("devise") or "VIDE" for r in rows)),
        "anomalies": anomalies,
    }
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", type=Path, default=Path("output/produits_daraz.csv"))
    args = parser.parse_args()
    if not args.path.exists():
        raise SystemExit(str(args.path) + " introuvable")
    print(json.dumps(analyse(args.path), ensure_ascii=True, indent=2))
