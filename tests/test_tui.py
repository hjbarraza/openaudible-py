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


@pytest.mark.asyncio
async def test_enter_on_new_book_queues_get(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAUDIBLE_HOME", str(tmp_path))
    _seed(tmp_path, [Book(asin="1", title="Dune", author="Herbert")])
    async with OpenAudibleApp().run_test() as pilot:
        await pilot.pause()
        app = pilot.app
        monkeypatch.setattr(app, "get_auth", lambda: object())  # pretend logged in
        started = []
        monkeypatch.setattr(app, "run_get", lambda asin: started.append(asin))
        await pilot.press("enter")
        await pilot.pause()
        assert started == ["1"]


@pytest.mark.asyncio
async def test_enter_on_converted_book_plays(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAUDIBLE_HOME", str(tmp_path))
    cfg = Config.load()
    cat = Catalog(cfg.db_file)
    cat.sync([Book(asin="1", title="Dune", author="Herbert")])
    cat.mark("1", converted=True)  # converted is set via mark, not sync
    async with OpenAudibleApp().run_test() as pilot:
        await pilot.pause()
        app = pilot.app
        played = []
        monkeypatch.setattr(app, "_play", lambda book: played.append(book.asin))
        monkeypatch.setattr(app, "run_get", lambda asin: played.append("GET"))
        await pilot.press("enter")
        await pilot.pause()
        assert played == ["1"]


@pytest.mark.asyncio
async def test_queue_respects_concurrency_cap(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAUDIBLE_HOME", str(tmp_path))
    _seed(tmp_path, [Book(asin=str(i), title=f"B{i}") for i in range(5)])
    async with OpenAudibleApp().run_test() as pilot:
        await pilot.pause()
        app = pilot.app
        monkeypatch.setattr(app, "get_auth", lambda: object())
        # don't actually start workers; just record dispatch
        monkeypatch.setattr(app, "run_get", lambda asin: app._busy)  # no-op
        app.action_get_all()
        await pilot.pause()
        from openaudible.tui.app import MAX_CONCURRENT
        assert len(app._busy) == MAX_CONCURRENT
        assert len(app._waiting) == 5 - MAX_CONCURRENT


@pytest.mark.asyncio
async def test_cancel_removes_queued(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAUDIBLE_HOME", str(tmp_path))
    _seed(tmp_path, [Book(asin=str(i), title=f"B{i}") for i in range(5)])
    async with OpenAudibleApp().run_test() as pilot:
        await pilot.pause()
        app = pilot.app
        monkeypatch.setattr(app, "get_auth", lambda: object())
        monkeypatch.setattr(app, "run_get", lambda asin: None)
        app.action_get_all()
        await pilot.pause()
        queued = list(app._waiting)
        assert queued
        # select the first queued row and cancel it
        table = app.query_one("#library")
        target = queued[0]
        for r in range(table.row_count):
            if table.coordinate_to_cell_key((r, 0)).row_key.value == target:
                table.move_cursor(row=r)
                break
        await pilot.pause()
        app.action_cancel()
        await pilot.pause()
        assert target not in app._waiting
