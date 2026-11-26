"""The three tools the model can call. The schemas are in setup.json."""
import json
from pathlib import Path

SETUP = json.loads((Path(__file__).resolve().parent / "setup.json").read_text())

TOOLS = SETUP["tools"]
