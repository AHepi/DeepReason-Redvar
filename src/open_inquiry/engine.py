"""Deterministic operational controller for specification Parts II–IX.

Read this module in dispatch order: ``prepare`` builds a bounded invitation,
``step`` dispatches its reserved call, ``receive`` retains prose before using a
current grant, and ``_advance`` enacts a bounded return. Uses and predicates live
in :mod:`open_inquiry.uses`; nothing here computes intellectual merit.

Persistence supports resumption, not deterministic reproduction of remote text.
The sequential CLI holds a workspace writer lock across the complete command.
"""

from copy import deepcopy
import json
from pathlib import Path

from .collection import Collection
from .checking import Checker
from .config import validate, effective_history
from .context import compile_cut
from .cursors import CursorTransaction
from .mediation import resolve_use, resolve_plan
from .persistence import FORMAT_VERSION, Recorder, atomic_json, read_json
from .providers import ProviderResult
from .resources import Ledger, BudgetExceeded
from .uses import UseOperations


BASELINE_METHOD = "Read the working question and original sources. Keep objections and their targets together. Ask to reopen missing material."
INVITATIONS = (
    ("develop", "Develop the current account or reconsider its question. Explain freely; no format or test is required."),
    ("examine", "Examine the supplied contribution. What might be mistaken, and why would that matter? A criticism is itself open to criticism."),
    ("respond", "Respond to the original objection and its target. You may revise the question, retain a view, suspend, or explain a withdrawal. Ordinary prose is sufficient."),
    ("read", "Read the supplied original material and its qualifications. Explain anything it brings into question, or request another passage."),
    ("variation", "Vary a content-bearing commitment in the supplied account. Keep its problem, scope and explanatory job visible. Explain what changes; renaming alone is not informative. You may challenge this invitation."),
    ("explore", "Explore associations, imagined situations or unfinished ideas. Immediate usefulness, a test and a finished explanation are not required. Imagined events remain imagined."),
)


