import json

import typer
from rich.console import Console
from rich.table import Table

from . import auth as auth_mod
from .catalog import Catalog
from .client import fetch_library
from .config import Config
from .jobs import process_book

app = typer.Typer(help="Sync, de-DRM, convert and play your Audible library.")
console = Console()


def _cfg() -> Config:
    return Config.load()


def _auth(cfg: Config):
    if not auth_mod.exists(cfg.auth_file):
        console.print("[red]Not logged in. Run 'openaudible login' first.[/red]")
        raise typer.Exit(1)
    return auth_mod.load(cfg.auth_file)


@app.command()
def login(
    marketplace: str = "us",
    manual: bool = typer.Option(
        False, "--manual", help="Use the copy/paste flow instead of the browser."),
    url: str = typer.Option(
        "", help="Paste the post-login URL (in quotes) to finish a --manual login."),
):
    """Audible login. By default opens a browser and captures the result for you."""
    cfg = _cfg()
    cfg.ensure_dirs()
    pending = cfg.base_dir / ".login_pending.json"

    # Finish a manual login.
    if url:
        if not pending.exists():
            console.print("[red]No pending login. Run 'openaudible login --manual' "
                          "first.[/red]")
            raise typer.Exit(1)
        state = json.loads(pending.read_text())
        authenticator = auth_mod.complete_login(url, state)
        auth_mod.save(authenticator, cfg.auth_file)
        pending.unlink(missing_ok=True)
        console.print("[green]Logged in.[/green]")
        return

    # Default: one-shot browser login.
    if not manual:
        console.print("Opening a browser to sign in to Audible…")
        try:
            authenticator = auth_mod.login_browser(marketplace)
        except ImportError:
            console.print("[yellow]Playwright not available — falling back to the "
                          "copy/paste flow.[/yellow]")
            manual = True
        else:
            auth_mod.save(authenticator, cfg.auth_file)
            console.print("[green]Logged in.[/green]")
            return

    # Manual copy/paste flow (fallback or --manual).
    oauth_url, state = auth_mod.begin_login(marketplace)
    pending.write_text(json.dumps(state))
    console.print(
        "[bold]1.[/bold] Open this URL and sign in. You'll land on a "
        "'page not found' — that's expected:\n")
    print(oauth_url)  # plain print: no wrapping/markup, copies clean
    console.print(
        "\n[bold]2.[/bold] Copy the full URL from your browser's address bar, "
        "then run (keep the quotes):\n")
    console.print(f'   openaudible login --manual --marketplace {marketplace} '
                  '--url "<PASTE_URL_HERE>"')


@app.command()
def logout():
    """Log out: deregister this device and remove stored credentials."""
    cfg = _cfg()
    if not auth_mod.exists(cfg.auth_file):
        console.print("Not logged in.")
        return
    auth_mod.logout(cfg.auth_file)
    console.print("[green]Logged out.[/green]")


@app.command()
def sync():
    """Pull your library from Audible into the local catalog."""
    cfg = _cfg()
    books = fetch_library(_auth(cfg))
    Catalog(cfg.db_file).sync(books)
    console.print(f"[green]Synced {len(books)} books.[/green]")


@app.command()
def ls(query: str = typer.Argument("")):
    """List (or search) the local catalog."""
    cfg = _cfg()
    cat = Catalog(cfg.db_file)
    books = cat.search(query) if query else cat.all()
    table = Table("ASIN", "Title", "Author", "✓", "Read")
    for b in books:
        table.add_row(b.asin, b.title, b.author,
                      "●" if b.converted else "", b.read_status or "")
    console.print(table)


@app.command()
def info(asin: str):
    """Show details for one book."""
    cfg = _cfg()
    b = Catalog(cfg.db_file).get(asin)
    if not b:
        console.print("[red]Not found.[/red]"); raise typer.Exit(1)
    console.print(b)


@app.command()
def get(asin: str, force: bool = False):
    """Download + de-DRM + convert one book."""
    cfg = _cfg()
    cat = Catalog(cfg.db_file)
    b = cat.get(asin)
    if not b:
        console.print("[red]Not in catalog. Run sync.[/red]"); raise typer.Exit(1)
    out = process_book(auth=_auth(cfg), cfg=cfg, book=b, force=force,
                       on_progress=lambda s: console.print(s, end="\r"))
    cat.mark(asin, downloaded=True, converted=True)
    console.print(f"\n[green]Done:[/green] {out}")


@app.command()
def status():
    """Show catalog counts."""
    cfg = _cfg()
    books = Catalog(cfg.db_file).all()
    done = sum(1 for b in books if b.converted)
    finished = sum(1 for b in books if b.read_status == "finished")
    console.print(f"Library: {len(books)} books, {done} converted, "
                  f"{finished} finished.")


@app.command()
def play(asin: str):
    """Play a converted book in your default OS player."""
    import subprocess, sys
    from .jobs import book_file
    cfg = _cfg()
    b = Catalog(cfg.db_file).get(asin)
    if not b:
        console.print("[red]Not found.[/red]"); raise typer.Exit(1)
    path = book_file(cfg, b)
    if not path.exists():
        console.print("[red]Not converted yet. Run 'get' first.[/red]"); raise typer.Exit(1)
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.run([opener, str(path)])


@app.command(name="import")
def import_books(path: str, no_copy: bool = typer.Option(
        False, "--no-copy", help="Reference files in place instead of copying.")):
    """Import local audiobooks (file or directory) into the catalog."""
    from .importer import import_path
    cfg = _cfg()
    added = import_path(cfg, path, copy=not no_copy)
    for b in added:
        console.print(f"[green]+[/green] {b.author} — {b.title}")
    console.print(f"[green]Imported {len(added)} book(s).[/green]")


@app.command()
def export(out: str):
    """Export the catalog to a .csv or .json file."""
    from .exporter import export_catalog
    cfg = _cfg()
    written = export_catalog(Catalog(cfg.db_file).all(), out)
    console.print(f"[green]Wrote[/green] {written}")


@app.command()
def read(asin: str, status: str):
    """Set read status: unread | reading | finished | dnf (or any string)."""
    cfg = _cfg()
    cat = Catalog(cfg.db_file)
    if not cat.get(asin):
        console.print("[red]Not found.[/red]"); raise typer.Exit(1)
    cat.set_read_status(asin, status)
    console.print(f"[green]{asin}[/green] → {status}")


@app.command()
def annotations(asin: str):
    """Show your bookmarks / notes for a book."""
    from .client import get_annotations
    cfg = _cfg()
    data = get_annotations(_auth(cfg), asin)
    console.print(data)


if __name__ == "__main__":
    app()
