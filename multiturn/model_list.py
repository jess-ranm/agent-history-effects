"""results/model_list.json: which model families and models have results, so the viewer finds new
models without anyone editing it.

    {"families": {"Qwen3": ["qwen3-0.6b", ...]},
     "arms": {"qwen3-4b": ["baseline", "praise", "harm-first"]},
     "incapable": {"qwen3-0.6b": "failed round 1 in all 3 pilot conversations"}}

run_pilot.py calls update() at the start of every run (so a model shows up as soon as it starts)
and again at the end. A model's arms are found by scanning the result folders, so the file can
also be rebuilt from scratch: python multiturn/model_list.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "results"
PATH = ROOT / "model_list.json"
ARMS = {"multiturn": "baseline", "multiturn-praise": "praise", "multiturn-harm-first": "harm-first"}


def load(path=PATH):
    try:
        return json.loads(Path(path).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"families": {}, "arms": {}}


def scan(root=ROOT):
    """{model: [arms]} for every model folder with an episodes.jsonl."""
    arms = {}
    for folder, arm in ARMS.items():
        for f in sorted((Path(root) / folder).glob("*/episodes.jsonl")):
            arms.setdefault(f.parent.name, []).append(arm)
    return arms


def mark_incapable(model, reason, root=ROOT):
    """Record that the pilot found model INCAPABLE, so the viewer can say so without a full run."""
    path = Path(root) / "model_list.json"
    m = load(path)
    m.setdefault("incapable", {})[model] = reason
    path.write_text(json.dumps(m, indent=2) + "\n")


def update(family=None, model=None, root=ROOT, path=None):
    """Record model under family (if given), refresh every model's arms, and write the file."""
    path = Path(path) if path else Path(root) / "model_list.json"
    m = load(path)
    fams = m.setdefault("families", {})
    if family and model:
        for members in fams.values():          # a model belongs to one family only
            if model in members:
                members.remove(model)
        fams.setdefault(family, []).append(model)
    m["arms"] = scan(root)
    m.setdefault("incapable", {})
    listed = {x for members in fams.values() for x in members}
    other = [x for x in m["arms"] if x not in listed]   # results with no family recorded
    if other:
        fams.setdefault("Other", []).extend(other)
    m["families"] = {f: sorted(set(v), key=_size) for f, v in fams.items() if v}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(m, indent=2) + "\n")
    return m


def _size(name):
    """Sort models by the number in their name (0.6b before 4b before 12b), then by name."""
    import re
    n = re.findall(r"(\d+(?:\.\d+)?)b", name.lower())
    return (float(n[-1]) if n else 1e9, name)


if __name__ == "__main__":
    print(json.dumps(update(), indent=2))
