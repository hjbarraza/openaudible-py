import subprocess
from pathlib import Path
import pytest

FIXTURES = Path(__file__).parent / "fixtures"

@pytest.fixture(scope="session")
def sample_m4a():
    FIXTURES.mkdir(exist_ok=True)
    out = FIXTURES / "sample.m4a"
    if not out.exists():
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
             "-c:a", "aac", str(out)],
            check=True, capture_output=True,
        )
    return out
