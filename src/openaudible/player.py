from pathlib import Path


class Player:
    def __init__(self):
        import mpv
        self._mpv = mpv.MPV()

    def play(self, path: Path) -> None:
        self._mpv.play(str(path))

    def toggle_pause(self) -> None:
        self._mpv.pause = not self._mpv.pause

    def seek(self, seconds: int) -> None:
        self._mpv.seek(seconds, "relative")

    def next_chapter(self) -> None:
        self._mpv.playlist_next()

    def stop(self) -> None:
        self._mpv.play("")
