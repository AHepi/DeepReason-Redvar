# DeepSeek continuation: more tokens exposed source and control dependencies

The resumed run completed eight additional DeepSeek V4 Flash 0731 calls in 180.2 seconds. It exposed a failure to recover primary evidence, repeated unsuccessful attention nominations, and a numerical interpretation error carried into the next working focus. It did not exercise explicit dependency propagation. No production code was changed.

## Expenditure and endpoint

The requested additional allowance was 70,000 harness token-volume units. The run charged 63,994 and stopped before the next dispatch because the remaining 6,006 could not fund that request. Ollama reported 43,684 input tokens and 7,756 output tokens, totaling 51,440. All eight ledger entries remain marked accounting-unknown because the adapter does not certify complete provider accounting. Charged units therefore must not be described as exact consumption or billing. There were no provider errors or overruns.

This continues the prior six-call state: fourteen model calls in total, eight newly funded. Only the total token and call envelopes changed. The model, thinking=false, 2,048-token per-call output ceiling, problem, context limits, learning gate, and participant count stayed fixed. Consequently this tests a longer trajectory, not a larger output allowance for each response. The final attempted ninth additional step returned `limit` without a model call.

## Actual execution

| Additional step | Invitation | Context mode | Observation |
|---|---|---|---|
| 1 | variation | work | Argues for discarding the trial and calls its information decision-irrelevant |
| 2 | explore | work | Continues analysis of the commentary exchange |
| 3 | method nomination | read | Explicitly identifies missing original evidence; no trial starts |
| 4 | develop | work | Reverses benefit/harm interpretation of the calculated effect bounds |
| 5 | examine | work | Criticism fails to repair the sign interpretation |
| 6 | method nomination | read | Again asks to reopen original evidence; no trial starts |
| 7 | respond | work | Sign interpretation error persists; response becomes working focus |
| 8 | read | work | Receives the new focus and broadly endorses it |

The event record contains eight dispatches, eight model responses, one focus change, and the initial operator budget change. It contains no trial reservation, trial return, attention-plan resolution, one-off read resolution, or dependency transition. Attention method revision remained 1; focus revision advanced from 2 to 3. Registered uses, bindings, and pending dependencies remained empty.

## Primary evidence disappeared from every new request

The original dossier remains retained as `o000001`, but the actual `included` lists in all eight new grants omit it. The model instead receives earlier model responses and criticisms. At step 3 (`o000011`) it correctly notices: “The materials are all secondary commentary”. At step 6 (`o000014`) it again describes a commentary loop and asks for the original question, data, validation, and reviewer statements.

This is an observed context-selection limitation, not evidence that originals were deleted. The pilot bundled all six source texts into one initial-question occurrence rather than individually ingested source records. The finding is specific to that setup and the current selection limits; independent source ingestion remains untested here.

## Recognition of a missing dependency did not cause access

Both requests for a different method arrived during nominations whose supplied contexts were marked partial reading. The host therefore retained the responses but did not reserve a trial. Increasing the run envelope did not remove that bottleneck.

The ordinary one-off read mediator is called only during the work phase and recognises a narrow opening grammar. It is not a general resolver for arbitrary prose requests inside a nomination. No `one-off-read-resolved` event occurred. The scheduled invitation called `read` at step 8 did not itself recover the original dossier.

The consequence is a control dependency: the model can diagnose missing evidence while the available transition fails to turn that diagnosis into evidence access. A useful diagnostic proposal remains legitimate prose even though actuation failed; the failure is not a reason to discard the proposal.

## A mathematical error entered the working focus

Given a = P(Y=1 | S=0, OFF) and b = P(Y=1 | S=0, ON), the supplied data imply:

`risk_OFF = 0.16 + 0.20a`

`risk_ON = 0.04 + 0.60b`

`risk_ON - risk_OFF = 0.60b - 0.20a - 0.12`

Because Y=1 is contamination, a negative contrast means ON reduces contamination. Step 4 labels the minimum −0.32 “ON much worse” and maximum +0.48 “ON much better”, reversing that interpretation. Step 7 (`o000015`) retains the formula but calls −0.08 “ON worse” and +0.08 “ON helps”. It also says near-zero a and b give approximately +0.12 despite its displayed formula giving −0.12. That step becomes focus revision 3 and appears in the next request.

This establishes a specific erroneous dependency between numerical calculation and interpretation. The host records and carries the prose; it does not verify those semantics. The recommendation to collect samples independently of eligibility survives, so the answer is not uniformly wrong. The run nevertheless demonstrates that retaining a broadly correct recommendation can coexist with accumulating errors in its supporting explanation.

The repeated endorsement of “throw the trial away” also overstates the defect. Actual contamination risk is bounded by [0.16, 0.36] OFF and [0.04, 0.64] ON. The sign of the effect is unresolved, but the observed data retain information. There is no matched new direct-model control, so these observations do not establish that the harness caused more errors than equal additional unstructured deliberation would have caused.

## Explicit dependency machinery was not tested

The saved account had no registered uses or dependencies before continuation and still has none afterward. The current prose mediator can act on eligible existing uses; it does not build an arbitrary use/dependency graph from discussion. Therefore a longer run of this setup cannot establish whether the propagation engine correctly withdraws or restores dependent uses. More tokens alone do not provide the missing setup.

The useful next experiment would separately exercise a source-access recovery path and a seeded explicit dependency chain, tracing actual downstream request contents. Both should preserve the original prose and keep operational permissions separate from model-generated claims. These are proposed follow-ups, not repairs silently applied during this run.

## Reproduction and audit

See [PROTOCOL.md](PROTOCOL.md), [run.py](run.py), and [analyse.py](analyse.py). The evidence directory includes the exact starting snapshot, ending workspace snapshot, requests, host events, raw responses, accounting summary, and source-file hashes. No credential is included. Retained snapshots support resumption; they do not promise identical future model responses.

This report supersedes the earlier pilot's suggestion that extra time alone might be enough to reach attention adoption. It also corrects two documentation defects in that report: assayed rates were 32/160 and 8/80 (not 16/40 and 4/40), and its `/tmp/run_harness3.py` command referenced an unshipped temporary script. The continuation runner and saved baseline supplied here are reproducible repository artifacts.
