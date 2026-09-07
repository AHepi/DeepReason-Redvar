"""Scoped checker observations, resumable work, and correction acceptance."""

import json
import unittest
from unittest.mock import patch

from open_inquiry.checking import Checker
from open_inquiry.collection import Collection


class CheckerTests(unittest.TestCase):
    def setUp(self):
        self.collection = Collection()
        self.checker = Checker()

    def finish(self, checker=None, *, slices=4, slice_bytes=65536):
        checker = checker or self.checker
        receipts = []
        for _ in range(1000):
            receipts.extend(checker.step(self.collection, slices=slices, slice_bytes=slice_bytes))
            if not checker.data["queue"]:
                return receipts
        self.fail("checker did not finish its finite test source")

    def test_exact_match_inside_denial_is_not_endorsement(self):
        source = self.collection.add('It is false that "B was zeroed against A."', "source")
        self.checker.add(self.collection, source, "B was zeroed against A.")
        receipt = self.finish()[-1]
        self.assertEqual(receipt["status"], "matched")
        self.assertEqual(receipt["match_offsets"], [18])
        self.assertFalse(receipt["scan_complete"])
        self.assertIn("no claim about endorsement", receipt["meaning"])
        self.assertNotIn("true", receipt)

    def test_invented_quote_or_paraphrase_produces_scoped_negative_only(self):
        source = self.collection.add("B was calibrated using A.", "source")
        check = self.checker.add(self.collection, source, "B was zeroed against A.")
        receipt = self.finish()[-1]
        self.assertEqual(receipt["status"], "completed-no-match")
        self.assertTrue(receipt["scan_complete"])
        self.assertEqual(receipt["check_id"], check)
        self.assertEqual(receipt["source_version"], self.collection.get(source)["version"])
        self.assertEqual((receipt["start"], receipt["end"]), (0, 25))

    def test_excerpt_absence_does_not_describe_whole_source(self):
        source = self.collection.add("first part; needle later", "source")
        self.checker.add(self.collection, source, "needle", start=0, end=10)
        receipt = self.finish()[-1]
        self.assertEqual(receipt["status"], "completed-no-match")
        self.assertEqual(receipt["end"], 10)
        self.checker.add(self.collection, source, "needle")
        self.assertEqual(self.finish()[-1]["status"], "matched")

    def test_range_excludes_phrase_crossing_its_boundary(self):
        source = self.collection.add("abneedlecd", "source")
        self.checker.add(self.collection, source, "needle", start=3)
        self.assertEqual(self.finish()[-1]["status"], "completed-no-match")
        self.checker.add(self.collection, source, "needle", end=7)
        self.assertEqual(self.finish()[-1]["status"], "completed-no-match")

    def test_phrase_spanning_byte_slices_and_json_reload_is_found(self):
        source = self.collection.add("α🙂needle終", "source")
        check = self.checker.add(self.collection, source, "🙂needle")
        first = self.checker.step(self.collection, slices=1, slice_bytes=3)[0]
        self.assertEqual(first["status"], "incomplete")
        self.assertLessEqual(first["inspected_bytes"], 3)
        restored = Checker(json.loads(json.dumps(self.checker.data)))
        receipts = self.finish(restored, slices=1, slice_bytes=1)
        self.assertEqual(receipts[-1]["check_id"], check)
        self.assertEqual(receipts[-1]["match_offsets"], [1])
        self.assertEqual(receipts[-1]["status"], "matched")
        self.assertTrue(all(receipt["inspected_bytes"] <= 1 for receipt in receipts))

    def test_no_match_requires_entire_range_and_budget_exhaustion_is_partial(self):
        source = self.collection.add("a" * 50, "source")
        self.checker.add(self.collection, source, "b")
        partial = self.checker.step(self.collection, slices=2, slice_bytes=7)
        self.assertEqual([receipt["status"] for receipt in partial], ["incomplete", "incomplete"])
        self.assertFalse(any(receipt["predicate_resolved"] for receipt in partial))
        final = self.finish(slice_bytes=7)[-1]
        self.assertEqual(final["status"], "completed-no-match")
        self.assertEqual(final["total_inspected_bytes"], 50)

    def test_match_resolves_existence_before_complete_coverage(self):
        source = self.collection.add("needle" + "x" * 10000, "source")
        self.checker.add(self.collection, source, "needle")
        receipt = self.checker.step(self.collection, slices=1, slice_bytes=20)[0]
        self.assertEqual(receipt["status"], "matched")
        self.assertTrue(receipt["predicate_resolved"])
        self.assertFalse(receipt["scan_complete"])
        self.assertEqual(receipt["match_offsets"], [0])
        self.assertEqual(self.checker.data["queue"], [])

    def test_generated_repetition_cannot_satisfy_source_condition(self):
        source = self.collection.add("This source contains no calibration sentence.", "source")
        self.collection.add("B was zeroed against A.", "model")
        self.checker.add(self.collection, source, "B was zeroed against A.")
        self.assertEqual(self.finish()[-1]["status"], "completed-no-match")

    def test_unreadable_missing_incomplete_and_checker_failure_are_distinct(self):
        unreadable = self.collection.add("", "source", readable=False)
        incomplete = self.collection.add("partial page", "source", extraction_complete=False)
        for source in (unreadable, "missing"):
            self.checker.add(self.collection, source, "x")
            self.assertEqual(self.finish()[-1]["status"], "unavailable")
        self.checker.add(self.collection, incomplete, "x")
        result = self.finish()[-1]
        self.assertEqual(result["status"], "incomplete")
        self.assertFalse(result["predicate_resolved"])
        self.checker.add(self.collection, incomplete, "partial")
        self.assertEqual(self.finish()[-1]["status"], "matched")
        valid = self.collection.add("valid text", "source")
        self.checker.add(self.collection, valid, "needle")
        with patch.object(self.collection, "_byte_slice", side_effect=RuntimeError("private path")):
            failure = self.finish()[-1]
        self.assertEqual(failure["status"], "checker-error")
        self.assertNotIn("private path", str(failure))

    def test_source_version_change_does_not_reuse_old_scope(self):
        source = self.collection.add("needle", "source")
        self.checker.add(self.collection, source, "needle")
        self.collection.data["occurrences"][source]["version"] = "changed-outside-supported-api"
        result = self.finish()[-1]
        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(result["predicate_resolved"])

    def test_literal_comparison_does_not_silently_normalize(self):
        source = self.collection.add("Māori x\ny", "source")
        self.checker.add(self.collection, source, "Ma\u0304ori")
        self.assertEqual(self.finish()[-1]["status"], "completed-no-match")
        self.checker.add(self.collection, source, "x y", comparison="whitespace-normalized")
        self.assertEqual(self.finish()[-1]["status"], "checker-error")

    def test_explicit_recheck_has_new_identity_and_disclosed_cache(self):
        source = self.collection.add("needle", "source")
        first_job = self.checker.add(self.collection, source, "needle")
        first = self.finish()[-1]
        second_job = self.checker.add(self.collection, source, "needle")
        with patch.object(self.collection, "_byte_slice", side_effect=AssertionError("must use cache")):
            second = self.finish()[-1]
        self.assertNotEqual(first_job, second_job)
        self.assertNotEqual(first["id"], second["id"])
        self.assertTrue(second["cached"])
        self.assertEqual(second["cache_receipt_id"], first["id"])
        self.assertEqual(second["status"], "matched")
        self.assertEqual(second["inspected_bytes"], 0)
        self.assertEqual(self.checker.data["receipts"][first["id"]], first)

    def test_changed_checker_version_and_operands_do_not_share_cache(self):
        source = self.collection.add("needle", "source")
        self.checker.add(self.collection, source, "needle", version="1")
        earlier = self.finish()[-1]
        self.checker.add(self.collection, source, "needle", version="2")
        later = self.finish()[-1]
        self.assertFalse(later["cached"])
        self.assertEqual(later["checker_version"], "2")
        self.assertEqual(self.checker.data["receipts"][earlier["id"]]["checker_version"], "1")
        self.checker.add(self.collection, source, "absent", version="2")
        self.assertEqual(self.finish()[-1]["status"], "completed-no-match")

    def test_queue_round_robin_preserves_order_with_saved_progress(self):
        source = self.collection.add("aaaa", "source")
        first = self.checker.add(self.collection, source, "b")
        second = self.checker.add(self.collection, source, "c")
        results = self.checker.step(self.collection, slices=3, slice_bytes=1)
        self.assertEqual([item["check_id"] for item in results], [first, second, first])
        self.assertEqual([item["total_inspected_bytes"] for item in results], [1, 1, 2])

    def test_queue_capacity_and_zero_slices_do_not_create_extra_work(self):
        checker = Checker(max_pending=1)
        source = self.collection.add("text", "source")
        checker.add(self.collection, source, "a")
        with self.assertRaises(ValueError):
            checker.add(self.collection, source, "b")
        self.assertEqual(checker.step(self.collection, slices=0), [])
        self.assertEqual(len(checker.data["queue"]), 1)

    def test_invalid_ranges_and_empty_phrase_yield_checker_error(self):
        source = self.collection.add("text", "source")
        for phrase, start, end in (("", 0, None), ("x", -1, None),
                                   ("x", 0, 20), ("x", 3, 2)):
            self.checker.add(self.collection, source, phrase, start=start, end=end)
            self.assertEqual(self.finish()[-1]["status"], "checker-error")

    def test_unicode_scoped_range_uses_character_offsets(self):
        source = self.collection.add("🙂αneedleβ", "source")
        self.checker.add(self.collection, source, "needle", start=2, end=8)
        receipt = self.finish(slice_bytes=2)[-1]
        self.assertEqual(receipt["match_offsets"], [2])
        self.assertTrue(receipt["scan_complete"])
        self.assertEqual((receipt["start"], receipt["end"]), (2, 8))

    def test_partial_utf8_character_is_not_reported_as_fully_scanned(self):
        source = self.collection.add("🙂needle", "source")
        self.checker.add(self.collection, source, "needle")
        first = self.checker.step(self.collection, slices=1, slice_bytes=1)[0]
        self.assertEqual(first["byte_cursor"], 1)
        self.assertEqual(first["scanned_end"], 0)
        self.assertEqual(first["status"], "incomplete")
        final = self.finish(slice_bytes=1)[-1]
        self.assertEqual(final["scanned_end"], 7)
        self.assertEqual(final["match_offsets"], [1])

    def test_local_timeout_saves_pending_job_for_later_bounded_work(self):
        source = self.collection.add("source", "source")
        self.checker.add(self.collection, source, "absent")
        with patch("open_inquiry.collection.time.monotonic", side_effect=[0, 2]):
            partial = self.checker.step(self.collection, slices=1)[0]
        self.assertEqual(partial["status"], "incomplete")
        self.assertEqual(partial["inspected_bytes"], 0)
        self.assertTrue(self.checker.data["queue"])
        self.assertEqual(self.finish()[-1]["status"], "completed-no-match")


if __name__ == "__main__":
    unittest.main()
