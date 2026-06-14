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
