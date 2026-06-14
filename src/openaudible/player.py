from pathlib import Path


class Player:
    """Headless audio playback via libmpv (no video window)."""

    def __init__(self):
        import mpv
        self._mpv = mpv.MPV(vid="no")
        self._path = None

    def play(self, path: Path) -> None:
        self._path = str(path)
        self._mpv.play(self._path)
        self._mpv.pause = False

    @property
    def playing(self) -> bool:
        return self._path is not None

    def toggle_pause(self) -> None:
        self._mpv.pause = not self._mpv.pause

    @property
    def paused(self) -> bool:
        return bool(self._mpv.pause)

    def seek(self, seconds: int) -> None:
        self._mpv.seek(seconds, "relative")

    def next_chapter(self) -> None:
        try:
            self._mpv.command("add", "chapter", 1)
        except Exception:
            pass

    def prev_chapter(self) -> None:
        try:
            self._mpv.command("add", "chapter", -1)
        except Exception:
            pass

    def change_speed(self, delta: float) -> float:
        speed = max(0.5, min(3.0, round(float(self._mpv.speed) + delta, 2)))
        self._mpv.speed = speed
        return speed

    def stop(self) -> None:
        self._mpv.play("")
        self._path = None
