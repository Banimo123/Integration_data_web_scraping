"""
Scraper Daraz.

Stratégie :
1. requests + BeautifulSoup + JSON-LD
2. Playwright seulement si les données principales manquent
"""

import json
import re
from bs4 import BeautifulSoup

from scrapers import playwright_manager as pm
from utils import (
    clean_text,
    extract_jsonld_products,
    fetch,
    host_currency,
    normalize_images,
    parse_price,
    product_image_candidate,
)

TITLE_SELECTORS = [
    "h1.pdp-mod-product-badge-title",
    "[class*='pdp-mod-product-badge-title']",
    "[class*='product-title']",
    "h1",
]

PRICE_SELECTORS = [
    "span.pdp-price_type_normal",
    "[class*='pdp-price_type_normal']",
    "[class*='pdp-mod-product-price'] [class*='pdp-price']",
    "[class*='pdp-price']",
]

BRAND_SELECTORS = [
    "[class*='pdp-product-brand'] a",
    "[class*='pdp-product-brand']",
    "[class*='brand']",
]

DESCRIPTION_SELECTORS = [
    "[class*='pdp-product-desc']",
    "[class*='detail-content']",
    "[class*='pdp-mod-detail-content']",
    "[class*='pdp-mod-section']",
]


def _first_text(soup, selectors):
    for selector in selectors:
        tag = soup.select_one(selector)
        if tag:
            text = clean_text(tag.get_text(" ", strip=True))
            if text:
                return text
    return ""


def _module_fields(soup):
    """Read Daraz's JSON state without evaluating JavaScript."""
    for script in soup.find_all("script"):
        raw = script.string or ""
        match = re.search(r"\bvar\s+__moduleData__\s*=\s*", raw)
        if match:
            try:
                data, _ = json.JSONDecoder().raw_decode(raw[match.end():])
                return data.get("data", {}).get("root", {}).get("fields", {})
            except (ValueError, TypeError, AttributeError):
                continue
    return {}


def _gallery_images(soup):
    fields = _module_fields(soup)
    sku = str(fields.get("primaryKey", {}).get("skuId", "0"))
    galleries = fields.get("skuGalleries") or {}
    gallery = galleries.get(sku, galleries.get("0", []))
    urls = normalize_images([
        item.get("src") for item in gallery
        if isinstance(item, dict) and item.get("type") in {"img", "image"}
    ])
    if urls:
        return urls
    for img in soup.select(
        "#module_item_gallery_1 img, .item-gallery img, .seo-gallery img"
    ):
        for source in (img.get("data-ks-lazyload"), img.get("data-src"), img.get("src")):
            if source and product_image_candidate(source) and re.search(r"/(?:p|kf)/", source):
                urls.extend(normalize_images(source))
    # One image may appear at several thumbnail resolutions.
    unique = {}
    for url in urls:
        key = re.sub(r"_(?:\d+x\d+).*", "", url.split("?")[0])
        unique.setdefault(key, url)
    return list(unique.values())


def _purchase_state(soup):
    """Require an explicit product purchase signal; defaults in JSON-LD are insufficient."""
    areas = soup.select("#module_add_to_cart, #module_quantity-input, .pdp-cart-concern")
    text = clean_text(" ".join(area.get_text(" ", strip=True) for area in areas)).lower()
    stock_text = re.sub(r"almost\s+sold\s+out", "low stock", text)
    if re.search(r"out\s+of\s+stock|sold\s+out|currently unavailable", stock_text):
        return "hors_stock"
    for area in areas:
        for button in area.select("button, [role=button]"):
            label = clean_text(button.get_text(" ", strip=True)).lower()
            classes = " ".join(button.get("class", []))
            if (re.search(r"buy now|add to cart", label)
                    and not button.has_attr("disabled")
                    and button.get("aria-disabled") != "true"
                    and "disabled" not in classes):
                return "ok"
    return "indetermine"


