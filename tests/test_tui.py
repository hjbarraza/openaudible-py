import pytest
from openaudible.config import Config
from openaudible.catalog import Catalog
from openaudible.models import Book
from openaudible.tui.app import (
    OpenAudibleApp, fmt_runtime, status_icon, convert_status,
)


def test_fmt_runtime():
    assert fmt_runtime(0) == ""
    assert fmt_runtime(45) == "45m"
    assert fmt_runtime(150) == "2h 30m"


def test_status_icon():
    assert status_icon(Book(asin="1", title="x", converted=True)) == "●"
    assert status_icon(Book(asin="1", title="x", downloaded=True)) == "↓"
    assert status_icon(Book(asin="1", title="x")) == "·"


def test_convert_status_parses_ffmpeg_time():
    assert convert_status("frame= 1 time=01:23:45.67 bitrate=...") == "⚙ 01:23:45"
    assert convert_status("no time here") == "⚙ converting"


def _seed(tmp_path, books):
    cfg = Config.load()
    Catalog(cfg.db_file).sync(books)


@pytest.mark.asyncio
async def test_tui_lists_books(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAUDIBLE_HOME", str(tmp_path))
    _seed(tmp_path, [Book(asin="1", title="Dune", author="Herbert")])
    async with OpenAudibleApp().run_test() as pilot:
        await pilot.pause()
        assert pilot.app.query_one("#library").row_count == 1


@pytest.mark.asyncio
async def test_search_filters(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAUDIBLE_HOME", str(tmp_path))
    _seed(tmp_path, [
        Book(asin="1", title="Dune", author="Herbert"),
        Book(asin="2", title="Foundation", author="Asimov"),
    ])
    async with OpenAudibleApp().run_test() as pilot:
        await pilot.pause()
        app = pilot.app
        assert app.query_one("#library").row_count == 2
        app.query_one("#search").value = "asimov"
        await pilot.pause()
        table = app.query_one("#library")
        assert table.row_count == 1


@pytest.mark.asyncio
async def test_detail_shows_selected(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAUDIBLE_HOME", str(tmp_path))
    _seed(tmp_path, [Book(asin="1", title="Dune", author="Herbert",
                          narrator="Scott Brick")])
    async with OpenAudibleApp().run_test() as pilot:
        await pilot.pause()
        detail = pilot.app.query_one("#detail")
        rendered = str(detail.render())
        assert "Dune" in rendered
        assert "Scott Brick" in rendered


@pytest.mark.asyncio
async def test_get_without_login_notifies(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAUDIBLE_HOME", str(tmp_path))
    _seed(tmp_path, [Book(asin="1", title="Dune", author="Herbert")])
    async with OpenAudibleApp().run_test() as pilot:
        await pilot.pause()
        app = pilot.app
        notes = []
        monkeypatch.setattr(app, "notify",
                            lambda msg, **kw: notes.append((msg, kw)))
        started = []
        monkeypatch.setattr(app, "run_get", lambda asin: started.append(asin))
        app.action_get()
        await pilot.pause()
        assert started == []  # no job started
        assert any("login" in m.lower() for m, _ in notes)
