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
def login(marketplace: str = "us"):
    """Interactive Audible login."""
    cfg = _cfg()
    authenticator = auth_mod.login_external(marketplace)
    auth_mod.save(authenticator, cfg.auth_file)
    console.print("[green]Logged in.[/green]")


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
    table = Table("ASIN", "Title", "Author", "✓")
    for b in books:
        table.add_row(b.asin, b.title, b.author, "●" if b.converted else "")
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
    console.print(f"Library: {len(books)} books, {done} converted.")


@app.command()
def play(asin: str):
    """Play a converted book in your default OS player."""
    import subprocess, sys
    from .jobs import output_path
    cfg = _cfg()
    b = Catalog(cfg.db_file).get(asin)
    if not b:
        console.print("[red]Not found.[/red]"); raise typer.Exit(1)
    path = output_path(cfg, b)
    if not path.exists():
        console.print("[red]Not converted yet. Run 'get' first.[/red]"); raise typer.Exit(1)
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.run([opener, str(path)])


if __name__ == "__main__":
    app()