def _extract(soup, url):
    if not extract_jsonld_products(soup) and not soup.select_one("h1.pdp-mod-product-badge-title"):
        page_text = clean_text(soup.get_text(" ", strip=True)).lower()
        if any(message in page_text for message in (
            "we seem to have lost this page", "page not found", "product is not available"
        )):
            raise RuntimeError("page produit invalide ou supprimee")

    result = {
        "titre": "",
        "marque": "",
        "prix": "",
        "devise": host_currency(url),
        "description": "",
        "liens_images": [],
        "hors_stock": False,
    }

    products = extract_jsonld_products(soup)

    if products:
        product = products[0]

        result["titre"] = clean_text(product.get("name"))

        brand = product.get("brand")
        if isinstance(brand, dict):
            brand = brand.get("name")
        result["marque"] = clean_text(brand)

        result["description"] = clean_text(
            product.get("description"),
            max_len=5000
        )

        result["liens_images"] = normalize_images(product.get("image"))

        offers = product.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}

        if isinstance(offers, dict):
            result["prix"] = parse_price(
                offers.get("price")
                or offers.get("lowPrice")
                or offers.get("highPrice")
            )

            result["devise"] = (
                clean_text(offers.get("priceCurrency"))
                or result["devise"]
            )

            availability = str(offers.get("availability") or "").lower()
            if "outofstock" in availability:
                result["hors_stock"] = True

    if not result["titre"]:
        result["titre"] = _first_text(soup, TITLE_SELECTORS)

    if not result["marque"]:
        brand = _first_text(soup, BRAND_SELECTORS)
        brand = re.sub(r"^\s*brand\s*:\s*", "", brand, flags=re.I)
        result["marque"] = clean_text(brand)

    if not result["prix"]:
        for selector in PRICE_SELECTORS:
            tag = soup.select_one(selector)
            if tag:
                price = parse_price(tag.get_text(" ", strip=True))
                if price:
                    result["prix"] = price
                    break

    if not result["prix"]:
        meta = (
            soup.find("meta", attrs={"property": "product:price:amount"})
            or soup.find("meta", attrs={"itemprop": "price"})
        )
        if meta:
            result["prix"] = parse_price(meta.get("content"))
    # -------------------------------------------------
    # Fallback prix par texte visible
    # -------------------------------------------------
    if not result["prix"]:
        price_area = soup.select_one("#module_product_price_1, .pdp-product-price")
        page_text = price_area.get_text(" ", strip=True) if price_area else ""

        price_patterns = [
            r"Rs\.?\s*([\d,]+(?:\.\d+)?)",   # Pakistan / Sri Lanka
            r"₨\s*([\d,]+(?:\.\d+)?)",
            r"৳\s*([\d,]+(?:\.\d+)?)",       # Bangladesh
            r"रू\s*([\d,]+(?:\.\d+)?)",      # Népal
        ]

        for pattern in price_patterns:
            match = re.search(pattern, page_text)

            if match:
                result["prix"] = parse_price(match.group(1))
                break
    # Prix propre au produit, en repli uniquement (jamais les recommandations).
    if not result["prix"]:
        for script in soup.find_all("script"):
            raw = script.string or ""
            match = re.search(r"\bvar\s+pdpTrackingData\s*=\s*", raw)
            if not match:
                continue
            try:
                tracking, _ = json.JSONDecoder().raw_decode(raw[match.end():])
                if isinstance(tracking, str):
                    tracking = json.loads(tracking)
                if isinstance(tracking, dict):
                    result["prix"] = parse_price(tracking.get("pdt_price"))
            except (ValueError, TypeError):
                continue
            if result["prix"]:
                break

    if not result["description"]:
        result["description"] = _first_text(soup, DESCRIPTION_SELECTORS)

    if not result["titre"]:
        og_title = soup.find("meta", attrs={"property": "og:title"})
        if og_title:
            result["titre"] = clean_text(og_title.get("content"))

    if not result["liens_images"]:
        for meta in soup.find_all("meta", attrs={"property": "og:image"}):
            url_img = meta.get("content")
            if url_img and product_image_candidate(url_img):
                result["liens_images"].extend(normalize_images(url_img))

    displayed_price = _first_text(soup, PRICE_SELECTORS[:2])
    if parse_price(displayed_price):
        result["prix"] = parse_price(displayed_price)

    gallery = _gallery_images(soup)
    if gallery:
        result["liens_images"] = gallery

    result["hors_stock"] = _purchase_state(soup) == "hors_stock"

    unique_images = []
    for url_img in result["liens_images"]:
        if (
            isinstance(url_img, str)
            and url_img.startswith(("http://", "https://"))
            and url_img not in unique_images
        ):
            unique_images.append(url_img)

    result["liens_images"] = unique_images
    result["devise"] = host_currency(url) or result["devise"]
    return result


