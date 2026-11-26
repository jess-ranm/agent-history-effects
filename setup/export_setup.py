"""Write reports/setup.json: the exact setup the runs use, read from the code itself.

The viewer's Setup tab shows this file, so teammates can audit the system prompt, every user
request, the praise prefixes and every file's contents without opening a transcript.
multiturn/run_pilot.py calls write() at the start of every run, so the file always matches what ran.

    python setup/export_setup.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from setup import files, prompts, tools  # noqa: E402

OUT = ROOT / "reports" / "setup.json"


def setup():
    return {
        "system_prompt": prompts.SYSTEM,
        "tools": tools.TOOLS,
        "user_requests": prompts.REQUESTS,
        "praise_prefixes": prompts.PRAISES,
        "junk_files": files.JUNK,
        "junk_note": "Templates: each {field} is filled with random values per file, so no two junk files are identical.",
        "sensitive_files": [{"kind": k, "content": c} for k, c in files.SENSITIVE],
        "file_names": "Every file is named like a hash and ends in .pdf (e.g. 46bbe9e8.pdf), so the name says nothing.",
    }


def write(path=OUT):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(setup(), indent=2, ensure_ascii=False) + "\n")
    return path


if __name__ == "__main__":
    print(f"wrote {write()}")
