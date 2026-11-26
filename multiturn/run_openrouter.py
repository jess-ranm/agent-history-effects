"""The main study and its two ablation arms on gpt-oss-120b, through OpenRouter's Batch API.

  export OPENROUTER_API_KEY=...                       # read from the environment, never stored
  python multiturn/run_openrouter.py                  # pilot, then full run and both arms
  python multiturn/run_openrouter.py --arms           # pilot and full run only
  python multiturn/run_openrouter.py --sync           # the same runs on the normal (sync) API

The experiments are run_gemma4.py's, with the same pilot rules:

  1. Pilot: 5 treatment conversations (k = 10) into results/pilot/gpt-oss-120b/. INCAPABLE
     (fails request 1 in all 5) or a broken pilot stops here; 3 or 4 of 5 is marked borderline.
  2. Full run: 20 baseline (k = 0) and 20 treatment (k = 10) conversations into
     results/multiturn/gpt-oss-120b/.
  3. Arms: praise and harm-first, 20 conversations each at k = 10, into
     results/multiturn-praise/ and results/multiturn-harm-first/.

Nothing in run_pilot.py is edited. Its episode loop runs as it is, one thread per conversation;
only its chat() is replaced.

How a multi-turn experiment runs on a batch API. A batch is a set of independent requests
answered together some time later, and here every model turn depends on the tool results of the
turn before, so one conversation cannot be one batch. Instead the conversations advance in
waves: each conversation that is waiting for the model puts its next request in a shared queue
and blocks; when all of them are waiting, the queue goes out as one batch (one request per
live conversation); when the batch is back, every conversation runs its tool calls and queues
its next turn. Steps 2 and 3 run side by side and share the waves, so a wave carries up to 80
requests.

What that costs in time. A k = 10 conversation is about 11 requests x up to 24 turns, so a
stage needs on the order of 100-250 waves. OpenRouter says most batches finish in minutes and
all within 24 hours. At 2 minutes a wave the whole study is roughly a day; if waves take much
longer it is not practical, and --sync does the same runs in well under an hour at about twice
the token price (the whole study is a few dollars either way). Start with --pilot-only to see
how long a wave takes.

Surviving a restart. Every answer is appended to a turn cache (--cache-dir, outside the repo)
as soon as it arrives. Conversations are deterministic given the model's answers (files and
requests come from the seed), so after a crash or Ctrl-C a rerun replays each unfinished
conversation from the cache in seconds and goes back to the API where it stopped. A batch that
was in flight when the script died is submitted again. Finished conversations are skipped by
run_pilot as always. The cache is keyed per stage and conversation, so two conversations never
share an answer.

Settings, and how they compare with the other runs:

  provider     Batch: DeepInfra, bf16 (full precision), the only provider of this model's
               batch variant. Sync: DeepInfra, Crusoe or Cerebras, the three that serve
               full-precision weights (bf16 or fp16); pinned to DeepInfra alone, 2 of the first
               5 conversations died on its rate limit. Change with --provider (sync only).
  temperature  1.0, the gpt-oss entry of serve.FAMILIES.
  step limit   24 model turns per request, as in run_gptoss.py (gpt-oss makes one tool call
               per turn); the vLLM runs use 12.
  reasoning    saved with each turn and not sent back, which is what run_pilot does. Under
               that protocol the model failed its pilot (4 of 5 conversations ran out of
               turns). --send-reasoning resends it within a request's tool loop, into
               separate gpt-oss-120b-reasoning folders.

Everything in a request is the experiment's synthetic text; no local file contents are sent.
"""
import argparse
import hashlib
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import model_list
import review
import run_pilot
import serve
from run_gemma4 import fails_round_1, pilot_problems, rows_of

API = "https://openrouter.ai/api/v1"
FAMILY, NAME, SLUG = "gpt-oss", "gpt-oss-120b", "openai/gpt-oss-120b"
ARMS = {"praise": ("results/multiturn-praise", "--praise"),
        "harm-first": ("results/multiturn-harm-first", "--harm-first")}
FINAL = {"completed", "failed", "expired", "cancelled"}
TL = threading.local()               # .argv for a stage's run_pilot.main(); .tag for a conversation
A = None                             # the parsed options
SUFFIX = ""                          # "-reasoning" with --send-reasoning


