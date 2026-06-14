from __future__ import annotations

import subprocess
import sys
import threading
from collections import deque
from typing import Optional

import httpx
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Header, Input, RichLog, Static
from textual_image.widget import Image as CoverImage

from .. import auth as auth_mod
from ..catalog import Catalog
from ..client import fetch_library
from ..config import Config
from ..convert import ConversionError
from ..jobs import output_path, process_book
from ..models import Book

MAX_CONCURRENT = 2
HALF_PAGE = 10
SORTS = ["author", "title", "recent"]


def sort_books(books: list[Book], mode: str) -> list[Book]:
    if mode == "title":
        return sorted(books, key=lambda b: b.title.lower())
    if mode == "recent":  # newest purchase first; undated sink to the bottom
        return sorted(books, key=lambda b: b.purchase_date or "", reverse=True)
    return sorted(books, key=lambda b: (b.author.lower(), b.title.lower()))


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


def _time_to_secs(stamp: str) -> int:
    parts = stamp.split(":")
    try:
        h, m, s = (int(p) for p in parts)
        return h * 3600 + m * 60 + s
    except ValueError:
        return 0


def convert_status(ffmpeg_line: str, total_min: int = 0) -> str:
    i = ffmpeg_line.find("time=")
    if i == -1:
        return "⚙ converting"
    stamp = ffmpeg_line[i + 5:].split(" ")[0].split(".")[0]
    if total_min:
        pct = min(99, int(_time_to_secs(stamp) * 100 / (total_min * 60)))
        return f"⚙ converting {pct}% · {stamp}"
    return f"⚙ converting {stamp}"


def download_status(written: int, total: Optional[int]) -> str:
    mb = written / (1024 * 1024)
    if total:
        pct = int(written * 100 / total)
        return f"⏬ downloading {pct}% · {mb:.0f}/{total / 1048576:.0f} MB"
    return f"⏬ downloading {mb:.0f} MB"


COLUMNS = [(" ", "status"), ("Title", "title"), ("Author", "author"),
           ("Series", "series"), ("Time", "time")]

HELP_TEXT = """[b]openaudible — keyboard controls[/b]

[b cyan]Move[/b cyan]
  ↑ / ↓ · j / k     up / down
  PgUp / PgDn       page
  Home / End        top / bottom
  Ctrl+U / Ctrl+D   half page

[b cyan]Act on the selected book[/b cyan]
  Enter             get if new, play if already converted
  g                 get  (download + de-DRM + convert)
  p                 play in your OS player
  o                 open the book's folder
  c                 cancel this book's job

[b cyan]Library[/b cyan]
  a                 get ALL un-converted books in view
  t                 sort: author → title → recently bought
  s                 sync library from Audible
  r                 refresh   ·   / search   ·   Esc clear

[b cyan]Account[/b cyan]
  l                 log in (opens a browser)
  L                 log out (deregister this device)

[b cyan]Other[/b cyan]
  ?                 this help     q  quit

[dim]Up to 2 downloads run at once; the rest wait as “queued”.[/dim]
[dim]Press Esc or ? to close.[/dim]"""


class HelpScreen(ModalScreen):
    BINDINGS = [("escape", "dismiss"), ("question_mark", "dismiss"),
                ("q", "dismiss")]
    CSS = """
    HelpScreen { align: center middle; }
    #help { width: 64; height: auto; padding: 1 2; background: $panel;
            border: round $accent; }
    """

    def compose(self) -> ComposeResult:
        yield Static(HELP_TEXT, id="help")


