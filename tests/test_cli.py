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
