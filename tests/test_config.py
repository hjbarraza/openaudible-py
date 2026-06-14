from pathlib import Path
from openaudible.config import Config

def test_paths_resolve(tmp_path):
    c = Config(base_dir=tmp_path, books_dir=tmp_path / "books")
    assert c.auth_file == tmp_path / "auth.json"
    assert c.db_file == tmp_path / "library.db"
    assert c.aax_dir == tmp_path / "aax"
    assert c.books_dir == tmp_path / "books"
    assert c.output_format == "m4b"
    assert c.marketplace == "us"

def test_books_dir_defaults_to_documents(monkeypatch):
    monkeypatch.delenv("OPENAUDIBLE_BOOKS", raising=False)
    c = Config()
    assert c.books_dir == Path.home() / "Documents" / "audiobooks"

def test_ensure_dirs_creates(tmp_path):
    c = Config(base_dir=tmp_path, books_dir=tmp_path / "books")
    c.ensure_dirs()
    assert c.aax_dir.is_dir()
    assert c.books_dir.is_dir()

def test_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAUDIBLE_HOME", str(tmp_path / "custom"))
    monkeypatch.setenv("OPENAUDIBLE_BOOKS", str(tmp_path / "abooks"))
    c = Config.load()
    assert c.base_dir == tmp_path / "custom"
    assert c.books_dir == tmp_path / "abooks"
