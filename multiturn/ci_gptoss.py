"""ci.py's tables with the Ollama-run models added (gpt-oss-20b and Qwen3 14B/30B/32B), their
follow-up arms, and one comparison ci.py lacks.

  python multiturn/ci_gptoss.py                                  # prints the tables
  python multiturn/ci_gptoss.py --out results/ci_summary_gptoss.md

ci.py is not edited: this file extends its model list and calls its main(), so every table is
computed by the same code. ci.py's follow-up tables list three Qwen models by name, so the
follow-up arms of the added models get their own table here, built the same way. The
between-models table gains the new pairs.

The added section tests the sensitive-file deletion rate at k=0 against k>=1 pooled, per model.
Erosion cannot be compared with the control (it is undefined at k=0, and a longer episode has
more rounds to break a rule in); the deletion rate is defined at every k.

The added models were run through Ollama (quantised builds) with --max-steps 24 instead of 12,
see run_gptoss.py; qwen3-0.6b to qwen3-8b are vLLM runs.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ci

EXTRA = ["qwen3-14b", "qwen3-30b", "qwen3-32b", "gpt-oss-20b"]     # all run through Ollama


def control_table(models):
    lines = ["", "## Sensitive file deleted: k=0 control against k>=1 pooled", "",
             "All episodes of each model. p is Fisher's exact test, two-sided.", "",
             "| model | k=0 | k>=1 | p |", "|---|---|---|---|"]
    for m in models:
        rows = ci.load("multiturn", m)
        c0 = [r for r in rows if r["rounds"] == 0]
        ck = [r for r in rows if r["rounds"] >= 1]
        a = (sum(r["deleted_sensitive"] for r in c0), len(c0))
        b = (sum(r["deleted_sensitive"] for r in ck), len(ck))
        p = f"{ci.fisher(a[0], a[1], b[0], b[1]):.3f}" if a[1] and b[1] else "-"
        lines.append(f"| {m} | {ci.fmt(*a)} | {ci.fmt(*b)} | {p} |")
    lines += ["", "qwen3-14b, qwen3-30b, qwen3-32b and gpt-oss-20b ran on Ollama (quantised builds) with "
                  "a step limit of 24; the smaller Qwen models ran on vLLM with a step limit of 12."]
    return "\n".join(lines)


def followup_table(models):
    """ci.py's two follow-up tables, for the models it does not list."""
    lines = ["", "## Follow-ups at k=5 for the Ollama models", "",
             "Same layout and tests as the Qwen follow-up tables above. `-` = arm not run.", "",
             "Erosion:", "",
             "| model | baseline | praise | p (praise) | sensitive file first | p (first) |",
             "|---|---|---|---|---|---|"]
    dele = ["", "Sensitive file deleted:", "",
            "| model | baseline k=5 | praise | p (praise) | k=0 control | sensitive file first (round 1) | p (first) |",
            "|---|---|---|---|---|---|---|"]
    n = lambda rows: (sum(r["deleted_sensitive"] for r in rows), len(rows))
    for m in models:
        pr, hf = ci.load("multiturn-praise", m), ci.load("multiturn-harm-first", m)
        if not pr and not hf:
            continue
        rows = ci.load("multiturn", m)
        b5 = [r for r in rows if r["rounds"] == 5]
        c0 = [r for r in rows if r["rounds"] == 0]
        e = [ci.erosion_counts(x) for x in (b5, pr, hf)]
        lines.append(f"| {m} | {ci.fmt(*e[0])} | {ci.fmt(*e[1])} | {ci.pval(e[1], e[0])} | "
                     f"{ci.fmt(*e[2])} | {ci.pval(e[2], e[0])} |")
        dele.append(f"| {m} | {ci.fmt(*n(b5))} | {ci.fmt(*n(pr))} | {ci.pval(n(pr), n(b5))} | "
                    f"{ci.fmt(*n(c0))} | {ci.fmt(*n(hf))} | {ci.pval(n(hf), n(c0))} |")
    return "\n".join(lines + dele)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", help="also write the tables to this markdown file")
    a = ap.parse_args()

    ci.MODELS = [m for m in ci.MODELS + [m for m in EXTRA if m not in ci.MODELS]
                 if ci.load("multiturn", m)]                           # main() reads it at call time; skip models not run yet
    ci.main()                                                          # prints, and writes --out
    extra = followup_table(EXTRA) + "\n" + control_table(ci.MODELS)
    print(extra)
    if a.out:
        with open(a.out, "a") as fh:
            fh.write(extra + "\n")


if __name__ == "__main__":
    main()
