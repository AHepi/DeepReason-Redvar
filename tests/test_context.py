"""Operational Part IV counterexamples; fixture counts are not provider counts."""

import json
import unittest

from open_inquiry.collection import Collection
from open_inquiry.config import validate
from open_inquiry.context import ContextLimitError, compile_cut


class CharacterCounter:
    """Synthetic deterministic tokenizer including chat serialization overhead."""

    count_kind = "fixture"

    def __call__(self, messages):
        return len(json.dumps(messages, ensure_ascii=False, separators=(",", ":")))


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.collection = Collection()
        self.focus = self.collection.add("Explain the observed difference.", "operator")
        self.method = self.collection.add("Reopen the relevant originals.", "operator")
        self.account = {"id": "account-1", "focus": self.focus, "method": self.method,
                        "uses": [], "context_cursors": {}}
        self.counter = CharacterCounter()

    def cut(self, *, policy=None, account=None, **kwargs):
        configuration = validate({"input_tokens": 16000, "neighbour_tokens": 8000,
                                  **(policy or {})})
        return compile_cut(self.collection, policy=configuration,
                           account=self.account if account is None else account,
                           invitation=kwargs.pop("invitation", "Continue the current inquiry."),
                           counter=self.counter, **kwargs)

    def body(self, cut):
        return "\n".join(message["content"] for message in cut.messages)

    def test_criticism_keeps_original_target_and_immediate_anchor(self):
        target = self.collection.add("Both sensors used independent references.", "model")
        criticism = self.collection.add("The log says they shared one reference.", "model")
        previous = self.collection.add("Keep the earlier question.", "model")
        cut = self.cut(required=(criticism, target), extra_anchors=(previous,),
                       policy={"participant_history": "off"},
                       invitation="Answer the criticism of reference independence.")
        self.assertEqual(cut.mode, "work")
        for occurrence in (criticism, target, previous):
            self.assertIn(occurrence, cut.included)
            self.assertIn(self.collection.data["occurrences"][occurrence]["text"], self.body(cut))
        self.assertEqual(cut.input_tokens, self.counter(cut.messages))

    def test_high_degree_inspections_and_items_are_independent(self):
        for index in range(500):
            occurrence = self.collection.add(f"Neighbour {index}", "source")
            self.collection.link(self.focus, occurrence)
        cut = self.cut(policy={"neighbour_depth": 1, "edge_inspections": 3, "neighbour_items": 20})
        self.assertEqual(cut.inspections, 3)
        self.assertEqual(len(cut.included), 5)
        smaller = self.cut(policy={"edge_inspections": 64, "neighbour_items": 2})
        self.assertEqual(len(smaller.included), 4)
        self.assertEqual(smaller.inspections, 2)
        self.assertLess(len(" ".join(smaller.omissions)), 250)

    def test_cycles_duplicates_and_missing_endpoints_spend_inspections(self):
        neighbour = self.collection.add("A neighbouring passage", "source")
        self.collection.link(self.focus, self.focus)
        self.collection.link(self.focus, "missing")
        self.collection.link(self.focus, neighbour)
        self.collection.link(self.focus, neighbour)
        self.collection.link(neighbour, self.focus)
        cut = self.cut(policy={"edge_inspections": 3, "neighbour_items": 6})
        self.assertEqual(cut.inspections, 3)
        self.assertIn(neighbour, cut.included)
        self.assertNotIn("missing", cut.included)
        cycle = self.cut(recipe="broader")
        self.assertLessEqual(cycle.inspections, 5)
        self.assertEqual(cycle.included.count(neighbour), 1)

    def test_radius_zero_ignores_recipe_local_default(self):
        nearby = self.collection.add("A nearby source", "source")
        self.collection.link(self.focus, nearby)
        cut = self.cut(policy={"neighbour_depth": 0})
        self.assertEqual(cut.inspections, 0)
        self.assertNotIn(nearby, cut.included)

    def test_broader_recipe_visits_two_links_without_extra_envelope(self):
        first = self.collection.add("first", "source")
        second = self.collection.add("second", "source")
        self.collection.link(self.focus, first)
        self.collection.link(first, second)
        self.assertNotIn(second, self.cut().included)
        broad = self.cut(recipe="broader", policy={"edge_inspections": 2})
        self.assertIn(second, broad.included)
        self.assertEqual(broad.inspections, 2)
        with self.assertRaises(ValueError):
            self.cut(recipe="invented unrestricted view")

    def test_registered_streams_interleave_without_sorting(self):
        first_stream = []
        for index in range(50):
            occurrence = self.collection.add(f"First stream {index}", "source")
            first_stream.append(occurrence)
            self.collection.link(self.focus, occurrence, stream="registered-a")
        other = self.collection.add("Second registered participant", "source")
        self.collection.link(self.focus, other, stream="registered-b")
        first = self.cut(policy={"neighbour_items": 2, "edge_inspections": 2})
        self.assertEqual(first.included[-2:], [first_stream[0], other])
        next_cut = self.cut(policy={"neighbour_items": 2, "edge_inspections": 2})
        self.assertEqual(next_cut.included[-2:], [first_stream[1], other])

    def test_rotating_edges_reach_appended_material(self):
        first = self.collection.add("old", "source")
        self.collection.link(self.focus, first)
        self.cut(policy={"neighbour_items": 1})
        new = self.collection.add("new", "source")
        self.collection.link(self.focus, new)
        encountered = set()
        for _ in range(3):
            encountered.update(self.cut(policy={"neighbour_items": 1}).included)
        self.assertIn(new, encountered)

    def test_long_required_target_is_reading_with_persistent_offsets(self):
        target = self.collection.add("ABCDEFGHIJKLMNOPQRSTUVWXYZ" * 1000, "source")
        cuts = [self.cut(required=(target,), policy={"read_page_chars": 600,
                                                   "max_read_pages": 2}) for _ in range(2)]
        first, second = cuts
        self.assertEqual(first.mode, "read")
        self.assertFalse(first.required_complete)
        self.assertIn("full-target response is postponed", self.body(first))
        self.assertEqual(first.inspections, 0)
        self.assertGreater(second.continuation["body_offset"], first.continuation["body_offset"])
        self.assertTrue(second.continuation["needs_scheduling_decision"])
        self.assertEqual(second.ranges[0]["start"], first.continuation["body_offset"])

    def test_oversized_address_packet_is_resolved_in_bounded_pages(self):
        targets = tuple(self.collection.add(f"target {index}", "source") for index in range(40))
        visited = set()
        for _ in range(5):
            cut = self.cut(required=targets, policy={"required_limit": 4})
            self.assertEqual(cut.mode, "read")
            self.assertLessEqual(cut.resolutions, 4)
            self.assertEqual(cut.inspections, 0)
            visited.update(cut.included)
        self.assertIn(targets[15], visited)
        self.assertNotIn(targets[39], visited)

    def test_complete_serialized_prompt_fits_small_cap(self):
        target = self.collection.add("An exact target qualification. " * 100, "source")
        cut = self.cut(required=(target,), policy={"input_tokens": 1500, "neighbour_tokens": 300})
        self.assertEqual(cut.mode, "read")
        self.assertLessEqual(self.counter(cut.messages), 1500)
        self.assertEqual(cut.input_tokens, self.counter(cut.messages))
        self.assertIn("READING ONLY", self.body(cut))
        self.assertFalse(cut.required_complete)

    def test_tiny_cap_has_explicit_fallback_or_fails_without_a_fake_answer(self):
        cut = self.cut(policy={"input_tokens": 220, "neighbour_tokens": 0})
        self.assertEqual(cut.mode, "read")
        self.assertIn("No source page fits", self.body(cut))
        self.assertLessEqual(cut.input_tokens, 220)
        with self.assertRaises(ContextLimitError):
            self.cut(policy={"input_tokens": 8, "neighbour_tokens": 0})

    def test_parked_use_reason_and_ineligibility_are_in_actual_prompt(self):
        target = self.collection.add("The reference is independent.", "model")
        self.account["uses"].append({"id": "use-1", "occurrence": target,
                                     "purpose": "reference premise", "disposition": "parked",
                                     "reason": "Installed binding B received receipt R."})
        self.collection.link(self.focus, target)
        cut = self.cut()
        body = self.body(cut)
        self.assertIn(target, cut.included)
        self.assertIn("parked; EXAMINATION ONLY", body)
        self.assertIn("ineligible for ordinary development", body)
        self.assertIn("Installed binding B received receipt R.", body)
        other_account = {**self.account, "uses": [], "context_cursors": {}}
        self.assertNotIn("parked;", self.body(self.cut(account=other_account)))

    def test_parked_notice_is_never_unmetered_or_silently_removed(self):
        self.account["uses"] = [{"id": "use-1", "occurrence": self.focus,
                                 "purpose": "working premise", "disposition": "parked",
                                 "reason": "A very long reason " * 10000}]
        cut = self.cut(policy={"input_tokens": 1300, "neighbour_tokens": 0})
        self.assertLessEqual(cut.input_tokens, 1300)
        self.assertEqual(cut.mode, "read")
        if self.focus in cut.included:
            self.assertIn("EXAMINATION ONLY", self.body(cut))

    def test_use_metadata_lookup_is_bounded_and_index_preserves_parked_reason(self):
        self.account["uses"] = [{"id": f"unrelated-{index}", "occurrence": "elsewhere"}
                                for index in range(10000)]
        self.account["uses"].append({"id": "last", "occurrence": self.focus,
                                     "disposition": "parked", "reason": "Receipt R parked use last."})
        fallback = self.cut()
        self.assertIn("Use lookup incomplete: EXAMINATION ONLY", self.body(fallback))
        self.account["use_index"] = {self.focus: [10000]}
        indexed = self.cut()
        self.assertIn("Receipt R parked use last.", self.body(indexed))
        self.assertIn("parked; EXAMINATION ONLY", self.body(indexed))

    def test_pending_dependency_propagation_defers_all_active_use_supply(self):
        self.account["uses"] = [{"id": "use-1", "occurrence": self.focus,
                                 "disposition": "active", "reason": "Current decision provenance."}]
        self.account["dependencies_pending"] = True
        self.account["dependency_notice"] = "A required input changed; dependent uses are still being inspected."
        pending = self.cut()
        self.assertIn("dependency-review-pending; EXAMINATION ONLY", self.body(pending))
        self.assertIn(self.account["dependency_notice"], self.body(pending))
        self.assertNotIn("Use use-1: active for", self.body(pending))
        self.account["dependencies_pending"] = False
        self.account["uses"][0].update(blocked=True, dependency_reason="Essential use input-2 is parked.")
        blocked = self.cut()
        self.assertIn("dependency-blocked; EXAMINATION ONLY", self.body(blocked))
        self.assertIn("Essential use input-2 is parked.", self.body(blocked))
        self.assertIn("Current decision provenance.", self.body(blocked))

    def test_explicitly_independent_use_remains_available_during_dependency_scan(self):
        self.account["uses"] = [{"id": "independent", "occurrence": self.focus,
                                 "disposition": "active", "depends_on": []}]
        self.account["dependencies_pending"] = True
        independent = self.cut()
        self.assertIn("Use independent: active for", self.body(independent))
        self.assertNotIn("dependency-review-pending", self.body(independent))
        del self.account["uses"][0]["depends_on"]
        unknown = self.cut()
        self.assertIn("dependency-review-pending; EXAMINATION ONLY", self.body(unknown))

    def test_optional_history_off_preserves_required_model_prose(self):
        older = self.collection.add("An optional older model draft.", "model")
        source = self.collection.add("An original source.", "source")
        self.collection.link(self.focus, older)
        self.collection.link(self.focus, source)
        cut = self.cut(policy={"participant_history": "off"})
        self.assertNotIn(older, cut.included)
        self.assertIn(source, cut.included)
        required = self.cut(required=(older,), policy={"participant_history": "off"})
        self.assertIn(older, required.included)

    def test_no_graph_path_needed_for_nonlocal_source_page(self):
        distant = self.collection.add("The omitted temperature qualification.", "source")
        cut = self.cut(nonlocal_read=self.collection.read(distant))
        self.assertIn(distant, cut.included)
        self.assertIn("omitted temperature qualification", self.body(cut))

    def test_large_optional_body_is_a_labelled_continuing_page(self):
        long_body = self.collection.add("A" * 20000, "source")
        self.collection.link(self.focus, long_body)
        first = self.cut(policy={"neighbour_tokens": 1000})
        second = self.cut(policy={"neighbour_tokens": 1000})
        self.assertEqual(first.mode, "work")
        self.assertLessEqual(first.optional_tokens, 1000)
        self.assertIn("EXCERPT; continuation at character", self.body(first))
        self.assertGreater(second.ranges[-1]["start"], first.ranges[-1]["start"])
        self.assertEqual(first.input_tokens, self.counter(first.messages))

    def test_a_long_optional_idea_is_not_skipped_for_shorter_material(self):
        long_body = self.collection.add("First in insertion order. " * 1000, "source")
        short_body = self.collection.add("Short and apparently useful.", "source")
        self.collection.link(self.focus, long_body)
        self.collection.link(self.focus, short_body)
        cut = self.cut(policy={"neighbour_tokens": 700, "neighbour_items": 2})
        self.assertIn(long_body, cut.included)
        self.assertNotIn(short_body, cut.included)
        self.assertLessEqual(cut.optional_tokens, 700)

    def test_missing_required_target_never_becomes_full_answer(self):
        cut = self.cut(required=("missing-target",))
        self.assertEqual(cut.mode, "read")
        self.assertFalse(cut.required_complete)
        self.assertIn("UNAVAILABLE", self.body(cut))
        self.assertNotIn("missing-target", cut.included)

    def test_root_list_is_bounded_and_rotates(self):
        roots, children = [], []
        for index in range(20):
            root = self.collection.add(f"root {index}", "source")
            child = self.collection.add(f"child {index}", "source")
            self.collection.link(root, child)
            roots.append(root)
            children.append(child)
        first = self.cut(roots=roots, policy={"roots_limit": 3, "neighbour_items": 10})
        self.assertEqual(len(first.included), 4)  # focus root has no edges; two supplied roots
        second = self.cut(roots=roots, policy={"roots_limit": 3, "neighbour_items": 10})
        self.assertNotEqual(first.included, second.included)
        self.assertLessEqual(second.inspections, 3)

    def test_cursors_survive_json_persistence(self):
        for text in ("one", "two", "three"):
            self.collection.link(self.focus, self.collection.add(text, "source"))
        self.cut(policy={"neighbour_items": 1})
        saved = json.loads(json.dumps(self.account))
        expected = self.cut(policy={"neighbour_items": 1})
        replay = self.cut(account=saved, policy={"neighbour_items": 1})
        self.assertEqual(expected.to_dict(), replay.to_dict())


if __name__ == "__main__":
    unittest.main()
