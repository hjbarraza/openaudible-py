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


@dataclass
class Config:
    base_dir: Path = field(default_factory=default_base_dir)
    books_dir: Path = field(default_factory=default_books_dir)
    output_format: str = "m4b"
    marketplace: str = "us"

    @classmethod
    def load(cls) -> "Config":
        return cls()

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
