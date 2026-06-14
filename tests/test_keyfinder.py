from openaudible.keyfinder import parse_checksum, parse_rcrack_key

def test_parse_checksum_from_ffmpeg_stderr():
    stderr = "Input #0\n[aax] file checksum == 1a2b3c4d5e\nDuration: ...\n"
    assert parse_checksum(stderr) == "1a2b3c4d5e"

def test_parse_rcrack_key():
    out = "statistics\nplaintext of 1a2b... is hex:deadbeef\n"
    assert parse_rcrack_key(out) == "deadbeef"
