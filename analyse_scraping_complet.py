"""Read-only full-dataset validation and report. Never scrapes or downloads images."""
import csv
import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from audit_daraz import audit, index_captures
from check_daraz import analyse
from main_daraz import INPUT_XLSX, OUTPUT_CSV, read_products, CSV_FIELDNAMES
from scrapers.daraz_scraper import _gallery_images

DIRECTORY = Path("output/validation/complet")


def latest(captures, key, kind, suffix):
    return index_captures(captures).get((key, kind, suffix))


def run():
    products = list(read_products(INPUT_XLSX))
    expected = {str(p["id"]) + "_daraz": p for p in products}
    with OUTPUT_CSV.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, delimiter=";")
        columns = reader.fieldnames
        rows = list(reader)
    actual = Counter(row["row_id"] for row in rows)
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    duplicates = {key: value for key, value in actual.items() if value > 1}
    if missing:
        raise SystemExit("Scraping incomplet, lignes manquantes : " + str(missing))
    captures = DIRECTORY / "captures"
    errors = []
    evidence_by_id = {}
    for row in rows:
        key = hashlib.sha256(row["lien"].encode()).hexdigest()[:12]
        http_path = latest(captures, key, "http", ".json")
        browser_path = latest(captures, key, "browser", ".html")
        browser_meta_path = latest(captures, key, "browser", ".json")
        http = json.loads(http_path.read_text(encoding="utf-8")) if http_path else {}
        browser_meta = json.loads(browser_meta_path.read_text(encoding="utf-8")) if browser_meta_path else {}
        html_path = browser_path or latest(captures, key, "http", ".html")
        needs_page = row["statut_scraping"] not in {"ok", "hors_stock"} or not row["prix"]
        soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "lxml") if html_path and needs_page else None
        title = soup.select_one("h1.pdp-mod-product-badge-title") if soup else None
        has_product = bool(title and title.get_text(strip=True))
        text = soup.get_text(" ", strip=True).lower() if soup else ""
        deleted = any(x in text for x in ("we seem to have lost this page", "page not found"))
        status_code = http.get("http_status")
        status = row["statut_scraping"]
        evidence = {"http_status": status_code, "capture": str(html_path) if html_path else None,
                    "http_evidence": str(http_path) if http_path else None, "page_produit": has_product,
                    "page_supprimee": deleted, "error_browser": browser_meta.get("error", "")}
        evidence_by_id[row["id"]] = evidence
        if status not in {"ok", "hors_stock"}:
            message = (status + " " + browser_meta.get("error", "")).lower()
            if status_code in {404, 410} and (deleted or not has_product):
                kind = "HTTP 404" if status_code == 404 else "autre anomalie (HTTP 410)"
                proof = {"id": row["id"], "url": row["lien"], "http_status": status_code, "source": str(http_path)}
                (DIRECTORY / ("preuve_" + row["id"] + ".json")).write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
            elif any(x in message for x in ("err_name_not_resolved", "err_connection", "err_tunnel", "err_internet", "net::err", "dns")) or status_code in {401, 403, 429, 500, 502, 503, 504}:
                kind = "page inaccessible"
            elif any(x in message for x in ("timeout", "timed out", "timeouterror")):
                kind = "timeout"
            elif "playwright" in message or "targetclosed" in message:
                kind = "erreur Playwright"
            elif "indeterminee" in message:
                kind = "disponibilite indeterminee"
            elif "titre introuvable" in message or "extract" in message:
                kind = "champ essentiel non extractible"
            else:
                kind = "autre anomalie"
            errors.append({"id": row["id"], "url": row["lien"], "type": kind, "raison": status, **evidence})
    shutil.copyfile(OUTPUT_CSV, DIRECTORY / "produits_daraz.csv")
    report = analyse(OUTPUT_CSV)
    report["captures"] = str(captures)
    (DIRECTORY / "rapport.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    page_audit = audit(DIRECTORY)
    audits = {row["id"]: row for row in page_audit["details"]}
    empty_prices = []
    for row in rows:
        if row["prix"].strip():
            continue
        details = audits.get(row["id"], {})
        if details.get("prix_affiche"):
            kind = "erreur d'extraction : prix affiche present"
        elif row["statut_scraping"] == "hors_stock" and evidence_by_id[row["id"]]["page_produit"]:
            kind = "hors_stock sans prix affiche"
        elif row["statut_scraping"] in {"ok", "hors_stock"} and evidence_by_id[row["id"]]["page_produit"]:
            kind = "prix reellement absent de la page capturee"
        else:
            kind = "page en erreur : prix non verifiable, absence reelle non affirmee"
        empty_prices.append({"id": row["id"], "type": kind, "url": row["lien"]})
    suspicious_images = []
    image_urls = []
    for row in rows:
        urls = [u for u in row["liens_images"].split("|") if u]
        image_urls.extend(urls)
        for url in urls:
            if not url.startswith(("http://", "https://")) or re.search(r"logo|sprite|payment|/g/tps/|/g/lzdfe/", url, re.I):
                suspicious_images.append({"id": row["id"], "url": url})
    initial = json.loads((DIRECTORY / "reprise_initiale.json").read_text(encoding="utf-8"))
    current = {row["row_id"]: row for row in rows}
    changed_resumed = [row["row_id"] for row in initial["resumed_rows"] if current.get(row["row_id"]) != row]
    changed_sources = [name for name, digest in initial["source_hashes"].items()
                       if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest]
    false_ok = [row["id"] for row in rows if row["statut_scraping"] == "ok" and
                (audits.get(row["id"], {}).get("stock_page") != "ok" or not row["titre"] or not row["prix"])]
    structural_errors = [error for error in errors if error["type"] not in {"HTTP 404", "page inaccessible", "autre anomalie (HTTP 410)"}]
    valid_without_gallery = [row["id"] for row in rows if row["statut_scraping"] in {"ok", "hors_stock"}
                             and (not row["liens_images"] or audits.get(row["id"], {}).get("images_galerie", 0) == 0)]
    ready = not (valid_without_gallery or missing or extra or duplicates or changed_resumed or changed_sources or false_ok or suspicious_images
                 or page_audit["fiches_avec_ecarts"] or report["devises_incoherentes"] or report["ok_prix_vide"]
                 or structural_errors or columns != CSV_FIELDNAMES)
    error_counts = dict.fromkeys([
        "HTTP 404", "page inaccessible", "erreur Playwright", "timeout",
        "champ essentiel non extractible", "disponibilite indeterminee", "autre anomalie"
    ], 0)
    for error in errors:
        error_counts[error["type"]] = error_counts.get(error["type"], 0) + 1
    price_counts = dict.fromkeys([
        "prix reellement absent de la page capturee", "hors_stock sans prix affiche",
        "erreur d'extraction : prix affiche present",
        "page en erreur : prix non verifiable, absence reelle non affirmee"
    ], 0)
    for item in empty_prices:
        price_counts[item["type"]] += 1
    summary = {
        "urls_attendues": len(products), "lignes_traitees": len(rows), "lignes_reprises": initial["valid_resumed"],
        "nouvelles_tentatives": len(products) - initial["valid_resumed"], "qualite": report,
        "erreurs_detaillees": errors, "repartition_erreurs": error_counts,
        "prix_vides_details": empty_prices, "prix_vides_repartition": price_counts, "urls_images_total": len(image_urls), "urls_images_uniques": len(set(image_urls)),
        "images_suspectes": suspicious_images, "galeries_valides_non_confirmees": valid_without_gallery,
        "par_categorie": dict(Counter(row["categorie"] for row in rows)),
        "par_sous_categorie": dict(Counter(row["sous_categorie"] for row in rows)),
        "par_domaine": dict(Counter(urlparse(row["lien"]).hostname for row in rows)),
        "row_id_dupliques": duplicates, "row_id_manquants": missing, "row_id_inattendus": extra,
        "reprises_modifiees": changed_resumed, "fichiers_scraper_modifies": changed_sources,
        "faux_ok": false_ok, "audit_ecarts": page_audit["fiches_avec_ecarts"],
        "pret_telechargement_galeries": ready,
    }
    (DIRECTORY / "bilan.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Bilan du scraping complet des metadonnees Daraz", "", "Execution avec reprise, sans --no-resume et sans telechargement local des images.", "", "## Volume et statuts", "",
             "- URLs attendues : " + str(len(products)), "- Lignes dans le CSV : " + str(len(rows)),
             "- Resultats valides repris sans modification : " + str(initial["valid_resumed"]),
             "- Nouvelles tentatives : " + str(len(products) - initial["valid_resumed"]),
             "- ok : " + str(report["ok"]), "- hors_stock : " + str(report["hors_stock"]), "- erreurs : " + str(report["erreurs"]),
             "", "## Champs et galeries", ""]
    for label, key in [("Titres vides", "titres_vides"), ("Prix vides", "prix_vides"), ("Marques vides", "marques_vides"), ("Descriptions vides", "descriptions_vides"), ("Fiches sans images", "sans_images")]:
        lines.append("- " + label + " : " + str(report[key]))
    lines += ["- URLs d'images collectees (somme des galeries) : " + str(len(image_urls)),
              "- URLs d'images distinctes : " + str(len(set(image_urls))),
              "- Fichiers images telecharges : 0", "", "## Devises, categories et domaines", ""]
    for label, values in [("Devises", report["devises"]), ("Categories", summary["par_categorie"]), ("Sous-categories", summary["par_sous_categorie"]), ("Domaines", summary["par_domaine"])]:
        lines.append("- " + label + " : " + json.dumps(values, ensure_ascii=False))
    lines += ["", "## Erreurs detaillees", ""]
    for error in errors:
        lines += ["- ID " + error["id"] + " : " + error["type"] + " ; " + error["raison"],
                  "  - URL : " + error["url"], "  - Preuve HTTP : " + str(error["http_evidence"]),
                  "  - Capture : " + str(error["capture"])]
    lines += ["", "Repartition des erreurs : " + json.dumps(summary["repartition_erreurs"], ensure_ascii=False),
              "", "## Prix vides", ""]
    for item in empty_prices:
        lines.append("- ID " + item["id"] + " : " + item["type"])
    lines.append("Repartition des prix vides : " + json.dumps(price_counts, ensure_ascii=False))
    if not empty_prices:
        lines.append("Aucun prix vide.")
    lines += ["", "## Integrite et audit", "",
              "- Exactement les 14 colonnes attendues : " + str(columns == CSV_FIELDNAMES),
              "- Lignes manquantes : " + str(missing), "- Lignes inattendues : " + str(extra),
              "- Doublons row_id : " + str(duplicates), "- Resultats repris modifies : " + str(changed_resumed),
              "- Fichiers du scraper modifies pendant l'execution : " + str(changed_sources),
              "- Faux ok detectes : " + str(false_ok),
              "- ok avec prix vide : " + str(report["ok_prix_vide"]),
              "- Disponibilites indeterminees : " + str(report["disponibilites_indeterminees"]),
              "- Devises incoherentes : " + str(report["devises_incoherentes"]),
              "- URLs d'images manifestement suspectes : " + str(len(suspicious_images)),
              "- Fiches avec ecarts CSV/capture : " + str(page_audit["fiches_avec_ecarts"]),
              "", "Les erreurs ne sont pas transformees en succes. Une page inaccessible ne permet pas d'affirmer que son prix est reellement absent.",
              "Les galeries sont comparees aux donnees de la variante selectionnee ; les captures des resultats repris proviennent des tests precedents.",
              "", "## Decision", "",
              "Dataset pret pour le telechargement des galeries des fiches valides : " + ("OUI" if ready else "NON, voir les anomalies non resolues"),
              "Aucun telechargement d'images n'est lance par cette validation.",
              "", "Details exploitables : output/validation/complet/bilan.json, rapport.json et audit.json."]
    Path("output/validation/bilan_scraping_complet.md").write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key not in {"qualite", "erreurs_detaillees", "prix_vides_details"}}, ensure_ascii=True, indent=2), flush=True)


if __name__ == "__main__":
    run()
