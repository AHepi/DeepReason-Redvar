"""Operator CLI: explicit actions, saved state, and no compulsory prose schema.

See docs/usage.md for runnable examples and docs/audit-and-change.md before
changing command contracts. All workspace mutations hold the single-writer
lock for their complete lifetime, including provider dispatch and settlement.
"""

from __future__ import annotations

import argparse
from contextlib import nullcontext
import json
from pathlib import Path
import sys

from . import __version__
from .config import default_toml, load_policy


def _positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def _nonnegative(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be a nonnegative integer")
    return number


def _json_value(value):
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _cursor(value):
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise argparse.ArgumentTypeError("copy the JSON next_cursor returned by search") from error
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("a search cursor must be a JSON object")
    return parsed


def _common(parser, *, initial=False):
    # Suppressed subparser defaults preserve options supplied before commands.
    parser.add_argument("--workspace", "-w", type=Path,
                        default=Path(".open-inquiry") if initial else argparse.SUPPRESS,
                        help="saved run directory (default: .open-inquiry)")
    parser.add_argument("--json", action="store_true",
                        default=False if initial else argparse.SUPPRESS,
                        help="emit JSON records for inspection or automation")


def _command(subparsers, name, help_text, **kwargs):
    parser = subparsers.add_parser(name, help=help_text, description=help_text, **kwargs)
    _common(parser)
    return parser


def _brief(parser):
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--brief", "-b", help="ordinary-language starting question")
    group.add_argument("--brief-file", type=Path, help="UTF-8 file containing the starting brief")


def _account_arg(parser):
    parser.add_argument("--account", help="account identifier; optional when exactly one account exists")


def _catalogue_args(parser):
    parser.add_argument("--cursor", type=_nonnegative, default=0, help="next catalogue offset")
    parser.add_argument("--limit", type=_positive, default=10, help="maximum records in this page")


def _read_args(parser):
    parser.add_argument("occurrence", help="source or contribution identifier from the catalogue")
    parser.add_argument("--start", type=_nonnegative, default=0, help="starting character offset")
    parser.add_argument("--limit", type=_positive, default=4000, help="maximum characters to open")


def _search_args(parser):
    parser.add_argument("phrase", help="nonempty literal phrase")
    parser.add_argument("--cursor", type=_cursor, help="previous JSON next_cursor, enclosed in single quotes")
    parser.add_argument("--page-size", type=_positive, default=10)
    parser.add_argument("--work-bytes", type=_positive, default=65536,
                        help="maximum source bytes examined in this invocation")
    parser.add_argument("--source", action="append", dest="source_ids",
                        help="limit search to this occurrence; repeat for several sources")


def _predicate_args(parser):
    parser.add_argument("--source", required=True, help="fixed source occurrence identifier")
    parser.add_argument("--phrase", required=True, help="exact nonempty character sequence")
    parser.add_argument("--start", type=_nonnegative, default=0)
    parser.add_argument("--end", type=_nonnegative, help="exclusive end of the declared character range")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="open-inquiry",
        description="Prose-first inquiry with revisable use and bounded attention.",
        epilog="Quick start: open-inquiry init --brief 'Your question'; then open-inquiry run --provider demo --steps 4. See docs/usage.md.",
    )
    _common(parser, initial=True)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    init = _command(commands, "init", "Create a saved run with a prose brief.")
    _brief(init)
    init.add_argument("--policy", type=Path, help="operator configuration in TOML")

    run = _command(commands, "run", "Resume bounded work using a demo or an Ollama model.")
    run.add_argument("--provider", choices=("demo", "ollama"), default="demo")
    run.add_argument("--model", help="required for Ollama; exact model identifier at the endpoint")
    run.add_argument("--base-url", default="http://localhost:11434", help="operator-selected Ollama endpoint")
    run.add_argument("--api-key-env", default="OLLAMA_API_KEY", help="environment variable containing a token")
    run.add_argument("--think", type=_json_value, help="provider-supported boolean or effort string")
    run.add_argument("--context-window", type=_positive,
                     help="optional Ollama num_ctx request; separate from host input and generation allowances")
    run.add_argument("--allow-estimates", action="store_true",
                     help="explicitly allow estimated token preflight in this saved run")
    run.add_argument("--steps", type=_positive, help="maximum additional controller steps; default: available run envelope")

    _command(commands, "status", "Show current scheduling and expenditure state.")
    _command(commands, "show", "Inspect the saved operational state.")
    contribute = _command(commands, "contribute", "Retain ordinary prose without requiring a working use.")
    text = contribute.add_mutually_exclusive_group(required=True)
    text.add_argument("--text")
    text.add_argument("--file", type=Path, help="UTF-8 prose file")
    contribute.add_argument("--label", default="")

    accounts = _command(commands, "accounts", "List service accounts or explicitly create one.")
    account_commands = accounts.add_subparsers(dest="accounts_action")
    add_account = _command(account_commands, "add", "Create an operator-authorised service account.")
    _brief(add_account)
    add_account.add_argument("--name")
    for action in ("pause", "resume"):
        operation = _command(account_commands, action, f"{action.capitalize()} dispatch opportunities for an account.")
        _account_arg(operation)

    sources = _command(commands, "sources", "Ingest, browse, open, or search the retained collection.")
    source_commands = sources.add_subparsers(dest="sources_action", required=True)
    add_source = _command(source_commands, "add", "Preserve a local source and disclose its readable representation.")
    add_source.add_argument("path", type=Path)
    _catalogue_args(_command(source_commands, "catalogue", "Browse a stable page of the collection."))
    _read_args(_command(source_commands, "read", "Open a character range from an occurrence."))
    _search_args(_command(source_commands, "search", "Search a bounded slice and return a continuation cursor."))
    _catalogue_args(_command(commands, "catalogue", "Alias for sources catalogue."))
    _read_args(_command(commands, "read", "Alias for sources read."))
    _search_args(_command(commands, "search", "Alias for sources search."))

    check = _command(commands, "check", "Request a scoped literal-occurrence check, with no automatic truth claim.")
    _predicate_args(check)
    check.add_argument("--comparison", default="literal", help="installed comparison (baseline: literal)")
    check.add_argument("--checker-version", default="1")
    checks = _command(commands, "checks", "Inspect checks or advance bounded local checking without a model call.")
    check_commands = checks.add_subparsers(dest="checks_action")
    _command(check_commands, "advance", "Process one configured slice of check and dependency work; apply only authorised consequences.")
    bind = _command(commands, "bind", "Authorise parking one current use if a fixed literal condition matches.")
    _predicate_args(bind)
    _account_arg(bind)
    bind.add_argument("--use", required=True, help="use identifier; the host fixes its current revision at installation")

    use = _command(commands, "use", "Inspect or change an addressed working use.")
    use_commands = use.add_subparsers(dest="use_action", required=True)
    list_use = _command(use_commands, "list", "Inspect account-local working uses.")
    _account_arg(list_use)
    add_use = _command(use_commands, "add", "Add a use with its purpose in ordinary prose.")
    _account_arg(add_use)
    add_use.add_argument("--occurrence", required=True)
    add_use.add_argument("--purpose", required=True)
    for action in ("park", "reactivate"):
        use_action = _command(use_commands, action, f"{action.capitalize()} one use without changing the truth status of its content.")
        _account_arg(use_action)
        use_action.add_argument("--use", required=True)
        use_action.add_argument("--reason", required=True, help="ordinary-language reason for this decision")
    for action, verb in (("depend", "Declare"), ("undepend", "Remove")):
        depend = _command(use_commands, action, f"{verb} an essential operational dependence between two uses in this account.")
        _account_arg(depend)
        depend.add_argument("--use", required=True, help="dependent use identifier")
        depend.add_argument("--on", required=True, dest="essential", help="essential supporting use identifier")

    learning = _command(commands, "learning", "Inspect or change the attention gate; reset is separate from freezing.")
    learning.add_argument("action", nargs="?", choices=("off", "observe", "on", "reset"))
    _account_arg(learning)
    commitments = _command(commands, "commitments", "Inspect or change automatic consequences of installed conditions.")
    commitments.add_argument("mode", nargs="?", choices=("off", "registered"))
    jolt = _command(commands, "jolt", "Request a bounded change to a future opportunity.")
    _account_arg(jolt)
    jolt.add_argument("--kind", default="fresh", choices=("fresh", "question", "method", "evidence"))

    config = _command(commands, "config", "Inspect validated policy or change an operator setting.")
    config_commands = config.add_subparsers(dest="config_action", required=True)
    defaults = _command(config_commands, "defaults", "Print or write an editable baseline TOML configuration.")
    defaults.add_argument("--output", type=Path)
    _command(config_commands, "show", "Show the saved effective operator policy.")
    set_config = _command(config_commands, "set", "Change a setting with a JSON value or ordinary string.")
    set_config.add_argument("key")
    set_config.add_argument("value", type=_json_value)

    export = _command(commands, "export", "Export retained inquiry material and available context as Markdown.")
    export.add_argument("--output", "-o", type=Path, help="destination; omit to print Markdown")
    return parser


