from typer.testing import CliRunner
from openaudible.cli import app
from openaudible.config import Config
from openaudible.catalog import Catalog
from openaudible.models import Book

runner = CliRunner()

def test_ls_lists_catalog(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAUDIBLE_HOME", str(tmp_path))
    cfg = Config.load()
    cat = Catalog(cfg.db_file)
    cat.sync([Book(asin="1", title="Dune", author="Herbert")])
    result = runner.invoke(app, ["ls"])
    assert result.exit_code == 0
    assert "Dune" in result.stdout

def test_status_reports_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAUDIBLE_HOME", str(tmp_path))
    cfg = Config.load()
    Catalog(cfg.db_file).sync([Book(asin="1", title="Dune")])
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "1" in result.stdout

def test_login_manual_prints_url_and_saves_pending(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAUDIBLE_HOME", str(tmp_path))
    result = runner.invoke(app, ["login", "--manual"])
    assert result.exit_code == 0
    assert "amazon.com/ap/signin" in result.stdout
    assert (tmp_path / ".login_pending.json").exists()

def test_login_browser_failure_falls_back_to_manual(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAUDIBLE_HOME", str(tmp_path))
    import openaudible.cli as cli_mod
    def boom(marketplace):
        raise ImportError("no playwright")
    monkeypatch.setattr(cli_mod.auth_mod, "login_browser", boom)
    result = runner.invoke(app, ["login"])
    assert result.exit_code == 0
    assert "copy/paste" in result.stdout.lower()
    assert (tmp_path / ".login_pending.json").exists()


def test_logout_removes_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAUDIBLE_HOME", str(tmp_path))
    import openaudible.cli as cli_mod
    cfg = Config.load(); cfg.ensure_dirs(); cfg.auth_file.write_text("{}")
    monkeypatch.setattr(cli_mod.auth_mod, "logout",
                        lambda f, **k: __import__("pathlib").Path(f).unlink())
    result = runner.invoke(app, ["logout"])
    assert result.exit_code == 0
    assert "Logged out" in result.stdout
    assert not cfg.auth_file.exists()

def test_logout_when_not_logged_in(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAUDIBLE_HOME", str(tmp_path))
    result = runner.invoke(app, ["logout"])
    assert result.exit_code == 0
    assert "Not logged in" in result.stdout


def test_import_command(tmp_path, monkeypatch, request):
    monkeypatch.setenv("OPENAUDIBLE_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("OPENAUDIBLE_BOOKS", str(tmp_path / "books"))
    sample = request.getfixturevalue("sample_m4a")
    result = runner.invoke(app, ["import", str(sample)])
    assert result.exit_code == 0
    assert "Imported" in result.stdout
    assert len(Catalog(Config.load().db_file).all()) == 1


def test_export_command(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAUDIBLE_HOME", str(tmp_path))
    cfg = Config.load()
    Catalog(cfg.db_file).sync([Book(asin="1", title="Dune", author="Herbert")])
    out = tmp_path / "lib.json"
    result = runner.invoke(app, ["export", str(out)])
    assert result.exit_code == 0 and out.exists()
    import json
    assert json.loads(out.read_text())[0]["title"] == "Dune"


def test_read_command(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAUDIBLE_HOME", str(tmp_path))
    cfg = Config.load()
    Catalog(cfg.db_file).sync([Book(asin="1", title="Dune")])
    result = runner.invoke(app, ["read", "1", "finished"])
    assert result.exit_code == 0
    assert Catalog(cfg.db_file).get("1").read_status == "finished"


def test_edit_command(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAUDIBLE_HOME", str(tmp_path))
    cfg = Config.load()
    Catalog(cfg.db_file).sync([Book(asin="1", title="Old", author="X")])
    result = runner.invoke(app, ["edit", "1", "--title", "New Title",
                                 "--author", "New Author"])
    assert result.exit_code == 0
    b = Catalog(cfg.db_file).get("1")
    assert b.title == "New Title" and b.author == "New Author"


def test_autofill_command(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAUDIBLE_HOME", str(tmp_path))
    cfg = Config.load(); cfg.ensure_dirs(); cfg.auth_file.write_text("{}")
    Catalog(cfg.db_file).sync([Book(asin="1", title="stub", author="?")])
    import openaudible.cli as cli_mod
    monkeypatch.setattr(cli_mod, "_auth", lambda c: object())
    import openaudible.client as client_mod
    monkeypatch.setattr(client_mod, "fetch_book_meta",
                        lambda auth, asin: Book(asin="1", title="Real", author="Real A"))
    result = runner.invoke(app, ["autofill", "1"])
    assert result.exit_code == 0
    assert Catalog(cfg.db_file).get("1").title == "Real"
