import sys, types

def _install_fake_mpv(monkeypatch):
    mod = types.ModuleType("mpv")
    class MPV:
        def __init__(self, *a, **k):
            self.calls = []; self.pause = False; self.speed = 1.0
        def play(self, path): self.calls.append(("play", path))
        def seek(self, secs, ref="relative"): self.calls.append(("seek", secs, ref))
        def playlist_next(self): self.calls.append(("next",))
        def command(self, *a): self.calls.append(("command", *a))
    mod.MPV = MPV
    monkeypatch.setitem(sys.modules, "mpv", mod)

def test_play_invokes_mpv(monkeypatch, tmp_path):
    _install_fake_mpv(monkeypatch)
    from openaudible.player import Player
    f = tmp_path / "a.m4b"; f.write_bytes(b"x")
    p = Player()
    p.play(f)
    assert ("play", str(f)) in p._mpv.calls
    assert p.playing is True

def test_toggle_pause(monkeypatch, tmp_path):
    _install_fake_mpv(monkeypatch)
    from openaudible.player import Player
    p = Player()
    p.toggle_pause()
    assert p._mpv.pause is True and p.paused is True

def test_change_speed_clamps(monkeypatch):
    _install_fake_mpv(monkeypatch)
    from openaudible.player import Player
    p = Player()
    assert p.change_speed(0.5) == 1.5
    assert p.change_speed(5.0) == 3.0   # clamped to max
    assert p.change_speed(-10.0) == 0.5  # clamped to min

def test_chapter_uses_mpv_command(monkeypatch):
    _install_fake_mpv(monkeypatch)
    from openaudible.player import Player
    p = Player()
    p.next_chapter(); p.prev_chapter()
    assert ("command", "add", "chapter", 1) in p._mpv.calls
    assert ("command", "add", "chapter", -1) in p._mpv.calls
