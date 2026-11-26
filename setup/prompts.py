"""What the model is told: the system prompt, the user requests and the praise prefixes.

The text itself is in setup.json, the one place the setup is kept; the viewer reads the same file.
"""
import json
from pathlib import Path

SETUP = json.loads((Path(__file__).resolve().parent / "setup.json").read_text())

SYSTEM = SETUP["system_prompt"]
# One per request, shuffled per conversation. Twelve, so a k = 10 conversation (11 requests) never
# repeats one. Each uses a different umbrella phrase that covers every kind of junk file without
# naming specific kinds.
REQUESTS = SETUP["user_requests"]
PRAISES = SETUP["praise_prefixes"]   # one is prefixed to every request after the first when --praise is set
