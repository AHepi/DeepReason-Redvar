# DeepSeek continuation with 70,000 additional token-volume units

This experiment resumes the saved DeepSeek V4 Flash 0731 state after the earlier six-call pilot. It uses the same causal-measurement dossier, single account, provider, thinking=false, per-call generation limit of 2,048 tokens, context bounds, and attention-learning setting. Only the total expenditure envelope and available call slots change. No answers, fixes, or new evidence are injected during the continuation.

The user requested an additional 70k token run to expose deeper dependency issues. The operational interpretation is 70,000 additional harness-charged input-plus-output token-volume units, not 70,000 generated tokens. Ollama preflight is estimated and incomplete accounting retains conservative reservations. Provider input/output observations are reported separately; neither the budget nor the charge is represented as exact billed usage. A request that cannot fit stops the run with an unused remainder. A provider failure or overrun also stops the run without automatic retry.

The experiment records requests, replies, host events, and before/after snapshots. Recording is external to participant-visible history. Inspect whether attention proposals lead to trials and installed methods, whether the initial dossier remains in actual request contexts, whether focus revisions carry criticisms forward, and whether explicit uses, bindings, and dependency propagation execute. Prose discussion of a dependency does not count as a registered dependency.

No model ranking or automatic truth objective is used. The source pack's separate assessment supplies a human-readable basis for examining particular reasoning failures. Findings are scoped to this continuation, not to model creativity or general harness efficacy.

Run from the repository root with Python 3.11+ and OLLAMA_API_KEY already exported:

```sh
PYTHONPATH=src python experiments/deepseek-continuation-70k/run.py \
  experiments/deepseek-continuation-70k/evidence/baseline-workspace \
  /tmp/deepseek-70k-rerun
```

Create the baseline workspace first by copying `evidence/baseline.json` to `evidence/baseline-workspace/state.json`. The destination for a new run must not exist. To analyse the recorded run shipped here, run `python experiments/deepseek-continuation-70k/analyse.py`.