def _brief_text(args):
    return args.brief if args.brief is not None else args.brief_file.read_text(encoding="utf-8")


def _accounts(engine):
    accounts = engine.state["accounts"]
    return list(accounts.values()) if isinstance(accounts, dict) else accounts


def _account(engine, identifier):
    accounts = _accounts(engine)
    if identifier is None:
        if len(accounts) != 1:
            raise ValueError("Specify --account; use 'accounts' to inspect available identifiers.")
        return accounts[0]
    for account in accounts:
        if account["id"] == identifier:
            return account
    raise ValueError(f"Unknown account: {identifier}")


def _write(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def _mutates(args):
    if args.command in {"status", "show", "catalogue", "read", "search", "export"}:
        return False
    if args.command == "sources":
        return args.sources_action == "add"
    if args.command == "accounts":
        return args.accounts_action is not None
    if args.command == "config":
        return args.config_action == "set"
    if args.command == "use":
        return args.use_action != "list"
    if args.command == "checks":
        return args.checks_action == "advance"
    if args.command == "learning":
        return args.action is not None
    if args.command == "commitments":
        return args.mode is not None
    return True


def _execute(args):
    # Lazy loading keeps help and baseline config usable without a saved run.
    if args.command == "config" and args.config_action == "defaults":
        contents = default_toml()
        if args.output:
            _write(args.output, contents)
            return {"output": str(args.output), "format": "toml"}
        return contents

    from .engine import Engine
    from .persistence import workspace_lock

    with workspace_lock(args.workspace) if _mutates(args) else nullcontext():
        if args.command == "init":
            engine = Engine.create(_brief_text(args),
                                   policy=load_policy(args.policy) if args.policy else None,
                                   directory=args.workspace)
            engine.save()
            return {"workspace": str(args.workspace), "created": True,
                    "accounts": [{"id": item["id"], "name": item.get("name")} for item in _accounts(engine)],
                    "next": "Run 'open-inquiry run --provider demo --steps 4' with this workspace."}

        engine = Engine.load(args.workspace, recover=_mutates(args))
        result = _dispatch(engine, args)
        if _mutates(args):
            engine.save()
        return result


def _dispatch(engine, args):
    command = args.command
    if command == "run":
        from .providers import DemoProvider, OllamaProvider
        if args.provider == "ollama":
            if not args.model:
                raise ValueError("Ollama requires --model MODEL_NAME; choose a model available at your endpoint.")
            if engine.policy["strict_tokens"] and not args.allow_estimates:
                raise ValueError("Ollama preflight is estimated. Use --allow-estimates to acknowledge this limit, or select a provider with verified bounds.")
            provider = OllamaProvider(args.model, base_url=args.base_url,
                                      api_key_env=args.api_key_env, think=args.think,
                                      context_window=args.context_window)
        else:
            provider = DemoProvider()
        if args.allow_estimates and engine.policy["strict_tokens"]:
            engine.update_policy({"strict_tokens": False})
        results = engine.run(provider, steps=args.steps)
        return {"provider": provider.name, "counter": provider.count_kind,
                "steps": results, "status": engine.status()}
    if command == "status":
        return engine.status()
    if command == "show":
        return engine.state
    if command == "accounts":
        if args.accounts_action == "add":
            identifier = engine.add_account(_brief_text(args), name=args.name)
            return {"account": identifier}
        if args.accounts_action in {"pause", "resume"}:
            account = _account(engine, args.account)
            paused = args.accounts_action == "pause"
            engine.set_account_paused(account["id"], paused)
            return {"account": account["id"], "paused": paused}
        return _accounts(engine)
    if command == "contribute":
        text = args.text if args.text is not None else args.file.read_text(encoding="utf-8")
        identifier = engine.add_text(text, label=args.label)
        return {"occurrence": identifier}
    if command == "sources" or command in {"catalogue", "read", "search"}:
        operation = args.sources_action if command == "sources" else command
        if operation == "add":
            identifier = engine.add_source(args.path)
            occurrence = engine.collection.get(identifier)
            return {key: occurrence.get(key) for key in
                    ("id", "label", "origin", "readable", "representation", "version",
                     "extraction_complete", "readability_note", "parser")}
        if operation == "catalogue":
            return engine.collection.catalogue(cursor=args.cursor, limit=args.limit)
        if operation == "read":
            return engine.collection.read(args.occurrence, start=args.start, limit=args.limit)
        return engine.collection.search(args.phrase, cursor=args.cursor,
                                        page_size=args.page_size, work_bytes=args.work_bytes,
                                        source_ids=args.source_ids)
    if command == "check":
        identifier = engine.check(args.source, args.phrase, start=args.start, end=args.end,
                                   comparison=args.comparison, version=args.checker_version)
        return {"check": identifier, "status": "queued",
                "next": "Use 'checks advance' for bounded local work without a model, or continue 'run'."}
    if command == "checks":
        if args.checks_action == "advance":
            receipts = engine.process_checks()
            dependencies = engine.process_dependencies()
            return {"receipts": receipts, "pending_checks": len(engine.checker.data["queue"]),
                    "dependencies": dependencies, "model_calls": 0}
        return {"checks": engine.checker.data["checks"], "receipts": engine.checker.data["receipts"],
                "pending_checks": len(engine.checker.data["queue"])}
    if command == "bind":
        account = _account(engine, args.account)
        binding = engine.bind(account["id"], args.use, args.source, args.phrase,
                              start=args.start, end=args.end)
        return {"binding": binding,
                "interpretation": f"A matching literal occurrence in the fixed source {args.source}, within the installed range, may park the current revision of use {args.use} in {account['id']}. This does not decide whether the account is false."}
    if command == "use":
        account = _account(engine, args.account)
        if args.use_action == "list":
            return {"account": account["id"], "uses": account["uses"]}
        if args.use_action == "add":
            return {"use": engine.add_use(account["id"], args.occurrence, args.purpose)}
        if args.use_action == "depend":
            return engine.add_dependency(account["id"], args.use, args.essential)
        if args.use_action == "undepend":
            return engine.remove_dependency(account["id"], args.use, args.essential)
        return engine.change_use(account["id"], args.use, args.use_action, args.reason)
    if command == "learning":
        if args.action == "reset":
            engine.reset_attention(account_id=args.account)
        elif args.action:
            engine.set_gate(args.action)
        return {"attention_learning": engine.policy["attention_learning"],
                "reset": args.action == "reset"}
    if command == "commitments":
        if args.mode:
            engine.set_commitments(args.mode)
        return {"commitment_actions": engine.policy["commitment_actions"]}
    if command == "jolt":
        return engine.jolt(account_id=args.account, kind=args.kind)
    if command == "config":
        if args.config_action == "set":
            engine.update_policy({args.key: args.value})
        return engine.policy
    if command == "export":
        contents = engine.export_markdown()
        if args.output:
            _write(args.output, contents)
            return {"output": str(args.output), "format": "markdown"}
        return contents
    raise ValueError(f"Unsupported command: {command}")


def _emit_status(status):
    resources = status["resources"]
    print(f"Open Inquiry {status['engine_version']} | profile: {status['profile']} | attention: {status['attention_learning']}")
    print(f"Calls: {resources['used_calls']}/{resources['max_calls']} used; "
          f"{resources['reserved_calls']} reserved; {resources['remaining_calls']} available.")
    print(f"Token-volume units: {resources['charged_tokens']} charged; "
          f"{resources['reserved_tokens']} reserved; {resources['remaining_tokens']} available.")
    print(f"Calls with unknown consumption: {resources['unknown_calls']}. "
          "Units and certainty depend on the provider.")
    print(f"Recording: {status['history']}; participant history: {status['participant_history']}; "
          f"conditional actions: {status['commitment_actions']}.")
    if status["recording_gap"]:
        print("A recording gap limits the retained observations.")
    if resources["paused"]:
        print(f"Dispatch paused: {resources.get('pause_reason') or 'inspect the saved state'}.")
    if status.get("inflight"):
        print(f"Saved in-flight request: {status['inflight']}; read-only inspection leaves it unchanged.")
    for account in status["accounts"]:
        active = sum(use["disposition"] == "active" for use in account["uses"])
        parked = sum(use["disposition"] == "parked" for use in account["uses"])
        blocked = sum(bool(use.get("blocked")) for use in account["uses"])
        print(f"\n{account['id']} ({account['name']}): {account['phase']}, cycle {account['cycle']}, "
              f"view {account['recipe']}; {active} active and {parked} parked uses, {blocked} blocked.")
        if account["paused"]:
            print("This account's dispatch opportunities are paused.")
        print(f"Focus: {account['focus']}. Method: {account['method']}.")
    print(f"\nRetained occurrences: {status['retained_occurrences']}.")
    notices = status.get("notices", [])
    if notices:
        print("\nRecent operating notices:")
        print("\n".join(notices[-5:]))
        if len(notices) > 5:
            print("Use status --json to inspect all retained notices.")


def _emit(result, *, as_json=False):
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif isinstance(result, dict) and {"provider", "counter", "steps"} <= result.keys():
        print(f"Provider: {result['provider']}. Counter: {result['counter']}.")
        if result["counter"] == "fixture":
            print("Demo/fixture responses and accounting are synthetic; no live model was called.")
        for step in result["steps"]:
            label = " ".join(str(step[key]) for key in ("account", "opportunity", "invitation") if key in step)
            print(f"\n{label + ': ' if label else ''}{step['status']}")
            if "response" in step:
                print(step["response"] if step["response"] else "An empty reply was retained.")
            if step.get("notice"):
                print(step["notice"])
        print()
        _emit_status(result["status"])
    elif isinstance(result, dict) and {"engine_version", "resources", "accounts"} <= result.keys():
        _emit_status(result)
    elif isinstance(result, dict) and {"id", "text", "start", "end", "representation"} <= result.keys():
        print(f"{result['id']} | {result['representation']} | characters {result['start']}:{result['end']}")
        if result.get("status") == "unavailable":
            print(result.get("reason", "Readable representation unavailable."))
        else:
            print()
            print(result["text"])
            if result.get("next_cursor") is not None:
                print(f"\nContinue with --start {result['next_cursor']}.")
            elif not result["complete"]:
                print("\nThe readable representation ends here; source extraction remains incomplete.")
            else:
                print("\nEnd of the declared readable representation.")
    elif isinstance(result, dict) and "binding" in result and isinstance(result["binding"], dict):
        binding = result["binding"]
        print(f"Installed {binding['id']}; conditional action {'enabled' if binding['enabled'] else 'disabled by policy'}.")
        print(binding["readback"])
        print(f"Check {binding['check_id']} is queued. Use checks advance or continue run.")
    elif isinstance(result, dict) and result.get("status") == "queued" and "check" in result:
        print(f"Check {result['check']} is queued. {result['next']}")
    elif isinstance(result, str):
        print(result, end="" if result.endswith("\n") else "\n")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = _execute(args)
        _emit(result, as_json=args.json)
        if args.command == "run" and any(step["status"] in {"provider-error", "paused", "blocked"}
                                         for step in result["steps"]):
            return 1
        return 0
    except KeyboardInterrupt:
        print("Interrupted. Inspect the saved status before resuming; dispatched work may remain charged.", file=sys.stderr)
        return 130
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print(f"open-inquiry: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
