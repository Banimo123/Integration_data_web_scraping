"""Echantillons limites et captures de preuve, sans telechargement des images."""
import argparse
import json
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

import main_daraz as main
from check_daraz import analyse
from scrapers import daraz_scraper as ds, playwright_manager as pm


def select_samples(products, target):
    groups = defaultdict(list)
    for product in products:
        groups[(urlparse(product["url"]).hostname, product["sous_categorie"])].append(product)
    # Interleave groups, sampling throughout each group rather than just its beginning.
    ordered = {}
    for key, group in sorted(groups.items()):
        indices = []
        for fraction in (0, 1, .5, .25, .75):
            index = round((len(group) - 1) * fraction)
            if index not in indices:
                indices.append(index)
        indices.extend(i for i in range(len(group)) if i not in indices)
        ordered[key] = [group[i] for i in indices]
    selected = []
    for index in range(max(map(len, ordered.values()))):
        for group in ordered.values():
            if index < len(group) and len(selected) < target:
                selected.append(group[index])
    return selected


def capture_pages(directory):
    directory.mkdir(parents=True, exist_ok=True)
    original_fetch, original_navigate = ds.fetch, pm.navigate
    counter = defaultdict(int)

    def prefix(url, kind):
        import hashlib
        key = hashlib.sha256(url.encode()).hexdigest()[:12]
        counter[(key, kind)] += 1
        return directory / (key + "_" + kind + "_" + str(counter[(key, kind)]))

    def fetch(url, session, **kwargs):
        response = original_fetch(url, session, **kwargs)
        base = prefix(url, "http")
        if response is not None:
            base.with_suffix(".html").write_text(response.text, encoding="utf-8")
        base.with_suffix(".json").write_text(json.dumps({"url": url, "final_url": response.url if response is not None else None, "http_status": response.status_code if response is not None else None}), encoding="utf-8")
        return response

    def navigate(url, **kwargs):
        base = prefix(url, "browser")
        try:
            html = original_navigate(url, **kwargs)
            base.with_suffix(".html").write_text(html, encoding="utf-8")
            base.with_suffix(".txt").write_text(pm.get_body_text(), encoding="utf-8")
            base.with_suffix(".json").write_text(json.dumps({"url": url, "final_url": pm.get_page().url}), encoding="utf-8")
            return html
        except Exception as exc:
            base.with_suffix(".json").write_text(json.dumps({"url": url, "error": str(exc)}), encoding="utf-8")
            raise

    ds.fetch, pm.navigate = fetch, navigate
    return original_fetch, original_navigate


def run_stage(stage, select_only=False, ids=None, exclude_ids=None):
    products = list(main.read_products(main.INPUT_XLSX))
    if exclude_ids:
        excluded = set(exclude_ids.split(","))
        products = [p for p in products if str(p["id"]) not in excluded]
    target = 9 if stage == "representative" else 36
    selected = products[:10] if stage == "first10" else select_samples(products, target)
    if ids:
        wanted = set(ids.split(","))
        selected = [p for p in products if str(p["id"]) in wanted]
    if not 0 < len(selected) <= 40:
        raise ValueError("Un test doit contenir entre 1 et 40 fiches")
    directory = Path("output/validation") / stage
    directory.mkdir(parents=True, exist_ok=True)
    manifest = [{**p, "domaine": urlparse(p["url"]).hostname} for p in selected]
    (directory / "selection.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=True, indent=2), flush=True)
    if select_only:
        return
    from datetime import datetime
    captures = directory / "captures" / datetime.now().strftime("%Y%m%d_%H%M%S")
    originals = capture_pages(captures)
    output = directory / "produits_daraz.csv"
    try:
        main.run(no_resume=True, product_ids=[p["id"] for p in selected], output=output)
    finally:
        ds.fetch, pm.navigate = originals
    report = analyse(output)
    report["captures"] = str(captures)
    (directory / "rapport.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    # Un echantillon ne doit jamais remplacer le livrable complet.
    print(json.dumps(report, ensure_ascii=True, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["representative", "final", "first10"])
    parser.add_argument("--check-only", action="store_true", help="Controle local du CSV complet, sans scraping ni ecrasement")
    parser.add_argument("--select-only", action="store_true")
    parser.add_argument("--ids")
    parser.add_argument("--exclude-ids")
    args = parser.parse_args()
    if args.check_only:
        print(json.dumps(analyse(main.OUTPUT_CSV), ensure_ascii=True, indent=2))
    elif args.stage:
        run_stage(args.stage, args.select_only, args.ids, args.exclude_ids)
    else:
        print(json.dumps(analyse(main.OUTPUT_CSV), ensure_ascii=True, indent=2))
