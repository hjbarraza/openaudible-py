import sys, types
from pathlib import Path

def _install_fake_mpv(monkeypatch):
    mod = types.ModuleType("mpv")
    class MPV:
        def __init__(self, *a, **k): self.calls = []; self.pause = False
        def play(self, path): self.calls.append(("play", path))
        def seek(self, secs, ref="relative"): self.calls.append(("seek", secs, ref))
        def playlist_next(self): self.calls.append(("next",))
    mod.MPV = MPV
    monkeypatch.setitem(sys.modules, "mpv", mod)

def test_play_invokes_mpv(monkeypatch, tmp_path):
    _install_fake_mpv(monkeypatch)
    from openaudible.player import Player
    f = tmp_path / "a.m4b"; f.write_bytes(b"x")
    p = Player()
    p.play(f)
    assert ("play", str(f)) in p._mpv.calls

def test_toggle_pause(monkeypatch, tmp_path):
    _install_fake_mpv(monkeypatch)
    from openaudible.player import Player
    p = Player()
    p.toggle_pause()
    assert p._mpv.pause is True
