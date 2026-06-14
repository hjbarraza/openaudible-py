from openaudible import auth

class FakeAuth:
    def __init__(self):
        self.saved_to = None
    def to_file(self, path, password=None, encryption="json"):
        self.saved_to = str(path)
        open(path, "w").write("{}")

def test_save_authenticator(tmp_path):
    fa = FakeAuth()
    auth.save(fa, tmp_path / "auth.json", password="pw")
    assert (tmp_path / "auth.json").exists()
    assert fa.saved_to.endswith("auth.json")

def test_exists(tmp_path):
    p = tmp_path / "auth.json"
    assert not auth.exists(p)
    p.write_text("{}")
    assert auth.exists(p)

def test_login_browser_passes_playwright_callback(monkeypatch):
    from audible.login import playwright_external_login_url_callback
    captured = {}
    class FakeAuthenticator:
        @classmethod
        def from_login_external(cls, locale, login_url_callback):
            captured["locale"] = locale
            captured["cb"] = login_url_callback
            return "AUTHED"
    monkeypatch.setattr(auth.audible, "Authenticator", FakeAuthenticator)
    result = auth.login_browser("uk")
    assert result == "AUTHED"
    assert captured["locale"] == "uk"
    assert captured["cb"] is playwright_external_login_url_callback

def test_begin_login_builds_url_and_state():
    url, state = auth.begin_login("us")
    assert url.startswith("https://www.amazon.com/ap/signin")
    assert "code_challenge" in url
    assert state["marketplace"] == "us"
    assert state["domain"] == "com"
    assert state["serial"]
    assert state["code_verifier"]

def test_complete_login_extracts_code(monkeypatch):
    captured = {}
    def fake_register(*, authorization_code, code_verifier, domain, serial):
        captured.update(authorization_code=authorization_code, domain=domain,
                        serial=serial)
        return {"adp_token": "x"}
    class FakeAuthenticator:
        locale = None
        def _update_attrs(self, **kw): self.attrs = kw
    monkeypatch.setattr(auth, "register", fake_register)
    monkeypatch.setattr(auth.audible, "Authenticator", FakeAuthenticator)
    monkeypatch.setattr(auth, "Locale", lambda mp: f"locale:{mp}")
    url = ("https://www.amazon.com/ap/maplanding?openid.oa2.authorization_code="
           "ANxyhamkEKUQBUXcWFrZrUby&openid.assoc_handle=amzn_audible_ios_us")
    result = auth.complete_login(url, {"marketplace": "us", "domain": "com",
                                       "serial": "S1", "code_verifier": "cv"})
    assert captured["authorization_code"] == "ANxyhamkEKUQBUXcWFrZrUby"
    assert captured["domain"] == "com" and captured["serial"] == "S1"
    assert result.attrs == {"adp_token": "x"}

def test_logout_deregisters_and_removes(tmp_path, monkeypatch):
    p = tmp_path / "auth.json"; p.write_text("{}")
    called = {}
    class Fake:
        def deregister_device(self): called["d"] = True
    monkeypatch.setattr(auth, "load", lambda f: Fake())
    auth.logout(p)
    assert called.get("d") is True
    assert not p.exists()

def test_logout_removes_even_if_deregister_fails(tmp_path, monkeypatch):
    p = tmp_path / "auth.json"; p.write_text("{}")
    def boom(f): raise RuntimeError("offline")
    monkeypatch.setattr(auth, "load", boom)
    auth.logout(p)
    assert not p.exists()
