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
