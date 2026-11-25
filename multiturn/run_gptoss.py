"""The same experiment on gpt-oss, served by Ollama instead of vLLM.

  OLLAMA_CONTEXT_LENGTH=32768 OLLAMA_NUM_PARALLEL=4 ollama serve
  ollama pull gpt-oss:20b
  python multiturn/run_gptoss.py --rounds 0 1 2 3 4 5 --episodes 10 --workers 4 \
      --out results/multiturn/gpt-oss-20b

Everything but the transport is run_pilot's: the system prompt, the requests, the environment,
the episode loop and the tally. Nothing in run_pilot.py is edited; this file swaps its chat()
for one that speaks gpt-oss's format, then calls its main().

The one difference that matters. Qwen3 puts its reasoning in the message content, inside
<think>...</think>, and the checker, the viewer and the stored rows all read it from there.
gpt-oss returns the reasoning in a separate field next to the content. So:

  coming back  : the reasoning field is folded into the content as <think>...</think>, which
                 gives stored transcripts the same shape as the Qwen ones.
  going out    : that block is taken out of the content again and sent as the message's
                 `reasoning` field, so the model never sees <think> tags in its own history.
                 --drop-reasoning sends earlier turns with no reasoning at all.

Defaults differ from run_pilot in four places, all overridable: --model gpt-oss:20b,
--base-url on Ollama's port (11434), --workers 4 (a Mac serves fewer parallel requests than a
GPU; match OLLAMA_NUM_PARALLEL), and --max-steps 24. gpt-oss makes one tool call per turn, so
a 5-file round is list + 5 reads + 5 deletes + the answer = 12 turns, exactly run_pilot's
limit of 12; one leftover file or one retry would be recorded as an unfinished run.

--kinds unlisted puts a file the rule does not name in the final round instead of one of its
five examples (see env_unlisted.py); --kinds both draws from all ten. The file is still chosen
by seed, so 10 seeds give each kind twice (once with both). Use a separate --out.

The final message of an episode usually carries no reasoning, so a row's `think` field is often
empty; the reasoning is in the earlier assistant turns under `messages`.
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_pilot

REASONING_KEYS = ("reasoning", "reasoning_content", "thinking")   # Ollama, vLLM/LM Studio, older Ollama
SEND_REASONING = True
REASONING_EFFORT = None            # None = the server's default (medium for gpt-oss)


def fold(msg):
    """The server's message with its reasoning moved into the content as a <think> block."""
    reasoning = next((msg[k] for k in REASONING_KEYS if msg.get(k)), None)
    out = {k: v for k, v in msg.items() if k not in REASONING_KEYS}
    if reasoning:
        out["content"] = f"<think>{reasoning.strip()}</think>\n\n{msg.get('content') or ''}".rstrip()
    return out


def unfold(msg):
    """The reverse, for sending: no <think> in the content, the reasoning in its own field."""
    if msg.get("role") != "assistant":
        return msg
    content = msg.get("content") or ""
    m = run_pilot.THINK.search(content)
    if not m:
        return msg
    out = dict(msg, content=run_pilot.visible_answer(content))
    if SEND_REASONING:
        out["reasoning"] = m.group(1).strip()
    return out


def chat(base, model, messages, tools, temperature, max_tokens, timeout=900):
    """run_pilot.chat for gpt-oss: (the assistant message in Qwen's shape, why generation stopped)."""
    body = {"model": model, "messages": [unfold(m) for m in messages], "tools": tools,
            "temperature": temperature, "max_tokens": max_tokens}
    if REASONING_EFFORT:
        body["reasoning_effort"] = REASONING_EFFORT
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json",
                                          "authorization": "Bearer none"})
    try:
        raw = urllib.request.urlopen(req, timeout=timeout).read()
    except urllib.error.HTTPError as e:      # the body says what the server objected to
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}") from None
    choice = json.loads(raw)["choices"][0]
    return fold(choice["message"]), choice.get("finish_reason")


def main():
    global SEND_REASONING, REASONING_EFFORT
    argv = sys.argv[1:]
    if "--drop-reasoning" in argv:
        argv.remove("--drop-reasoning")
        SEND_REASONING = False
    if "--reasoning-effort" in argv:
        i = argv.index("--reasoning-effort")
        REASONING_EFFORT = argv[i + 1]
        del argv[i:i + 2]
    if "--kinds" in argv:
        i = argv.index("--kinds")
        from env_unlisted import pool
        run_pilot.SENSITIVE = pool(argv[i + 1])   # episode() picks SENSITIVE[seed % len(SENSITIVE)]
        del argv[i:i + 2]
    for flag, default in (("--model", "gpt-oss:20b"),
                          ("--base-url", "http://127.0.0.1:11434/v1"),
                          ("--workers", "4"),
                          ("--max-steps", "24")):
        if flag not in argv:
            argv += [flag, default]
    sys.argv = [sys.argv[0]] + argv
    run_pilot.chat = chat                    # play_round looks chat up at call time
    run_pilot.main()


if __name__ == "__main__":
    main()
