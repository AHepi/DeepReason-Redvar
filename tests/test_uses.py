"""Real Engine acceptance for scoped use, source actions, and dependencies."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from open_inquiry.engine import Engine
from open_inquiry.providers import ScriptedProvider


class UseTests(unittest.TestCase):
    def setUp(self):
        self.engine = Engine.create("Why do A and B disagree?")
        self.account_id = self.engine.accounts[0]["id"]
        self.source = self.engine.add_text("The calibration says: B was zeroed against A.", "calibration")
        self.use_id = self.engine.add_use(self.account_id, self.source, "B as an independent reference")

    def use(self, use_id=None, account_id=None):
        account = self.engine.account(account_id or self.account_id)
        return self.engine._use(account, use_id or self.use_id)

    def another_use(self, purpose="other application", account_id=None):
        return self.engine.add_use(account_id or self.account_id, self.source, purpose)

    def drain_dependencies(self):
        reports = []
        for _ in range(2000):
            reports.append(self.engine.process_dependencies())
            if not self.engine.state["dependency_queue"]:
                return reports
        self.fail("finite dependency case failed to terminate")

    def bind(self, **kwargs):
        return self.engine.bind(self.account_id, self.use_id, self.source,
                                "B was zeroed against A.", **kwargs)

    def test_prose_judgment_parks_only_named_use_without_a_check(self):
        second_account = self.engine.add_account("A separate question")
        second_use = self.another_use(account_id=second_account)
        result = self.engine.change_use(self.account_id, self.use_id, "park",
            "The reference shares the very calibration we are trying to explain.")
        self.assertTrue(result["changed"])
        self.assertEqual(self.use()["disposition"], "parked")
        self.assertEqual(self.use(second_use, second_account)["disposition"], "active")
        self.assertEqual(self.engine.checker.data["checks"], {})
        self.assertTrue(self.engine.collection.read(self.source)["complete"])
        self.engine.change_use(self.account_id, self.use_id, "reactivate", "We reconsidered what independent meant here.")
        self.assertEqual(self.use()["disposition"], "active")
        self.assertEqual(self.use()["revision"], 2)

    def test_parked_use_is_not_selected_in_next_actual_request(self):
        self.engine.change_use(self.account_id, self.use_id, "park", "Prose objection accepted for this use.")
        request = self.engine.prepare(ScriptedProvider(["continue inquiry"]))
        self.assertEqual(request["status"], "ready")
        grant = self.engine.state["grants"][request["grant"]]
        self.assertIsNone(grant["current_use"])
        self.assertNotIn("The selected working use is " + self.use_id,
                         " ".join(message["content"] for message in request["messages"]))
        self.assertEqual(self.use()["disposition"], "parked")

    def test_binding_match_parks_once_and_receipt_is_available(self):
        binding = self.bind()
        receipts = self.engine.process_checks()
        self.assertEqual(receipts[-1]["status"], "matched")
        self.assertEqual(self.use()["disposition"], "parked")
        self.assertIn(binding["id"], self.use()["reason"])
        self.assertTrue(self.engine.state["bindings"][binding["id"]]["consumed"])
        retained = [item for item in self.engine.collection.data["occurrences"].values()
                    if item.get("receipt_id") == receipts[-1]["id"]]
        self.assertEqual(len(retained), 1)
        self.assertEqual(retained[0]["origin"], "checker")
        revision = self.use()["revision"]
        with patch.object(self.engine.checker, "step", return_value=receipts):
            self.engine.process_checks()
        self.assertEqual(self.use()["revision"], revision)

    def test_gate_off_on_needs_explicit_matching_recheck(self):
        binding = self.bind()
        self.engine.set_commitments("off")
        old = self.engine.process_checks()[-1]
        self.assertEqual(old["status"], "matched")
        self.assertEqual(self.use()["disposition"], "active")
        self.engine.set_commitments("registered")
        self.assertEqual(self.engine.process_checks(), [])
        self.assertEqual(self.use()["disposition"], "active")
        self.assertFalse(self.engine.state["bindings"][binding["id"]]["enabled"])
        new_check = self.engine.check(self.source, "B was zeroed against A.")
        new = self.engine.process_checks()[-1]
        self.assertEqual(new["check_id"], new_check)
        self.assertNotEqual(new["id"], old["id"])
        self.assertTrue(new["cached"])
        self.assertEqual(self.use()["disposition"], "parked")

    def test_wrong_scope_version_or_source_does_not_rearm_gated_binding(self):
        binding = self.bind()
        self.engine.set_commitments("off")
        self.engine.process_checks()
        self.engine.set_commitments("registered")
        other_source = self.engine.add_text("B was zeroed against A.", "different document")
        for source, kwargs in ((other_source, {}), (self.source, {"version": "2"}),
                               (self.source, {"start": 1})):
            self.engine.check(source, "B was zeroed against A.", **kwargs)
            self.engine.process_checks()
            self.assertEqual(self.use()["disposition"], "active")
            self.assertFalse(self.engine.state["bindings"][binding["id"]]["enabled"])

    def test_stale_use_revision_invalidates_only_target_binding(self):
        another = self.another_use("same carrier in another argument")
        first = self.bind()
        second = self.engine.bind(self.account_id, another, self.source, "B was zeroed against A.")
        self.engine.change_use(self.account_id, self.use_id, "park", "Prose decision.")
        self.engine.change_use(self.account_id, self.use_id, "reactivate", "Revised application.")
        self.engine.process_checks()
        self.assertEqual(self.use()["disposition"], "active")
        self.assertEqual(self.use(another)["disposition"], "parked")
        self.assertTrue(self.engine.state["bindings"][first["id"]]["stale"])
        self.assertTrue(self.engine.state["bindings"][second["id"]]["consumed"])

    def test_generated_source_and_unavailable_addresses_do_not_install(self):
        generated = self.engine.collection.add("B was zeroed against A.", "model")
        before = len(self.engine.state["bindings"])
        for source in (generated, "missing"):
            with self.assertRaises(ValueError):
                self.engine.bind(self.account_id, self.use_id, source, "B was zeroed against A.")
        self.assertEqual(len(self.engine.state["bindings"]), before)
        self.assertEqual(self.engine.collection.read(generated)["text"], "B was zeroed against A.")

    def test_incomplete_or_failed_checks_never_park_the_use(self):
        self.engine.update_policy({"checker_slices_per_boundary": 1, "checker_slice_bytes": 1})
        self.bind()
        self.assertEqual(self.engine.process_checks()[0]["status"], "incomplete")
        self.assertEqual(self.use()["disposition"], "active")
        with patch.object(self.engine.collection, "_byte_slice", side_effect=RuntimeError("reader failure")):
            self.assertEqual(self.engine.process_checks()[0]["status"], "checker-error")
        self.assertEqual(self.use()["disposition"], "active")

    def test_binding_limit_is_operational_and_retired_slot_is_reusable(self):
        self.engine.update_policy({"conditional_bindings_per_account": 1})
        first = self.bind()
        with self.assertRaises(ValueError):
            self.bind()
        self.engine.process_checks()
        self.engine.change_use(self.account_id, self.use_id, "reactivate", "New operator decision.")
        second = self.bind()
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(len(self.engine.account(self.account_id)["binding_slots"]), 1)

    def test_forged_matching_receipt_with_changed_scope_does_not_fire(self):
        binding = self.bind()
        receipt = self.engine.checker.step(self.engine.collection)[-1]
        altered = deepcopy(receipt)
        altered["source_version"] = "another version"
        with patch.object(self.engine.checker, "step", return_value=[altered]):
            self.engine.process_checks()
        self.assertFalse(self.engine.state["bindings"][binding["id"]]["consumed"])
        self.assertEqual(self.use()["disposition"], "active")

    def test_cross_account_use_address_is_rejected(self):
        other_account = self.engine.add_account("Separate authority")
        with self.assertRaises(ValueError):
            self.engine.change_use(other_account, self.use_id, "park", "Outside this account")
        with self.assertRaises(ValueError):
            self.engine.bind(other_account, self.use_id, self.source, "calibration")

    def test_dependencies_defer_unprocessed_uses_and_finish_with_local_blocks(self):
        self.engine.update_policy({"dependency_slice": 1})
        dependent = self.another_use("depends on independent calibration")
        independent = self.another_use("a different application")
        self.engine.add_dependency(self.account_id, dependent, self.use_id)
        self.drain_dependencies()
        self.engine.change_use(self.account_id, self.use_id, "park", "Calibration independence withdrawn.")
        first = self.engine.process_dependencies()
        self.assertEqual(first["work"], 1)
        account = self.engine.account(self.account_id)
        self.assertTrue(account["dependencies_pending"])
        selected = self.engine._active_use(account)
        self.assertEqual(selected["id"], independent)
        self.assertEqual(selected["depends_on"], [])
        reports = self.drain_dependencies()
        self.assertTrue(all(report["work"] <= 1 for report in reports))
        self.assertTrue(self.use(dependent)["blocked"])
        self.assertFalse(self.use(independent)["blocked"])
        self.assertEqual(self.use(dependent)["disposition"], "active")
        self.assertFalse(account["dependencies_pending"])

    def test_cycle_terminates_and_root_reactivation_clears_its_effects(self):
        second = self.another_use("second")
        third = self.another_use("third")
        for dependent, essential in ((second, self.use_id), (third, second), (self.use_id, third)):
            self.engine.add_dependency(self.account_id, dependent, essential)
        self.drain_dependencies()
        self.engine.change_use(self.account_id, self.use_id, "park", "Root premise withdrawn.")
        self.drain_dependencies()
        self.assertTrue(self.use(second)["blocked"])
        self.assertTrue(self.use(third)["blocked"])
        self.engine.change_use(self.account_id, self.use_id, "reactivate", "Root premise reconsidered.")
        self.drain_dependencies()
        self.assertFalse(any(self.use(item)["blocked"] for item in (self.use_id, second, third)))

    def test_reactivating_one_root_preserves_other_root_block(self):
        other_root = self.another_use("second essential premise")
        dependent = self.another_use("requires both premises")
        self.engine.add_dependency(self.account_id, dependent, self.use_id)
        self.engine.add_dependency(self.account_id, dependent, other_root)
        self.drain_dependencies()
        for root in (self.use_id, other_root):
            self.engine.change_use(self.account_id, root, "park", "Premise withdrawn.")
        self.drain_dependencies()
        self.engine.change_use(self.account_id, self.use_id, "reactivate", "First premise restored.")
        self.drain_dependencies()
        self.assertTrue(self.use(dependent)["blocked"])
        self.assertEqual(set(self.use(dependent)["blocked_by"]), {other_root})

    def test_new_edge_inherits_block_from_already_blocked_use(self):
        middle = self.another_use("middle")
        dependent = self.another_use("new dependent")
        self.engine.add_dependency(self.account_id, middle, self.use_id)
        self.drain_dependencies()
        self.engine.change_use(self.account_id, self.use_id, "park", "Root withdrawn.")
        self.drain_dependencies()
        self.engine.add_dependency(self.account_id, dependent, middle)
        self.drain_dependencies()
        self.assertTrue(self.use(dependent)["blocked"])
        self.assertIn(self.use_id, self.use(dependent)["blocked_by"])

    def test_remove_dependency_reconciles_descendants_without_truth_claim(self):
        middle = self.another_use("middle")
        dependent = self.another_use("dependent")
        self.engine.add_dependency(self.account_id, middle, self.use_id)
        self.engine.add_dependency(self.account_id, dependent, middle)
        self.drain_dependencies()
        self.engine.change_use(self.account_id, self.use_id, "park", "Root withdrawn.")
        self.drain_dependencies()
        self.engine.remove_dependency(self.account_id, middle, self.use_id)
        self.assertTrue(self.engine.account(self.account_id)["dependencies_pending"])
        self.drain_dependencies()
        self.assertFalse(self.use(middle)["blocked"])
        self.assertFalse(self.use(dependent)["blocked"])
        self.assertEqual(self.use()["disposition"], "parked")

    def test_remove_one_path_preserves_block_through_another_path(self):
        left = self.another_use("left path")
        right = self.another_use("right path")
        dependent = self.another_use("common dependent")
        for child, parent in ((left, self.use_id), (right, self.use_id), (dependent, left), (dependent, right)):
            self.engine.add_dependency(self.account_id, child, parent)
        self.drain_dependencies()
        self.engine.change_use(self.account_id, self.use_id, "park", "Root withdrawn.")
        self.drain_dependencies()
        self.engine.remove_dependency(self.account_id, dependent, left)
        self.drain_dependencies()
        self.assertTrue(self.use(dependent)["blocked"])
        self.engine.remove_dependency(self.account_id, dependent, right)
        self.drain_dependencies()
        self.assertFalse(self.use(dependent)["blocked"])
        self.assertTrue(self.use(left)["blocked"])
        self.assertTrue(self.use(right)["blocked"])

    def test_remove_during_pending_cascade_remains_bounded_and_correct(self):
        self.engine.update_policy({"dependency_slice": 1})
        dependent = self.another_use("dependent")
        sibling = self.another_use("sibling")
        self.engine.add_dependency(self.account_id, dependent, self.use_id)
        self.engine.add_dependency(self.account_id, sibling, self.use_id)
        self.drain_dependencies()
        self.engine.change_use(self.account_id, self.use_id, "park", "Root withdrawn.")
        self.engine.process_dependencies()
        self.engine.process_dependencies()
        self.engine.remove_dependency(self.account_id, dependent, self.use_id)
        self.drain_dependencies()
        self.assertFalse(self.use(dependent)["blocked"])
        self.assertTrue(self.use(sibling)["blocked"])

    def test_pending_checker_and_dependency_state_survive_real_save_load(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine.create("Saved inquiry", directory=directory,
                                   policy={"checker_slices_per_boundary": 1, "checker_slice_bytes": 1,
                                           "dependency_slice": 1})
            self.engine = engine
            self.account_id = engine.accounts[0]["id"]
            self.source = engine.add_text("prefix needle suffix")
            self.use_id = engine.add_use(self.account_id, self.source, "current reference")
            dependent = self.another_use("dependent")
            engine.add_dependency(self.account_id, dependent, self.use_id)
            engine.bind(self.account_id, self.use_id, self.source, "needle")
            engine.process_checks()
            engine.process_dependencies()
            engine.save()
            self.engine = Engine.load(directory)
            for _ in range(100):
                self.engine.process_checks()
                if not self.engine.checker.data["queue"]:
                    break
            self.drain_dependencies()
            self.assertEqual(self.use()["disposition"], "parked")
            self.assertTrue(self.use(dependent)["blocked"])
            self.assertTrue(Path(directory, "state.json").exists())
            json.dumps(self.engine.state)


if __name__ == "__main__":
    unittest.main()
