"""Acceptance examples for fidelity and bounded, unranked source access."""

import base64
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from open_inquiry.collection import Collection


class CollectionTests(unittest.TestCase):
    def test_empty_and_malformed_prose_are_retained_without_uses(self):
        collection = Collection()
        empty = collection.add("", "model")
        malformed = collection.add('{"unfinished": I cannot yet explain', "model")
        self.assertEqual(collection.get(empty)["text"], "")
        self.assertEqual(collection.get(malformed)["text"], '{"unfinished": I cannot yet explain')
        self.assertNotIn("uses", collection.data)
        self.assertNotIn("truth", collection.get(malformed))

    def test_utf8_markdown_original_bytes_and_newlines_survive(self):
        original = "\ufeff# Māori\r\nNo: x ≠ y.\r\n".encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.md"
            path.write_bytes(original)
            collection = Collection()
            source = collection.ingest(path)
        item = collection.get(source)
        self.assertEqual(item["text"].encode("utf-8"), original)
        self.assertEqual(base64.b64decode(item["original_bytes_b64"]), original)
        self.assertEqual(item["representation"], "utf8-text-v1")
        self.assertEqual(item["origin"], "source")
        item["text"] = "mutated snapshot"
        self.assertEqual(collection.get(source)["text"].encode("utf-8"), original)

    def test_new_source_bytes_create_new_identity_and_version(self):
        collection = Collection()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.txt"
            path.write_text("first", encoding="utf-8")
            first = collection.ingest(path)
            path.write_text("second", encoding="utf-8")
            second = collection.ingest(path)
        self.assertNotEqual(first, second)
        self.assertNotEqual(collection.get(first)["version"], collection.get(second)["version"])
        self.assertEqual(collection.get(first)["text"], "first")

    def test_unsupported_or_invalid_encoding_remains_unavailable(self):
        collection = Collection()
        with tempfile.TemporaryDirectory() as directory:
            for filename, raw in (("image.png", b"\x89PNG\r\n"), ("broken.txt", b"\xff\xfe")):
                path = Path(directory) / filename
                path.write_bytes(raw)
                source = collection.ingest(path)
                self.assertFalse(collection.get(source)["readable"])
                self.assertEqual(base64.b64decode(collection.get(source)["original_bytes_b64"]), raw)
                self.assertEqual(collection.read(source)["status"], "unavailable")

    def test_catalogue_has_stable_submission_order_and_paging(self):
        collection = Collection()
        ids = [collection.add(f"text {i}", "model", label=f"label {i}") for i in range(5)]
        first = collection.catalogue(limit=2)
        second = collection.catalogue(cursor=first["next_cursor"], limit=2)
        last = collection.catalogue(cursor=second["next_cursor"], limit=2)
        self.assertEqual([item["id"] for page in (first, second, last) for item in page["items"]], ids)
        self.assertTrue(last["complete"])
        self.assertIsNone(last["next_cursor"])
        self.assertNotIn("text", first["items"][0])

    def test_read_paging_uses_characters_not_utf8_bytes(self):
        collection = Collection()
        source = collection.add("α🙂a\r\n終", "source")
        page = collection.read(source, limit=2)
        self.assertEqual(page["text"], "α🙂")
        self.assertEqual(page["next_cursor"], 2)
        self.assertEqual(collection.read(source, start=2)["text"], "a\r\n終")
        self.assertTrue(collection.read(source, start=2)["complete"])

    def test_search_overlapping_duplicates_survive_every_byte_boundary(self):
        collection = Collection()
        source = collection.add("🙂ababa🙂aba", "source")
        cursor = None
        matches = []
        for _ in range(100):
            page = collection.search("aba", cursor=cursor, page_size=1, work_bytes=1)
            self.assertLessEqual(page["work_bytes"], 1)
            matches.extend((item["source_id"], item["offset"]) for item in page["items"])
            cursor = page["next_cursor"]
            if cursor is None:
                break
        self.assertEqual(matches, [(source, 1), (source, 3), (source, 7)])
        self.assertTrue(page["complete"])

    def test_unicode_phrase_can_span_partial_utf8_bytes(self):
        collection = Collection()
        source = collection.add("a🙂界b🙂界", "source")
        cursor = None
        offsets = []
        for _ in range(100):
            page = collection.search("🙂界", cursor=cursor, work_bytes=1)
            offsets.extend(item["offset"] for item in page["items"])
            cursor = page["next_cursor"]
            if cursor is None:
                break
        self.assertEqual(offsets, [1, 4])
        self.assertEqual(collection.read(source, start=offsets[1], limit=2)["text"], "🙂界")

    def test_search_scope_does_not_grow_with_generated_repetitions(self):
        collection = Collection()
        source = collection.add("no literal quotation here", "source")
        first = collection.search("quoted claim", work_bytes=3)
        collection.add("quoted claim", "model")
        cursor = first["next_cursor"]
        while cursor is not None:
            result = collection.search("quoted claim", cursor=cursor, work_bytes=3)
            cursor = result["next_cursor"]
        self.assertEqual(result["status"], "completed-no-match")
        self.assertEqual(collection.search("quoted claim", source_ids=[source])["items"], [])
        self.assertEqual(len(collection.search("quoted claim")["items"]), 1)

    def test_search_missing_or_incomplete_source_cannot_claim_absence(self):
        collection = Collection()
        source = collection.add("readable page", "source", extraction_complete=False)
        result = collection.search("missing", source_ids=[source, "unknown"])
        self.assertTrue(result["traversal_complete"])
        self.assertFalse(result["complete"])
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["unavailable_count"], 2)

    def test_empty_source_fanout_has_record_bound_even_without_bytes(self):
        collection = Collection()
        for _ in range(1030):
            collection.add("", "source")
        page = collection.search("x")
        self.assertEqual(page["inspected_sources"], 1024)
        self.assertIsNotNone(page["next_cursor"])
        end = collection.search("x", cursor=page["next_cursor"])
        self.assertEqual(end["status"], "completed-no-match")

    def test_search_continuation_is_bound_to_operands(self):
        collection = Collection()
        source = collection.add("0123456789", "source")
        cursor = collection.search("x", source_ids=[source], work_bytes=1)["next_cursor"]
        with self.assertRaises(ValueError):
            collection.search("y", cursor=cursor)
        with self.assertRaises(ValueError):
            collection.search("x", cursor=cursor, source_ids=["another"])

    def test_search_and_indexes_survive_json_round_trip(self):
        collection = Collection()
        source = collection.add("z" * 4100 + "needle", "source")
        cursor = collection.search("needle", work_bytes=4103)["next_cursor"]
        restored = Collection(json.loads(json.dumps(collection.data)))
        page = restored.search("needle", cursor=json.loads(json.dumps(cursor)), work_bytes=3)
        self.assertEqual(page["items"][0]["offset"], 4100)
        self.assertEqual(restored.read(source, start=4100)["text"], "needle")

    def test_links_keep_missing_endpoints_and_stable_stream_indexes(self):
        collection = Collection()
        source = collection.add("one", "source")
        target = collection.add("two", "source")
        collection.link(source, target, stream="response")
        collection.link(source, "missing", stream="other")
        collection.link(source, source, stream="response")
        self.assertEqual(collection.data["adjacency_stream_order"][source], ["response", "other"])
        self.assertEqual(collection.data["adjacency_streams"][source], {"response": [0, 2], "other": [1]})
        self.assertEqual(collection.data["adjacency"][source][1]["target"], "missing")

    def test_retention_failure_is_explicit_and_atomic(self):
        collection = Collection(max_source_bytes=4, max_collection_bytes=6)
        source = collection.add("one", "model")
        with self.assertRaises(ValueError):
            collection.add("larger", "source")
        with self.assertRaises(ValueError):
            collection.add("four", "source")
        self.assertEqual(collection.data["order"], [source])
        self.assertEqual(collection.data["total_bytes"], 3)

    def test_invalid_bounds_are_explicit(self):
        collection = Collection()
        source = collection.add("text", "source")
        for call in (lambda: collection.read(source, limit=0),
                     lambda: collection.catalogue(limit=1001),
                     lambda: collection.search(""),
                     lambda: collection.search("x", work_bytes=0)):
            with self.assertRaises(ValueError):
                call()

    def test_explicit_source_sets_and_links_have_input_caps(self):
        collection = Collection()
        seen = []

        def addresses():
            for i in range(100000):
                seen.append(i)
                yield f"missing{i}"

        with self.assertRaises(ValueError):
            collection.search("x", source_ids=addresses())
        self.assertEqual(len(seen), 1025)
        before = json.dumps(collection.data, sort_keys=True)
        with self.assertRaises(ValueError):
            collection.add("retained only if valid", "model", links=[None])
        self.assertEqual(json.dumps(collection.data, sort_keys=True), before)

    def test_timeout_returns_continuation_without_negative_claim(self):
        collection = Collection()
        collection.add("source text", "source")
        with patch("open_inquiry.collection.time.monotonic", side_effect=[0, 2, 2]):
            page = collection.search("absent", timeout_seconds=1)
        self.assertTrue(page["timed_out"])
        self.assertEqual(page["status"], "incomplete")
        self.assertEqual(page["work_bytes"], 0)
        self.assertIsNotNone(page["next_cursor"])
        self.assertEqual(collection.search("absent", cursor=page["next_cursor"])["status"], "completed-no-match")

    def test_pdf_adapter_discloses_unread_pages_and_extracted_representation(self):
        fake_parser = SimpleNamespace(__version__="fixture-1", PdfReader=lambda stream:
            SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: "readable page"),
                                   SimpleNamespace(extract_text=lambda: "")]))
        with patch.dict("sys.modules", {"pypdf": fake_parser}):
            text, details = Collection._extract_pdf(b"fixture bytes")
        self.assertEqual(text, "readable page\n\f\n")
        self.assertTrue(details["readable"])
        self.assertFalse(details["extraction_complete"])
        self.assertEqual(details["representation"], "pypdf-extracted-text-fixture-1")
        self.assertFalse(details["page_ranges"][1]["readable"])


if __name__ == "__main__":
    unittest.main()
