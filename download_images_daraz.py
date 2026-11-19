import argparse
import csv
import mimetypes
import json
import hashlib
from datetime import datetime, timezone
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

from tqdm import tqdm

from utils import get_session

CSV_PATH = Path("output/produits_daraz.csv")
IMAGES_ROOT = Path("output/images/daraz")


def valid_image(path):
    """Decode all pixels: a header alone does not prove a complete image."""
    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            im.load()
        return path.stat().st_size > 0
    except (OSError, ValueError, SyntaxError):
        return False


def extension_from(url, content_type=""):
    ext = Path(urlparse(url).path).suffix.lower()

    if ext in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}:
        return ".jpg" if ext == ".jpeg" else ext

    guessed = mimetypes.guess_extension(
        (content_type or "").split(";")[0].strip()
    )

    if guessed in {".jpg", ".png", ".webp", ".gif", ".avif"}:
        return guessed

    return ".jpg"


def load_jobs(only_id=None, resume=True):
    if not CSV_PATH.exists():
        raise FileNotFoundError(
            "Lance d'abord : python main_daraz.py"
        )

    jobs = []

    with CSV_PATH.open(
        newline="",
        encoding="utf-8-sig"
    ) as file:

        for row in csv.DictReader(file, delimiter=";"):

            if row.get("site") != "daraz":
                continue

            if row.get("statut_scraping") not in {"ok", "hors_stock"}:
                continue

            pid = str(row["id"])

            if only_id is not None and pid != str(only_id):
                continue

            urls = [
                u
                for u in (row.get("liens_images") or "").split("|")
                if u
            ]

            for index, url in enumerate(urls, start=1):
                jobs.append((pid, index, url, resume))

    return jobs


def download_one(job):
    pid, index, url, resume = job

    folder = IMAGES_ROOT / pid
    folder.mkdir(parents=True, exist_ok=True)

    existing = list(folder.glob(f"image_{index}.*"))

    if resume:
        for path in existing:
            if valid_image(path):
                return "skip", str(path)

    session = get_session()

    try:
        response = session.get(
            url,
            timeout=30,
            stream=True
        )

        response.raise_for_status()

        temporary = folder / f"image_{index}.part"
        with temporary.open("wb") as file:
            for chunk in response.iter_content(
                chunk_size=128 * 1024
            ):
                if chunk:
                    file.write(chunk)

        if not valid_image(temporary):
            raise ValueError("Reponse vide, corrompue ou non image (fichier .part conserve)")
        with Image.open(temporary) as im:
            ext = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "GIF": ".gif", "AVIF": ".avif"}.get(im.format)
        if not ext:
            raise ValueError("Format image non pris en charge")
        destination = folder / f"image_{index}{ext}"
        temporary.replace(destination)
        return "ok", str(destination)

    except Exception as exc:
        return "error", f"{pid}/image_{index}: {exc}"
    finally:
        session.close()


def main():
    Path("output/validation").mkdir(parents=True, exist_ok=True)
    parser = argparse.ArgumentParser()

    parser.add_argument("--id", default=None)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--sample", action="store_true", help="Une fiche par domaine et sous-categorie")

    args = parser.parse_args()

    jobs = load_jobs(
        only_id=args.id,
        resume=not args.no_resume
    )
    if args.sample:
        with CSV_PATH.open(encoding="utf-8-sig", newline="") as file:
            selected = {}
            for row in csv.DictReader(file, delimiter=";"):
                if row["liens_images"] and row["statut_scraping"] in {"ok", "hors_stock"}:
                    selected.setdefault((urlparse(row["lien"]).hostname, row["sous_categorie"]), row["id"])
        wanted = set(selected.values())
        jobs = [job for job in jobs if job[0] in wanted]
        Path("output/validation/images_sample.json").write_text(json.dumps(sorted(wanted), indent=2), encoding="utf-8")

    stats = {
        "ok": 0,
        "skip": 0,
        "error": 0,
    }

    with ThreadPoolExecutor(
        max_workers=max(1, args.workers)
    ) as executor:

        futures = {executor.submit(download_one, job): job for job in jobs}

        for future in tqdm(
            as_completed(futures),
            total=len(futures)
        ):
            status, message = future.result()
            stats[status] += 1
            pid, index, url, _ = futures[future]
            record = {"time": datetime.now(timezone.utc).isoformat(), "id": pid, "index": index, "url": url, "status": status, "message": message}
            if status != "error":
                record["sha256"] = hashlib.sha256(Path(message).read_bytes()).hexdigest()
            with Path("output/validation/download_images.jsonl").open("a", encoding="utf-8") as log:
                log.write(json.dumps(record, ensure_ascii=False) + "\n")

            if status == "error":
                print("[ERREUR IMAGE]", message)

    print(stats)
    if stats["error"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
