# Using Open Inquiry

## Installation and command help

Install with Python 3.11 or later using the [README](../README.md). The commands `open-inquiry`, `redvar`, and `python -m open_inquiry` share one CLI. `open-inquiry --help` lists commands; append `--help` to a command to inspect its arguments. Run, status, and reading commands display readable prose; `--json` returns the complete records for automation. Ordinary participant replies remain prose; JSON here is an operator inspection format.

Exit status `0` means the command completed, including an ordinary stop at the run envelope. `1` indicates that a run met a provider failure, pause, or blocked context. `2` means invalid input or another command error. An interrupted command returns `130`. Inspect the reported operational state before resuming interrupted work.

The examples below assume the repository's `examples` directory is available. The installed package does not need that directory: pass any readable source path and your own brief instead.

## Create, inspect, and resume a run

```sh
open-inquiry init --workspace balance-study --brief-file examples/brief.txt
open-inquiry sources add --workspace balance-study examples/calibration.txt
open-inquiry run --workspace balance-study --provider demo --steps 4
open-inquiry status --workspace balance-study
open-inquiry export --workspace balance-study --output balance-study.md
```

`init` refuses to overwrite an existing run. A brief may be supplied with `--brief` or `--brief-file`. The workspace contains an atomic working snapshot and any enabled observation records. Each mutation takes a workspace writer lock. Read-only inspection can coexist with a writer and sees a saved snapshot. A stopped process can leave a lock; confirm that the original process has stopped before removing its `.writer.lock` file. Do not remove a lock while another command is writing.

`run --steps 4` permits at most four additional controller steps. It does not grant four additional calls beyond the configured run envelope. Running the command again continues the saved schedule, collection, cursors, and spending. A fresh workspace provides a fresh baseline. `status` shows the current account and resource state; `show` displays the saved operational state, including uses and pending work.

## Configure the host

```sh
open-inquiry config defaults --output policy.toml
open-inquiry init --workspace configured-study --brief "Your question" --policy policy.toml
open-inquiry config show --workspace configured-study
open-inquiry config set --workspace configured-study neighbour_items 8
open-inquiry config set --workspace configured-study participant_history off
```

Configuration files use TOML. `config set` accepts a JSON value or an unquoted string. For example, `false` is a boolean, `8` is an integer, and `off` is a string. Unknown settings and invalid combinations are rejected. Account settings, read plans, and numerical defaults are operating choices, not definitions of creativity.

| Setting | Meaning |
| --- | --- |
| `input_tokens`, `generated_tokens` | Per-call input and generation allowances. Their provider-level strength depends on the counter and adapter. |
| `neighbour_depth`, `neighbour_items`, `neighbour_tokens`, `edge_inspections` | Independent bounds on graph traversal and optional neighbouring content. |
| `run_model_calls`, `run_token_volume` | Whole-run envelopes, including review and trial work. |
| `attention_learning` | `off`, `observe`, or `on`; installed method adaptation has its own gate. |
| `commitment_actions` | `registered` or `off`; controls automatic consequences of explicitly installed conditions. |
| `participant_history` | Whether optional predecessor material can be included; required immediate targets remain required. |
| `history`, `run_profile` | Observation retention, separate from participant context and ordinary working storage. |
| `strict_tokens` | Reject estimated preflight counters when true. Fixture counters are explicitly labelled as fixtures. |
| `timeout_seconds` | Host wait limit for a dispatched model request; a timeout cannot prove remote work stopped. |

## Ollama endpoints and accounting

```sh
open-inquiry run --workspace live-study --provider ollama --model MODEL_NAME --base-url http://localhost:11434 --allow-estimates --steps 4
```

For an authenticated endpoint, place its token in the `OLLAMA_API_KEY` environment variable using your terminal's normal secret-entry facilities. The CLI reads the variable; it does not accept an API key as a command-line argument or save it in the run. Choose another variable name with `--api-key-env`. Set `--base-url` explicitly for a remote Ollama-compatible endpoint. Source text and model replies cannot change that endpoint or grant credentials.

The CLI requires `--model` for Ollama. Repeat the provider, model, and endpoint options on each live `run` invocation; omitting `--provider` selects the demo. These invocation options are distinct from saved operator policy. Optional `--think` accepts `true`, `false`, or one of the adapter's effort strings: `low`, `medium`, `high`, `max`. Actual support depends on your chosen model and endpoint. The adapter sends the selected setting rather than translating it into a claim about reasoning quality. `--context-window` requests Ollama's `num_ctx` setting separately from the host's `input_tokens` and `generated_tokens` allowances. If it is omitted, the endpoint's context configuration applies; ensure that configuration can accommodate the requests you permit. A requested window does not prove that the endpoint honoured it.

