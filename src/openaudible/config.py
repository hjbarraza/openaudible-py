import os
from dataclasses import dataclass, field
from pathlib import Path

VALID_FORMATS = ("m4b", "mp3", "mp3-split")


def default_base_dir() -> Path:
    env = os.environ.get("OPENAUDIBLE_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / "Library" / "Application Support" / "openaudible-py"


def default_books_dir() -> Path:
    env = os.environ.get("OPENAUDIBLE_BOOKS")
    if env:
        return Path(env).expanduser()
    return Path.home() / "Documents" / "audiobooks"


def _env_flag(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    base_dir: Path = field(default_factory=default_base_dir)
    books_dir: Path = field(default_factory=default_books_dir)
    output_format: str = "m4b"
    marketplace: str = "us"
    download_pdfs: bool = True          # OPENAUDIBLE_NO_PDF=1 to disable
    delete_source: bool = False         # OPENAUDIBLE_DELETE_AAX=1 to enable

    @classmethod
    def load(cls) -> "Config":
        return cls(
            download_pdfs=not _env_flag("OPENAUDIBLE_NO_PDF", False),
            delete_source=_env_flag("OPENAUDIBLE_DELETE_AAX", False),
        )

    def __post_init__(self) -> None:
        self.base_dir = Path(self.base_dir)
        self.books_dir = Path(self.books_dir)
        if self.output_format not in VALID_FORMATS:
            raise ValueError(f"output_format must be one of {VALID_FORMATS}")

    @property
    def auth_file(self) -> Path:
        return self.base_dir / "auth.json"

    @property
    def db_file(self) -> Path:
        return self.base_dir / "library.db"

    @property
    def aax_dir(self) -> Path:
        return self.base_dir / "aax"

    @property
    def covers_dir(self) -> Path:
        return self.base_dir / "covers"

    def ensure_dirs(self) -> None:
        for d in (self.base_dir, self.aax_dir, self.books_dir, self.covers_dir):
            d.mkdir(parents=True, exist_ok=True)