def http(method, path, body=None, timeout=300, tries=6):
    """One OpenRouter call, retried on rate limits, server errors and dropped connections."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        sys.exit("set OPENROUTER_API_KEY in the environment first (export OPENROUTER_API_KEY=...)")
    data = None if body is None else json.dumps(body).encode()
    for attempt in range(tries):
        req = urllib.request.Request(API + path, data=data, method=method,
                                     headers={"authorization": f"Bearer {key}",
                                              "content-type": "application/json",
                                              "x-title": "rule-erosion"})
        try:
            return json.loads(urllib.request.urlopen(req, timeout=timeout).read() or b"{}")
        except urllib.error.HTTPError as e:
            text = e.read().decode(errors="replace")[:300]
            if e.code not in (408, 409, 429) and e.code < 500:
                raise RuntimeError(f"HTTP {e.code} on {method} {path}: {text}") from None
            err = f"HTTP {e.code}: {text}"
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            err = str(e)
        if attempt == tries - 1:
            raise RuntimeError(f"{method} {path} failed after {tries} tries: {err}")
        time.sleep(min(120, 5 * 2 ** attempt))


def choice_of(body):
    """(message, finish_reason) from a chat-completions response body, or raise."""
    if not body.get("choices"):
        raise RuntimeError(f"no choices in the response: {json.dumps(body)[:300]}")
    c = body["choices"][0]
    return c["message"], c.get("finish_reason")


class Cache:
    """Answers already received, on disk: {key: [message, finish_reason]}, one json line each."""

    def __init__(self, path):
        self.path, self.lock, self.d = Path(path), threading.Lock(), {}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if line.strip():
                    k, v = json.loads(line)
                    self.d[k] = v

    def get(self, k):
        return self.d.get(k)

    def put(self, k, v):
        with self.lock:
            self.d[k] = v
            with open(self.path, "a") as fh:
                fh.write(json.dumps([k, v], ensure_ascii=False) + "\n")


class Batcher:
    """Collects the next turn of every waiting conversation and sends them as one batch."""

    def __init__(self):
        self.cv, self.pending, self.last = threading.Condition(), [], 0.0
        self.waves, self.cost, self.requests = 0, 0.0, 0
        threading.Thread(target=self.loop, daemon=True).start()

    def ask(self, body):
        """Called by a conversation's thread: queue body and block until its answer is back."""
        job = dict(body=body, done=threading.Event(), out=None, err=None, tries=0)
        with self.cv:
            self.pending.append(job)
            self.last = time.time()
            self.cv.notify()
        job["done"].wait()
        if job["err"]:
            raise RuntimeError(job["err"])
        return job["out"]

    def loop(self):
        while True:
            with self.cv:
                # a wave goes out once nothing new has been queued for --gather seconds: tool
                # calls are instant, so by then every live conversation is waiting
                while not self.pending or time.time() - self.last < A.gather:
                    self.cv.wait(timeout=1)
                wave, self.pending = self.pending[:A.max_batch], self.pending[A.max_batch:]
            try:
                self.run(wave)
            except Exception as e:                      # the whole batch was lost
                self.retry(wave, f"batch failed: {e}")

    def retry(self, jobs, why):
        again = []
        for j in jobs:
            j["tries"] += 1
            if j["tries"] >= A.retries:
                j["err"] = why
                j["done"].set()
            else:
                again.append(j)
        if again:
            with self.cv:
                self.pending = again + self.pending
                self.last = time.time() - A.gather      # no need to wait for stragglers again
                self.cv.notify()

    def run(self, wave):
        t0 = time.time()
        # endpoint and model have to come before requests: the body is read as a stream
        batch = http("POST", "/batches", {
            "endpoint": "/v1/chat/completions", "model": SLUG,
            "requests": [{"custom_id": f"r{i}", "body": j["body"]} for i, j in enumerate(wave)]})
        bid = batch["id"]
        while not (batch.get("status") in FINAL
                   and (batch["status"] != "completed" or batch.get("results") is not None)):
            time.sleep(A.poll)
            batch = http("GET", f"/batches/{bid}")
        if batch["status"] != "completed":
            raise RuntimeError(f"{bid} ended {batch['status']}: {(batch.get('error') or {}).get('message')}")
        got = {r["custom_id"]: r for r in batch["results"]}
        bad = []
        for i, j in enumerate(wave):
            r = got.get(f"r{i}") or {}
            resp = r.get("response") or {}
            try:
                if r.get("error") or resp.get("status_code") != 200:
                    raise RuntimeError(json.dumps(r.get("error") or resp)[:300])
                j["out"] = choice_of(resp["body"])
                j["done"].set()
            except Exception as e:
                j["why"] = str(e)
                bad.append(j)
        self.waves += 1
        self.requests += len(wave)
        self.cost += (batch.get("usage") or {}).get("cost") or 0
        print(f"wave {self.waves}: {len(wave)} requests, {len(bad)} failed, {time.time() - t0:.0f} s "
              f"({batch.get('provider')}, ${self.cost:.2f} so far)", flush=True)
        for j in bad:
            self.retry([j], f"request failed {A.retries} times: {j['why']}")


