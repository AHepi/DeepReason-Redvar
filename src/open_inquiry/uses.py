"""Addressed working use, conditional parking, and bounded dependencies.

Spec: ``The collection is not the active working set``, ``Triggering a
conditional withdrawal``, and ``Dependency effects are scoped, not a truth
cascade``. The public methods are operator actions. A model can reach them
only through the engine's separately checked account-local grant mediator.

Bindings watch one immutable source scope and one use revision. Receipts enter
the ordinary collection before a permitted operating consequence is enacted.
Dependency jobs propagate explicit parked-premise causes, with saved edge
cursors and visited addresses; they make no claim about implicit dependence.
"""

from copy import deepcopy
import json
import time


_SCOPE = ("source_id", "source_version", "representation", "comparison",
          "checker_version", "phrase", "start", "end")


class UseOperations:
    """Mixin using Engine's accounts, collection, checker, policy and events."""

    def _use(self, account, use_id):
        if "use_id_index" not in account:
            account["use_id_index"] = {item["id"]: index for index, item in enumerate(account["uses"])}
        position = account["use_id_index"].get(use_id)
        if position is None:
            raise ValueError(f"Unknown use {use_id} in account {account['id']}")
        return account["uses"][position]

    def add_use(self, account_id, occurrence, purpose):
        account = self.account(account_id)
        if occurrence not in self.collection.data["occurrences"]:
            raise ValueError("A working use needs an available occurrence address")
        if not isinstance(purpose, str):
            raise ValueError("A use purpose must be ordinary prose")
        use_id = self._id("use")
        use = {"id": use_id, "occurrence": occurrence, "purpose": purpose,
               "disposition": "active", "blocked": False, "blocked_by": {},
               "blocker_order": [], "blocker_known": {}, "reason": "Operator installed this working use.",
               "revision": 0, "depends_on": [], "depends_on_index": {},
               "dependents": [], "binding_ids": []}
        uses = account.setdefault("uses", [])
        if "use_id_index" not in account:
            account["use_id_index"] = {item["id"]: index for index, item in enumerate(uses)}
        account["use_id_index"][use_id] = len(uses)
        account.setdefault("use_index", {}).setdefault(occurrence, []).append(len(uses))
        uses.append(use)
        self._event("use-added", account_id=account["id"], use_id=use_id,
                    occurrence=occurrence, purpose=purpose)
        return use_id

    def change_use(self, account_id, use_id, action, reason):
        """Apply one addressed decision; an identical disposition is a no-op."""
        account = self.account(account_id)
        use = self._use(account, use_id)
        if action not in {"park", "reactivate"}:
            raise ValueError("Use action must be park or reactivate")
        if not isinstance(reason, str):
            raise ValueError("The operating reason must be prose")
        disposition = "parked" if action == "park" else "active"
        if use["disposition"] == disposition:
            return {"changed": False, "use": deepcopy(use), "reason": "Use already has that disposition"}
        use.update(disposition=disposition, revision=use.get("revision", 0) + 1, reason=reason)
        # Only the addressed revision becomes stale. Sharing an occurrence with
        # another use or account does not change that other use's permissions.
        for binding_id in tuple(use.get("binding_ids", ())):
            binding = self.state.get("bindings", {}).get(binding_id)
            if binding is not None and binding.get("use_revision") != use["revision"]:
                binding.update(enabled=False, stale=True, disabled_by_gate=False)
                self._retire_binding(binding, account)
        use["binding_ids"] = []
        account["dependency_epoch"] = account.get("dependency_epoch", 0) + 1
        if use.get("dependents"):
            self._enqueue_dependency(account, {
                "kind": "cascade", "root": use_id, "frontier": [{"use_id": use_id, "edge": -1}],
                "frontier_cursor": 0, "visited": {use_id: True},
            })
        self._event("use-changed", account_id=account["id"], use_id=use_id,
                    action=action, revision=use["revision"], reason=reason)
        return {"changed": True, "use": deepcopy(use)}

    def _retire_binding(self, binding, account):
        """Retain observation history while removing a retired live watcher."""
        binding_id = binding["id"]
        slots = account.get("binding_slots", [])
        if binding_id in slots:
            slots.remove(binding_id)
        watchers = self.state.get("binding_source_index", {}).get(binding["source_id"], [])
        if binding_id in watchers:
            watchers.remove(binding_id)
        use = self._use(account, binding["use_id"])
        use_bindings = use.get("binding_ids", [])
        if binding_id in use_bindings:
            use_bindings.remove(binding_id)

    def bind(self, account_id, use_id, source_id, phrase, start=0, end=None):
        """Explicit operator installation of a literal-match parking action."""
        account = self.account(account_id)
        use = self._use(account, use_id)
        source = self.collection.data["occurrences"].get(source_id)
        if source is None or not source.get("readable"):
            raise ValueError("Binding installation needs a readable, identified source")
        if source.get("origin") not in {"source", "operator", "checker"}:
            raise ValueError("A source condition cannot bind a generated conversation contribution")
        if not isinstance(phrase, str) or not phrase or len(phrase.encode("utf-8")) > self.checker.max_phrase_bytes:
            raise ValueError("Binding needs a nonempty supported literal phrase")
        actual_end = len(source["text"]) if end is None else end
        if (type(start) is not int or type(actual_end) is not int or
                not 0 <= start <= actual_end <= len(source["text"])):
            raise ValueError("Binding range must lie inside the identified representation")
        slots = account.setdefault("binding_slots", [])
        if len(slots) >= self.policy.get("conditional_bindings_per_account", 16):
            raise ValueError("Account conditional-binding limit reached; prose remains available")
        check_id = self.checker.add(self.collection, source_id, phrase, start=start, end=actual_end)
        binding_id = self._id("binding")
        enabled = self.policy.get("commitment_actions", "registered") == "registered"
        binding = {"id": binding_id, "account_id": account["id"], "use_id": use_id,
                   "use_revision": use.get("revision", 0), "source_id": source_id,
                   "source_version": source["version"], "representation": source["representation"],
                   "comparison": "literal", "checker_version": "1", "phrase": phrase,
                   "start": start, "end": actual_end, "action": "park", "trigger": "matched",
                   "enabled": enabled, "disabled_by_gate": not enabled, "consumed": False,
                   "stale": False, "check_id": check_id, "authorisation": "operator-explicit-installation",
                   "readback": f"Finding {phrase!r} in source {source_id}, characters {start}:{actual_end}, "
                               f"will park only use {use_id} at revision {use.get('revision', 0)}. "
                               "This does not decide whether the explanation is false."}
        self.state.setdefault("bindings", {})[binding_id] = binding
        self.state.setdefault("binding_source_index", {}).setdefault(source_id, []).append(binding_id)
        self.state.setdefault("binding_check_index", {}).setdefault(check_id, []).append(binding_id)
        slots.append(binding_id)
        use.setdefault("binding_ids", []).append(binding_id)
        self._event("binding-installed", binding=deepcopy(binding))
        return deepcopy(binding)

    def check(self, source_id, phrase, start=0, end=None, comparison="literal", version="1"):
        """Explicit new check; matching gated bindings may receive new authority.

        Re-enabling the policy alone never consumes an earlier observation.
        An explicit recheck re-arms only the exact previously installed scope
        at its current revision; consumed or otherwise invalidated actions stay
        retired. Checker version changes therefore require a new binding.
        """
        check_id = self.checker.add(self.collection, source_id, phrase, start=start,
                                    end=end, comparison=comparison, version=version)
        job = self.checker.data["checks"][check_id]
        if self.policy.get("commitment_actions", "registered") == "registered":
            for binding_id in self.state.get("binding_source_index", {}).get(source_id, ()):
                binding = self.state["bindings"][binding_id]
                if binding.get("consumed") or binding.get("stale"):
                    continue
                if not all(binding.get(key) == job.get(key) for key in _SCOPE):
                    continue
                account = self.account(binding["account_id"])
                use = self._use(account, binding["use_id"])
                if use.get("revision", 0) != binding["use_revision"]:
                    continue
                if binding.get("enabled") or binding.get("disabled_by_gate"):
                    binding.update(enabled=True, disabled_by_gate=False, check_id=check_id)
                    self.state.setdefault("binding_check_index", {}).setdefault(check_id, []).append(binding_id)
                    self._event("binding-recheck-authorised", binding_id=binding_id, check_id=check_id)
        self._event("check-scheduled", check_id=check_id)
        return check_id

    def process_checks(self):
        """Advance permitted checker work, retain receipts, enact exact bindings."""
        receipts = self.checker.step(self.collection,
            slices=self.policy.get("checker_slices_per_boundary", 4),
            slice_bytes=self.policy.get("checker_slice_bytes", 65536))
        for receipt in receipts:
            # The result is ordinary available material before any consequence.
            occurrence = self.collection.add(
                json.dumps(receipt, ensure_ascii=False, sort_keys=True), "checker",
                label=f"Scoped source check {receipt['id']}", receipt_id=receipt["id"],
                links=[receipt["source_id"]] if receipt.get("source_id") else ())
            self._event("check-observed", receipt=receipt, occurrence=occurrence)
            if self.policy.get("commitment_actions", "registered") != "registered":
                continue
            for binding_id in self.state.get("binding_check_index", {}).get(receipt["check_id"], ()):
                binding = self.state["bindings"][binding_id]
                if (not binding.get("enabled") or binding.get("consumed") or binding.get("stale") or
                        binding.get("check_id") != receipt["check_id"] or
                        receipt["status"] != binding.get("trigger", "matched") or
                        not receipt.get("predicate_resolved") or
                        not all(binding.get(key) == receipt.get(key) for key in _SCOPE)):
                    continue
                account = self.account(binding["account_id"])
                use = self._use(account, binding["use_id"])
                source = self.collection.data["occurrences"].get(binding["source_id"])
                if (use.get("revision", 0) != binding["use_revision"] or
                        source is None or source["version"] != binding["source_version"] or
                        source["representation"] != binding["representation"]):
                    continue
                binding.update(consumed=True, enabled=False, consumed_receipt=receipt["id"])
                self._retire_binding(binding, account)
                reason = (f"Use {use['id']} was parked because installed condition {binding_id} "
                          f"received matching result {receipt['id']}. No truth verdict follows.")
                result = self.change_use(account["id"], use["id"], "park", reason)
                self._event("binding-consequence", binding_id=binding_id,
                            receipt_id=receipt["id"], changed=result["changed"])
        return receipts

    def add_dependency(self, account_id, dependent_use_id, essential_use_id):
        """Declare one essential operational dependence within one account."""
        account = self.account(account_id)
        dependent = self._use(account, dependent_use_id)
        essential = self._use(account, essential_use_id)
        dependencies = dependent.setdefault("depends_on", [])
        if "depends_on_index" not in dependent:
            dependent["depends_on_index"] = {item: True for item in dependencies}
        if essential_use_id in dependent["depends_on_index"]:
            return {"changed": False, "dependent": dependent_use_id, "essential": essential_use_id}
        dependencies.append(essential_use_id)
        dependent["depends_on_index"][essential_use_id] = True
        essential.setdefault("dependents", []).append(dependent_use_id)
        account["dependency_epoch"] = account.get("dependency_epoch", 0) + 1
        # Inheriting existing causes is itself queued: an already blocked use
        # may have many causes, and registration cannot scan them without bound.
        self._enqueue_dependency(account, {"kind": "inherit", "essential": essential_use_id,
                                           "dependent": dependent_use_id, "cause_cursor": -1})
        self._event("dependency-added", account_id=account["id"],
                    dependent_use_id=dependent_use_id, essential_use_id=essential_use_id)
        return {"changed": True, "dependent": dependent_use_id, "essential": essential_use_id}

    def remove_dependency(self, account_id, dependent_use_id, essential_use_id):
        """Withdraw a declared edge and reconcile its actual blocking effects.

        A deleted edge is not sufficient reason to clear a block: another path
        from the same parked premise may remain. Reconciliation therefore
        traverses each implicated root's current graph and then inspects only
        that root's previously affected use addresses. Both stages are paged.
        """
        account = self.account(account_id)
        dependent = self._use(account, dependent_use_id)
        essential = self._use(account, essential_use_id)
        dependencies = dependent.setdefault("depends_on", [])
        if essential_use_id not in dependencies:
            return {"changed": False, "dependent": dependent_use_id, "essential": essential_use_id}
        dependencies.remove(essential_use_id)
        dependent.get("depends_on_index", {}).pop(essential_use_id, None)
        essential.setdefault("dependents", []).remove(dependent_use_id)
        account["dependency_epoch"] = account.get("dependency_epoch", 0) + 1
        # This barrier runs after previously queued cascades. It reads their
        # resulting cause indexes incrementally instead of snapshotting a large
        # root list at registration time.
        self._enqueue_dependency(account, {"kind": "reconcile-roots",
            "sources": [essential_use_id, dependent_use_id], "source_cursor": 0,
            "cause_cursor": -1, "roots_seen": {}})
        self._event("dependency-removed", account_id=account["id"],
                    dependent_use_id=dependent_use_id, essential_use_id=essential_use_id)
        return {"changed": True, "dependent": dependent_use_id, "essential": essential_use_id}

    def _enqueue_dependency(self, account, job):
        job.update(account_id=account["id"], epoch=account.get("dependency_epoch", 0))
        self.state.setdefault("dependency_queue", []).append(job)
        account["dependency_pending_count"] = account.get("dependency_pending_count", 0) + 1
        account["dependencies_pending"] = True
        account["dependency_notice"] = (
            "Explicit dependency propagation is pending. All working-use applications in this account "
            "are deferred for automatic supply; readable contents remain available for examination. "
            "No unprocessed application has been checked clear.")

    def _set_dependency_cause(self, account, use, root, blocked, changed):
        causes = use.setdefault("blocked_by", {})
        before = bool(causes)
        if blocked and use["id"] != root["id"]:
            causes[root["id"]] = True
            if root["id"] not in use.setdefault("blocker_known", {}):
                use["blocker_known"][root["id"]] = True
                use.setdefault("blocker_order", []).append(root["id"])
            if use["id"] not in root.setdefault("dependency_target_index", {}):
                root["dependency_target_index"][use["id"]] = True
                root.setdefault("dependency_target_order", []).append(use["id"])
        else:
            causes.pop(root["id"], None)
        use["blocked"] = bool(causes)
        if use["blocked"]:
            use["dependency_reason"] = "An explicitly essential use is parked; this application is deferred, not declared false."
        else:
            use.pop("dependency_reason", None)
        if before != use["blocked"]:
            changed.append(use["id"])
            self._event("dependency-use-updated", account_id=account["id"],
                        use_id=use["id"], blocked=use["blocked"], root_use_id=root["id"])

    def process_dependencies(self):
        """Inspect a bounded number of explicit dependency records/edges.

        Cause propagation removes only the effects of a reactivated root use.
        Another parked root still blocks the application. Cycles are visited
        once per job. A saved account-wide defer prevents undiscovered affected
        applications from being advertised as clear during partial traversal.
        """
        queue = self.state.setdefault("dependency_queue", [])
        cursor = self.state.setdefault("dependency_queue_cursor", 0)
        allowance = self.policy.get("dependency_slice", 64)
        deadline = time.monotonic() + min(float(self.policy.get("timeout_seconds", 120)), 1.0)
        work = 0
        changed = []
        while cursor < len(queue) and work < allowance and time.monotonic() < deadline:
            job = queue[cursor]
            account = self.account(job["account_id"])
            done = False
            work += 1
            if job["kind"] == "reconcile-roots":
                if job["source_cursor"] >= len(job["sources"]):
                    done = True
                else:
                    source = self._use(account, job["sources"][job["source_cursor"]])
                    position = job["cause_cursor"]
                    root_id = None
                    if position == -1:
                        root_id = source["id"]
                    elif position < len(source.get("blocker_order", [])):
                        root_id = source["blocker_order"][position]
                    else:
                        job["source_cursor"] += 1
                        job["cause_cursor"] = -2
                    job["cause_cursor"] += 1
                    if root_id is not None and root_id not in job["roots_seen"]:
                        job["roots_seen"][root_id] = True
                        self._enqueue_dependency(account, {"kind": "cascade", "root": root_id,
                            "frontier": [{"use_id": root_id, "edge": -1}], "frontier_cursor": 0,
                            "visited": {root_id: True}, "reconcile": True, "reconcile_cursor": 0})
            elif job["kind"] == "inherit":
                essential = self._use(account, job["essential"])
                dependent = self._use(account, job["dependent"])
                cause_cursor = job["cause_cursor"]
                root = None
                if essential["id"] not in dependent.get("depends_on_index", {}):
                    done = True
                elif cause_cursor == -1:
                    if essential["disposition"] == "parked":
                        root = essential["id"]
                elif cause_cursor < len(essential.get("blocker_order", [])):
                    candidate = essential["blocker_order"][cause_cursor]
                    if candidate in essential.get("blocked_by", {}):
                        root = candidate
                else:
                    done = True
                job["cause_cursor"] += 1
                if root is not None:
                    seed = job["dependent"]
                    self._enqueue_dependency(account, {"kind": "cascade", "root": root,
                        "frontier": [{"use_id": seed, "edge": -1}], "frontier_cursor": 0,
                        "visited": {seed: True}})
            else:
                front_cursor = job["frontier_cursor"]
                if front_cursor >= len(job["frontier"]):
                    root = self._use(account, job["root"])
                    position = job.get("reconcile_cursor", 0)
                    targets = root.get("dependency_target_order", [])
                    if not job.get("reconcile") or position >= len(targets):
                        done = True
                    else:
                        target_id = targets[position]
                        job["reconcile_cursor"] = position + 1
                        if target_id not in job["visited"] or root["disposition"] != "parked":
                            self._set_dependency_cause(account, self._use(account, target_id), root, False, changed)
                else:
                    item = job["frontier"][front_cursor]
                    use = self._use(account, item["use_id"])
                    if item["edge"] == -1:
                        root = self._use(account, job["root"])
                        self._set_dependency_cause(account, use, root, root["disposition"] == "parked", changed)
                        item["edge"] = 0
                    elif item["edge"] < len(use.get("dependents", [])):
                        dependent_id = use["dependents"][item["edge"]]
                        item["edge"] += 1
                        if dependent_id not in job["visited"]:
                            job["visited"][dependent_id] = True
                            job["frontier"].append({"use_id": dependent_id, "edge": -1})
                    else:
                        job["frontier_cursor"] += 1
            if done:
                account["dependency_pending_count"] -= 1
                account["dependencies_pending"] = account["dependency_pending_count"] > 0
                if not account["dependencies_pending"]:
                    account["dependency_notice"] = "Explicit dependency queue complete; implicit dependencies remain interpretive."
                cursor += 1
        self.state["dependency_queue_cursor"] = cursor
        if cursor == len(queue):
            self.state["dependency_queue"] = []
            self.state["dependency_queue_cursor"] = 0
        return {"work": work, "changed_uses": changed, "pending": len(queue) - cursor,
                "complete": cursor == len(queue)}
