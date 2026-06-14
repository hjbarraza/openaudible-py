from __future__ import annotations

import subprocess
import sys
from typing import Optional

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import DataTable, Footer, Header, Input, RichLog, Static

from .. import auth as auth_mod
from ..catalog import Catalog
from ..client import fetch_library
from ..config import Config
from ..jobs import output_path, process_book
from ..models import Book


def fmt_runtime(minutes: int) -> str:
    if not minutes:
        return ""
    h, m = divmod(int(minutes), 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def trunc(text: str, width: int) -> str:
    text = text or ""
    return text if len(text) <= width else text[: width - 1] + "…"


def status_icon(book: Book) -> str:
    if book.converted:
        return "●"
    if book.downloaded:
        return "↓"
    return "·"


def convert_status(ffmpeg_line: str) -> str:
    """Turn an ffmpeg progress line into a short 'converting HH:MM:SS' label."""
    i = ffmpeg_line.find("time=")
    if i == -1:
        return "⚙ converting"
    stamp = ffmpeg_line[i + 5:].split(" ")[0].split(".")[0]
    return f"⚙ {stamp}"


COLUMNS = [(" ", "status"), ("Title", "title"), ("Author", "author"),
           ("Series", "series"), ("Time", "time")]


class OpenAudibleApp(App):
    TITLE = "openaudible"
    CSS = """
    #main { height: 1fr; }
    #library { width: 2fr; }
    #detail { width: 1fr; border-left: solid $panel; padding: 0 1; }
    #search { dock: top; display: none; }
    #search.visible { display: block; }
    #log { height: 8; border-top: solid $panel; padding: 0 1; }
    """
    BINDINGS = [
        ("/", "search", "Search"),
        ("g", "get", "Get"),
        ("p", "play", "Play"),
        ("o", "open_folder", "Folder"),
        ("s", "sync", "Sync"),
        ("r", "refresh", "Refresh"),
        ("escape", "clear_search", "Clear"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.cfg = Config.load()
        self.catalog = Catalog(self.cfg.db_file)
        self._auth = None
        self._active: dict[str, str] = {}  # asin -> live status label

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Input(placeholder="Search title / author / series…", id="search")
        with Horizontal(id="main"):
            yield DataTable(id="library")
            yield Static(id="detail")
        yield RichLog(id="log", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#library", DataTable)
        table.cursor_type = "row"
        for label, key in COLUMNS:
            table.add_column(label, key=key)
        self.load_rows()
        self.log_line("[dim]Ready. / search · g get · p play · s sync · q quit[/dim]")

    # ---- data / rendering ----
    def current_books(self) -> list[Book]:
        query = self.query_one("#search", Input).value.strip()
        return self.catalog.search(query) if query else self.catalog.all()

    def load_rows(self) -> None:
        table = self.query_one("#library", DataTable)
        table.clear()
        for b in self.current_books():
            table.add_row(self._active.get(b.asin) or status_icon(b),
                          trunc(b.title, 48), trunc(b.author, 24),
                          trunc(b.series, 22), fmt_runtime(b.runtime_min),
                          key=b.asin)
        self.update_detail()

    def selected_asin(self) -> Optional[str]:
        table = self.query_one("#library", DataTable)
        if table.row_count == 0:
            return None
        try:
            cell = table.coordinate_to_cell_key(table.cursor_coordinate)
            return cell.row_key.value
        except Exception:
            return None

    def update_detail(self) -> None:
        detail = self.query_one("#detail", Static)
        asin = self.selected_asin()
        book = self.catalog.get(asin) if asin else None
        if not book:
            detail.update("[dim]No selection[/dim]")
            return
        state = ("[green]converted[/green]" if book.converted
                 else "downloaded" if book.downloaded else "not downloaded")
        lines = [
            f"[b]{book.title}[/b]", "",
            f"[cyan]Author[/cyan]    {book.author}",
            f"[cyan]Narrator[/cyan]  {book.narrator or '—'}",
            f"[cyan]Series[/cyan]    {book.series or '—'}",
            f"[cyan]Length[/cyan]    {fmt_runtime(book.runtime_min) or '—'}",
            f"[cyan]ASIN[/cyan]      {book.asin}",
            "",
            f"[cyan]Status[/cyan]    {self._active.get(book.asin) or state}",
        ]
        out = output_path(self.cfg, book)
        if book.converted and out.exists():
            lines += ["", f"[dim]{out}[/dim]"]
        detail.update("\n".join(lines))

    def log_line(self, text: str) -> None:
        self.query_one("#log", RichLog).write(text)

    def set_status(self, asin: str, text: str) -> None:
        self._active[asin] = text
        table = self.query_one("#library", DataTable)
        try:
            table.update_cell(asin, "status", text, update_width=False)
        except Exception:
            pass  # row not currently visible (filtered) — table refreshes later
        self.update_detail()

    # ---- events ----
    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self.update_detail()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search":
            self.load_rows()

    # ---- navigation actions ----
    def action_search(self) -> None:
        box = self.query_one("#search", Input)
        box.add_class("visible")
        box.focus()

    def action_clear_search(self) -> None:
        box = self.query_one("#search", Input)
        box.value = ""
        box.remove_class("visible")
        self.query_one("#library", DataTable).focus()
        self.load_rows()

    def action_refresh(self) -> None:
        self.load_rows()

    # ---- file actions ----
    def _open(self, path) -> None:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([opener, str(path)])

    def action_play(self) -> None:
        book = self._selected_book()
        if not book:
            return
        path = output_path(self.cfg, book)
        if not path.exists():
            self.notify("Not converted yet — press g to get it.", severity="warning")
            return
        self._open(path)

    def action_open_folder(self) -> None:
        book = self._selected_book()
        if not book:
            return
        folder = output_path(self.cfg, book).parent
        folder.mkdir(parents=True, exist_ok=True)
        self._open(folder)

    def _selected_book(self) -> Optional[Book]:
        asin = self.selected_asin()
        return self.catalog.get(asin) if asin else None

    # ---- auth ----
    def get_auth(self):
        if self._auth is None and auth_mod.exists(self.cfg.auth_file):
            self._auth = auth_mod.load(self.cfg.auth_file)
        return self._auth

    # ---- jobs ----
    def action_get(self) -> None:
        book = self._selected_book()
        if not book:
            return
        if book.converted:
            self.notify(f"Already converted: {book.title}")
            return
        if book.asin in self._active:
            return
        if self.get_auth() is None:
            self.notify("Not logged in. Run 'openaudible login'.", severity="error")
            return
        self.set_status(book.asin, "⏬ downloading")
        self.log_line(f"[yellow]Getting[/yellow] {book.title}")
        self.run_get(book.asin)

    @work(thread=True, group="jobs")
    def run_get(self, asin: str) -> None:
        book = self.catalog.get(asin)
        auth = self.get_auth()

        def progress(line: str) -> None:
            self.call_from_thread(self.set_status, asin, convert_status(line))

        try:
            process_book(auth=auth, cfg=self.cfg, book=book, on_progress=progress)
        except Exception as exc:  # surface, don't crash the UI
            self.call_from_thread(self.job_failed, asin, str(exc))
            return
        self.catalog.mark(asin, downloaded=True, converted=True)
        self.call_from_thread(self.job_done, asin)

    def job_done(self, asin: str) -> None:
        self._active.pop(asin, None)
        book = self.catalog.get(asin)
        try:
            self.query_one("#library", DataTable).update_cell(
                asin, "status", "●", update_width=False)
        except Exception:
            pass
        self.log_line(f"[green]Done[/green] {book.title}")
        self.update_detail()

    def job_failed(self, asin: str, message: str) -> None:
        self._active.pop(asin, None)
        try:
            self.query_one("#library", DataTable).update_cell(
                asin, "status", "✗", update_width=False)
        except Exception:
            pass
        last = message.splitlines()[-1] if message else "error"
        self.log_line(f"[red]Failed[/red] {asin}: {last}")
        self.update_detail()

    def action_sync(self) -> None:
        if self.get_auth() is None:
            self.notify("Not logged in. Run 'openaudible login'.", severity="error")
            return
        self.log_line("[yellow]Syncing library…[/yellow]")
        self.run_sync()

    @work(thread=True, group="sync", exclusive=True)
    def run_sync(self) -> None:
        try:
            books = fetch_library(self.get_auth())
        except Exception as exc:
            self.call_from_thread(self.log_line, f"[red]Sync failed[/red]: {exc}")
            return
        self.catalog.sync(books)
        self.call_from_thread(self.after_sync, len(books))

    def after_sync(self, count: int) -> None:
        self.log_line(f"[green]Synced {count} books.[/green]")
        self.load_rows()


def main() -> None:
    OpenAudibleApp().run()


if __name__ == "__main__":
    main()