def _merge(base, extra):
    for key in ("titre", "marque", "prix", "devise", "description"):
        if not base.get(key) and extra.get(key):
            base[key] = extra[key]

    if len(extra.get("liens_images", [])) > len(base.get("liens_images", [])):
        base["liens_images"] = extra["liens_images"]

    base["hors_stock"] = bool(
        base.get("hors_stock") or extra.get("hors_stock")
    )

    return base


def _extract_visible_price_and_stock(text, url):
    """
    Extraction du prix et du statut depuis le texte réellement
    visible dans le navigateur Playwright.
    """

    result = {
        "prix": "",
        "devise": host_currency(url),
        "hors_stock": False,
    }

    if not text:
        return result

    # ---------------------------------------------
    # Statut hors stock
    # ---------------------------------------------
    normalized_text = re.sub(r"almost\s+sold\s+out", "low stock", clean_text(text).lower())

    stock_patterns = [
        "out of stock",
        "sold out",
        "currently unavailable",
    ]

    result["hors_stock"] = any(
        pattern in normalized_text
        for pattern in stock_patterns
    )

    # ---------------------------------------------
    # Prix suivant le pays Daraz
    # ---------------------------------------------
    patterns = [
        r"Rs\.?\s*([\d,]+(?:\.\d+)?)",   # Pakistan / Sri Lanka
        r"৳\s*([\d,]+(?:\.\d+)?)",      # Bangladesh
        r"रू\s*([\d,]+(?:\.\d+)?)",     # Népal
    ]

    for pattern in patterns:
        match = re.search(pattern, text)

        if match:
            result["prix"] = parse_price(
                match.group(1)
            )
            break

    return result

def scrape(url, session):
    result = {
        "titre": "",
        "marque": "",
        "prix": "",
        "devise": host_currency(url),
        "description": "",
        "liens_images": [],
        "hors_stock": False,
    }

    # -------------------------------------------------
    # 1. Extraction rapide avec requests
    # -------------------------------------------------
    response = fetch(url, session)

    if response is not None:
        soup = BeautifulSoup(response.text, "lxml")
        result = _merge(result, _extract(soup, url))

    if response is not None and _purchase_state(soup) != "indetermine" and all(
        result.get(key) for key in ("titre", "prix", "description", "liens_images")
    ):
        result["stock_indetermine"] = False
        return result

    # -------------------------------------------------
    # 2. Daraz : vérification avec Playwright
    #    Le navigateur devient la référence pour
    #    le prix et la disponibilité.
    # -------------------------------------------------
    for stock_attempt in range(2):
        html = pm.navigate(
            url,
            wait_selector=(
                "span.pdp-price_type_normal, "
                ':text-matches("out\\s+of\\s+stock|sold\\s+out|currently unavailable", "i")'
            ),
            timeout=25000,
        )

        rendered_soup = BeautifulSoup(html, "lxml")
        rendered = _extract(rendered_soup, url)
        price_area = rendered_soup.select_one("#module_product_price_1, .pdp-product-price")
        visible = _extract_visible_price_and_stock(
            price_area.get_text(" ", strip=True) if price_area else "", url
        )

        # Compléter titre, marque, description, images...
        result = _merge(result, rendered)

        # IMPORTANT :
        # le contenu rendu par navigateur est prioritaire
        # pour le prix et le stock.
        if visible.get("prix") or rendered.get("prix"):
            result["prix"] = visible.get("prix") or rendered["prix"]

        state = _purchase_state(rendered_soup)
        result["hors_stock"] = state == "hors_stock"
        result["stock_indetermine"] = state == "indetermine"
        result["devise"] = host_currency(url)

        if not result["stock_indetermine"]:
            break
        if stock_attempt == 0:
            print("   [Daraz] disponibilite indeterminee, nouvelle verification")

    if not result["titre"]:
        raise RuntimeError("titre introuvable")

    return result