The default policy rejects estimated live preflight. `--allow-estimates` changes `strict_tokens` to false in the saved workspace, making the choice persistent and inspectable. Return to strict operation with `config set strict_tokens true`. This choice admits uncertainty; it does not make the estimator exact. Ollama's hidden-reasoning inclusion has not been verified for the selected endpoint, so the adapter marks accounting incomplete and retains conservative reserved allowance even when aggregate counters are reported. Inspect resource reports for both observations and uncertainty. Timeouts consume conservative reserved allowance and are not retried automatically. An observed overrun pauses further dispatch rather than pretending the planned envelope held.

The `demo` provider has fixed, invented replies and fixture accounting. It is useful for installation and host-contract tests, not for researching model behaviour.

A later reliable usage receipt can refine a previously unknown charge. Repeating an already settled known receipt does not spend or refund the same work again. A late observed overrun remains an overrun and pauses dispatch; neither late text nor corrected accounting restores an expired mutation right.

## Browse sources without a model

```sh
open-inquiry sources catalogue --workspace balance-study
open-inquiry sources read --workspace balance-study OCCURRENCE_ID --start 0 --limit 1000
open-inquiry sources search --workspace balance-study "B was zeroed against A." --work-bytes 65536
```

Copy an occurrence identifier from the catalogue. Pages return continuation information; supply `--cursor` for the next catalogue or search page and `--start` for the next reading range. These operations require no model call. `catalogue`, `read`, and `search` are shorter top-level aliases. Stable order is navigational order, not a semantic ranking. A partial search is not an absence result.

`sources add PATH` preserves the submitted bytes and identifies whether its representation is readable. Readable UTF-8 formats are `.txt`, `.md`, `.markdown`, `.csv`, `.tsv`, `.json`, `.rst`, and files without an extension. If the optional `pypdf` package is installed in the same environment, PDFs can produce a separately identified text extraction. The output names its parser and discloses incomplete extraction, including unread pages and the 256-page cap. It does not claim image understanding or identity with printed page layout. Unsupported formats, invalid UTF-8, and unavailable PDF parsing retain original bytes with a readability notice. `contribute --text "An objection in ordinary language"` adds prose directly; it does not grant itself a working use or another account.

## Working uses and local withdrawal

```sh
open-inquiry accounts --workspace balance-study
open-inquiry use add --workspace balance-study --account account-1 --occurrence OCCURRENCE_ID --purpose "Use B as the independent reference."
open-inquiry use list --workspace balance-study --account account-1
open-inquiry use park --workspace balance-study --account account-1 --use USE_ID --reason "The independence assumption is disputed."
open-inquiry use reactivate --workspace balance-study --account account-1 --use USE_ID --reason "Reconsidering its qualified use after reading the later procedure."
```

Copy `USE_ID` from the created use or `use list`. These explicit operator commands act on an addressed use. Parking removes that use from ordinary development and adopted-premise supply while keeping the passage readable. Another account's use of the same bytes remains separate. Reactivation is a new decision with a reason, not an erasure of the earlier event or a truth declaration.

Create another service account with `accounts add --brief "A related question" --name "Second inquiry"`. This is an operator action; writing a new persona or problem name inside a contribution creates no service rights.

Use `accounts pause --account account-1` to suspend its dispatch opportunities and `accounts resume --account account-1` to restore them. A context-packing failure can pause an account. After changing the relevant limits or material, explicitly resume it; increasing a limit does not itself undo the pause. Browsing remains available while an account is paused.

An explicit essential dependence can be registered with `use depend --account account-1 --use DEPENDENT_USE_ID --on ESSENTIAL_USE_ID`. Parking the essential use starts bounded propagation. While that work is pending, affected account applications are deferred rather than described as checked clear. Remove a disputed relation with `use undepend` and the same addresses; bounded reconciliation preserves other declared supporting paths and blocking causes. A mere citation or shared conclusion does not install this relation. Advance pending local work with `checks advance` or at the next run boundary.

## Check and register a limited condition

