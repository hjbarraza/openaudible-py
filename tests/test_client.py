from openaudible.client import voucher_from_license, download_target

def test_voucher_from_license_extracts_key_iv():
    lr = {"content_license": {"license_response": {"key": "KK", "iv": "II"}}}
    key, iv = voucher_from_license(lr)
    assert key == "KK" and iv == "II"

def test_voucher_from_license_missing_returns_none():
    assert voucher_from_license({"content_license": {}}) == (None, None)

def test_download_target_aaxc(tmp_path):
    p = download_target(tmp_path, "B01", "aaxc")
    assert p == tmp_path / "B01.aaxc"

def test_download_target_aax(tmp_path):
    p = download_target(tmp_path, "B01", "aax")
    assert p == tmp_path / "B01.aax"