class Engine(UseOperations):
    """Own current host rights, independent of all participant self-descriptions."""

    def __init__(self, state, directory=None):
        self.state = state
        self.directory = Path(directory) if directory else None
        self.policy = validate(state["policy"])
        self.state["policy"] = self.policy
        self.collection = Collection(state["collection"],
            max_source_bytes=self.policy["max_source_bytes"],
            max_collection_bytes=self.policy["max_collection_bytes"])
        self.checker = Checker(state["checker"])
        self.ledger = Ledger(state["ledger"])
        self.recorder = Recorder(self.directory, effective_history(self.policy), self.policy["history_limit"])

    @classmethod
    def create(cls, brief, policy=None, directory=None):
        policy = validate(policy)
        if effective_history(policy) != "off" and directory is None:
            raise ValueError("Recording requires an explicit run directory; init --workspace supplies that destination")
        if directory and (Path(directory) / "state.json").exists():
            raise ValueError("A run already exists at this workspace")
        state = {"format_version": FORMAT_VERSION, "engine_version": "0.4.0",
                 "policy": policy, "epoch": 1, "next_ids": {}, "accounts": [],
                 "account_cursor": 0, "collection": Collection().data,
                 "checker": Checker().data,
                 "ledger": Ledger(max_calls=policy["run_model_calls"], max_tokens=policy["run_token_volume"]).data,
                 "bindings": {}, "dependency_queue": [], "grants": {},
                 "notices": [], "recording_gap": False, "inflight": None,
                 "last_dispatch": None, "dispatch_count": 0}
        engine = cls(state, directory)
        engine.add_account(brief)
        engine._event("run-created", policy=deepcopy(policy), initial_collection=deepcopy(engine.collection.data),
                      accounting="Fixture units and estimated production routes are separately identified per dispatch.")
        engine.save()
        return engine

    @classmethod
    def load(cls, directory, recover=True):
        path = Path(directory) / "state.json"
        if not path.exists():
            raise ValueError("No saved run here. Start with open-inquiry init --brief 'Your question'.")
        state = read_json(path)
        if state.get("format_version") != FORMAT_VERSION:
            raise ValueError("Unsupported snapshot format; migrate explicitly before resuming")
        engine = cls(state, directory)
        # An interrupted process cannot know whether the provider finished.
        # Charge its existing reservation; never automatically repeat that call.
        pending = state.get("inflight")
        if pending and recover:
            grant = state["grants"][pending]
            engine.ledger.cancel(grant["reservation"])
            grant["cancelled"] = True
            grant["consumed"] = True
            state["inflight"] = None
            engine._notice("Interrupted dispatch recovered with unknown consumption; it will not be retried automatically.")
            account = engine.account(grant["account"])
            engine._cancel_trial(account, "Interrupted dispatch; trial integration remains unresolved.")
            account["phase"] = "work"
        return engine

    @property
    def accounts(self):
        return self.state["accounts"]

    def account(self, identifier):
        for account in self.accounts:
            if account["id"] == identifier:
                return account
        raise ValueError(f"Unknown attention account: {identifier}")

    def _id(self, prefix):
        count = self.state["next_ids"].get(prefix, 0) + 1
        self.state["next_ids"][prefix] = count
        return f"{prefix}-{count}"

    def _notice(self, text):
        self.state["notices"].append(str(text))
        # Operational notices are a bounded view; occurrence prose is separate.
        self.state["notices"] = self.state["notices"][-128:]

    def _event(self, kind, **payload):
        event = {"kind": kind, "epoch": self.state["epoch"],
                 "dispatch_count": self.state["dispatch_count"], **payload}
        try:
            self.recorder.record(event)
        except OSError:
            self.state["recording_gap"] = True
            self._notice("Observation recording failed. Further dispatch is paused until the recording policy is explicitly resolved.")
            raise

    def save(self):
        if self.directory:
            atomic_json(self.directory / "state.json", self.state)

    def add_account(self, brief, name=None):
        if not isinstance(brief, str):
            raise ValueError("The brief must be ordinary text")
        identifier = self._id("account")
        focus = self.collection.add(brief, "operator", label=f"{identifier} initial question")
        method = self.collection.add(BASELINE_METHOD, "operator", label=f"{identifier} baseline attention")
        account = {"id": identifier, "name": name or identifier,
                   "focus": focus, "focus_revision": 1, "focus_anchors": [],
                   "method": method, "method_revision": 1, "baseline_method": method,
                   "method_anchors": [], "recipe": "local", "uses": [],
                   "use_index": {}, "use_cursor": 0, "context_cursors": {},
                   "phase": "work", "work_done": 0, "ordinary_total": 0,
                   "cycle": 0, "trial": None, "routes": ["participant-1"],
                   "route_cursor": 0, "deliveries": {"participant-1": []},
                   "delivery_cursors": {"participant-1": 0}, "delivery_route_cursor": 0,
                   "last_response": None, "last_criticism": None,
                   "last_target": None, "mediation_used": 0, "pending_reads": [],
                   "nonlocal_cursor": 0, "pending_jolt": None,
                   "last_jolt": -self.policy["jolt_cooldown"], "paused": False}
        self.accounts.append(account)
        self._event("account-created", account=identifier, focus=focus, method=method)
        return identifier

    def register_route(self, account_id, name):
        """Operator registration; personas named in a reply do not call this API."""
        account = self.account(account_id)
        if not isinstance(name, str) or not name or len(account["routes"]) >= 16:
            raise ValueError("A route needs a name; at most 16 routes per account")
        if name not in account["routes"]:
            account["routes"].append(name)
            account["deliveries"][name] = []
            account["delivery_cursors"][name] = 0

    def add_source(self, path):
        identifier = self.collection.ingest(path)
        self._event("source-ingested", occurrence=deepcopy(self.collection.get(identifier)))
        return identifier

    def add_text(self, text, label=""):
        identifier = self.collection.add(text, "operator", label=label)
        self._event("contribution-retained", occurrence=deepcopy(self.collection.get(identifier)))
        return identifier

    def _cancel_trial(self, account, reason):
        trial = account.get("trial")
        if trial:
            account["focus"] = trial["old_focus"]
            account["method"] = trial["old_method"]
            account["recipe"] = trial["old_recipe"]
            for key in trial["reservations"]:
                entry = self.ledger.data["entries"][key]
                if entry["status"] == "reserved":
                    self.ledger.cancel(key)
            account["trial"] = None
            account["phase"] = "work"
            account["work_done"] = 0
            self._notice(reason)

    def update_policy(self, changes):
        """Explicit operator transaction. Protected parameters never come from prose."""
        policy = validate({**self.policy, **changes})
        if effective_history(policy) != "off" and self.directory is None:
            raise ValueError("Recording needs an explicit directory")
        totals = self.ledger.report()
        inflight_volume = sum(entry["amount"] for entry in self.ledger.data["entries"].values() if entry["status"] == "dispatched")
        if policy["run_model_calls"] < totals["used_calls"] or policy["run_token_volume"] < totals["charged_tokens"] + inflight_volume:
            raise ValueError("The new envelope cannot erase already spent resources")
        old_gate = self.policy["attention_learning"]
        gate_only = set(changes) == {"attention_learning"}
        for account in self.accounts:
            if account["trial"] and (not gate_only or account["trial"]["kind"] == "method"):
                self._cancel_trial(account, "Operator policy changed; pending trial restored its prior settings.")
            if gate_only:
                for grant in self.state["grants"].values():
                    if grant["account"] == account["id"] and grant["kind"] == "method-nomination":
                        grant["cancelled"] = True
        if not gate_only:
            self.state["epoch"] += 1
        self.state["policy"] = self.policy = policy
        self.ledger.data["max_calls"] = policy["run_model_calls"]
        self.ledger.data["max_tokens"] = policy["run_token_volume"]
        if "run_model_calls" in changes or "run_token_volume" in changes:
            if self.ledger.available()["tokens"] >= 0 and self.ledger.available()["calls"] >= 0:
                self.ledger.data["paused"] = False
                self.ledger.data["pause_reason"] = None
        if changes.get("commitment_actions") == "off":
            for binding in self.state["bindings"].values():
                binding["enabled"] = False
                binding["disabled_by_gate"] = True
        observers = self.recorder.observers
        self.recorder = Recorder(self.directory, effective_history(policy), policy["history_limit"])
        self.recorder.observers = observers
        if "history" in changes:
            self.state["recording_gap"] = False
            self._notice("Recording policy changed explicitly. Earlier recording gaps remain limitations of the earlier observations.")
        self._event("policy-changed", changes=deepcopy(changes), old_attention_gate=old_gate)

    def set_gate(self, value):
        self.update_policy({"attention_learning": value})

    def set_commitments(self, value):
        self.update_policy({"commitment_actions": value})

    def set_account_paused(self, account_id, paused):
        if type(paused) is not bool:
            raise ValueError("paused must be boolean")
        self.account(account_id)["paused"] = paused
        self._event("account-paused" if paused else "account-resumed", account=account_id)

    def reset_attention(self, account_id=None):
        for account in ([self.account(account_id)] if account_id else self.accounts):
            self._cancel_trial(account, "Attention reset restored the named baseline.")
            account["method"] = account["baseline_method"]
            account["recipe"] = "local"
            account["method_revision"] += 1
            account["method_anchors"] = []
        self._event("attention-reset", account=account_id)

    def jolt(self, account_id=None, kind="fresh"):
        if kind not in {"fresh", "question", "method", "evidence"}:
            raise ValueError("Jolt kind must be fresh, question, method or evidence")
        account = self.account(account_id) if account_id else self.accounts[0]
        account["pending_jolt"] = kind
        self._event("jolt-requested", account=account["id"], jolt=kind)
        return {"account": account["id"], "jolt": kind, "status": "queued for an ordinary opportunity"}

    def _surface(self, account, limit=4):
        """Deliver originals through bounded rotating registered-route cursors."""
        result = []
        routes = account["routes"]
        for offset in range(min(len(routes) * limit, 64)):
            route = routes[(account["delivery_route_cursor"] + offset) % len(routes)]
            cursor = account["delivery_cursors"][route]
            stream = account["deliveries"][route]
            if cursor < len(stream):
                result.append(stream[cursor])
                account["delivery_cursors"][route] = cursor + 1
                if len(result) == limit:
                    break
        account["delivery_route_cursor"] = (account["delivery_route_cursor"] + 1) % len(routes)
        return result

    def _active_use(self, account):
        uses = account["uses"]
        if not uses:
            return None
        # Save the cursor even when all entries in this bounded slice are parked.
        for _ in range(min(len(uses), self.policy["edge_inspections"] or 1)):
            position = account["use_cursor"] % len(uses)
            account["use_cursor"] = position + 1
            use = uses[position]
            pending = account.get("dependencies_pending") and use.get("depends_on", ["unknown"])
            if use["disposition"] == "active" and not use.get("blocked") and not pending:
                return use
        return None

    def _invitation(self, account):
        phase = account["phase"]
        required, nonlocal_id = [], None
        current_use = None
        recipe = account["recipe"]
        extra_anchors = []
        if phase == "work":
            kind, text = INVITATIONS[account["ordinary_total"] % len(INVITATIONS)]
            if kind == "explore" and not self.policy["daydreaming"]:
                kind, text = "read", "Reopen available material and examine its qualifications."
            if kind == "develop":
                current_use = self._active_use(account)
                if current_use:
                    required.append(current_use["occurrence"])
                    text += " The selected working use is " + current_use["id"] + ": " + current_use["purpose"]
                else:
                    text = "Browse, explore or reconsider the question. No eligible development use was selected; this is not a verdict on the available ideas."
            if kind in {"examine", "variation"} and account["last_response"]:
                required.append(account["last_response"])
            if kind == "respond":
                required.extend(x for x in (account["last_criticism"], account["last_target"]) if x)
                if account["uses"]:
                    current_use = self._active_use(account)
                if current_use:
                    required.append(current_use["occurrence"])
                    text += f" Current addressed use: {current_use['id']} of {current_use['occurrence']} for {current_use['purpose']}."
                text += " A direct request such as 'Park the current use because …' can be resolved within this account's current action opportunity; all other prose remains legitimate."
            if (account["ordinary_total"] + 1) % self.policy["nonlocal_every"] == 0 or kind == "read":
                page = self.collection.catalogue(account["nonlocal_cursor"], 1)
                if page["items"]:
                    nonlocal_id = page["items"][0]["id"]
                account["nonlocal_cursor"] = page.get("next_cursor") or 0
                text += " A catalogue page independent of the local graph is supplied when available."
            if account.get("pending_reads"):
                request = account["pending_reads"].pop(0)
                kind, text = "requested-read", "Read the requested original material and its qualifications. This one-off access does not install an attention method."
                required.extend([request["request"], *request["anchors"]])
            jolt = account["pending_jolt"]
            if jolt:
                account["pending_jolt"] = None
                account["last_jolt"] = account["ordinary_total"]
                if jolt == "fresh":
                    kind, text, required = "fresh", "Make a fresh attempt from the question and available original sources. The latest answer and objection are withheld; do not claim to have answered an omitted objection.", []
                elif jolt == "question":
                    text += " Examine a presupposition of the working question."
                elif jolt == "method":
                    required.append(account["method"])
                    text += " Criticise the installed attention note and these finite view limits."
                else:
                    text += " Reopen an original rather than trusting a paraphrase."
        elif phase == "nomination":
            method_review = (account["cycle"] % self.policy["attention_review_every"] == 0 and self.policy["attention_learning"] != "off")
            account["review_kind"] = "method" if method_review else "problem"
            kind = "method-nomination" if method_review else "problem-nomination"
            text = ("What about material selection may be keeping this inquiry inside a mistaken approach? Propose a different method and explain what it would change."
                    if method_review else "Reconsider the working question in light of these original contributions. Propose a working focus, including keeping the old question if you have reasons.")
            account["surfaced"] = self._surface(account)
            required.extend([account["method"] if method_review else account["focus"], *account["surfaced"]])
        else:
            trial = account["trial"]
            kind = "trial" if phase == "trial" else "return"
            required.extend([trial["old_focus"], trial["old_method"], trial["proposal"], *trial["reasons"]])
            required.extend(trial["results"][-self.policy["trial_calls"]:])
            if phase == "return":
                required.extend(trial.get("cut_records", []))
            if phase == "return":
                required.extend(self._surface(account, 2))
                text = "Return to the earlier difficulty. Consider the old focus/method, proposal, surfaced reasons and actual trial material. Explain the next working focus or attention note, including qualifications or an inconclusive outcome. A blank return restores the previous setting."
            else:
                text = "Try the proposed " + trial["kind"] + " within this existing opportunity. Its promise is not a verdict. Explain what the supplied material lets you examine."
            if trial["kind"] == "method":
                recipe = trial["recipe"]
                extra_anchors = trial["anchors"]
            if trial.get("incomplete"):
                text += " Some trial work was only a partial reading; larger integration remains unresolved."
        return kind, text, required, current_use, recipe, extra_anchors, nonlocal_id

    def prepare(self, provider):
        """Reserve and persist one complete dispatch before any provider work."""
        if self.state["inflight"]:
            raise ValueError("A dispatch is already in flight")
        if self.state["recording_gap"]:
            raise ValueError("Recording gap: choose an explicit recording policy before dispatch")
        if self.ledger.paused:
            return {"status": "paused", "notice": self.ledger.data["pause_reason"]}
        if self.policy["strict_tokens"] and provider.count_kind not in {"exact", "bounded", "fixture"}:
            raise ValueError("This provider has estimated preflight accounting. Explicitly allow estimates; no exact token ceiling is claimed.")
        self.process_checks()
        self.process_dependencies()
        original_account_cursor = self.state["account_cursor"]
        active = None
        for _ in range(len(self.accounts)):
            position = self.state["account_cursor"] % len(self.accounts)
            self.state["account_cursor"] = position + 1
            candidate = self.accounts[position]
            if not candidate["paused"]:
                active = candidate
                break
        if active is None:
            return {"status": "paused", "notice": "No active account"}
        account = active
        cursor_fields = ("use_cursor", "nonlocal_cursor", "delivery_cursors", "delivery_route_cursor", "route_cursor", "pending_jolt", "last_jolt", "review_kind", "surfaced", "pending_reads")
        checkpoint = {key: deepcopy(account.get(key)) for key in cursor_fields}

        def rollback_selection():
            self.state["account_cursor"] = original_account_cursor
            for key, value in checkpoint.items():
                if value is None:
                    account.pop(key, None)
                else:
                    account[key] = value

        kind, invitation, required, current_use, recipe, extra, nonlocal_id = self._invitation(account)
        trial = account["trial"]
        view_account = dict(account)
        cursor_transaction = CursorTransaction(account["context_cursors"])
        view_account["context_cursors"] = cursor_transaction
        if trial and trial["kind"] == "method":
            view_account["method"] = trial["proposal"]
        if trial and trial["kind"] == "problem":
            view_account["focus"] = trial["proposal"]
        view_policy = dict(self.policy)
        if kind == "fresh":
            view_policy["participant_history"] = "off"
        required = list(dict.fromkeys([*account["focus_anchors"], *required]))
        grant_id = self._id("grant")
        try:
            cut = compile_cut(self.collection, policy=view_policy, account=view_account,
                invitation={"text": invitation, "request_id": f"{account['id']}:{account['phase']}:{account['cycle']}"},
                required=required, roots=[view_account["focus"]], counter=provider.count,
                recipe=recipe, extra_anchors=extra, nonlocal_read=nonlocal_id)
        except ValueError as error:
            cursor_transaction.discard()
            rollback_selection()
            account["paused"] = True
            self._notice(f"{account['id']}: context cannot be represented at the current limit: {error}")
            return {"status": "blocked", "account": account["id"], "notice": str(error)}
        if trial:
            reservation = trial["reservations"][trial["used_slots"]]
        else:
            reservation = self._id("call")
            try:
                self.ledger.reserve(reservation, cut.input_tokens + self.policy["generated_tokens"])
            except BudgetExceeded:
                cursor_transaction.discard()
                rollback_selection()
                return {"status": "limit", "notice": "No unreserved allowance for another model call"}
        route = account["routes"][account["route_cursor"] % len(account["routes"])]
        account["route_cursor"] += 1
        eligible_use_ids = ([current_use["id"]] if current_use else [])
        for use in account["uses"][:16]:
            if use["id"] not in eligible_use_ids and len(eligible_use_ids) < 16:
                eligible_use_ids.append(use["id"])
        grant = {"id": grant_id, "account": account["id"], "route": route,
                 "epoch": self.state["epoch"], "phase": account["phase"],
                 "focus_revision": account["focus_revision"], "method_revision": account["method_revision"],
                 "cycle": account["cycle"], "kind": kind, "reservation": reservation,
                 "required": required, "cut": cut.to_dict(), "consumed": False,
                 "cancelled": False, "current_use": current_use["id"] if current_use else None,
                 "use_revisions": {identifier: self._use(account, identifier)["revision"] for identifier in eligible_use_ids},
                 "surfaced": account.get("surfaced", [])[:4],
                 "input_limit": self.policy["input_tokens"], "output_limit": self.policy["generated_tokens"],
                 "trial_id": trial["id"] if trial else None}
        self.state["grants"][grant_id] = grant
        self.state["last_dispatch"] = {"grant": grant_id, "messages": cut.messages,
                                       "count_kind": provider.count_kind, "input_tokens": cut.input_tokens}
        metadata = {key: getattr(provider, key) for key in ("name", "model", "base_url", "think", "context_window") if hasattr(provider, key)}
        try:
            self._event("dispatch-prepared", grant=deepcopy(grant), messages=deepcopy(cut.messages),
                        provider=metadata, count_kind=provider.count_kind)
        except OSError:
            cursor_transaction.discard()
            rollback_selection()
            if not trial:
                self.ledger.cancel(reservation)
            self.save()
            raise
        cursor_transaction.commit()
        self.ledger.dispatch(reservation)
        self.state["inflight"] = grant_id
        self.state["dispatch_count"] += 1
        self.save()
        return {"status": "ready", "grant": grant_id, "messages": cut.messages}

    def step(self, provider):
        prepared = self.prepare(provider)
        if prepared["status"] != "ready":
            self.save()
            return prepared
        try:
            result = provider.generate(prepared["messages"], max_tokens=self.policy["generated_tokens"], timeout=self.policy["timeout_seconds"])
        except (Exception, KeyboardInterrupt) as error:
            self.fail(prepared["grant"])
            if isinstance(error, KeyboardInterrupt):
                raise
            # Error objects can contain credentials; retain only the operational fact.
            return {"status": "provider-error", "notice": "Provider call failed or timed out. Consumption is unknown and conservatively charged; no automatic retry."}
        return self.receive(prepared["grant"], result, counter=provider.count)

    def _current(self, grant):
        account = self.account(grant["account"])
        return (not grant["consumed"] and not grant["cancelled"]
                and grant["epoch"] == self.state["epoch"]
                and grant["focus_revision"] == account["focus_revision"]
                and grant["method_revision"] == account["method_revision"]
                and grant["cycle"] == account["cycle"]
                and grant["phase"] == account["phase"]
                and grant["route"] in account["routes"]
                and grant.get("trial_id") == (account["trial"]["id"] if account["trial"] else None))

    def receive(self, grant_id, result, counter=None):
        """Keep raw bytes before parsing; stale content has no current mutation right."""
        if grant_id not in self.state["grants"]:
            raise ValueError("Unknown host-issued grant")
        grant = self.state["grants"][grant_id]
        account = self.account(grant["account"])
        if not isinstance(result, ProviderResult) or not isinstance(result.text, str):
            self.fail(grant_id)
            raise ValueError("Provider result must carry raw text")
        occurrence = self.collection.add(result.text, "model", label=f"{grant['kind']} response",
            links=tuple(grant["required"][:16]), account=account["id"], route=grant["route"],
            grant=grant_id, anchors=grant["required"][:16], reading_only=not grant["cut"].get("required_complete", True))
        # A stale response still reports real consumption and remains recoverable.
        self.ledger.settle(grant["reservation"], result.usage)
        current = self._current(grant)
        if self.state["inflight"] == grant_id:
            self.state["inflight"] = None
        account["deliveries"][grant["route"]].append(occurrence)
        usage = self.ledger.data["entries"][grant["reservation"]].get("usage") or {}
        observed_input = usage.get("input_tokens")
        observed_output = usage.get("output_tokens")
        if observed_output is not None and usage.get("reasoning_included") is False and usage.get("reasoning_tokens") is not None:
            observed_output += usage["reasoning_tokens"]
        if (observed_input is not None and observed_input > grant["input_limit"]) or (observed_output is not None and observed_output > grant["output_limit"]):
            self.ledger.data["paused"] = True
            self.ledger.data["pause_reason"] = "provider exceeded a per-call input or generation ceiling"
            self._notice("Reported per-call overrun retained at its actual size; further dispatch is paused.")
        try:
            self._event("model-response", grant=grant_id, occurrence=deepcopy(self.collection.get(occurrence)),
                        usage=deepcopy(self.ledger.data["entries"][grant["reservation"]]), metadata=result.metadata or {}, current=current)
            if current:
                complete = grant["cut"].get("required_complete", True) and grant["cut"]["mode"] != "read"
                if complete and grant["kind"] in {"respond", "return"}:
                    self._mediate_use(grant, result.text)
                if grant["phase"] == "work":
                    self._mediate_read(grant, occurrence, result.text)
                self._advance(account, grant, occurrence, result.text, complete, counter)
            else:
                self._notice("Late, duplicate or invalidated response retained without changing its old working slot.")
        except OSError:
            grant["consumed"] = grant["cancelled"] = True
            self._cancel_trial(account, "Recording failed after receipt; raw response and spent resources remain in the working snapshot.")
            self.save()
            raise
        grant["consumed"] = True
        # Full dispatch history belongs to the selected recorder. The last view
        # and pending trial cuts have a working purpose; completed tickets do not
        # secretly preserve every prompt when history is off.
        grant["cut"].pop("messages", None)
        self.save()
        return {"status": "received" if current else "retained-stale", "account": account["id"],
                "opportunity": grant_id, "invitation": grant["kind"], "occurrence": occurrence,
                "response": result.text, "mode": grant["cut"]["mode"]}

    def _mediate_use(self, grant, text):
        account = self.account(grant["account"])
        if account["mediation_used"] >= self.policy["mediation_calls_per_cycle"]:
            if text.lstrip().lower().startswith(("park ", "stop using ", "reactivate ")):
                self._notice("The prose action was not applied: this cycle's shared mediation allowance is exhausted.")
            return
        eligible = [self._use(account, identifier) for identifier, revision in grant["use_revisions"].items()
                    if self._use(account, identifier)["revision"] == revision]
        action = resolve_use(text, eligible, current_use=grant["current_use"])
        if action and action.get("use_id"):
            account["mediation_used"] += 1
            self.change_use(account["id"], action["use_id"], action["action"], action["reason"])
            self._event("prose-action-resolved", grant=grant["id"], readback=action["readback"])
        elif text.lstrip().lower().startswith(("park ", "stop using ", "reactivate ")):
            self._notice("The prose action was not applied: its address or interpretation is unresolved, stale, or outside this grant's bounded account-local packet.")

    def _mediate_read(self, grant, occurrence, text):
        """Bounded one-off source requests work independently of the learning gate."""
        account = self.account(grant["account"])
        if account["mediation_used"] >= self.policy["mediation_calls_per_cycle"]:
            if text.lstrip().lower().startswith("read "):
                self._notice("Read request retained but not resolved: the shared mediation allowance is exhausted.")
            return
        anchors = []
        first = text.lstrip().split("\n", 1)[0].casefold()
        for sentence, target in (("read the original criticism.", account["last_criticism"]),
                                 ("read the original target.", account["last_target"])):
            if first.startswith(sentence) and target:
                anchors = [target]
                break
        if not anchors:
            resolution = resolve_plan(text, self.policy["recipes"], self.collection)
            if resolution:
                anchors = resolution.get("anchors", [])[:2]
        if anchors:
            account["pending_reads"] = [{"request": occurrence, "anchors": anchors}]
            account["mediation_used"] += 1
            self._event("one-off-read-resolved", account=account["id"], request=occurrence,
                        anchors=anchors, readback="The next ordinary view will open these retained originals; no installed method changes.")
        elif first.startswith("read "):
            self._notice("Read request remains unresolved. The bounded resolver accepts existing addresses or the original criticism/target; catalogue browsing remains available.")

    def _reserve_trial(self, account, proposal, kind, counter, reasons):
        if self.ledger.paused:
            self._notice("Proposal retained; provider overrun prevents a new trial.")
            return False
        if sum(bool(item["trial"]) for item in self.accounts) >= self.policy["max_pending_trials"]:
            self._notice("Proposal retained; the pending-trial limit leaves it unscheduled.")
            return False
        plan = {"recipe": account["recipe"], "anchors": []}
        text = self.collection.get(proposal)["text"]
        if kind == "method":
            if counter is None or counter([{"role": "user", "content": text}]) > self.policy["attention_note_tokens"]:
                self._notice("Attention proposal retained whole but too large to install; the current method remains.")
                return False
            if account["mediation_used"] < self.policy["mediation_calls_per_cycle"]:
                resolution = resolve_plan(text, self.policy["recipes"], self.collection)
                if resolution and (resolution.get("recipe") or resolution.get("anchors")):
                    plan.update({key: resolution[key] for key in ("recipe", "anchors") if resolution.get(key)})
                    account["mediation_used"] += 1
                    self._event("attention-plan-resolved", account=account["id"], resolution=resolution)
        count = self.policy["trial_calls"] + 1
        amount = self.policy["input_tokens"] + self.policy["generated_tokens"]
        available = self.ledger.available()
        if available["calls"] < count or available["tokens"] < amount * count:
            self._notice("Proposal retained; the whole trial and return cannot be funded.")
            return False
        keys = []
        for _ in range(count):
            key = self._id("call")
            self.ledger.reserve(key, amount)
            keys.append(key)
        account["trial"] = {"id": self._id("trial"), "kind": kind, "proposal": proposal,
            "old_focus": account["focus"], "old_method": account["method"], "old_recipe": account["recipe"],
            "recipe": plan["recipe"], "anchors": plan["anchors"][:2],
            "reservations": keys, "used_slots": 0, "results": [], "cuts": [], "cut_records": [],
            "reasons": reasons[:4], "incomplete": False}
        account["phase"] = "trial"
        self._event("trial-reserved", account=account["id"], trial=deepcopy(account["trial"]),
                    change="note-only" if plan["recipe"] == account["recipe"] and not plan["anchors"] else "note and concrete view")
        return True

    def _advance(self, account, grant, occurrence, text, complete, counter):
        phase = grant["phase"]
        previous_response = account["last_response"]
        account["last_response"] = occurrence
        if phase == "work":
            if grant["kind"] == "examine":
                account["last_criticism"] = occurrence
                account["last_target"] = next((item for item in reversed(grant["required"]) if item), account["focus"])
            if grant["kind"] == "respond" and complete and text.strip():
                account["focus"] = occurrence
                account["focus_revision"] += 1
                account["focus_anchors"] = grant["required"][-4:]
                self._event("focus-changed", account=account["id"], occurrence=occurrence, cause="prose response")
            if self.policy["jolt_echo"] and previous_response and account["ordinary_total"] - account["last_jolt"] >= self.policy["jolt_cooldown"]:
                if text and text == self.collection.get(previous_response)["text"]:
                    account["pending_jolt"] = "fresh"
            account["ordinary_total"] += 1
            account["work_done"] += 1
            if account["work_done"] >= self.policy["work_before_review"]:
                account["cycle"] += 1
                account["phase"] = "nomination"
        elif phase == "nomination":
            kind = account["review_kind"]
            if kind == "method" and self.policy["attention_learning"] == "observe":
                self._event("attention-observed", account=account["id"], proposal=occurrence,
                            applied=False, note="Proposal retained; no live trial or installed change.")
                account["phase"] = "work"
                account["work_done"] = 0
                account["mediation_used"] = 0
            elif complete and text.strip() and self._reserve_trial(account, occurrence, kind, counter, grant["surfaced"]):
                pass
            else:
                account["phase"] = "work"
                account["work_done"] = 0
                account["mediation_used"] = 0
                self._notice("Nomination did not start a trial; its prose remains available.")
        elif phase == "trial":
            trial = account["trial"]
            trial["results"].append(occurrence)
            trial["cuts"].append(deepcopy(grant["cut"]))
            facts = {key: grant["cut"].get(key) for key in ("recipe", "mode", "ranges", "omissions", "required_complete", "input_tokens", "inspections")}
            cut_record = self.collection.add("Actual trial view supplied by the host:\n" + json.dumps(facts, ensure_ascii=False),
                "host", label="Trial view selection and limits", links=(occurrence,))
            trial["cut_records"].append(cut_record)
            trial["incomplete"] = trial["incomplete"] or not complete
            trial["used_slots"] += 1
            if trial["used_slots"] >= self.policy["trial_calls"]:
                account["phase"] = "return"
        elif phase == "return":
            trial = account["trial"]
            adopted = False
            if complete and text.strip():
                if trial["kind"] == "problem":
                    account["focus"] = occurrence
                    account["focus_revision"] += 1
                    account["focus_anchors"] = [trial["old_focus"], trial["proposal"], *trial["results"]][-4:]
                    adopted = True
                elif self.policy["attention_learning"] == "on" and counter and counter([{"role": "user", "content": text}]) <= self.policy["attention_note_tokens"]:
                    account["method"] = occurrence
                    account["method_revision"] += 1
                    account["recipe"] = trial["recipe"]
                    account["method_anchors"] = [trial["proposal"], occurrence]
                    adopted = True
            if not adopted:
                account["focus"] = trial["old_focus"]
                account["method"] = trial["old_method"]
                account["recipe"] = trial["old_recipe"]
                self._notice("Blank, oversized or incomplete return restored the prior setting; no rival was declared defeated.")
            self._event("trial-return", account=account["id"], occurrence=occurrence,
                        installed=adopted, kind_of_trial=trial["kind"], trial=deepcopy(trial))
            account["trial"] = None
            account["phase"] = "work"
            account["work_done"] = 0
            account["mediation_used"] = 0

    def fail(self, grant_id):
        grant = self.state["grants"][grant_id]
        self.ledger.cancel(grant["reservation"])
        owns_flight = self.state["inflight"] == grant_id
        grant["cancelled"] = grant["consumed"] = True
        if owns_flight:
            self.state["inflight"] = None
            account = self.account(grant["account"])
            self._cancel_trial(account, "A provider failure interrupted the trial; its existing results remain available.")
            account["phase"] = "work"
            account["work_done"] = 0
        self._event("provider-incomplete", grant=grant_id, consumption="unknown; reserved bound charged")
        self.save()

    def run(self, provider, steps=None):
        if steps is not None and (type(steps) is not int or steps < 1):
            raise ValueError("steps must be a positive integer")
        results = []
        for _ in range(steps if steps is not None else self.policy["run_model_calls"]):
            result = self.step(provider)
            results.append(result)
            if result["status"] in {"limit", "paused", "provider-error"}:
                break
        return results

    def status(self):
        return {"engine_version": self.state["engine_version"], "profile": self.policy["run_profile"],
                "history": effective_history(self.policy), "participant_history": self.policy["participant_history"],
                "attention_learning": self.policy["attention_learning"], "commitment_actions": self.policy["commitment_actions"],
                "recording_gap": self.state["recording_gap"], "epoch": self.state["epoch"],
                "inflight": self.state["inflight"], "resources": self.ledger.report(),
                "accounts": [{key: deepcopy(account[key]) for key in ("id", "name", "focus", "method", "recipe", "phase", "cycle", "uses", "paused")} for account in self.accounts],
                "retained_occurrences": len(self.collection.data["order"]), "notices": list(self.state["notices"]),
                "claims": "Inspectable inquiry material; no truth, creativity or explanatory-improvement certification. Snapshot resumption, not remote-response replay."}

    def export_markdown(self):
        report = self.ledger.report()
        lines = ["# Open Inquiry material", "", "This export preserves attempted inquiry and current host facts. It certifies neither truth nor creativity.", "",
                 f"Recording: {effective_history(self.policy)}. Participant predecessor history: {self.policy['participant_history']}. Attention learning: {self.policy['attention_learning']}.", "",
                 f"Model calls used: {report['used_calls']}; charged token-volume units: {report['charged_tokens']}; calls with unknown consumption: {report['unknown_calls']}.", "",
                 "Fixture counters are synthetic. Estimated production routes cannot establish an exact token or money ceiling. Current snapshots support resumption; retained events do not promise event-sourced replay.", ""]
        if self.state["recording_gap"]:
            lines.extend(["A recording gap limits reinspection of this run.", ""])
        for account in self.accounts:
            lines.extend([f"## {account['name']}", "", f"Current focus: {account['focus']}. Installed method: {account['method']}. View recipe: {account['recipe']}.", ""])
            for use in account["uses"]:
                lines.extend([f"Use {use['id']} of {use['occurrence']}: {use['disposition']} for {use['purpose']}. {use.get('reason', '')}", ""])
        for identifier in self.collection.data["order"]:
            occurrence = self.collection.get(identifier)
            lines.extend([f"## {identifier}: {occurrence['label']}", "",
                          f"Origin: {occurrence['origin']}; representation: {occurrence['representation']}; version: {occurrence['version']}.", "",
                          occurrence["text"] if occurrence["readable"] else "Original retained but not readable through an installed adapter.", ""])
        return "\n".join(lines)