class OpenAudibleApp(App):
    TITLE = "openaudible"
    CSS = """
    #main { height: 1fr; }
    #library { width: 3fr; }
    #side { width: 2fr; border-left: solid $panel; padding: 0 1; }
    /* fix height, width auto → cover scales to fit the pane and keeps aspect */
    #cover { height: 22; width: auto; max-width: 100%; content-align: center top; }
    #detail { height: auto; }
    #search { dock: top; display: none; }
    #search.visible { display: block; }
    #log { height: 8; border-top: solid $panel; padding: 0 1; }
    """
    BINDINGS = [
        Binding("enter", "primary", "Get/Play"),
        Binding("g", "get", "Get"),
        Binding("p", "play", "Play"),
        Binding("o", "open_folder", "Folder"),
        Binding("c", "cancel", "Cancel"),
        Binding("a", "get_all", "Get all"),
        Binding("t", "sort", "Sort"),
        Binding("s", "sync", "Sync"),
        Binding("slash", "search", "Search"),
        Binding("question_mark", "help", "Help"),
        Binding("q", "quit", "Quit"),
        # Account (hidden from the footer).
        Binding("l", "login", "Login", show=False),
        Binding("L", "logout", "Logout", show=False),
        # Navigation + housekeeping (hidden from the footer to keep it readable).
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("ctrl+d", "half_down", "Half down", show=False),
        Binding("ctrl+u", "half_up", "Half up", show=False),
        Binding("r", "refresh", "Refresh", show=False),
        Binding("escape", "clear_search", "Clear", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.cfg = Config.load()
        self.catalog = Catalog(self.cfg.db_file)
        self._auth = None
        self._sort = "author"
        self._status: dict[str, str] = {}          # asin -> live status label
        self._cancel: dict[str, threading.Event] = {}  # asin -> cancel flag
        self._waiting: deque[str] = deque()          # waiting asins
        self._busy: set[str] = set()            # asins in a worker
        self._cover_for: Optional[str] = None   # asin whose cover is shown

    # ---- layout ----
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Input(placeholder="Search title / author / series…", id="search")
        with Horizontal(id="main"):
            yield DataTable(id="library")
            with Vertical(id="side"):
                yield CoverImage(id="cover")
                yield Static(id="detail")
        yield RichLog(id="log", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#library", DataTable)
        table.cursor_type = "row"
        for label, key in COLUMNS:
            table.add_column(label, key=key)
        self.sub_title = f"sort: {self._sort}"
        self.load_rows()
        table.focus()
        self.log_line("[dim]Ready. Enter=get/play · g get · a all · t sort · "
                      "s sync · ? help · q quit[/dim]")

    # ---- data / rendering ----
    def current_books(self) -> list[Book]:
        query = self.query_one("#search", Input).value.strip()
        books = self.catalog.search(query) if query else self.catalog.all()
        return sort_books(books, self._sort)

    def load_rows(self) -> None:
        table = self.query_one("#library", DataTable)
        table.clear()
        for b in self.current_books():
            table.add_row(self._status.get(b.asin) or status_icon(b),
                          trunc(b.title, 48), trunc(b.author, 24),
                          trunc(b.series, 22), fmt_runtime(b.runtime_min),
                          key=b.asin)
        self.update_detail()

    def selected_asin(self) -> Optional[str]:
        table = self.query_one("#library", DataTable)
        if table.row_count == 0:
            return None
        try:
            return table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        except Exception:
            return None

    def selected_book(self) -> Optional[Book]:
        asin = self.selected_asin()
        return self.catalog.get(asin) if asin else None

    def update_detail(self) -> None:
        detail = self.query_one("#detail", Static)
        book = self.selected_book()
        self.update_cover(book)
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
            f"[cyan]Status[/cyan]    {self._status.get(book.asin) or state}",
        ]
        out = output_path(self.cfg, book)
        if book.converted and out.exists():
            lines += ["", f"[dim]{out}[/dim]"]
        detail.update("\n".join(lines))

    # ---- cover art ----
    # Rendered by textual-image, which auto-selects the best protocol the
    # terminal supports (Kitty / Sixel / iTerm2) and falls back to half-cells.
    def _cover_path(self, asin: str):
        return self.cfg.covers_dir / f"{asin}.jpg"

    def _show_cover(self, path) -> None:
        try:
            self.query_one("#cover", CoverImage).image = str(path) if path else None
        except Exception:
            pass

    def update_cover(self, book: Optional[Book]) -> None:
        if not book or not book.cover_url:
            self._show_cover(None)
            self._cover_for = None
            return
        if self._cover_for == book.asin:
            return  # already showing this one
        self._cover_for = book.asin
        path = self._cover_path(book.asin)
        if path.exists():
            self._show_cover(path)
        else:
            self._show_cover(None)
            self.load_cover(book.asin, book.cover_url)

    @work(thread=True, group="cover", exclusive=True)
    def load_cover(self, asin: str, url: str) -> None:
        path = self._cover_path(asin)
        if not path.exists():
            try:
                resp = httpx.get(url, timeout=15, follow_redirects=True)
                resp.raise_for_status()
                self.cfg.covers_dir.mkdir(parents=True, exist_ok=True)
                path.write_bytes(resp.content)
            except Exception:
                return
        self.call_from_thread(self._cover_loaded, asin, path)

    def _cover_loaded(self, asin: str, path) -> None:
        if self.selected_asin() == asin:  # selection may have moved on
            self._show_cover(path)

    def log_line(self, text: str) -> None:
        self.query_one("#log", RichLog).write(text)

    def _set_cell(self, asin: str, text: str) -> None:
        try:
            self.query_one("#library", DataTable).update_cell(
                asin, "status", text, update_width=False)
        except Exception:
            pass  # row filtered out of view; will refresh later

    def set_status(self, asin: str, text: str) -> None:
        self._status[asin] = text
        self._set_cell(asin, text)
        self.update_detail()

    def clear_status(self, asin: str) -> None:
        self._status.pop(asin, None)
        book = self.catalog.get(asin)
        if book:
            self._set_cell(asin, status_icon(book))
        self.update_detail()

    # ---- events ----
    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self.update_detail()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search":
            self.load_rows()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "search":
            self.query_one("#library", DataTable).focus()

    # ---- navigation ----
    def action_cursor_down(self) -> None:
        self.query_one("#library", DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#library", DataTable).action_cursor_up()

    def action_half_down(self) -> None:
        t = self.query_one("#library", DataTable)
        if t.row_count:
            t.move_cursor(row=min(t.cursor_row + HALF_PAGE, t.row_count - 1))

    def action_half_up(self) -> None:
        t = self.query_one("#library", DataTable)
        if t.row_count:
            t.move_cursor(row=max(t.cursor_row - HALF_PAGE, 0))

    # ---- search / help ----
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

    def action_sort(self) -> None:
        self._sort = SORTS[(SORTS.index(self._sort) + 1) % len(SORTS)]
        self.sub_title = f"sort: {self._sort}"
        self.load_rows()

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    # ---- file actions ----
    def _open(self, path) -> None:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([opener, str(path)])

    def _play(self, book: Book) -> None:
        path = output_path(self.cfg, book)
        if not path.exists():
            self.notify("Not converted yet — press g to get it.", severity="warning")
            return
        self._open(path)

    def action_play(self) -> None:
        book = self.selected_book()
        if book:
            self._play(book)

    def action_open_folder(self) -> None:
        book = self.selected_book()
        if not book:
            return
        folder = output_path(self.cfg, book).parent
        folder.mkdir(parents=True, exist_ok=True)
        self._open(folder)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        # Enter on a focused DataTable arrives here (not via the key binding).
        self._primary(event.row_key.value)

    def action_primary(self) -> None:
        asin = self.selected_asin()
        if asin:
            self._primary(asin)

    def _primary(self, asin: str) -> None:
        """Enter: play if already converted, otherwise get."""
        book = self.catalog.get(asin)
        if not book:
            return
        if book.converted:
            self._play(book)
        else:
            self._get(asin)

    # ---- auth ----
    def get_auth(self):
        if self._auth is None and auth_mod.exists(self.cfg.auth_file):
            self._auth = auth_mod.load(self.cfg.auth_file)
        return self._auth

    def action_login(self) -> None:
        if self.get_auth() is not None:
            self.notify("Already logged in. Press L to log out first.")
            return
        self.log_line("[yellow]Opening a browser to sign in…[/yellow]")
        self.run_login()

    @work(thread=True, group="login", exclusive=True)
    def run_login(self, marketplace: str = "us") -> None:
        try:
            authenticator = auth_mod.login_browser(marketplace)
        except Exception as exc:
            self.call_from_thread(self.log_line, f"[red]Login failed[/red]: {exc}")
            return
        auth_mod.save(authenticator, self.cfg.auth_file)
        self.call_from_thread(self._login_done)

    def _login_done(self) -> None:
        self._auth = None
        self.get_auth()
        self.notify("Logged in. Press s to sync your library.")
        self.log_line("[green]Logged in.[/green]")

    def action_logout(self) -> None:
        if not auth_mod.exists(self.cfg.auth_file):
            self.notify("Not logged in.")
            return
        self.log_line("[yellow]Logging out…[/yellow]")
        self.run_logout()

    @work(thread=True, group="logout", exclusive=True)
    def run_logout(self) -> None:
        auth_mod.logout(self.cfg.auth_file)
        self.call_from_thread(self._logout_done)

    def _logout_done(self) -> None:
        self._auth = None
        self.notify("Logged out.")
        self.log_line("[dim]Logged out.[/dim]")

    # ---- job queue ----
    def _enqueue(self, asin: str) -> bool:
        book = self.catalog.get(asin)
        if not book or book.converted:
            return False
        if asin in self._busy or asin in self._waiting:
            return False
        self._cancel[asin] = threading.Event()
        self._waiting.append(asin)
        self.set_status(asin, "queued")
        return True

    def _pump(self) -> None:
        while len(self._busy) < MAX_CONCURRENT and self._waiting:
            asin = self._waiting.popleft()
            event = self._cancel.get(asin)
            if event and event.is_set():       # canceled while queued
                self.clear_status(asin)
                self._cancel.pop(asin, None)
                continue
            self._busy.add(asin)
            self.run_get(asin)

    def _after_job(self, asin: str) -> None:
        self._busy.discard(asin)
        self._cancel.pop(asin, None)
        self._pump()

    def action_get(self) -> None:
        asin = self.selected_asin()
        if asin:
            self._get(asin)

    def _get(self, asin: str) -> None:
        book = self.catalog.get(asin)
        if not book:
            return
        if book.converted:
            self.notify("Already converted — press p to play.")
            return
        if self.get_auth() is None:
            self.notify("Not logged in. Run 'openaudible login'.", severity="error")
            return
        if self._enqueue(asin):
            self.log_line(f"[yellow]Queued[/yellow] {book.title}")
            self._pump()

    def action_get_all(self) -> None:
        if self.get_auth() is None:
            self.notify("Not logged in. Run 'openaudible login'.", severity="error")
            return
        queued = sum(1 for b in self.current_books() if self._enqueue(b.asin))
        if queued:
            self.log_line(f"[yellow]Queued {queued} books.[/yellow]")
            self._pump()
        else:
            self.notify("Nothing to get.")

    def action_cancel(self) -> None:
        asin = self.selected_asin()
        if not asin:
            return
        event = self._cancel.get(asin)
        if asin in self._waiting:
            self._waiting.remove(asin)
            self._cancel.pop(asin, None)
            self.clear_status(asin)
            self.log_line("[dim]Removed from queue.[/dim]")
        elif asin in self._busy and event:
            event.set()
            self.log_line("[yellow]Canceling…[/yellow]")
        else:
            self.notify("No active job for this book.")

    @work(thread=True, group="jobs")
    def run_get(self, asin: str) -> None:
        book = self.catalog.get(asin)
        auth = self.get_auth()
        event = self._cancel.get(asin)
        last = {"d": -1, "c": -1}  # throttle UI updates to whole-percent changes
        self.call_from_thread(self.log_line, f"[yellow]Downloading[/yellow] {book.title}")
        self.call_from_thread(self.set_status, asin, "⏬ downloading")

        def on_download(written: int, total) -> None:
            pct = int(written * 100 / total) if total else written // (1 << 21)
            if pct == last["d"]:
                return
            last["d"] = pct
            self.call_from_thread(self.set_status, asin,
                                  download_status(written, total))

        def on_convert(line: str) -> None:
            i = line.find("time=")
            if i == -1:
                return
            secs = _time_to_secs(line[i + 5:].split(" ")[0].split(".")[0])
            pct = int(secs * 100 / (book.runtime_min * 60)) if book.runtime_min else secs
            if pct == last["c"]:
                return
            last["c"] = pct
            self.call_from_thread(self.set_status, asin,
                                  convert_status(line, book.runtime_min))

        try:
            process_book(auth=auth, cfg=self.cfg, book=book,
                         on_progress=on_convert, on_download=on_download,
                         cancel_check=(event.is_set if event else None))
        except ConversionError as exc:
            if "canceled" in str(exc):
                self.call_from_thread(self.job_canceled, asin)
            else:
                self.call_from_thread(self.job_failed, asin, str(exc))
            return
        except Exception as exc:
            if event and event.is_set():
                self.call_from_thread(self.job_canceled, asin)
            else:
                self.call_from_thread(self.job_failed, asin, str(exc))
            return
        self.catalog.mark(asin, downloaded=True, converted=True)
        self.call_from_thread(self.job_done, asin)

    def job_done(self, asin: str) -> None:
        self._status.pop(asin, None)
        self._set_cell(asin, "●")
        book = self.catalog.get(asin)
        self.log_line(f"[green]Done[/green] {book.title if book else asin}")
        self.update_detail()
        self._after_job(asin)

    def job_failed(self, asin: str, message: str) -> None:
        self.clear_status(asin)
        last = message.splitlines()[-1] if message else "error"
        self.log_line(f"[red]Failed[/red] {asin}: {last}")
        self._after_job(asin)

    def job_canceled(self, asin: str) -> None:
        self.clear_status(asin)
        self.log_line(f"[dim]Canceled[/dim] {asin}")
        self._after_job(asin)

    # ---- sync ----
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
