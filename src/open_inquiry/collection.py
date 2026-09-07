"""Retain occurrences faithfully and open them with bounded, unranked access.

Spec: ``A shared working collection``, ``Source access does not require coding``,
and ``Quote-by-phrase has a precise, limited contract``. Retention gives no
working-use rights. Public offsets count Unicode characters; work allowances
count UTF-8 representation bytes. Original source bytes are a separate carrier.

Ingestion prepares fixed-size byte blocks and sparse character indexes once.
Subsequent reads and resumable literal searches need not encode or scan an
entire source. Search snapshots the submission-order boundary; later additions
are available to a new search, without changing an already open continuation.
"""

from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
from typing import Any


_BLOCK_BYTES = 4096
_CHAR_STRIDE = 1024
_MAX_PAGE = 1000
_MAX_SOURCE_SET = 1024


def _bounded_addresses(values, name: str) -> list[str]:
    result = []
    seen = set()
    for index, value in enumerate(values):
        if index >= _MAX_SOURCE_SET:
            raise ValueError(f"{name} exceeds {_MAX_SOURCE_SET} entries; page the request")
        if not isinstance(value, str):
            raise ValueError(f"{name} must contain occurrence addresses")
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _positive_int(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _nonnegative_int(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _pattern_table(pattern: bytes) -> list[int]:
    """KMP prefix table: overlap survives chunk and page boundaries."""
    table = [0] * len(pattern)
    matched = 0
    for i in range(1, len(pattern)):
        while matched and pattern[i] != pattern[matched]:
            matched = table[matched - 1]
        if pattern[i] == pattern[matched]:
            matched += 1
        table[i] = matched
    return table


def _scan_literal(chunk: bytes, pattern: bytes, table: list[int], *,
                  prefix: int, chars_seen: int, phrase_chars: int,
                  max_matches: int, deadline: float | None = None,
                  utf8_pending: int = 0) -> tuple[list[int], int, int, int, int]:
    """Inspect at most this chunk, returning offsets and resumable state."""
    offsets: list[int] = []
    consumed = 0
    for byte in chunk:
        if deadline is not None and consumed % 1024 == 0 and time.monotonic() >= deadline:
            break
        consumed += 1
        if byte & 0xC0 != 0x80:
            chars_seen += 1
            utf8_pending = 0 if byte < 0x80 else 1 if byte < 0xE0 else 2 if byte < 0xF0 else 3
        else:
            utf8_pending = max(0, utf8_pending - 1)
        while prefix and byte != pattern[prefix]:
            prefix = table[prefix - 1]
        if byte == pattern[prefix]:
            prefix += 1
        if prefix == len(pattern):
            offsets.append(chars_seen - phrase_chars)
            prefix = table[prefix - 1]
            if len(offsets) >= max_matches:
                break
    return offsets, consumed, prefix, chars_seen, utf8_pending


class Collection:
    """JSON-backed immutable occurrences, mutable navigational relationships.

    ``get`` returns a snapshot. Changes to prose create a new occurrence; no
    update API overwrites source content or its version. The owning engine is
    responsible for protecting its private ``data`` from external mutation.
    """

    def __init__(self, data: dict[str, Any] | None = None, *,
                 max_source_bytes: int = 16_777_216,
                 max_collection_bytes: int = 134_217_728):
        self.max_source_bytes = _positive_int(max_source_bytes, "max_source_bytes")
        self.max_collection_bytes = _positive_int(max_collection_bytes, "max_collection_bytes")
        self.data = data if data is not None else {}
        self.data.setdefault("occurrences", {})
        self.data.setdefault("order", [])
        self.data.setdefault("adjacency", {})
        self.data.setdefault("next_id", len(self.data["order"]) + 1)
        self.data.setdefault("total_bytes", sum(
            item.get("retained_bytes", len(item.get("text", "").encode("utf-8")))
            for item in self.data["occurrences"].values()))
        if "adjacency_streams" not in self.data:
            self.data["adjacency_streams"] = {}
            self.data["adjacency_stream_order"] = {}
            for source, edges in self.data["adjacency"].items():
                for index, edge in enumerate(edges):
                    self._index_edge(source, edge.get("stream", "default"), index)
        self.data.setdefault("adjacency_stream_order", {})

    def add(self, text: str, origin: str, label: str = "", links=(), **metadata) -> str:
        """Retain prose exactly, including an empty or malformed reply.

        Metadata describes operational provenance, never intellectual merit.
        Physical limit failures are explicit and leave the collection intact.
        """
        if not isinstance(text, str) or not isinstance(origin, str):
            raise TypeError("text and origin must be strings")
        links = _bounded_addresses(links, "links")
        encoded = text.encode("utf-8")
        raw_b64 = metadata.pop("original_bytes_b64", None)
        raw_size = metadata.pop("original_byte_count", 0)
        if raw_b64 is not None:
            original = base64.b64decode(raw_b64, validate=True)
            if raw_size != len(original):
                raise ValueError("original byte count does not match retained bytes")
        retained_size = len(encoded) + raw_size
        if max(len(encoded), raw_size) > self.max_source_bytes:
            raise ValueError("source exceeds max_source_bytes; nothing was ingested")
        if self.data["total_bytes"] + retained_size > self.max_collection_bytes:
            raise ValueError("collection exceeds max_collection_bytes; nothing was ingested")
        representation = metadata.pop("representation", "unicode-text-v1")
        readable = metadata.pop("readable", True)
        extraction_complete = metadata.pop("extraction_complete", True)
        reserved = {"id", "text", "origin", "label", "version", "retained_bytes",
                    "byte_blocks", "char_byte_index", "representation_byte_count"}
        if reserved.intersection(metadata):
            raise ValueError("metadata cannot replace immutable occurrence fields")
        # Validate provenance before changing host state.
        json.dumps(metadata, allow_nan=False)
        source_hash = hashlib.sha256(original if raw_b64 is not None else encoded).hexdigest()
        version = hashlib.sha256(
            (source_hash + "\0" + representation + "\0").encode("utf-8") + encoded
        ).hexdigest()
        char_index = [0]
        byte_offset = 0
        for start in range(0, len(text), _CHAR_STRIDE):
            byte_offset += len(text[start:start + _CHAR_STRIDE].encode("utf-8"))
            char_index.append(byte_offset)
        occurrence_id = f"o{self.data['next_id']:06d}"
        item = {
            **deepcopy(metadata), "id": occurrence_id, "text": text,
            "origin": origin, "label": str(label), "version": version,
            "representation": representation, "readable": bool(readable),
            "extraction_complete": bool(extraction_complete),
            "source_sha256": source_hash, "retained_bytes": retained_size,
            "representation_byte_count": len(encoded),
            "byte_blocks": [base64.b64encode(encoded[i:i + _BLOCK_BYTES]).decode("ascii")
                            for i in range(0, len(encoded), _BLOCK_BYTES)],
            "char_byte_index": char_index,
        }
        if raw_b64 is not None:
            item.update(original_bytes_b64=raw_b64, original_byte_count=raw_size)
        self.data["occurrences"][occurrence_id] = item
        self.data["order"].append(occurrence_id)
        self.data["next_id"] += 1
        self.data["total_bytes"] += retained_size
        self.data["adjacency"].setdefault(occurrence_id, [])
        for target in links:
            self.link(occurrence_id, target)
        return occurrence_id

    def get(self, occurrence_id: str) -> dict[str, Any] | None:
        item = self.data["occurrences"].get(occurrence_id)
        return deepcopy(item) if item is not None else None

    def _index_edge(self, source: str, stream: str, index: int) -> None:
        streams = self.data["adjacency_streams"].setdefault(source, {})
        if stream not in streams:
            streams[stream] = []
            self.data["adjacency_stream_order"].setdefault(source, []).append(stream)
        streams[stream].append(index)

    def link(self, a: str, b: str, stream: str = "default") -> None:
        """Add one directed navigation edge; missing targets stay missing."""
        if a not in self.data["occurrences"]:
            raise KeyError(f"unknown link origin: {a}")
        if not isinstance(b, str) or not isinstance(stream, str) or not stream:
            raise ValueError("link target and stream must be strings; stream is nonempty")
        edges = self.data["adjacency"].setdefault(a, [])
        edges.append({"target": b, "stream": stream})
        self._index_edge(a, stream, len(edges) - 1)

    def ingest(self, path) -> str:
        """Read UTF-8 text/Markdown or optional pypdf text extraction.

        Unsupported media retain their actual bytes and an unreadable status.
        PDF extraction never claims byte or page-image fidelity. Image-only or
        failed pages make the extraction incomplete; no OCR is invented.
        """
        source_path = Path(path)
        with source_path.open("rb") as handle:
            raw = handle.read(self.max_source_bytes + 1)
        if len(raw) > self.max_source_bytes:
            raise ValueError("source exceeds max_source_bytes; nothing was ingested")
        metadata: dict[str, Any] = {
            "original_bytes_b64": base64.b64encode(raw).decode("ascii"),
            "original_byte_count": len(raw), "filename": source_path.name,
            "source_path": str(source_path), "representation": "unreadable-original-v1",
            "readable": False, "extraction_complete": False,
        }
        text = ""
        suffix = source_path.suffix.lower()
        if suffix in {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".rst", ""}:
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                metadata["readability_note"] = "Original bytes retained; decoding as UTF-8 failed."
            else:
                metadata.update(representation="utf8-text-v1", readable=True,
                                extraction_complete=True, parser="python-utf8-strict")
        elif suffix == ".pdf":
            text, details = self._extract_pdf(raw)
            metadata.update(details)
        else:
            metadata["readability_note"] = f"No installed adapter for {suffix or 'this media'}; original bytes retained."
        return self.add(text, "source", label=source_path.name, **metadata)

    @staticmethod
    def _extract_pdf(raw: bytes) -> tuple[str, dict[str, Any]]:
        try:
            import pypdf
        except ImportError:
            return "", {"readability_note": "PDF bytes retained; optional pypdf is not installed."}
        from io import BytesIO
        try:
            reader = pypdf.PdfReader(BytesIO(raw))
            count = len(reader.pages)
            pieces: list[str] = []
            ranges: list[dict[str, Any]] = []
            offset = 0
            complete = count <= 256
            for number in range(min(count, 256)):
                try:
                    piece = reader.pages[number].extract_text() or ""
                except Exception:
                    piece = ""
                has_text = bool(piece.strip())
                complete = complete and has_text
                if number:
                    pieces.append("\n\f\n")
                    offset += 3
                ranges.append({"page": number + 1, "start": offset,
                               "end": offset + len(piece), "readable": has_text})
                pieces.append(piece)
                offset += len(piece)
            text = "".join(pieces)
            return text, {
                "representation": f"pypdf-extracted-text-{pypdf.__version__}",
                "parser": f"pypdf {pypdf.__version__}",
                "readable": any(item["readable"] for item in ranges),
                "extraction_complete": complete, "page_ranges": ranges,
                "page_count": count,
                "readability_note": "Text extraction is not the printed page. " +
                    ("All visited pages supplied text." if complete else
                     "Extraction incomplete: unread pages, failed extraction, or 256-page limit."),
            }
        except Exception:
            return "", {"readability_note": "PDF extraction failed; original bytes retained."}

    def catalogue(self, cursor: int = 0, limit: int = 10) -> dict[str, Any]:
        _nonnegative_int(cursor, "cursor")
        _positive_int(limit, "limit")
        if limit > _MAX_PAGE:
            raise ValueError(f"catalogue limit exceeds {_MAX_PAGE}")
        order = self.data["order"]
        stop = min(cursor + limit, len(order))
        items = []
        for occurrence_id in order[cursor:stop]:
            item = self.data["occurrences"][occurrence_id]
            items.append({key: item[key] for key in
                          ("id", "origin", "label", "version", "representation", "readable")})
            items[-1]["characters"] = len(item["text"])
            items[-1]["extraction_complete"] = item.get("extraction_complete", True)
        complete = stop >= len(order)
        return {"items": items, "next_cursor": None if complete else stop, "complete": complete}

    def read(self, occurrence_id: str, start: int = 0, limit: int = 4000) -> dict[str, Any]:
        _nonnegative_int(start, "start")
        _positive_int(limit, "limit")
        if limit > self.max_source_bytes:
            raise ValueError("read limit exceeds max_source_bytes")
        item = self.data["occurrences"].get(occurrence_id)
        if item is None or not item.get("readable", False):
            return {"id": occurrence_id, "text": "", "start": start, "end": start,
                    "next_cursor": None, "complete": False, "status": "unavailable",
                    "reason": "Unknown occurrence" if item is None else
                    item.get("readability_note", "No readable representation"),
                    "version": None if item is None else item["version"],
                    "representation": None if item is None else item["representation"]}
        end = min(start + limit, len(item["text"]))
        start = min(start, len(item["text"]))
        at_end = end >= len(item["text"])
        extraction_complete = item.get("extraction_complete", True)
        return {"id": occurrence_id, "text": item["text"][start:end],
                "start": start, "end": end, "next_cursor": None if at_end else end,
                "complete": at_end and extraction_complete, "representation_complete": at_end,
                "extraction_complete": extraction_complete, "status": "readable",
                "version": item["version"], "representation": item["representation"],
                "offset_unit": "unicode-characters"}

    def _char_to_byte(self, occurrence_id: str, char_offset: int) -> int:
        item = self.data["occurrences"][occurrence_id]
        block, remainder = divmod(char_offset, _CHAR_STRIDE)
        return item["char_byte_index"][block] + len(
            item["text"][block * _CHAR_STRIDE:block * _CHAR_STRIDE + remainder].encode("utf-8"))

    def _byte_slice(self, occurrence_id: str, start: int, limit: int) -> bytes:
        item = self.data["occurrences"][occurrence_id]
        end = min(start + limit, item["representation_byte_count"])
        if end <= start:
            return b""
        first = start // _BLOCK_BYTES
        last = (end - 1) // _BLOCK_BYTES
        chunks = []
        for index in range(first, last + 1):
            block = base64.b64decode(item["byte_blocks"][index], validate=True)
            begin = max(0, start - index * _BLOCK_BYTES)
            stop = min(len(block), end - index * _BLOCK_BYTES)
            chunks.append(block[begin:stop])
        return b"".join(chunks)

    def search(self, phrase: str, cursor: dict[str, Any] | None = None,
               page_size: int = 10, work_bytes: int = 65536,
               source_ids=None, timeout_seconds: float = 1.0) -> dict[str, Any]:
        """Enumerate exact occurrences without ranks, including overlaps.

        ``complete`` means all declared readable representations were covered.
        ``traversal_complete`` may be true with unavailable/incomplete sources;
        that situation never supplies a completed-no-match result. Each call
        inspects at most ``work_bytes`` source bytes and 1024 source records.
        """
        if not isinstance(phrase, str) or not phrase:
            raise ValueError("literal search requires a nonempty phrase")
        _positive_int(page_size, "page_size")
        _positive_int(work_bytes, "work_bytes")
        if not isinstance(timeout_seconds, (int, float)) or not 0 < timeout_seconds <= 60:
            raise ValueError("timeout_seconds must be greater than zero and at most 60")
        deadline = time.monotonic() + timeout_seconds
        if page_size > _MAX_PAGE:
            raise ValueError(f"search page size exceeds {_MAX_PAGE}")
        pattern = phrase.encode("utf-8")
        if len(pattern) > 65536:
            raise ValueError("search phrase exceeds 65536 UTF-8 bytes")
        signature = hashlib.sha256(pattern).hexdigest()
        if cursor is None:
            selected = _bounded_addresses(source_ids, "source_ids") if source_ids is not None else None
            cursor = {"phrase_sha256": signature, "source_ids": selected,
                      "stop_index": len(selected) if selected is not None else len(self.data["order"]),
                      "index": 0, "byte_cursor": 0, "prefix": 0, "chars_seen": 0,
                      "utf8_pending": 0,
                      "unavailable_count": 0, "found_any": False, "source_version": None}
        else:
            cursor = deepcopy(cursor)
            if cursor.get("phrase_sha256") != signature:
                raise ValueError("continuation belongs to a different phrase")
            if source_ids is not None and _bounded_addresses(source_ids, "source_ids") != cursor.get("source_ids"):
                raise ValueError("continuation belongs to a different source set")
        order = cursor["source_ids"] if cursor["source_ids"] is not None else self.data["order"]
        table = _pattern_table(pattern)
        items = []
        unavailable = []
        used = 0
        inspected = 0
        while cursor["index"] < cursor["stop_index"] and used < work_bytes and len(items) < page_size and inspected < 1024:
            if time.monotonic() >= deadline:
                break
            inspected += 1
            occurrence_id = order[cursor["index"]]
            source = self.data["occurrences"].get(occurrence_id)
            changed = source is not None and cursor["source_version"] not in (None, source["version"])
            if source is None or not source.get("readable") or changed:
                cursor["unavailable_count"] += 1
                unavailable.append({"source_id": occurrence_id, "reason":
                    "Source changed during continuation" if changed else "No readable representation"})
                self._next_search_source(cursor)
                continue
            cursor["source_version"] = source["version"]
            size = source["representation_byte_count"]
            chunk = self._byte_slice(occurrence_id, cursor["byte_cursor"], work_bytes - used)
            offsets, consumed, prefix, chars_seen, utf8_pending = _scan_literal(
                chunk, pattern, table, prefix=cursor["prefix"], chars_seen=cursor["chars_seen"],
                phrase_chars=len(phrase), max_matches=page_size - len(items), deadline=deadline,
                utf8_pending=cursor.get("utf8_pending", 0))
            for offset in offsets:
                items.append({"id": occurrence_id, "source_id": occurrence_id,
                              "source_version": source["version"],
                              "representation": source["representation"], "comparison": "literal",
                              "offset": offset, "start": offset, "end": offset + len(phrase),
                              "offset_unit": "unicode-characters"})
            cursor.update(byte_cursor=cursor["byte_cursor"] + consumed,
                          prefix=prefix, chars_seen=chars_seen, utf8_pending=utf8_pending)
            used += consumed
            cursor["found_any"] = cursor["found_any"] or bool(offsets)
            if cursor["byte_cursor"] >= size:
                if not source.get("extraction_complete", True):
                    cursor["unavailable_count"] += 1
                    unavailable.append({"source_id": occurrence_id, "reason": "Source extraction is incomplete"})
                self._next_search_source(cursor)
            elif consumed == 0:
                break
        finished = cursor["index"] >= cursor["stop_index"]
        complete = finished and cursor["unavailable_count"] == 0
        status = "matched" if cursor["found_any"] else "completed-no-match" if complete else "incomplete"
        return {"items": items, "next_cursor": None if finished else cursor,
                "complete": complete, "traversal_complete": finished, "status": status,
                "work_bytes": used, "inspected_sources": inspected, "unavailable": unavailable,
                "unavailable_count": cursor["unavailable_count"], "comparison": "literal",
                "timed_out": not finished and time.monotonic() >= deadline,
                "offset_unit": "unicode-characters"}

    @staticmethod
    def _next_search_source(cursor: dict[str, Any]) -> None:
        cursor.update(index=cursor["index"] + 1, byte_cursor=0, prefix=0,
                      chars_seen=0, utf8_pending=0, source_version=None)
