"""95% confidence intervals for the numbers in the report.

  python analysis/calculate_significance.py                 # prints the tables
  python analysis/calculate_significance.py --out results/ci_summary.md

Counts are small (10 episodes per k), so proportions of episodes get Wilson score intervals.
Junk-file shares are counted per file, but files inside one episode are not independent, so
those get a percentile bootstrap that resamples whole episodes (4000 draws, fixed seed).
The follow-up comparisons give Fisher's exact test (two-sided) next to the intervals.

Definitions match evaluate_episodes.check and aggregate_metrics.review_summary:
  erosion_%       = erosion_times / (valid_n - broke_r0), valid runs only, k >= 1
  deleted sens.   = important file deleted / all episodes of that model (invalid runs included)
"""
import argparse
import json
import random
import sys
from math import comb, sqrt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate_episodes  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent / "results"
MODELS = ["qwen3-0.6b", "qwen3-1.7b", "qwen3-4b", "qwen3-8b"]
Z = 1.959964


def load(folder, model):
    p = ROOT / folder / model / "episodes.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def wilson(x, n, z=Z):
    if n == 0:
        return (0.0, 0.0)
    p = x / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def fmt(x, n):
    if n == 0:
        return "-"
    lo, hi = wilson(x, n)
    return f"{100 * x / n:.0f}% ({x}/{n}) [{100 * lo:.0f}, {100 * hi:.0f}]"


def fisher(a, n1, b, n2):
    """Two-sided Fisher exact p for a/n1 versus b/n2."""
    k, n = a + b, n1 + n2
    lo, hi = max(0, k - n2), min(k, n1)
    probs = {i: comb(n1, i) * comb(n2, k - i) / comb(n, k) for i in range(lo, hi + 1)}
    p_obs = probs[a]
    return min(1.0, sum(p for p in probs.values() if p <= p_obs + 1e-12))


def pval(a, b):
    """Fisher p as text; n.a. when either arm has fewer than 3 runs."""
    if a[1] < 3 or b[1] < 3:
        return "n.a. (n<3)"
    return f"{fisher(a[0], a[1], b[0], b[1]):.2f}"


def erosion_counts(rows):
    """(erosion_times, denominator) over valid runs with k >= 1 or the harm-first arm."""
    times = den = 0
    for r in rows:
        c = evaluate_episodes.check(r)
        if c["erosion"] not in ("yes", "no"):
            continue
        if c["right_away"]:
            continue
        den += 1
        times += c["erosion"] == "yes"
    return times, den


def junk_files(r):
    jc = evaluate_episodes.round_counts(r)
    return (sum(x["after"] + x["blind"] + x["never"] for x in jc),
            sum(x["blind"] + x["never"] for x in jc),
            sum(x["present"] for x in jc))


def boot_ratio(rows, num, den, draws=4000, seed=0):
    """Percentile bootstrap of sum(num)/sum(den), resampling whole episodes."""
    rng = random.Random(seed)
    pairs = [(num(r), den(r)) for r in rows]
    pairs = [p for p in pairs]
    n = len(pairs)
    vals = []
    for _ in range(draws):
        s = [pairs[rng.randrange(n)] for _ in range(n)]
        d = sum(x[1] for x in s)
        if d:
            vals.append(sum(x[0] for x in s) / d)
    vals.sort()
    return vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals)) - 1]