def chat(base, model, messages, tools, temperature, max_tokens, timeout=180):
    """run_pilot.chat on OpenRouter: (the assistant message, why generation stopped)."""
    # reasoning is saved, not resent. --send-reasoning resends it for the turns of the request
    # being worked on (everything after the last user message), which is how gpt-oss is meant
    # to be called: it sees its own reasoning between a request's tool calls, never older ones.
    live = max(i for i, m in enumerate(messages) if m["role"] == "user") if A.send_reasoning else len(messages)
    sent = [{k: v for k, v in m.items() if k != "reasoning" or i > live} for i, m in enumerate(messages)]
    body = {"model": SLUG, "messages": sent, "tools": tools,
            "temperature": temperature, "max_tokens": max_tokens}
    key = hashlib.sha256((TL.tag + json.dumps(body, sort_keys=True)).encode()).hexdigest()
    hit = CACHE.get(key)
    if hit:
        return hit[0], hit[1]
    if A.sync:
        out = choice_of(http("POST", "/chat/completions",
                             dict(body, provider={"only": A.provider, "allow_fallbacks": True}), tries=10))
    else:
        out = BATCHER.ask(body)
    CACHE.put(key, list(out))
    return out


class Pool(ThreadPoolExecutor):
    """run_pilot's thread pool, with each conversation's thread told which conversation it is.

    The tag (stage, k, seed) goes into the cache key: harm-first and baseline conversations of
    one seed open with the same request, and must not be handed the same cached answer."""

    def submit(self, fn, *args, **kw):
        tag = f"{TL.stage}|{args[2]}:{args[3]}|"         # episode(base, model, rounds, seed, ...)

        def tagged():
            TL.tag = tag
            return fn(*args, **kw)
        return super().submit(tagged)


class Parser(argparse.ArgumentParser):
    """run_pilot.main() reads sys.argv; stages run side by side, so each thread brings its own."""

    def parse_args(self, args=None, namespace=None):
        return super().parse_args(TL.argv, namespace)


class _Argparse:                       # what run_pilot sees as `argparse`
    ArgumentParser = Parser
    RawDescriptionHelpFormatter = argparse.RawDescriptionHelpFormatter


def stage(label, rounds, episodes, out, extra=()):
    """One run_pilot.main() call: resumes by itself and prints its tally when done."""
    TL.stage = label + SUFFIX
    TL.argv = ["--model", NAME + SUFFIX, "--family", FAMILY, "--base-url", API,
               "--rounds", *map(str, rounds), "--episodes", str(episodes),
               "--temperature", str(A.temperature), "--max-tokens", str(A.max_tokens),
               "--max-steps", str(A.max_steps), "--out", str(out), *extra,
               # batch: every conversation at once, so a wave holds one request from each
               "--workers", str(A.workers if A.sync else max(1, len(rounds) * episodes))]
    run_pilot.main()


