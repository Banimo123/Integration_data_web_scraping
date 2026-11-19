import os
import time

from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
    Error as PlaywrightError,
)

_pw = None
_browser = None
_context = None
_page = None


def _reset():
    """
    Ferme proprement les anciens objets Playwright
    et remet toutes les références à zéro.
    """
    global _pw, _browser, _context, _page

    try:
        if _page is not None and not _page.is_closed():
            _page.close()
    except Exception:
        pass

    try:
        if _context is not None:
            _context.close()
    except Exception:
        pass

    try:
        if _browser is not None and _browser.is_connected():
            _browser.close()
    except Exception:
        pass

    try:
        if _pw is not None:
            _pw.stop()
    except Exception:
        pass

    _page = None
    _context = None
    _browser = None
    _pw = None


def _ensure_browser():
    """
    Vérifie que Chromium fonctionne.
    Sinon, recrée complètement Playwright.
    """
    global _pw, _browser

    # Si le navigateur existe et fonctionne encore
    if _browser is not None:
        try:
            if _browser.is_connected():
                return
        except Exception:
            pass

    # Ancienne instance inutilisable
    _reset()

    _pw = sync_playwright().start()

    headless = os.getenv(
        "DARAZ_HEADLESS",
        "1"
    ) != "0"

    # IMPORTANT :
    # on utilise le Chromium installé par Playwright,
    # et non plus Google Chrome système.
    _browser = _pw.chromium.launch(
        headless=headless
    )


def _create_page():
    """
    Crée un nouveau contexte et une nouvelle page.
    """
    global _context, _page

    _ensure_browser()

    try:
        if _context is not None:
            _context.close()
    except Exception:
        pass

    _context = _browser.new_context(
        locale="en-US",

        viewport={
            "width": 1366,
            "height": 900,
        },

        user_agent=(
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/131.0.0.0 "
            "Safari/537.36"
        ),
    )

    _context.set_default_timeout(30000)

    _page = _context.new_page()

    return _page


def get_page():
    """
    Retourne une page valide.

    Si l'ancienne page ou le navigateur ont été fermés,
    une nouvelle page est automatiquement créée.
    """
    global _page, _browser

    # Vérifier le navigateur
    if _browser is None:
        return _create_page()

    try:
        if not _browser.is_connected():
            return _create_page()
    except Exception:
        return _create_page()

    # Vérifier la page
    if _page is None:
        return _create_page()

    try:
        if _page.is_closed():
            return _create_page()
    except Exception:
        return _create_page()

    return _page


def navigate(
    url,
    wait_selector=None,
    timeout=30000
):
    """
    Charge une URL.

    En cas de TargetClosedError :
    - recrée Chromium ;
    - recrée le contexte ;
    - recrée la page ;
    - réessaie une fois.
    """

    global _page

    last_error = None

    for attempt in range(1, 3):

        try:
            page = get_page()

            print(
                f"   [Playwright] tentative "
                f"{attempt}/2"
            )

            try:
                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=60000,
                )

            except PlaywrightTimeoutError:
                print(
                    "   [Playwright] "
                    "domcontentloaded trop lent, "
                    "fallback commit"
                )

                page.goto(
                    url,
                    wait_until="commit",
                    timeout=60000,
                )

            if wait_selector:
                try:
                    page.wait_for_selector(
                        wait_selector,
                        timeout=timeout,
                    )
                except PlaywrightTimeoutError:
                    # Ce n'est pas forcément une erreur :
                    # certains produits n'ont pas les mêmes classes.
                    pass

            # Laisser les données dynamiques s'afficher
            time.sleep(2)

            return page.content()

        except PlaywrightError as exc:
            last_error = exc

            print(
                f"   [Playwright] navigateur/page "
                f"fermé(e) : {exc}"
            )

            # Reconstruction complète
            _reset()

            if attempt < 2:
                print(
                    "   [Playwright] "
                    "redémarrage automatique..."
                )
                time.sleep(1)

        except Exception as exc:
            last_error = exc

            print(
                f"   [Playwright] erreur : {exc}"
            )

            _reset()

            if attempt < 2:
                time.sleep(1)

    raise RuntimeError(
        f"Playwright impossible après 2 tentatives : "
        f"{last_error}"
    )


def get_body_text():
    """
    Retourne le texte visible de la page actuelle.
    """
    page = get_page()

    try:
        if page.is_closed():
            return ""

        return page.locator(
            "body"
        ).inner_text(
            timeout=10000
        )

    except Exception:
        return ""


def close_all():
    """
    Fermeture finale à la fin du scraping.
    """
    _reset()