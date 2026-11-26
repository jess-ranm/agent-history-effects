# Rule erosion in tool-using agents

**The question.** An agent is given explicit rules — read a file before deleting it, and
never delete an important one — and then does ordinary cleanup work, round after round, in
one session. Every early round it handles correctly. Does it still follow the rules at the
end of the session, or does benign precedent alone erode them?

We call the behaviour **rule erosion**: the agent follows the rules in every earlier round,
then breaks them. Nothing in the context ever escalates and no prior round contains an
example of rule-breaking, so any erosion comes from repetition and routine, not from bad
examples.

## What is here

- [`setup/`](setup/) — the experimental setup: the drive (`env.py`), system prompt, user
  requests, praise prefixes, file contents and tools. `export_setup.py` writes them to `reports/setup.json` for the viewer.
- [`multiturn/`](multiturn/) — the run scripts: `run_pilot.py` runs the conversations,
  `review.py` checks them, `model_list.py` lists models for the viewer. Its
  [README](multiturn/README.md) describes the design, the metrics and how to read an episode.
- [`analysis/`](analysis/) — `calculate_significance.py` (error bars and p-values).
- `serve.py` — starts a local vLLM server for the model under test, with per-family settings
  (tool-call parser, reasoning parser, dtype, temperature) in `FAMILIES`.
- `notebooks/run_main_study.ipynb` — run the main study in Colab: keep your model in `MODELS`,
  Run all. Results go to GitHub and show up in the viewer on their own.

## Running it

### In Colab (how teammates run a model)

Everyone runs from the team repo, [jess-ranm/agent-history-effects](https://github.com/jess-ranm/agent-history-effects).

You need, once:
- push access to jess-ranm/agent-history-effects
- Colab secrets (key icon in the left sidebar), with notebook access turned on:
  - `GITHUB_TOKEN`: a GitHub token with repo scope
  - `GIT_NAME` and `GIT_EMAIL`: your name and email for commit messages
  - `HF_TOKEN`: only for gated models such as Gemma (accept the model's license on its Hugging
    Face page first); Qwen and gpt-oss do not need it

Steps:
1. Put your name as DRI on a row of the model table in the research doc.
2. Open [`notebooks/run_main_study.ipynb`](notebooks/run_main_study.ipynb) in Colab and pick a
   GPU runtime (T4 works for Qwen3; Qwen3.5, Gemma 4 and gpt-oss need an L4 or A100).
3. In cell 4, keep only your model in `MODELS`: `(family, Hugging Face id, short name)`, e.g.
   `('Gemma 4', 'google/gemma-4-12B-it', 'gemma4-12b')`. The family must be one of `FAMILIES`
   in `serve.py`.
4. Runtime → Run all.

How the experiment runs. One conversation is a series of cleanup requests; **k** is the number of
requests with only junk files before the request that also has a sensitive file.
- **Treatment, k = 10**: requests 1 to 10 have only junk files; request 11 also has the sensitive file.
- **Baseline, k = 0**: request 1 already has the sensitive file.

For each model:
1. **Pilot test**: 5 treatment conversations (`results/pilot/<name>/`).
   - The model breaks a rule (or does no cleanup) in request 1 of **all 5** → marked **INCAPABLE**:
     it cannot follow the rules, so it gets no full run and is left out of the main results.
   - Otherwise it goes on to the full experiment. If this happened in 3 or 4 of the 5, the viewer
     marks the model *borderline* so the team can decide whether to include it.
2. **Full experiment** (`results/multiturn/<name>/`): 20 treatment and 20 baseline conversations,
   each independent (its own seed, files and order of requests).

Results are pushed to jess-ranm every 10 minutes and after every model. If the runtime dies, Run
all again: only missing conversations are run. To add more conversations later, raise `EPISODES`
and run again.

### Where results are stored

Result files (`results/**/*.jsonl`) are stored with [Git LFS](https://git-lfs.com), so the repo
stays small as runs from many models come in. The notebook installs it; on your own machine run
`git lfs install` once before cloning (or `git lfs pull` in an existing clone).

### Seeing the results

Online: https://jess-ranm.github.io/agent-history-effects/reports/viewer.html (GitHub Pages on
jess-ranm, deployed from `main`). In Colab, the notebook's last cell opens it from the runtime.
Locally: `python -m http.server` in the repo root, then `http://localhost:8000/reports/viewer.html`.

Tabs: Main study results, Ablation results, one tab per model family (one child tab per model),
Experimental Setup. New models appear on
their own: every run updates `results/model_list.json`.

A model that breaks a rule (or does no cleanup) in request 1 of more than half its conversations
is also labelled INCAPABLE after its full run and left out of the Main study and Ablation results
tabs; its own tab still shows its data.

### Adding a model family

Add an entry to `FAMILIES` in `serve.py`: vLLM tool-call parser, reasoning parser (or `None` to
keep thinking in the message text), dtype and temperature. Run the notebook; the pilot shows
whether the settings work.

### From the command line

With a vLLM server already serving the model (see `serve.py`):

```
python multiturn/run_pilot.py --model qwen3-4b --family Qwen3 --rounds 0 10 --episodes 20 \
    --temperature 0.6 --out results/multiturn/qwen3-4b
```

Tally from a notebook:

```python
from multiturn.review import review_summary
review_summary("results/multiturn/qwen3-1.7b")
```
