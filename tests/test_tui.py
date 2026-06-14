import pytest
from openaudible.config import Config
from openaudible.catalog import Catalog
from openaudible.models import Book
from openaudible.tui.app import OpenAudibleApp

@pytest.mark.asyncio
async def test_tui_lists_books(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAUDIBLE_HOME", str(tmp_path))
    cfg = Config.load()
    Catalog(cfg.db_file).sync([Book(asin="1", title="Dune", author="Herbert")])
    app = OpenAudibleApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.query_one("#library")
        assert table.row_count == 1
