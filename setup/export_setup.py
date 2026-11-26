"""Write reports/setup.json for the viewer's Setup tab, from the code in setup/.

setup/ is the source of truth. The JSON is not kept in git: the Pages workflow
(.github/workflows/pages.yml) runs this on every publish, so the site always matches the code.
Run it yourself only to view the page locally:

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
