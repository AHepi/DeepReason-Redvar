"""Token-volume reservations, implementing specification Part VII.

This module accounts for service; it does not appraise reasoning. A reservation
owns both volume and call slots, including promised future trial returns. The
controller reserves individual future keys before opening a trial. Unknown
post-dispatch consumption keeps its conservative charge; it never becomes zero.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


class ResourceError(ValueError):
    """An invalid resource transition, with no change to the ledger."""


class BudgetExceeded(ResourceError):
    """There is insufficient unreserved allowance for this request."""


def _natural(value: Any, name: str, *, positive: bool = False) -> int:
    if type(value) is not int or value < int(positive):
        raise ResourceError(f"{name} must be a {'positive' if positive else 'nonnegative'} integer")
    return value


def _usage_charge(usage: dict | None, reserved: int) -> tuple[dict | None, int, bool, int | None]:
    """Keep only accounting facts; never retain arbitrary provider response fields.

    Cache is a subset of input. Separate reasoning contributes only when its
    inclusion relationship is explicitly false. Unknown inclusion preserves the
    reservation, or a larger already observed lower bound.
    """
    if not isinstance(usage, dict):
        return None, reserved, True, None
    facts: dict[str, Any] = {}
    for name in ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens"):
        value = usage.get(name)
        facts[name] = value if type(value) is int and value >= 0 else None
    included = usage.get("reasoning_included")
    facts["reasoning_included"] = included if type(included) is bool else None
    input_count, output_count = facts["input_tokens"], facts["output_tokens"]
    lower_bound = (input_count or 0) + (output_count or 0)
    reasoning = facts["reasoning_tokens"]
    if facts["reasoning_included"] is False and reasoning is not None:
        lower_bound += reasoning
    unknown = input_count is None or output_count is None
    if usage.get("accounting_complete") is False:
        facts["accounting_complete"] = False
        unknown = True
    if reasoning and facts["reasoning_included"] is None:
        unknown = True
    if facts["reasoning_included"] is False and reasoning is None:
        unknown = True
    cached = facts["cached_input_tokens"]
    if cached is not None and input_count is not None and cached > input_count:
        unknown = True
        facts["cache_counter_inconsistent"] = True
    return facts, max(reserved, lower_bound) if unknown else lower_bound, unknown, None if unknown else lower_bound


class Ledger:
    """A sequential, persistable ledger with idempotent operation identities.

    ``data`` is shared with the controller state for ordinary JSON persistence.
    A restored ledger retains its saved envelope, irrespective of constructor
    defaults. The controller owns concurrency and operator policy changes.
    """

    def __init__(self, data: dict | None = None, *, max_calls: int = 24, max_tokens: int = 262144):
        self.data = data if data is not None else {
            "max_calls": _natural(max_calls, "max_calls"),
            "max_tokens": _natural(max_tokens, "max_tokens"),
            "entries": {}, "paused": False, "pause_reason": None,
        }
        _natural(self.data["max_calls"], "max_calls")
        _natural(self.data["max_tokens"], "max_tokens")
        if not isinstance(self.data.get("entries"), dict):
            raise ResourceError("ledger entries must be a mapping")

    @property
    def paused(self) -> bool:
        return bool(self.data.get("paused", False))

    def _totals(self) -> dict:
        totals = {"charged_tokens": 0, "reserved_tokens": 0, "used_calls": 0,
                  "reserved_calls": 0, "unknown_calls": 0}
        for entry in self.data["entries"].values():
            if entry["status"] == "settled":
                totals["charged_tokens"] += entry["charged_tokens"]
                totals["used_calls"] += entry["calls"]
                totals["unknown_calls"] += entry["calls"] if entry["unknown"] else 0
            elif entry["status"] == "dispatched":
                totals["reserved_tokens"] += entry["amount"]
                totals["used_calls"] += entry["calls"]
            elif entry["status"] == "reserved":
                totals["reserved_tokens"] += entry["amount"]
                totals["reserved_calls"] += entry["calls"]
        return totals

    def available(self) -> dict:
        totals = self._totals()
        return {
            "tokens": self.data["max_tokens"] - totals["charged_tokens"] - totals["reserved_tokens"],
            "calls": self.data["max_calls"] - totals["used_calls"] - totals["reserved_calls"],
        }

    def reserve(self, key: str, amount: int, calls: int = 1) -> dict:
        """Reserve all of a promised unit, or reserve nothing."""
        if not isinstance(key, str) or not key:
            raise ResourceError("reservation key must be nonempty text")
        _natural(amount, "amount")
        _natural(calls, "calls", positive=True)
        old = self.data["entries"].get(key)
        if old is not None:
            if old["amount"] == amount and old["calls"] == calls:
                return deepcopy(old)
            raise ResourceError("reservation identity already has a different amount or call count")
        if self.paused:
            raise BudgetExceeded("resource ledger is paused after a provider overrun")
        available = self.available()
        if amount > available["tokens"] or calls > available["calls"]:
            raise BudgetExceeded("insufficient unreserved token allowance or future call slots")
        entry = {"key": key, "amount": amount, "calls": calls, "status": "reserved",
                 "usage": None, "charged_tokens": 0, "observed_total": None, "unknown": False}
        self.data["entries"][key] = entry
        return deepcopy(entry)

    def _entry(self, key: str) -> dict:
        try:
            return self.data["entries"][key]
        except KeyError:
            raise ResourceError("unknown reservation identity") from None

    def dispatch(self, key: str) -> dict:
        """Mark dispatch before network work. Repeated receipts do not spend twice."""
        entry = self._entry(key)
        if entry["status"] in {"dispatched", "settled"}:
            return deepcopy(entry)
        if entry["status"] == "cancelled":
            raise ResourceError("a cancelled identity cannot be dispatched")
        if self.paused:
            raise BudgetExceeded("resource ledger is paused after a provider overrun")
        entry["status"] = "dispatched"
        return deepcopy(entry)

    def settle(self, key: str, usage: dict | None) -> dict:
        """Settle once, with refinement of genuinely unknown consumption.

        A late reliable report may replace a provisional unknown charge, even
        when the caller has lost mutation permission. Repeated known receipts
        are idempotent. A contradictory decreasing observation remains unknown.
        """
        entry = self._entry(key)
        refining = entry["status"] == "settled" and entry["unknown"]
        if entry["status"] == "settled" and (not refining or not isinstance(usage, dict)):
            return deepcopy(entry)
        if entry["status"] != "dispatched" and not refining:
            raise ResourceError("only a dispatched reservation may settle")
        facts, charge, unknown, observed = _usage_charge(usage, entry["amount"])
        if refining:
            if facts == entry.get("usage"):
                return deepcopy(entry)
            previous = entry.get("usage") or {}
            conflict = any(
                previous.get(field) is not None and facts.get(field) is not None
                and facts[field] < previous[field]
                for field in ("input_tokens", "output_tokens", "reasoning_tokens")
            )
            if conflict:
                facts["accounting_conflict"] = True
                unknown, observed = True, None
            if unknown:
                charge = max(charge, entry["charged_tokens"])
            entry.setdefault("prior_unknown_charge", entry["charged_tokens"])
            entry.setdefault("prior_usage", deepcopy(entry.get("usage")))
            entry["reconciled_from_unknown"] = True
        entry.update(status="settled", usage=facts, charged_tokens=charge,
                     observed_total=observed, unknown=unknown)
        if charge > entry["amount"]:
            self.data["paused"] = True
            self.data["pause_reason"] = "provider consumption exceeded its reservation"
            entry["overrun_tokens"] = charge - entry["amount"]
        return deepcopy(entry)

    def cancel(self, key: str) -> dict:
        """Only cancellation before dispatch releases a claim on the envelope."""
        entry = self._entry(key)
        if entry["status"] == "reserved":
            entry["status"] = "cancelled"
        elif entry["status"] == "dispatched":
            return self.settle(key, None)
        return deepcopy(entry)

    def report(self) -> dict:
        """Read-only accounting snapshot, suitable for CLI display or export."""
        totals = self._totals()
        available = self.available()
        return {"max_calls": self.data["max_calls"], "max_tokens": self.data["max_tokens"],
                **totals, "remaining_tokens": available["tokens"], "remaining_calls": available["calls"],
                "paused": self.paused, "pause_reason": self.data.get("pause_reason"),
                "entries": deepcopy(self.data["entries"])}
