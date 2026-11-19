"""Regression tests for product-scoped extraction; no network access."""
import json
import unittest
from bs4 import BeautifulSoup
from scrapers.daraz_scraper import _extract, _purchase_state


def soup(html):
    return BeautifulSoup(html, "lxml")


class ExtractionTests(unittest.TestCase):
    def test_low_stock_is_available(self):
        page = soup('<div id="module_quantity-input">Almost sold out, buy now!</div><div id="module_add_to_cart"><button>Buy Now</button><button>Add to Cart</button></div>')
        self.assertEqual(_purchase_state(page), "ok")

    def test_explicit_stock_and_disabled_purchase(self):
        self.assertEqual(_purchase_state(soup('<div id="module_quantity-input">Out of stock</div>')), "hors_stock")
        self.assertEqual(_purchase_state(soup('<div id="module_add_to_cart"><button disabled>Add to Cart</button></div>')), "indetermine")
        self.assertEqual(_purchase_state(soup('<div id="module_add_to_cart"><button aria-disabled="true">Buy Now</button></div>')), "indetermine")

    def test_recommendations_do_not_supply_price_or_stock(self):
        page = soup('<h1 class="pdp-mod-product-badge-title">Product</h1><aside>Sold out Rs. 999</aside>')
        result = _extract(page, "https://www.daraz.pk/a")
        self.assertEqual(result["prix"], "")
        self.assertFalse(result["hors_stock"])

    def test_displayed_price_and_domain_currency_override_schema(self):
        product = {"@type": "Product", "name": "Product", "offers": {"price": "2000", "priceCurrency": "USD", "availability": "https://schema.org/InStock"}}
        for domain, currency, display in [("daraz.pk", "PKR", "Rs. 1,250"), ("daraz.lk", "LKR", "Rs. 1,250"), ("daraz.com.bd", "BDT", "? 1,250"), ("daraz.com.np", "NPR", "Rs. 1,250")]:
            with self.subTest(domain=domain):
                page = soup('<script type="application/ld+json">' + json.dumps(product) + '</script><span class="pdp-price_type_normal">' + display + '</span>')
                result = _extract(page, "https://www." + domain + "/a")
                self.assertEqual(result["prix"], "1250")
                self.assertEqual(result["devise"], currency)
                self.assertEqual(_purchase_state(page), "indetermine")

    def test_selected_gallery_excludes_other_variants_and_videos(self):
        first = "https://lk-live-21.slatic.net/kf/first.jpg"
        second = "https://lk-live-21.slatic.net/kf/second.jpg"
        fields = {"primaryKey": {"skuId": "selected"}, "skuGalleries": {"selected": [{"type": "img", "src": first}, {"type": "img", "src": first}, {"type": "video", "src": "https://youtube.com/a"}], "other": [{"type": "img", "src": second}]}}
        page = soup('<script>var __moduleData__ = ' + json.dumps({"data": {"root": {"fields": fields}}}) + ';</script><aside><img src="https://static-01.daraz.pk/p/recommendation.jpg"></aside>')
        self.assertEqual(_extract(page, "https://www.daraz.lk/a")["liens_images"], [first])

    def test_invalid_page_cannot_supply_recommended_product(self):
        with self.assertRaisesRegex(RuntimeError, "invalide"):
            _extract(soup('<h1>We seem to have lost this page</h1><aside>Rs. 788</aside>'), "https://www.daraz.pk/a")


if __name__ == "__main__":
    unittest.main()
