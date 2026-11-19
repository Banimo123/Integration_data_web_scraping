"""Audit reproductible, sans suppression ni transformation des images sources."""
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps
from download_images_daraz import CSV_PATH, IMAGES_ROOT, valid_image

OUT = Path("output/validation")


def run():
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter=";"))
    journal = OUT / "download_images.jsonl"
    latest = {}
    if journal.exists():
        for line in journal.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            latest[(entry["id"], entry["index"], entry["url"])] = entry
    records, products, hashes = [], [], defaultdict(list)
    visual_file = OUT / "observations_visuelles.json"
    visual = json.loads(visual_file.read_text(encoding="utf-8")) if visual_file.exists() else []
    visual_by_key = {(r["id"], r["index"]): r["raison"] for r in visual}
    for row in rows:
        urls = [u for u in row["liens_images"].split("|") if u]
        good = 0
        for index, url in enumerate(urls, 1):
            files = sorted((IMAGES_ROOT / row["id"]).glob(f"image_{index}.*"))
            candidates = [p for p in files if p.suffix != ".part"]
            path = next((p for p in candidates if valid_image(p)), candidates[0] if candidates else None)
            item = {"id": row["id"], "index": index, "url": url, "path": str(path) if path else None, "valid": False, "reasons": []}
            if path:
                item["bytes"] = path.stat().st_size
                item["extension"] = path.suffix
                if valid_image(path):
                    item["valid"] = True
                    good += 1
                    with Image.open(path) as im:
                        w, h = im.size
                        item.update(width=w, height=h, format=im.format)
                    if min(w, h) < 200:
                        item["reasons"].append("resolution faible (<200 px)")
                    if max(w, h) / min(w, h) > 5:
                        item["reasons"].append("ratio anormal (>5)")
                    if item["bytes"] < 2048:
                        item["reasons"].append("taille faible (<2048 octets)")
                    item["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                    proof = latest.get((row["id"], index, url), {})
                    item["association_verified"] = proof.get("sha256") == item["sha256"] and proof.get("message") == str(path)
                    if not item["association_verified"]:
                        item["reasons"].append("association URL/fichier non confirmee par le journal")
                    hashes[item["sha256"]].append(str(path))
                else:
                    item["reasons"].append("vide" if not item["bytes"] else "illisible/corrompue")
            else:
                item["reasons"].append("telechargement manquant")
            if re.search(r"logo|sprite|payment|badge|qrcode|/g/tps/|/g/lzdfe/", url, re.I):
                item["reasons"].append("URL suspecte : inspection manuelle")
            if (row["id"], index) in visual_by_key:
                item["visual_observation"] = visual_by_key[(row["id"], index)]
                item["reasons"].append("revue visuelle : " + item["visual_observation"])
            records.append(item)
        products.append({"id": row["id"], "expected": len(urls), "nb_images_csv": int(row["nb_images"] or 0), "valid": good, "difference": int(row["nb_images"] or 0) - good})
    valid = [r for r in records if r["valid"]]
    duplicates = [paths for paths in hashes.values() if len(paths) > 1]
    summary = {"products_expected": sum(p["expected"] > 0 for p in products), "expected": len(records), "downloaded_valid": len(valid), "missing": sum(r["path"] is None for r in records), "invalid": sum(bool(r["path"]) and not r["valid"] for r in records), "empty": sum(r.get("bytes") == 0 for r in records), "suspect": sum(bool(r["reasons"]) for r in valid), "extensions": dict(Counter(r["extension"] for r in valid)), "bytes_total": sum(r["bytes"] for r in valid), "exact_duplicate_groups": len(duplicates), "exact_duplicate_excess": sum(len(g)-1 for g in duplicates), "products_no_valid_image": [p["id"] for p in products if not p["valid"]], "products_expected_no_valid_image": [p["id"] for p in products if p["expected"] and not p["valid"]], "semantic_review": "Heuristiques uniquement : propre techniquement ne signifie pas contenu certifie. Voir planches et revue manuelle.", "near_duplicates": "Non classes automatiquement : risque de confondre des vues pertinentes."}
    report = {"summary": summary, "products": products, "images": records, "exact_duplicates": duplicates, "anomalies": [r for r in records if r["reasons"]]}
    summary["latest_download_failures"] = sum(latest.get((r["id"], r["index"], r["url"]), {}).get("status") == "error" for r in records)
    summary["unverified_associations"] = sum(not r["association_verified"] for r in valid)
    summary["visual_suspects"] = sum("visual_observation" in r for r in valid)
    summary["images_without_flags"] = sum(not r["reasons"] for r in valid)
    summary["size_bytes_min_max"] = [min((r["bytes"] for r in valid), default=0), max((r["bytes"] for r in valid), default=0)]
    summary["width_min_max"] = [min((r["width"] for r in valid), default=0), max((r["width"] for r in valid), default=0)]
    summary["height_min_max"] = [min((r["height"] for r in valid), default=0), max((r["height"] for r in valid), default=0)]
    summary["orphan_files"] = [str(p) for p in IMAGES_ROOT.rglob("image_*.*") if p.suffix != ".part" and str(p) not in {r["path"] for r in records}]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "images_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    # Planches derivees uniquement pour inspection ; les originaux restent intacts.
    contact = OUT / "planches"
    contact.mkdir(exist_ok=True)
    for start in range(0, len(valid), 48):
        sheet = Image.new("RGB", (1200, 8 * 145), "white")
        draw = ImageDraw.Draw(sheet)
        for offset, item in enumerate(valid[start:start+48]):
            x, y = (offset % 6)*200, (offset//6)*145
            with Image.open(item["path"]) as im:
                thumb = ImageOps.contain(im.convert("RGBA"), (190, 120))
                sheet.paste(thumb, (x, y), thumb.getchannel("A"))
            draw.text((x, y+123), f"{item['id']} / {item['index']}", fill="black")
        sheet.save(contact / f"planche_{start//48+1:03}.jpg")
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    return report


if __name__ == "__main__":
    run()
