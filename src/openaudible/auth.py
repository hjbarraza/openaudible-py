from pathlib import Path
from typing import Optional

import audible


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


def login_external(marketplace: str = "us"):
    """Interactive browser login. Returns an Authenticator. Not unit-tested."""
    return audible.Authenticator.from_login_external(locale=marketplace)
