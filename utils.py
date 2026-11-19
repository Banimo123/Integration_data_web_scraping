import json
import random
import re
import time
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]

CURRENCY_BY_HOST = {
    "daraz.pk": "PKR",
    "daraz.com.bd": "BDT",
    "daraz.lk": "LKR",
    "daraz.com.np": "NPR",
    "shop.com.mm": "MMK",
}


def get_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })
    return session


def polite_delay(min_s=4.0, max_s=7.0):
    time.sleep(random.uniform(min_s, max_s))


def fetch(url, session, retries=3, timeout=25):
    last_error = None
    for attempt in range(1, retries + 1):
        session.headers["User-Agent"] = random.choice(USER_AGENTS)
        try:
            response = session.get(url, timeout=timeout, allow_redirects=True)
            if response.status_code == 200:
                return response
            last_error = f"HTTP {response.status_code}"
        except requests.RequestException as exc:
            last_error = str(exc)

        if attempt < retries:
            time.sleep(2 * attempt)

    print(f"[HTTP ECHEC] {url} -> {last_error}")
    return None


def host_currency(url):
    host = urlparse(url).netloc.lower().replace("www.", "")
    return CURRENCY_BY_HOST.get(host, "")


def parse_price(raw):
    if raw is None:
        return ""

    text = str(raw).replace("\xa0", " ").strip()
    match = re.search(r"\d[\d\s,.\u202f]*", text)
    if not match:
        return ""

    number = match.group(0).replace(" ", "").replace("\u202f", "")

    if "," in number and "." in number:
        if number.rfind(".") > number.rfind(","):
            number = number.replace(",", "")
        else:
            number = number.replace(".", "").replace(",", ".")
    elif "," in number:
        if re.fullmatch(r"\d{1,3}(,\d{3})+", number):
            number = number.replace(",", "")
        elif re.fullmatch(r"\d+,\d{1,2}", number):
            number = number.replace(",", ".")
        else:
            number = number.replace(",", "")

    parts = number.split(".")
    if len(parts) > 2:
        number = "".join(parts[:-1]) + "." + parts[-1]

    try:
        float(number)
        return number
    except ValueError:
        return ""


def extract_jsonld_products(soup):
    products = []

    def visit(obj):
        if isinstance(obj, dict):
            typ = obj.get("@type")
            if typ == "Product" or (isinstance(typ, list) and "Product" in typ):
                products.append(obj)
            graph = obj.get("@graph")
            if isinstance(graph, list):
                for item in graph:
                    visit(item)
        elif isinstance(obj, list):
            for item in obj:
                visit(item)

    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text(strip=True)
        if not raw:
            continue
        try:
            visit(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            continue

    return products


def normalize_images(value):
    urls = []

    def add(item):
        if isinstance(item, str):
            u = item.strip()
            if u.startswith("//"):
                u = "https:" + u
            if u.startswith(("http://", "https://")) and u not in urls:
                urls.append(u)
        elif isinstance(item, dict):
            add(item.get("url"))
            add(item.get("contentUrl"))
        elif isinstance(item, list):
            for x in item:
                add(x)

    add(value)
    return urls


def clean_text(value, max_len=5000):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:max_len]


def product_image_candidate(url):
    if not isinstance(url, str):
        return False

    u = url.lower()
    if u.startswith("//"):
        u = "https:" + u

    if not u.startswith(("http://", "https://")):
        return False

    if not any(x in u for x in ("lazcdn.com", "alicdn.com", "daraz")):
        return False

    banned = (
        "logo", "icon", "sprite", "payment", "visa", "mastercard",
        "download-app", "qr", "badge", "rating", "seller"
    )
    return not any(x in u for x in banned)
