"""The main study on gpt-oss-20b, run locally through Ollama.

  python multiturn/run_gptoss.py                           # pilot, then the full run
  python multiturn/run_gptoss.py --arms praise harm-first  # also the two ablation arms at k = 10

This is run_gemma4.py with the family and the model swapped: the same pilot, full run, arms,
chunking, step limit of 24 and options (see that file's docstring and --help). Results go to
results/pilot/gpt-oss-20b, results/multiturn/gpt-oss-20b and the two arm folders.

Two things specific to gpt-oss:

  temperature  1.0, the gpt-oss entry of serve.FAMILIES.
  reasoning    Ollama returns gpt-oss's reasoning in the message's `reasoning` field.
               run_pilot saves it with each turn and does not send it back, as in the vLLM
               runs of this study. gpt-oss's own guidance is to send the reasoning back
               while a round's tool calls are still going, so this is the study's protocol
               and not the model's recommended one.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_gemma4

run_gemma4.FAMILY = "gpt-oss"
run_gemma4.PREFIX = "gpt-oss"
run_gemma4.MODELS = {"20b": "gpt-oss:20b"}

if __name__ == "__main__":
    run_gemma4.main()
