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


def login_browser(marketplace: str = "us"):
    """One-shot login: opens a browser, signs in, and auto-captures the result.

    Returns a registered Authenticator. Raises ImportError if Playwright (the
    browser automation backend) is not installed, so the caller can fall back to
    the manual paste flow.
    """
    from audible.login import playwright_external_login_url_callback

    return audible.Authenticator.from_login_external(
        locale=marketplace,
        login_url_callback=playwright_external_login_url_callback,
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
