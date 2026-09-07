# Audit and change workflow

This workflow is for a person or coding agent changing DeepReason Redvar. Start from the [code map](code-map.md), preserve the [supplied specification](spec/open-inquiry-0.4.md), and leave a reviewer enough evidence to follow a behavioural claim into an actual request or state transition.

## Establish the question and baseline

Write the alleged defect or requested behaviour in ordinary language before choosing an implementation. Identify the relevant specification section and the module that owns the boundary. Record the current commit with `git rev-parse HEAD` and inspect `git status --short` so unrelated local work is preserved. Work on a separate branch when publishing a change; do not infer permission to merge or deploy from permission to edit.

Explain what an operator or participant would observe if the behaviour were wrong. Useful observations include an obsolete premise still entering the next request, a lost original, an uncharged model call, an estimated count advertised as exact, or an installed method changing while the gate is off. “The model said it improved” is not a host-level acceptance condition.

## Trace the actual control boundary

Read the owning module and its immediate callers. Follow the concrete input, current host authority, state revision, recorded event, and downstream effect. Separate retained prose from installed operational action and a scoped checker result from its interpretation. Do not infer semantic dependencies from links or citations without an explicit declared contract.

For a suspected prompt-injection boundary defect, use inert fixture text that claims authority and verify that it cannot create a call, change a protected setting, alter the endpoint, or install a binding. Do not develop exploit payloads or probe external services. The useful evidence is whether the local permission boundary holds.

## Make a reviewable change

Change the smallest responsible component that fixes the defect while preserving the complete behaviour. Keep interfaces narrow and replaceable. A new model call must consume a registered opportunity and shared resource reservation. A new predicate must state exact operands, source identity, representation, scope, completion semantics, and permitted consequence. A new media adapter must distinguish original bytes from its extraction and identify unavailable material.

Use prose participation as an ordinary test route. Do not require structured actions, formal discriminators, confidence fields, or code before preserving a criticism. Do not introduce rankings, reward signals, agreement votes, formal immunity, or automatic truth labels. If a requested implementation changes the intended semantics, describe the conflict explicitly rather than editing the source specification to make the change appear conforming.

## Verify the consequence

Add or adjust a regression test when the change affects a meaningful boundary. The strongest fixture demonstrates the original failure and inspects the downstream effect after the repair. For example, a parking test should inspect the next provider request, and a stale-return test should show both retained text and denied mutation. Avoid tests that only restate private implementation details.

```sh
python -m unittest discover -s tests -v
python -m open_inquiry --help
```

Use the focused test file while iterating, then run the local suite for a cross-component change. CLI changes need a subprocess smoke test. Provider changes need fixture evidence about request fields and errors before any live test. A live test requires a configured endpoint and authorised expenditure; record which model, settings, source material, counter capability, and observation destination were actually used. Fixture accounting never establishes a live token cap.

No finite test suite proves creativity, understanding, explanatory universality, or that a criticism is sound. Describe measured host behaviours and remaining failures precisely.

## Update code and documents together

| If the change affects… | Update… |
| --- | --- |
| A public command, argument, or exit behaviour | CLI help, [usage](usage.md), relevant README example, and CLI tests |
| A module boundary or new file | Its module docstring and the [code map](code-map.md) |
| A policy setting or default | Configuration validation, help or usage, and any shipped example policy |
| Supported media, provider guarantees, recording, or replay | [Limitations](limitations.md) and the relevant usage explanation |
| A conformance claim | A named test or observed record and an explicit statement of its scope |

Run the documented commands against a temporary workspace when their syntax changes. Check that relative documentation links name real files, and that examples use the current default account and returned identifiers. Keep the attached specification unchanged as a historical input; document implementation departures in the limitations page or change report.

## Report and hand over

Describe the original problem, the resulting behaviour, the exact verification performed, and material limitations. Link the responsible files and tests. Distinguish work completed locally from commits, remote publication, and live model investigation. If work stops, state the saved branch or commit, the failing command, the suspected boundary, and the next concrete action; a new agent should not have to reconstruct intent from an unlabelled transcript.

The CI workflow executes the same local unittest suite on supported Python versions. Passing CI verifies those cases at that revision. It does not waive the behavioural review or turn a documentation statement into a demonstrated result.