def main():
    global A, CACHE, BATCHER, SUFFIX
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sync", action="store_true", help="use the normal API instead of batches: fast, about twice the price")
    ap.add_argument("--episodes", type=int, default=20, help="conversations per condition")
    ap.add_argument("--treatment", type=int, default=10, help="k of the treatment; the baseline is always k = 0")
    ap.add_argument("--pilot-episodes", type=int, default=5)
    ap.add_argument("--skip-pilot", action="store_true")
    ap.add_argument("--pilot-only", action="store_true", help="stop after the pilot (a cheap way to time the waves)")
    ap.add_argument("--arms", nargs="*", default=list(ARMS), choices=list(ARMS),
                    help="ablation arms to run next to the full run; --arms alone runs none")
    ap.add_argument("--send-reasoning", action="store_true",
                    help="resend the model's reasoning within a request's tool loop (not the study's "
                         "protocol); results go to folders named gpt-oss-120b-reasoning")
    ap.add_argument("--temperature", type=float, default=serve.FAMILIES[FAMILY]["temperature"])
    ap.add_argument("--max-tokens", type=int, default=6000)
    ap.add_argument("--max-steps", type=int, default=24)
    ap.add_argument("--poll", type=int, default=30, help="batch: seconds between status checks")
    ap.add_argument("--gather", type=float, default=5, help="batch: quiet seconds before a wave is sent")
    ap.add_argument("--max-batch", type=int, default=500, help="batch: requests per batch")
    ap.add_argument("--retries", type=int, default=3, help="batch: times a request or batch is tried")
    ap.add_argument("--workers", type=int, default=8, help="sync: conversations in flight")
    ap.add_argument("--provider", nargs="+", default=["deepinfra", "crusoe", "cerebras"],
                    help="sync: the providers a request may go to, all serving full-precision weights")
    ap.add_argument("--cache-dir", default=str(Path.home() / ".cache" / "agent-history-effects" / "openrouter"))
    A = ap.parse_args()

    SUFFIX = "-reasoning" if A.send_reasoning else ""
    FOLDER = NAME + SUFFIX                             # results folders, and the name in the viewer's model list
    os.chdir(ROOT)                                     # results/ paths are relative to the repo root
    if not os.environ.get("OPENROUTER_API_KEY"):
        sys.exit("set OPENROUTER_API_KEY in the environment first (export OPENROUTER_API_KEY=...)")
    CACHE = Cache(Path(A.cache_dir) / f"{NAME}.jsonl")
    BATCHER = None if A.sync else Batcher()
    run_pilot.chat = chat                              # play_round looks chat up at call time
    run_pilot.ThreadPoolExecutor = Pool
    run_pilot.argparse = _Argparse
    print(f"{NAME} on OpenRouter, {'sync API' if A.sync else 'Batch API'}; "
          f"{len(CACHE.d)} cached turns in {CACHE.path}", flush=True)

    pilot = f"results/pilot/{FOLDER}"
    if not A.skip_pilot:
        stage("pilot", [A.treatment], A.pilot_episodes, pilot)
        rows = rows_of(pilot)
        failed = sum(fails_round_1(r) for r in rows)
        if len(rows) == A.pilot_episodes and failed == len(rows):
            model_list.mark_incapable(NAME, f"failed round 1 in all {len(rows)} pilot conversations")
            sys.exit(f"{NAME}: INCAPABLE, failed round 1 in all {len(rows)} pilot conversations; no full run")
        if failed >= 3:
            model_list.mark_borderline(NAME, f"failed round 1 in {failed} of {len(rows)} pilot conversations")
            print(f"{NAME}: borderline, failed round 1 in {failed} of {len(rows)} pilot conversations; running in full")
        problems = pilot_problems(rows, A.pilot_episodes)
        if problems:
            sys.exit(f"{NAME}: pilot failed, skipping the full run:\n- " + "\n- ".join(problems))
    if A.pilot_only:
        return

    stages = [("full", [0, A.treatment], f"results/multiturn/{FOLDER}", ())]
    stages += [(arm, [A.treatment], f"{ARMS[arm][0]}/{FOLDER}", (ARMS[arm][1],)) for arm in A.arms]
    threads = []
    for label, rounds, out, extra in stages:           # side by side, so they share the waves
        t = threading.Thread(target=stage, args=(label, rounds, A.episodes, out, extra))
        t.start()
        threads.append(t)
        time.sleep(2)                                  # each rewrites model_list.json as it starts
    for t in threads:
        t.join()

    model_list.update(FAMILY, NAME + SUFFIX)
    for label, _, out, _ in stages:                    # the tallies again, one at a time
        print(f"\n===== {NAME} / {label} =====")
        review.review_summary(out)
    if BATCHER:
        print(f"\n{BATCHER.waves} waves, {BATCHER.requests} requests, ${BATCHER.cost:.2f}")


if __name__ == "__main__":
    main()
