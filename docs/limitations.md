# Implementation scope and limits

This is a bounded Python deployment of [Open Inquiry 0.4](spec/open-inquiry-0.4.md). Its outputs are inquiry material and operational records. It does not establish that an LLM understood a criticism, made an explanatory advance, learned a better method, or instantiated universal creativity.

## What the included adapters establish

| Surface | Implemented scope | Limit |
| --- | --- | --- |
| Participant interface | Ordinary prose is retained without a required schema. Optional operator and mediator actions use separate bounded interfaces. | A retained objection is not proof that later reasoning recognised it. |
| Sources | Original submitted bytes, supported UTF-8 readable representations, optional `pypdf` text extraction, direct paging, stable catalogue and bounded literal search. | PDF extraction is separately labelled and capped at 256 pages; unread pages make it incomplete. No OCR, image understanding, remote retrieval, or semantic search. |
| Checking | Versioned literal-occurrence checks over identified source ranges. | Occurrence does not establish endorsement, entailment, truth, or applicability. |
| Context | Bounded local traversal, required anchors, nonlocal reading and disclosed incomplete reading. | A finite cut can omit an important qualification; packing cannot establish comprehension. |
| Attention | Off/observe/on gates, bounded method notes, preauthorised recipes and trial-return control. | Note changes are not weight training or evidence that a method became better. |
| Accounting | Whole-run reservations and settlements, explicit usage provenance, conservative unknown charges and overrun pause. | Ollama preflight is estimated and hidden-reasoning inclusion is unverified; reservations remain conservatively charged. A `num_ctx` request does not establish endpoint enforcement or absence of truncation. |
| Persistence | Atomic mutable working snapshots and separately selected observation recording. | Ordinary resumption is supported; exact event-sourced replay and remote-response recovery are not promised. |
| Execution | No generated-code execution or sandbox is required or installed. | A production sandbox or new external capability requires an independently enforced adapter and its own validation. |

## Operational boundaries

Dispatch is sequential. Each CLI `run` invocation uses its selected provider configuration for all scheduled accounts. Registered route names organise delivery and do not themselves select another model. The CLI excludes simultaneous writers to the same workspace. Python callers must provide equivalent coordination. The snapshot and observation log are separate writes, so a crash can leave a recording gap or a charged dispatch whose remote outcome is unknown. The engine must disclose that uncertainty and must not automatically retry the call as though nothing happened.

The working collection has explicit source and total-retention limits. An oversized required packet may need several reading opportunities. Those opportunities cannot establish that a single later answer fully addressed material it never received. The host's bounded traversal and search allowances control local work but do not guarantee low wall-clock latency for every deployment.

Installed bindings act only on named uses and fixed revisions. Explicit dependency handling concerns declared applications, not every implication hidden in prose. A parked idea may reappear as a paraphrase; the host has no guaranteed semantic-equivalence detector. Turning conditional actions off does not erase checks or reverse earlier decisions. Reactivation remains a new bounded decision.

Optional mediation is an operational convenience, not the admission route for thought. The included recogniser handles only the finite direct-opening phrases documented in [usage](usage.md); it does not resolve arbitrary prose requests, paraphrases, or ambiguous source references. No LLM mediator call is installed. Direct CLI browsing and operator use actions remain available. A participant may fail to name an action, produce malformed structured text, or provide no actuation at all while its contribution remains available. A method note alone must not be reported as a concrete retrieval-plan change.

## Evidence and further investigation

The included unit and integration tests use local fixtures and intercepted provider requests. They check particular host contracts and failure boundaries at the tested revision. The demo is synthetic. No live model experiment, provider-token calibration, source-parser benchmark, or comparative creativity result is implied by installation or a passing test run.

A live comparison needs the same initial collection, focus, installed method, endpoint settings, and authorised resource envelope across separately recorded runs. Turning learning off after adoption does not restore the initial method; reset it or begin from the same saved baseline. Compare the particular explanatory defects, preserved qualifications, and actual spending in each run. A count of wins must not become a reward or scheduling objective.
