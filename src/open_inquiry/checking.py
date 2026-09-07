"""Bounded read-only literal existence predicates with scoped observations.

Spec: ``Quote-by-phrase has a precise, limited contract``, ``Checkers have their
own bounded work allowance``, and ``Checker correction``. This module reports
what its comparison found; the engine alone owns authorised consequences.

Jobs advance through a fixed-capacity FIFO round-robin queue. The scanner saves
its byte cursor and KMP boundary state, including partial UTF-8 characters.
An existence check stops at its first match. Collection.search is the separate
route for enumerating every duplicate occurrence. A match can settle existence
without claiming complete scan coverage. Rechecking always creates a fresh
job and fresh receipt; immutable completed-result caching is explicit.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import time
from typing import Any

from .collection import Collection, _pattern_table, _positive_int, _scan_literal


_SCOPE = ("source_id", "source_version", "representation", "comparison",
          "checker_version", "phrase", "start", "end")


class Checker:
    """A JSON-compatible checker queue; neither a model nor a truth oracle."""

    def __init__(self, data: dict[str, Any] | None = None, *, max_pending: int = 64,
                 max_phrase_bytes: int = 65536, timeout_seconds: float = 1.0):
        self.max_pending = _positive_int(max_pending, "max_pending")
        self.max_phrase_bytes = _positive_int(max_phrase_bytes, "max_phrase_bytes")
        if not isinstance(timeout_seconds, (int, float)) or not 0 < timeout_seconds <= 60:
            raise ValueError("timeout_seconds must be greater than zero and at most 60")
        self.timeout_seconds = timeout_seconds
        self.data = data if data is not None else {}
        for key, default in (("checks", {}), ("queue", []), ("receipts", {}),
                             ("cache", {}), ("next_check", 1), ("next_receipt", 1)):
            self.data.setdefault(key, default)

    def add(self, collection: Collection, source_id: str, phrase: str,
            start: int = 0, end: int | None = None, comparison: str = "literal",
            version: str = "1") -> str:
        """Schedule one explicit check/recheck against the current fixed source.

        Invalid predicate inputs generate checker-error receipts when serviced;
        an unresolved source generates unavailable. Capacity failure is an
        operational refusal to enqueue, not a judgment about the prose.
        """
        if len(self.data["queue"]) >= self.max_pending:
            raise ValueError("checker queue is full; no additional check was scheduled")
        source = collection.data["occurrences"].get(source_id)
        actual_end = len(source["text"]) if end is None and source is not None else end
        check_id = f"check{self.data['next_check']:06d}"
        job = {
            "id": check_id, "source_id": source_id,
            "source_version": source["version"] if source is not None else None,
            "representation": source["representation"] if source is not None else None,
            "comparison": comparison, "checker_version": str(version),
            "phrase": phrase, "start": start, "end": actual_end,
            "status": "pending", "byte_cursor": 0, "end_byte": 0,
            "prefix": 0, "chars_seen": start, "work_bytes": 0,
            "utf8_pending": 0,
            "last_receipt": None, "error": None,
        }
        if not isinstance(phrase, str) or not phrase:
            job["error"] = "literal checking requires a nonempty character sequence"
        elif len(phrase.encode("utf-8")) > self.max_phrase_bytes:
            job["error"] = f"phrase exceeds {self.max_phrase_bytes} UTF-8 bytes"
        elif comparison != "literal":
            job["error"] = f"unsupported comparison: {comparison}"
        elif isinstance(start, bool) or not isinstance(start, int) or start < 0:
            job["error"] = "start must be a nonnegative character offset"
        elif source is not None and (isinstance(actual_end, bool) or
                                    not isinstance(actual_end, int) or
                                    not start <= actual_end <= len(source["text"])):
            job["error"] = "range must be inside the fixed readable representation"
        elif source is not None:
            try:
                job["byte_cursor"] = collection._char_to_byte(source_id, start)
                job["end_byte"] = collection._char_to_byte(source_id, actual_end)
            except (KeyError, IndexError, TypeError):
                job["error"] = "representation index is unavailable or malformed"
        if job["error"] is None:
            key = json.dumps({field: job[field] for field in _SCOPE},
                             sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            job["cache_key"] = hashlib.sha256(key.encode("utf-8")).hexdigest()
            job["cached_receipt"] = self.data["cache"].get(job["cache_key"])
            if isinstance(phrase, str):
                job["prefix_table"] = _pattern_table(phrase.encode("utf-8"))
        # All retained fields are JSON-compatible. Fail before mutating state.
        json.dumps(job, allow_nan=False)
        self.data["checks"][check_id] = job
        self.data["queue"].append(check_id)
        self.data["next_check"] += 1
        return check_id

    def step(self, collection: Collection, slices: int = 4,
             slice_bytes: int = 65536) -> list[dict[str, Any]]:
        """Service at most ``slices`` jobs with independent byte allowances.

        One job may receive successive slices when it is the only pending job.
        Incomplete receipts remain observations of their actual saved prefix.
        No cache lookup, timeout, or source failure is relabelled as absence.
        """
        if isinstance(slices, bool) or not isinstance(slices, int) or slices < 0:
            raise ValueError("slices must be a nonnegative integer")
        _positive_int(slice_bytes, "slice_bytes")
        emitted = []
        for _ in range(slices):
            if not self.data["queue"]:
                break
            check_id = self.data["queue"].pop(0)
            job = self.data["checks"][check_id]
            try:
                result, pending = self._step_job(collection, job, slice_bytes)
            except Exception:
                # Exceptions are operational checker failure, never no-match.
                # Raw exception messages may carry private paths or input data.
                result = self._receipt(job, "checker-error", scan_complete=False,
                                       reason="Checker failed while reading or comparing the representation")
                pending = False
            job["status"] = result["status"]
            job["last_receipt"] = result["id"]
            self.data["receipts"][result["id"]] = result
            if pending:
                self.data["queue"].append(check_id)
            elif result["status"] in {"matched", "completed-no-match"}:
                self.data["cache"][job["cache_key"]] = result["id"]
            emitted.append(deepcopy(result))
        return emitted

    def _step_job(self, collection: Collection, job: dict[str, Any],
                  allowance: int) -> tuple[dict[str, Any], bool]:
        if job["error"] is not None:
            return self._receipt(job, "checker-error", reason=job["error"]), False
        source = collection.data["occurrences"].get(job["source_id"])
        if source is None or not source.get("readable", False):
            return self._receipt(job, "unavailable", reason="No readable fixed source representation"), False
        if (source["version"] != job["source_version"] or
                source["representation"] != job["representation"]):
            return self._receipt(job, "unavailable", reason="Source version or representation changed after scheduling"), False
        if job.get("cached_receipt"):
            earlier = self.data["receipts"][job["cached_receipt"]]
            # A new explicit job produces a new observation identity. The old
            # receipt is never silently replayed as a new operating event.
            return self._receipt(job, earlier["status"],
                                 offsets=earlier["match_offsets"],
                                 scan_complete=earlier["scan_complete"],
                                 cached=True, cache_receipt_id=earlier["id"],
                                 scanned_end=earlier["scanned_end"],
                                 inspected_bytes=0), False
        remaining = job["end_byte"] - job["byte_cursor"]
        if remaining:
            pattern = job["phrase"].encode("utf-8")
            chunk = collection._byte_slice(job["source_id"], job["byte_cursor"], min(allowance, remaining))
            if not chunk:
                return self._receipt(job, "unavailable", reason="Representation bytes ended before the declared range"), False
            offsets, consumed, prefix, chars_seen, utf8_pending = _scan_literal(
                chunk, pattern, job["prefix_table"], prefix=job["prefix"],
                chars_seen=job["chars_seen"], phrase_chars=len(job["phrase"]), max_matches=1,
                deadline=time.monotonic() + self.timeout_seconds,
                utf8_pending=job.get("utf8_pending", 0))
            job.update(byte_cursor=job["byte_cursor"] + consumed,
                       prefix=prefix, chars_seen=chars_seen,
                       utf8_pending=utf8_pending,
                       work_bytes=job["work_bytes"] + consumed)
        else:
            offsets, consumed = [], 0
        at_end = job["byte_cursor"] >= job["end_byte"]
        coverage = at_end and source.get("extraction_complete", True)
        if offsets:
            return self._receipt(job, "matched", offsets=offsets, scan_complete=coverage,
                                 inspected_bytes=consumed), False
        if at_end:
            if coverage:
                return self._receipt(job, "completed-no-match", scan_complete=True,
                                     inspected_bytes=consumed), False
            return self._receipt(job, "incomplete", reason="Extraction is incomplete; no absence claim is available",
                                 inspected_bytes=consumed), False
        return self._receipt(job, "incomplete", reason="This work slice ended before the declared range was complete",
                             inspected_bytes=consumed), True

    def _receipt(self, job: dict[str, Any], status: str, *, offsets=(),
                 scan_complete: bool = False, **details) -> dict[str, Any]:
        receipt_id = f"receipt{self.data['next_receipt']:06d}"
        self.data["next_receipt"] += 1
        return {
            **{key: job[key] for key in _SCOPE}, "id": receipt_id, "check_id": job["id"],
            "status": status, "match_offsets": list(offsets),
            "scan_complete": scan_complete, "predicate_resolved": status in {"matched", "completed-no-match"},
            "offset_unit": "unicode-characters", "byte_cursor": job["byte_cursor"],
            "scanned_end": job["chars_seen"] - int(bool(job.get("utf8_pending", 0))),
            "total_inspected_bytes": job["work_bytes"],
            "cached": False, "inspected_bytes": 0,
            "meaning": "Literal occurrence in the identified representation; no claim about endorsement, truth, or explanatory force.",
            **details,
        }
