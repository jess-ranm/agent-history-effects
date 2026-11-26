"""Start a local vLLM server for the multiturn pilot and wait until it answers.

Used by the Colab notebook:

    import serve
    proc, log = serve.start_server("Qwen/Qwen3-1.7B", "qwen3-1.7b", 0, 8000, 32768, 0.95, "results", family="Qwen3")
    serve.wait_for_server(proc, 8000, log)
"""
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


# Per-family vLLM settings: how the model writes tool calls and thinking, which dtype it needs,
# and the sampling temperature its authors recommend (passed to multiturn/run.py --temperature).
# reasoning=None leaves the thinking inside the message text as <think>...</think> (Qwen3, as in
# the pilot); with a reasoning parser vLLM returns it separately and multiturn/run.py saves it per turn.
FAMILIES = {
    "Qwen3":   dict(tool_parser="hermes",       reasoning=None,            dtype="half",     temperature=0.6),
    "Qwen3.5": dict(tool_parser="qwen3_coder",  reasoning="qwen3",         dtype="bfloat16", temperature=0.6),
    "Gemma 4": dict(tool_parser="gemma4",       reasoning="gemma4",        dtype="bfloat16", temperature=1.0),
    "gpt-oss": dict(tool_parser="openai",       reasoning="openai_gptoss", dtype="auto",     temperature=1.0),
}


def start_server(hf_id, name, gpu=0, port=8000, max_len=32768, gpu_mem=0.95, log_dir=".", family="Qwen3"):
    """Launch a vLLM OpenAI-compatible server for one model on one GPU; returns (process, log path).

    family picks the tool-call parser, reasoning parser and dtype from FAMILIES."""
    if family not in FAMILIES:
        sys.exit(f"unknown family {family!r}; add it to FAMILIES in serve.py (known: {', '.join(FAMILIES)})")
    cfg = FAMILIES[family]
    log = Path(log_dir) / f"vllm_gpu{gpu}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "vllm.entrypoints.openai.api_server",
           "--model", hf_id, "--served-model-name", name,
           "--dtype", cfg["dtype"],                 # half works on T4; bfloat16 needs an L4 or A100
           "--max-model-len", str(max_len),
           "--gpu-memory-utilization", str(gpu_mem),
           "--enable-auto-tool-choice", "--tool-call-parser", cfg["tool_parser"],
           "--enable-prefix-caching",               # rounds share a long prefix
           "--port", str(port)]
    if cfg["reasoning"]:
        cmd += ["--reasoning-parser", cfg["reasoning"]]
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(gpu))
    proc = subprocess.Popen(cmd, env=env, stdout=open(log, "w"),
                            stderr=subprocess.STDOUT, start_new_session=True)
    return proc, log


def wait_for_server(proc, port=8000, log=None, minutes=20):
    """Block until the server answers, printing its latest log line every 30 s so the wait is visible."""
    t0 = time.time()
    for n in range(minutes * 12):
        if proc.poll() is not None:
            tail = "".join(log.read_text(errors="replace").splitlines(True)[-15:]) if log else ""
            sys.exit(f"the model server on port {port} stopped while loading; last log lines:\n{tail}")
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=3)
            print(f"server on port {port} is up after {time.time() - t0:.0f} s")
            return
        except Exception:
            pass
        if n % 6 == 0 and log is not None and Path(log).exists():
            lines = [l.strip() for l in Path(log).read_text(errors="replace").replace("\r", "\n").splitlines()
                     if l.strip()]
            last = lines[-1][:160] if lines else "(no output yet: starting up)"
            print(f"[{time.time() - t0:.0f} s] port {port}: {last}", flush=True)
        time.sleep(5)
    sys.exit(f"the model server on port {port} did not come up in {minutes} min; see {log}")
