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
