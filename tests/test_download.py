from openaudible.download import download_file

class FakeResp:
    def __init__(self, chunks, status=200, headers=None):
        self._chunks = chunks
        self.status_code = status
        self.headers = headers or {}
    def iter_bytes(self):
        yield from self._chunks
    def raise_for_status(self):
        pass
    def __enter__(self): return self
    def __exit__(self, *a): pass

class FakeClient:
    def __init__(self, resp):
        self._resp = resp
    def stream(self, method, url, headers=None):
        return self._resp
    def __enter__(self): return self
    def __exit__(self, *a): pass

def test_download_writes_file(tmp_path, monkeypatch):
    import openaudible.download as d
    monkeypatch.setattr(d, "_make_client", lambda: FakeClient(FakeResp([b"abc", b"def"])))
    out = tmp_path / "x.aaxc"
    download_file("http://x", out)
    assert out.read_bytes() == b"abcdef"

def test_download_skips_if_complete(tmp_path, monkeypatch):
    import openaudible.download as d
    out = tmp_path / "x.aaxc"
    out.write_bytes(b"done")
    called = {"n": 0}
    def boom():
        called["n"] += 1
        return FakeClient(FakeResp([b"x"]))
    monkeypatch.setattr(d, "_make_client", boom)
    download_file("http://x", out, expected_size=4)
    assert called["n"] == 0
    assert out.read_bytes() == b"done"
