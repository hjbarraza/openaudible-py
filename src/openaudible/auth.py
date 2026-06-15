from pathlib import Path
from typing import Optional

import audible
import httpx
from audible.localization import Locale
from audible.login import (
    build_oauth_url,
    create_code_verifier,
    extract_code_from_url,
)
from audible.register import register


def exists(auth_file: Path) -> bool:
    return Path(auth_file).exists()


def save(authenticator, auth_file: Path, password: Optional[str] = None) -> None:
    Path(auth_file).parent.mkdir(parents=True, exist_ok=True)
    if password:
        authenticator.to_file(auth_file, password=password, encryption="json")
    else:
        authenticator.to_file(auth_file, encryption=False)


def load(auth_file: Path, password: Optional[str] = None):
    if password:
        return audible.Authenticator.from_file(auth_file, password=password)
    return audible.Authenticator.from_file(auth_file)


def logout(auth_file: Path, deregister: bool = True) -> None:
    """Remove stored credentials, deregistering the device with Audible first.

    The local auth file is always removed, even if deregistration fails (e.g.
    offline or an already-revoked token).
    """
    if deregister and exists(auth_file):
        try:
            load(auth_file).deregister_device()
        except Exception:
            pass
    Path(auth_file).unlink(missing_ok=True)


def _playwright_login(url: str) -> str:
    """Open the sign-in page, raise it to the front, and capture the redirect.

    Mirrors audible's built-in Playwright callback but adds bring_to_front() so
    the login window surfaces above the terminal.

    On Linux, playwright's pre-built webkit binary links against Ubuntu-specific
    library versions that don't exist on other distros (ICU 74, libwebkitgtk-6.0,
    libjxl 0.8, etc.). System chromium is used instead on Linux — it supports the
    same iPhone 12 Pro device profile and works without any extra deps.
    """
    import shutil
    import sys

    from audible.login import build_init_cookies
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        iphone = p.devices["iPhone 12 Pro"]

        browser = None
        if sys.platform == "linux":
            for exe in ("chromium", "chromium-browser", "google-chrome-stable", "google-chrome"):
                path = shutil.which(exe)
                if path:
                    browser = p.chromium.launch(headless=False, executable_path=path)
                    break

        if browser is None:
            browser = p.webkit.launch(headless=False)

        context = browser.new_context(**iphone)
        context.add_cookies([{"name": n, "value": v, "url": url}
                             for n, v in build_init_cookies().items()])
        page = context.new_page()
        page.goto(url)
        try:
            page.bring_to_front()
        except Exception:
            pass
        try:
            while "/ap/maplanding" not in page.url:
                page.wait_for_timeout(500)
            return page.url
        finally:
            browser.close()


def login_browser(marketplace: str = "us"):
    """One-shot login: opens a browser, signs in, and auto-captures the result.

    Returns a registered Authenticator. Raises ImportError if Playwright (the
    browser automation backend) is not installed, so the caller can fall back to
    the manual paste flow.
    """
    import importlib.util
    if importlib.util.find_spec("playwright") is None:
        raise ImportError("playwright is not installed")

    return audible.Authenticator.from_login_external(
        locale=marketplace,
        login_url_callback=_playwright_login,
    )


def begin_login(marketplace: str = "us") -> tuple[str, dict]:
    """Step 1 of a promptless browser login.

    Returns the Amazon sign-in URL and the PKCE state needed to finish. The
    state must be persisted and handed back to ``complete_login`` because the
    ``code_verifier`` here must match the ``authorization_code`` minted by the
    URL the user actually visits.
    """
    locale = Locale(marketplace)
    code_verifier = create_code_verifier()  # bytes
    oauth_url, serial = build_oauth_url(
        country_code=locale.country_code,
        domain=locale.domain,
        market_place_id=locale.market_place_id,
        code_verifier=code_verifier,
    )
    state = {
        "marketplace": marketplace,
        "domain": locale.domain,
        "serial": serial,
        "code_verifier": code_verifier.decode(),
    }
    return oauth_url, state


def complete_login(response_url: str, state: dict):
    """Step 2: exchange the post-login URL for a registered Authenticator."""
    code = extract_code_from_url(httpx.URL(response_url))
    register_device = register(
        authorization_code=code,
        code_verifier=state["code_verifier"].encode(),
        domain=state["domain"],
        serial=state["serial"],
    )
    authenticator = audible.Authenticator()
    authenticator.locale = Locale(state["marketplace"])
    authenticator._update_attrs(**register_device)
    return authenticator