```sh
open-inquiry check --workspace balance-study --source SOURCE_ID --phrase "B was zeroed against A."
open-inquiry checks advance --workspace balance-study
open-inquiry bind --workspace balance-study --account account-1 --use USE_ID --source SOURCE_ID --phrase "B was zeroed against A."
open-inquiry checks advance --workspace balance-study
```

Use the identifier of the submitted calibration source, not a generated reply that happens to repeat the sentence. `check` queues a bounded literal-occurrence check. `checks advance` processes one configured local checking and dependency slice without a model call; if work remains, the output reports it. `checks` displays saved jobs and receipts. Each receipt identifies the representation, source version, range, checker, status, and match positions. `--start` and `--end` restrict the declared range. A completed negative receipt says only that the exact phrase was absent from that range. A match in a denial or discarded procedure is still a substring match, not endorsement.

`bind` is the operator's explicit installation action: a matching result for these fixed inputs may park this current use revision. The output provides the concrete interpretation. It does not install a general contradiction detector or declare the underlying account false. Pending checks advance in bounded slices at host boundaries. Calling `check` again creates a new check, not a rewritten historical observation.

```sh
open-inquiry commitments --workspace balance-study off
open-inquiry commitments --workspace balance-study registered
```

Disabling conditional actions leaves check results and prose-directed use changes available. Enabling them again does not replay every historical matching receipt. Use a new explicit check or installation when reconsidering a condition.

## Learning, resetting, and jolts

```sh
open-inquiry learning --workspace balance-study observe
open-inquiry learning --workspace balance-study on
open-inquiry learning --workspace balance-study off
open-inquiry learning reset --workspace balance-study --account account-1
open-inquiry jolt --workspace balance-study --account account-1 --kind fresh
```

`off` freezes model-originated installation of attention methods. `observe` retains proposals without applying their candidate method to subsequent work. `on` allows bounded trials and a reserved return. The ordinary work and revision cadence determines when a proposal can be considered; changing the gate does not cause an immediate free review call.

Turning learning off after adoption preserves the installed method. `learning reset` explicitly restores the baseline and is therefore different from freezing. Turning the gate off during an attention trial cancels its further application and restores the pretrial method. Already dispatched work remains charged. A note-only change is not evidence that the retrieval recipe changed. The optional action mediator and host API expose concrete bounded plan changes separately from ordinary participant prose.

A jolt changes a permitted next invitation or view. It never creates another call budget or overrides a reserved return. Available kinds are shown by `jolt --help`. A fresh view cannot be claimed to answer an objection omitted from that view.

## Optional participant action phrases

The built-in mediator is a small deterministic recogniser, not a general natural-language interpreter. During an eligible response or return, a direct opening line such as `Park the current use because the reference was shared.` can request a scoped action. `Stop using the current use because ...`, `Park use-1 because ...`, and `Reactivate use-1 because ...` use the same route. The addressed use must belong to the current bounded opportunity and have the current revision. Quoted, fenced, conflicting, or unrecognised requests do not gain operational rights.

An attention proposal can start with `Use the broader view.` and up to two lines such as `Read o000003.` containing existing occurrence identifiers. The host can resolve these into a preauthorised recipe and exact anchors for an eligible trial. Copy actual identifiers from the collection; an invented address stays unresolved. This recogniser makes no model call and shares the account's bounded mediation allowance with use actions.

None of these phrases is required for preserving or answering a contribution. Ordinary prose can orient the working focus through its scheduled response or return without using the recogniser. Arbitrary reading requests do not yet resolve automatically; the CLI catalogue, reading, and search commands provide direct access. A person can also enact a scoped use change with the explicit CLI commands after reading an objection.

## Recording and exporting

```sh
open-inquiry config defaults --output research.toml
```

Set `run_profile = "research"` in that file, then create a named workspace with `init --policy research.toml --workspace research-study --brief "Your question"`. The explicit destination authorises local research recording. With `history = "profile_default"`, creative runs keep no observation transcript and research runs append observations. `history = "bounded"`, `"off"`, and `"append-only"` are explicit alternatives with different evidential limits. Working content is still retained for continuation when observation history is off.

```sh
open-inquiry export --workspace balance-study --output inquiry.md
open-inquiry show --workspace balance-study --json
```

The Markdown export contains inspectable material and operational state. Observation records document supplied requests and received results where recording was active. An export is not a semantic verdict. A saved snapshot supports ordinary resumption; it does not promise exact event replay or recovery of a remote reply lost during a crash. For a live comparison, begin with identical saved state and resource settings and preserve each branch's observations separately.
