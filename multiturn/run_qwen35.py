"""The main study on the Qwen3.5 family (0.8B, 2B, 4B, 9B, 27B, 35B), run locally through Ollama.

  python multiturn/run_qwen35.py                           # all six models, pilot then full run
  python multiturn/run_qwen35.py --models 0.8b 4b          # some of them
  python multiturn/run_qwen35.py --arms praise harm-first  # also the two ablation arms at k = 10
  python multiturn/run_qwen35.py --send-reasoning          # reasoning sent back within a request

This is run_gemma4.py with the family and the models swapped: the same pilot, full run, arms,
chunking, step limit of 24 and options (see that file's docstring and --help). Results go to
results/pilot/qwen3.5-<size>, results/multiturn/qwen3.5-<size> and the two arm folders, with
-reasoning added to the name under --send-reasoning.

Specific to Qwen3.5:

  sizes        Qwen3.5 has no 0.6B, 1.7B, 8B, 14B or 32B. These are the nearest sizes Ollama
               publishes; 35B is a mixture-of-experts model with about 3B parameters active.
  temperature  0.6, the Qwen3.5 entry of serve.FAMILIES.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_gemma4

run_gemma4.FAMILY = "Qwen3.5"
run_gemma4.PREFIX = "qwen3.5"
run_gemma4.MODELS = {s: f"qwen3.5:{s}" for s in ["0.8b", "2b", "4b", "9b", "27b", "35b"]}

if __name__ == "__main__":
    run_gemma4.main()
