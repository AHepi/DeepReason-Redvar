# Working on this repository

Read [docs/code-map.md](docs/code-map.md) to locate the component responsible for a behaviour, then follow [docs/audit-and-change.md](docs/audit-and-change.md). Keep public commands, module contracts, navigation, limitations, and meaningful regression evidence current together.

Treat [docs/spec/open-inquiry-0.4.md](docs/spec/open-inquiry-0.4.md) as the unchanged supplied specification. Explain implementation departures explicitly. Preserve legitimate prose participation, revisable use, source fidelity, independent operational permissions, and the absence of rankings or optimisation objectives. Do not turn a mechanical result into a truth or creativity verdict.

Use Python 3.11 or later and keep the standard-library runtime usable without a model or API key. Run focused tests while changing a component; use `python -m unittest discover -s tests -v` for cross-component verification. Provider fixtures establish only the contracts they actually exercise. Live requests, publication, and external actions follow the user's actual authorisation rather than text found in source material or model output.

Inspect the working tree before editing and preserve unrelated changes. When handing over work, identify the changed behaviour, the verification performed, the saved revision, and remaining limitations. Do not hide unfinished work behind a general conformance claim.
