from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header

from ..catalog import Catalog
from ..config import Config


class OpenAudibleApp(App):
    BINDINGS = [("q", "quit", "Quit"), ("/", "focus_search", "Search")]
    CSS = "DataTable { height: 1fr; }"

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="library")
        yield Footer()

    def on_mount(self) -> None:
        cfg = Config.load()
        table = self.query_one("#library", DataTable)
        table.add_columns("ASIN", "Title", "Author", "Done")
        for b in Catalog(cfg.db_file).all():
            table.add_row(b.asin, b.title, b.author, "●" if b.converted else "")

    def action_focus_search(self) -> None:
        pass


def main() -> None:
    OpenAudibleApp().run()


if __name__ == "__main__":
    main()
