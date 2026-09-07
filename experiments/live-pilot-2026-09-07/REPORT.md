# Live pilot: does the harness help?

Date: 2026-09-07. Provider: Ollama Cloud (`https://ollama.com/api/chat`). Models tested: `glm-5.3-flash`, `deepseek-v4-flash:0731`, and `gpt-oss:20b`; Kimi K3 was excluded as requested. The credential was supplied through an environment variable and is not stored in this repository.

## Problem

The visible dossier is a synthetic randomized controller trial with post-treatment assay eligibility. The recorded contamination rates are 32/200 (OFF) and 8/200 (ON), but the assay observes only eligible samples: 16/40 OFF versus 4/40 ON. The task asks whether deployment is justified, requires resolving two competing reviewers, and requires constructing compatible worlds and a discriminating follow-up. The hidden assessment expects recognition that the randomized assignment is valid while the total effect is not identified because eligibility is affected by treatment.

## Conditions

Each model received the identical visible dossier. The direct condition made one Ollama call. The harness condition used six calls with `work_before_review=2`, attention learning enabled, one trial call, 8,000-character reading pages, 2,048 generated tokens, and thinking disabled for GLM/DeepSeek. GPT-OSS used Ollama's `low` thinking level. The first exploratory run used default 4,000-character pages and exposed a configuration failure: the required dossier was repeatedly treated as a read-only page and several final contents were empty. That run is retained as `pilot_results.json`/`pilot_results2.json`; the corrected run is `pilot_harness3.json`.

## Observations

| model | direct response | harness time | harness step lengths (characters) | attention trial adopted? |
|---|---:|---:|---|---|
| DeepSeek V4 Flash | 8,650 chars, 28.5 s | 169.0 s | 4,813 / 4,116 / 7,333 / 5,776 / 4,930 / 2,079 | No (`method_revision` stayed 1) |
| GLM 5.3 Flash | 7,905 chars, 35.1 s, length stop | 245.4 s | 8,313 / 8,870 / 10,636 / 9,842 / 7,854 / 10,285 | No (`method_revision` stayed 1) |
| GPT-OSS 20B | 7,897 chars, 34.1 s, low thinking | 177.1 s | 4,995 / 6,014 / 5,937 / 5,985 / 5,933 / 5,202 | No (`method_revision` stayed 1) |

All corrected harness calls completed without authentication or transport errors and returned provider records. DeepSeek's direct answer and the harness work responses explicitly preserved the key distinction between valid randomization and non-identification. GLM and GPT-OSS also produced substantive analyses, but their harness trajectories spent substantially more time generating repeated proposals and reviews than producing a matched final answer. The harness added roughly 5–7x wall-clock latency in this six-call configuration.

## What this pilot supports

The harness works end to end with Ollama Cloud: it persists a run, exposes the same source pack, records step-level responses, and keeps the model out of the hidden assessment. It also surfaces operational failure modes that a one-shot call hides: page-size limits, thinking/content separation, and incomplete method adoption.

For this problem, the harness did not yet demonstrate a reasoning-quality improvement. No model adopted an attention method (`method_revision` remained 1), and the six-step harness endpoint was not equivalent to the one-shot final answer. The fair conclusion is therefore operational: the harness currently **hinders throughput and endpoint comparability** unless the run is configured to reach a final response and the attention proposal is compact enough to be trialled. It may still help auditing by making intermediate reasoning and control decisions inspectable.

This is a three-model, one-problem pilot, not a model ranking. A follow-up evaluation should predeclare a matched final-answer endpoint (for example, ten steps or an explicit `respond` stop), score the hidden assessment with the same rubric for both conditions, and record whether a method was actually adopted before comparing quality or latency.

## Reproduction

From the repository root:

```bash
export OLLAMA_API_KEY='…'
python /tmp/run_harness3.py
```

The checked-in JSON files contain the provider metadata and raw model responses; transient harness workspaces are ignored by Git. Do not place provider credentials in files, command history, or reports.
