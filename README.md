# DeepReason Redvar

Open Inquiry is a Python CLI for keeping explanations, criticisms, sources, and revisable working uses in a shared collection. Participants can reply in ordinary prose. A deterministic controller limits context and expenditure, rotates work, and carries permitted problem or attention changes into later requests. It does not rank ideas or certify truth, creativity, or understanding.

This repository implements a bounded local deployment of the supplied [Open Inquiry executable specification 0.4](docs/spec/open-inquiry-0.4.md). Read [implementation limits](docs/limitations.md) before treating a mechanical test as evidence about a live model.

## Install

Use Python 3.11 or later. The runtime has no third-party Python dependencies. From the repository directory:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
open-inquiry --help
```

For an ordinary installation directly from GitHub:

```sh
python3 -m pip install git+https://github.com/AHepi/DeepReason-Redvar.git
```

`redvar` is a shorter alias. `python -m open_inquiry` works if your shell cannot find the installed command. On Windows, activate the virtual environment with `.venv\Scripts\activate` instead. On Android, these commands need a Python terminal environment such as Termux; they are not Android application commands.

## Try it without an API key

```sh
open-inquiry init --brief "Why do two balances disagree?"
open-inquiry run --provider demo --steps 4
open-inquiry status
open-inquiry export --output inquiry.md
```

The demo uses deterministic fixture replies. It exercises the application without calling a model and is not an inquiry result or a provider-token measurement. The default working directory is `.open-inquiry`. Use `--workspace balance-study` on any command to keep a named run. Repeating `run` resumes that saved state and its existing expenditure counters.

## Use a model

The included live adapter targets Ollama's chat API. Start an Ollama server with a model available, then name that model explicitly:

```sh
open-inquiry init --workspace live-study --brief "Explain the disagreement between these measurements."
open-inquiry sources add --workspace live-study examples/calibration.txt
open-inquiry run --workspace live-study --provider ollama --model MODEL_NAME --allow-estimates --steps 4
```

`MODEL_NAME` is the model identifier your endpoint provides. `--allow-estimates` explicitly selects estimated token preflight for that saved run. The adapter has no verified provider tokenizer, so this mode cannot promise a hard provider-token cap. Generation settings, observed usage, and the host's accounting remain visible. See [usage](docs/usage.md) for endpoint configuration, source reading, conditional parking, learning controls, and research recording.

## Read and change the implementation

Start with the [code map](docs/code-map.md), which connects behavioural contracts to source files and tests. The [audit and change workflow](docs/audit-and-change.md) explains how to investigate a defect, change the smallest responsible component, and update its documentation and evidence. The specification remains a separate reference rather than being rewritten to fit implementation shortcuts.

```sh
python -m unittest discover -s tests -v
```

The tests exercise local contracts with fixtures. A passing suite does not establish explanatory progress or live-provider conformance.
