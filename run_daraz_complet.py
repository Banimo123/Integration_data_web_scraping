"""Launch main_daraz.py with its normal resume mode and metadata evidence only."""
import csv
import hashlib
import json
import runpy
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import main_daraz as main
from scrapers import daraz_scraper as ds, playwright_manager as pm

DIRECTORY = Path("output/validation/complet")
CAPTURES = DIRECTORY / "captures"


def read_rows(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, delimiter=";")
        if reader.fieldnames != main.CSV_FIELDNAMES:
            raise ValueError("Colonnes inattendues : " + str(path))
        return list(reader)


def prepare_resume():
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    CAPTURES.mkdir(parents=True, exist_ok=True)
    products = list(main.read_products(main.INPUT_XLSX))
    expected = {str(p["id"]) + "_daraz": p for p in products}
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if main.OUTPUT_CSV.exists():
        shutil.copyfile(main.OUTPUT_CSV, DIRECTORY / ("avant_reprise_" + stamp + ".csv"))
    rows = {}
    sources = {}
    stages = [Path("output/validation") / stage for stage in ("first10", "representative", "final")]
    for stage in stages:
        for row in read_rows(stage / "produits_daraz.csv"):
            if row["statut_scraping"] in {"ok", "hors_stock"} and row["row_id"] in expected:
                if row["lien"] != expected[row["row_id"]]["url"]:
                    raise ValueError("URL differente pour " + row["row_id"])
                rows[row["row_id"]] = row
                sources[row["row_id"]] = stage
    for row in read_rows(main.OUTPUT_CSV):
        if row["row_id"] not in expected:
            raise ValueError("Ligne inconnue dans le CSV : " + row["row_id"])
        if row["lien"] != expected[row["row_id"]]["url"]:
            raise ValueError("URL differente pour " + row["row_id"])
        # Current canonical results take precedence over older test snapshots.
        if row["statut_scraping"] in {"ok", "hors_stock"}:
            matched = next((stage for stage in reversed(stages)
                            if row in read_rows(stage / "produits_daraz.csv")), None)
            rows[row["row_id"]] = row
            sources[row["row_id"]] = matched
        elif row["row_id"] not in rows:
            rows[row["row_id"]] = row
    valid = [r for r in rows.values() if r["statut_scraping"] in {"ok", "hors_stock"}]
    for row in valid:
        stage = sources.get(row["row_id"])
        if stage is None:
            continue
        report = json.loads((stage / "rapport.json").read_text(encoding="utf-8-sig"))
        source = Path(report.get("captures", stage / "captures"))
        key = hashlib.sha256(row["lien"].encode()).hexdigest()[:12]
        for capture in source.glob(key + "_*"):
            target = CAPTURES / capture.name
            if not target.exists():
                shutil.copy2(capture, target)
    with main.OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=main.CSV_FIELDNAMES, delimiter=";")
        writer.writeheader()
        writer.writerows(rows.values())
        file.flush()
    manifest = {
        "expected": len(products), "valid_resumed": len(valid),
        "resumed_rows": valid, "command": "python main_daraz.py",
        "captures": str(CAPTURES), "started": stamp,
        "source_hashes": {name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
                          for name in ["main_daraz.py", "scrapers/daraz_scraper.py", "scrapers/playwright_manager.py", "utils.py"]},
    }
    (DIRECTORY / ("reprise_" + stamp + ".json")).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if not (DIRECTORY / "reprise_initiale.json").exists():
        (DIRECTORY / "reprise_initiale.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def instrument():
    original_fetch, original_navigate = ds.fetch, pm.navigate
    counters = defaultdict(int)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def prefix(url, kind):
        key = hashlib.sha256(url.encode()).hexdigest()[:12]
        counters[(key, kind)] += 1
        return CAPTURES / (key + "_" + kind + "_" + stamp + "_" + str(counters[(key, kind)]))

    def fetch(url, session, **kwargs):
        responses = []
        def record(response, *args, **kwargs):
            responses.append(response)
        session.hooks.setdefault("response", []).append(record)
        base = prefix(url, "http")
        try:
            response = original_fetch(url, session, **kwargs)
        finally:
            session.hooks["response"].remove(record)
        last = response if response is not None else (responses[-1] if responses else None)
        if last is not None:
            base.with_suffix(".html").write_text(last.text, encoding="utf-8")
        evidence = {"url": url, "final_url": last.url if last is not None else None,
                    "http_status": last.status_code if last is not None else None,
                    "attempt_statuses": [r.status_code for r in responses]}
        base.with_suffix(".json").write_text(json.dumps(evidence), encoding="utf-8")
        return response

    def navigate(url, **kwargs):
        base = prefix(url, "browser")
        try:
            html = original_navigate(url, **kwargs)
            base.with_suffix(".html").write_text(html, encoding="utf-8")
            base.with_suffix(".txt").write_text(pm.get_body_text(), encoding="utf-8")
            evidence = {"url": url, "final_url": pm.get_page().url}
        except Exception as exc:
            evidence = {"url": url, "error": str(exc)}
            base.with_suffix(".json").write_text(json.dumps(evidence), encoding="utf-8")
            raise
        base.with_suffix(".json").write_text(json.dumps(evidence), encoding="utf-8")
        return html

    ds.fetch, pm.navigate = fetch, navigate


class Tee:
    def __init__(self, stream, log):
        self.stream, self.log = stream, log
    def write(self, text):
        self.stream.write(text)
        self.log.write(text)
        self.flush()
    def flush(self):
        self.stream.flush()
        self.log.flush()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    manifest = prepare_resume()
    log = (DIRECTORY / "execution.log").open("a", encoding="utf-8", buffering=1)
    sys.stdout = Tee(sys.stdout, log)
    sys.stderr = Tee(sys.stderr, log)
    print("[REPRISE]", manifest["valid_resumed"], "resultats valides conserves sur", manifest["expected"], flush=True)
    instrument()
    sys.argv = ["main_daraz.py"]
    runpy.run_path("main_daraz.py", run_name="__main__")
