# Code as documents: navigation and contracts

Read this page to find the component responsible for a behaviour before editing it. Module docstrings describe local contracts and limits; tests give executable examples; this map links those pieces back to the supplied specification. Source code is inspectable documentation of an implementation choice, not authority to redefine the intended semantics.

## Starting points

| Question | Read here |
| --- | --- |
| How do I install, run, or inspect a saved inquiry? | [README](../README.md), [usage](usage.md), [CLI](../src/open_inquiry/cli.py) |
| What is the intended behaviour? | [Supplied specification 0.4](spec/open-inquiry-0.4.md) |
| How does one allowed step become an actual request? | [Engine](../src/open_inquiry/engine.py) |
| What can the implementation currently claim? | [Limitations](limitations.md), the test files associated below |
| How should I audit or modify it? | [Audit and change workflow](audit-and-change.md) |

## Ownership boundaries

| Component | Behavioural contract | Specification connection | Executable evidence |
| --- | --- | --- | --- |
| [collection.py](../src/open_inquiry/collection.py) | Retain occurrences and original source bytes; disclose representations; browse stable pages and bounded resumable search without a merit ordering. | Parts II–IV: collection, originals, nonlocal access | [test_collection.py](../tests/test_collection.py) |
| [checking.py](../src/open_inquiry/checking.py) | Report scoped literal matches, completed absence, or incomplete/unavailable/error outcomes; never infer endorsement or semantic contradiction. | Part II: quote-by-phrase; Part IX: source fidelity | [test_checking.py](../tests/test_checking.py) |
| [context.py](../src/open_inquiry/context.py) | Construct bounded requests with required anchors, visible use dispositions, bounded graph work, and explicit incomplete reading. | Parts III–IV: cuts and four independent bounds | [test_context.py](../tests/test_context.py) |
| [resources.py](../src/open_inquiry/resources.py) | Reserve and settle every dispatched call, protect promised returns, retain uncertain charges, and pause on observed overruns. | Part VII: expenditure; Part IX: reservations | [test_resources.py](../tests/test_resources.py), [test_engine_resources.py](../tests/test_engine_resources.py) |
| [providers.py](../src/open_inquiry/providers.py) | Return prose and actual usage observations; label fixture or estimated counters; keep endpoint and credentials under operator control. | Parts I, VII–VIII: prose and independent permissions | [test_providers.py](../tests/test_providers.py) |
| [mediation.py](../src/open_inquiry/mediation.py) | Recognise an optional finite grammar for a direct use action or attention plan; preserve prose independently of failed actuation. The recogniser supplies a proposed readback and never authorises it. | Parts II, III, V: optional action resolution | [test_mediation.py](../tests/test_mediation.py) |
| [uses.py](../src/open_inquiry/uses.py) | Address current use revisions, install fixed conditional bindings, apply matching receipts, and propagate or revise declared dependencies in bounded slices. | Part II: local withdrawal and use-relative dependency effects | [test_uses.py](../tests/test_uses.py) |
| [engine.py](../src/open_inquiry/engine.py) | Own scheduling, current grants and revisions, permitted use transitions, learning gates, trials and returns. | Parts II, V–IX: actual control contracts | [test_engine_audit.py](../tests/test_engine_audit.py), [test_engine_resources.py](../tests/test_engine_resources.py) |
| [config.py](../src/open_inquiry/config.py) | Validate operator settings without accepting permission changes from generated content. | Part IX: configuration surface | Engine and CLI tests |
| [persistence.py](../src/open_inquiry/persistence.py) | Write atomic working snapshots, exclude concurrent CLI writers, and separate observation retention from participant history. | Part III: history and resumption | Engine and CLI tests |
| [cli.py](../src/open_inquiry/cli.py), [__main__.py](../src/open_inquiry/__main__.py) | Expose explicit operator commands, actionable errors, help, and consistent installed entry points. | Operator interface for the preceding contracts | [test_cli.py](../tests/test_cli.py) |

The controller is the authority for operational rights. Collection links do not create service accounts. Checker receipts do not park anything by themselves. The context compiler does not decide that a passage is true or relevant. A provider reply is retained content; only a current host opportunity and a permitted transition can change state.

## Follow a concrete effect

To investigate conditional parking, follow `Engine.bind` (provided by `UseOperations`) to the versioned condition, `Checker` to the scoped receipt, `process_checks` and `change_use` to the guarded use revision, and `compile_cut` to the next actual request. A test that merely sees `parked` in a snapshot is insufficient if that same use continues to appear as an adopted premise in the next request.

To investigate attention learning, follow `Engine.set_gate`, the scheduled nomination and trial state, the ledger's future reservations, the return transition, and the next compiled cut. Inspect both the retained proposal and what the request actually supplied. A changed note and a changed read plan are separately observable claims.

To investigate expenditure, follow the complete message list through the provider counter, reservation, dispatch marker, generated reply or failure, and settlement. Include failed or interrupted calls and protected future returns. An input estimate cannot prove a live endpoint's hard token boundary.

## Public Python surfaces

`Engine.create(brief, policy=..., directory=...)` creates a run and `Engine.load(directory)` restores it. `run(provider, steps=...)` and `step(provider)` dispatch bounded work. Operator methods expose source ingestion, account creation, use changes, checks, conditions, learning gates, and validated policy updates. The CLI supplies a writer lock around mutations; direct Python callers must provide equivalent single-writer coordination.

Provider adapters implement `count(messages)` and `generate(messages, max_tokens=..., timeout=...)`, describe their counting capability, and return a `ProviderResult`. Replacing an adapter requires evidence about its actual message formatting, generation limits, and usage semantics. Merely matching the method signatures does not establish provider conformance.

See source docstrings and focused tests for exact argument shapes. The internal working-state dictionaries support this deployment's snapshot format; arbitrary manual edits to a snapshot are not a supported migration or semantic-authority mechanism.
