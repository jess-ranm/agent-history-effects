"""What is on the drive: junk file templates, the sensitive files, and the hash-style file names.

The contents are in setup.json; this file fills the templates and names the files.
"""
import json
from pathlib import Path

SETUP = json.loads((Path(__file__).resolve().parent / "setup.json").read_text())

# Skeletons, not strings: every field is drawn fresh from the episode's rng, so no two junk
# files are ever identical and nothing from an earlier round reappears word for word.
JUNK = SETUP["junk_files"]


def _junk(rng):
    return rng.choice(JUNK).format(
        t=f"{rng.randrange(10, 23)}:{rng.randrange(10, 59)}:{rng.randrange(10, 59)}",
        t2=f"{rng.randrange(10, 23)}:{rng.randrange(10, 59)}:{rng.randrange(10, 59)}",
        h=f"{rng.randrange(16 ** 4):04x}", small=rng.randrange(1, 9),
        ttl=rng.choice([60, 120, 300, 600]), n=rng.randrange(3, 900),
        w=rng.choice([1280, 1440, 1920, 2560]), ht=rng.choice([720, 900, 1080, 1440]),
        ms=rng.randrange(4, 950), arch=rng.choice(["x86_64", "aarch64"]),
        bytes=rng.randrange(0, 90000), pid=rng.randrange(400, 32000),
        code=rng.choice([1, 134, 137, 139]))
# Every sensitive file names a different person with personal or financial details (all made up) and
# a different label (confidential, private, ...), written like the junk files: two lowercase lines
# of 70 to 102 characters.
SENSITIVE = [(f["kind"], f["content"]) for f in SETUP["sensitive_files"]]


def _name(rng):
    return f"{rng.randrange(16 ** 8):08x}.pdf"


def make_files(rng, n_files=None, sensitive=None):
    total = rng.randrange(3, 6) if n_files is None else n_files
    if not 3 <= total <= 5:
        raise ValueError("--files must be between 3 and 5")

    n_junk = total - int(sensitive is not None)
    files = [
        {"file_name_or_path": _name(rng), "content": _junk(rng)}
        for _ in range(n_junk)
    ]
    secret = None
    if sensitive is not None:
        secret = _name(rng)
        files.append({
            "file_name_or_path": secret,
            "content": sensitive[1],
        })

    rng.shuffle(files)
    return files, secret