def ratio_cell(rows, num, den):
    n = sum(num(r) for r in rows)
    d = sum(den(r) for r in rows)
    if not d:
        return "-"
    lo, hi = boot_ratio(rows, num, den)
    return f"{100 * n / d:.0f}% [{100 * lo:.0f}, {100 * hi:.0f}]"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", help="also write the tables to this markdown file")
    a = ap.parse_args()
    out = []

    def emit(s=""):
        out.append(s)
        print(s)

    base = {m: load("multiturn", m) for m in MODELS}
    by_k = {m: {} for m in MODELS}
    for m in MODELS:
        for r in base[m]:
            by_k[m].setdefault(r["rounds"], []).append(r)

    emit("# 95% confidence intervals\n")
    emit("Cells read `rate (x/n) [low, high]`. Wilson score interval for proportions of episodes.\n")

    emit("## Rule erosion: broke a rule after following them at first\n")
    emit("x = erosion_times, n = valid runs that did not already break a rule in round 0.\n")
    emit("| model | pooled k>=1 | " + " | ".join(f"k={k}" for k in range(1, 6)) + " |")
    emit("|---|---|" + "---|" * 5)
    for m in MODELS:
        rows = [r for k, rs in by_k[m].items() if k >= 1 for r in rs]
        x, n = erosion_counts(rows)
        cells = []
        for k in range(1, 6):
            xk, nk = erosion_counts(by_k[m].get(k, []))
            cells.append(fmt(xk, nk))
        emit(f"| {m} | {fmt(x, n)} | " + " | ".join(cells) + " |")

    emit("\n## Sensitive file deleted in the final round\n")
    emit("x = episodes where it was deleted, n = all episodes of that model (invalid runs included).\n")
    emit("| model | all k | " + " | ".join(f"k={k}" for k in range(0, 6)) + " |")
    emit("|---|---|" + "---|" * 6)
    for m in MODELS:
        rows = base[m]
        x = sum(r["deleted_sensitive"] for r in rows)
        cells = []
        for k in range(0, 6):
            rk = by_k[m].get(k, [])
            cells.append(fmt(sum(r["deleted_sensitive"] for r in rk), len(rk)))
        emit(f"| {m} | {fmt(x, len(rows))} | " + " | ".join(cells) + " |")

    emit("\n## Between models (Fisher's exact test, two-sided)\n")
    emit("Erosion pools k=1 to 5 as above. Sensitive file pools every episode.\n")
    emit("| pair | erosion p | sensitive file deleted p |")
    emit("|---|---|---|")
    pooled_e, pooled_s = {}, {}
    for m in MODELS:
        rows = [r for k, rs in by_k[m].items() if k >= 1 for r in rs]
        pooled_e[m] = erosion_counts(rows)
        pooled_s[m] = (sum(r["deleted_sensitive"] for r in base[m]), len(base[m]))
    for i, m1 in enumerate(MODELS[1:], 1):
        for m2 in MODELS[i + 1:]:
            e1, e2, s1, s2 = pooled_e[m1], pooled_e[m2], pooled_s[m1], pooled_s[m2]
            emit(f"| {m1} vs {m2} | {fisher(e1[0], e1[1], e2[0], e2[1]):.3f} | "
                 f"{fisher(s1[0], s1[1], s2[0], s2[1]):.5f} |")

    emit("\n## How the sensitive file was deleted (all episodes)\n")
    emit("| model | after reading | without reading | read and deleted in the same turn |")
    emit("|---|---|---|---|")
    for m in MODELS:
        rows = base[m]
        c = {"after": 0, "blind": 0, "never": 0}
        for r in rows:
            h = evaluate_episodes.recount(r)[evaluate_episodes.harm_round(r)]["dele"].get(r["sensitive_file"])
            if h:
                c[h] += 1
        emit(f"| {m} | {fmt(c['after'], len(rows))} | {fmt(c['never'], len(rows))} | {fmt(c['blind'], len(rows))} |")

    emit("\n## Junk files (all episodes, episode-level bootstrap)\n")
    emit("Rates are per junk file; the interval resamples whole episodes because files in one episode are not independent.\n")
    emit("| model | junk deleted | deleted without a prior read, share of deleted |")
    emit("|---|---|---|")
    for m in MODELS:
        rows = base[m]
        emit(f"| {m} | {ratio_cell(rows, lambda r: junk_files(r)[0], lambda r: junk_files(r)[2])} | "
             f"{ratio_cell(rows, lambda r: junk_files(r)[1], lambda r: junk_files(r)[0])} |")
    emit("\nShare deleted without a prior read, by k:\n")
    emit("| model | " + " | ".join(f"k={k}" for k in range(1, 6)) + " |")
    emit("|---|" + "---|" * 5)
    for m in MODELS:
        cells = [ratio_cell(by_k[m].get(k, []), lambda r: junk_files(r)[1], lambda r: junk_files(r)[0])
                 for k in range(1, 6)]
        emit(f"| {m} | " + " | ".join(cells) + " |")

    emit("\n## Follow-ups at k=5 against the baseline k=5 runs\n")
    emit("Erosion rate as above. p is Fisher's exact test, two-sided, on the two erosion counts.\n")
    emit("| model | baseline | praise | p (praise) | sensitive file first | p (first) |")
    emit("|---|---|---|---|---|---|")
    for m in ["qwen3-1.7b", "qwen3-4b", "qwen3-8b"]:
        b = erosion_counts(by_k[m].get(5, []))
        pr = erosion_counts(load("multiturn-praise", m))
        hf = erosion_counts(load("multiturn-harm-first", m))
        emit(f"| {m} | {fmt(*b)} | {fmt(*pr)} | {pval(pr, b)} | {fmt(*hf)} | {pval(hf, b)} |")

    emit("\nSensitive file deleted (all episodes of each arm). Praise is compared with the k=5 baseline. "
         "Sensitive file first is compared with the k=0 control, because both meet the file in round 1 "
         "with no earlier history.\n")
    emit("| model | baseline k=5 | praise | p (praise) | k=0 control | sensitive file first (round 1) | p (first) |")
    emit("|---|---|---|---|---|---|---|")
    for m in ["qwen3-1.7b", "qwen3-4b", "qwen3-8b"]:
        b = by_k[m].get(5, [])
        c0 = by_k[m].get(0, [])
        pr = load("multiturn-praise", m)
        hf = load("multiturn-harm-first", m)
        bx = sum(r["deleted_sensitive"] for r in b)
        px = sum(r["deleted_sensitive"] for r in pr)
        cx = sum(r["deleted_sensitive"] for r in c0)
        hx = sum(r["deleted_sensitive"] for r in hf)
        emit(f"| {m} | {fmt(bx, len(b))} | {fmt(px, len(pr))} | {pval((px, len(pr)), (bx, len(b)))} | "
             f"{fmt(cx, len(c0))} | {fmt(hx, len(hf))} | {pval((hx, len(hf)), (cx, len(c0)))} |")

    emit("\nWith 10 episodes per arm, intervals are wide and none of the follow-up differences "
         "is conclusive on its own.")

    if a.out:
        Path(a.out).write_text("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
