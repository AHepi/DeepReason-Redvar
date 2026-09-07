"""Counterexamples for Part VII: spending future returns and losing unknown work."""

import json
import unittest

from open_inquiry.resources import BudgetExceeded, Ledger, ResourceError


class LedgerTests(unittest.TestCase):
    def test_future_return_cannot_be_spent_by_ordinary_work(self):
        ledger = Ledger(max_calls=4, max_tokens=400)
        for key in ("trial-1", "trial-2", "return"):
            ledger.reserve(key, 100)
        ledger.reserve("ordinary", 100)
        with self.assertRaises(BudgetExceeded):
            ledger.reserve("extra", 1)
        ledger.dispatch("ordinary")
        ledger.settle("ordinary", {"input_tokens": 25, "output_tokens": 25})
        self.assertEqual(ledger.available(), {"tokens": 50, "calls": 0})
        for key in ("trial-1", "trial-2", "return"):
            ledger.dispatch(key)
            ledger.settle(key, {"input_tokens": 40, "output_tokens": 50})
        self.assertEqual(ledger.report()["used_calls"], 4)
        self.assertEqual(ledger.report()["charged_tokens"], 320)

    def test_bundle_checks_call_slots_even_if_tokens_fit(self):
        ledger = Ledger(max_calls=2, max_tokens=1000)
        with self.assertRaises(BudgetExceeded):
            ledger.reserve("trial-and-return", 300, calls=3)
        self.assertEqual(ledger.data["entries"], {})

    def test_call_and_token_reservation_idempotence(self):
        ledger = Ledger(max_calls=2, max_tokens=100)
        ledger.reserve("a", 50)
        ledger.reserve("a", 50)
        self.assertEqual(ledger.available(), {"tokens": 50, "calls": 1})
        with self.assertRaises(ResourceError):
            ledger.reserve("a", 51)
        ledger.dispatch("a")
        ledger.dispatch("a")
        first = ledger.settle("a", {"input_tokens": 10, "output_tokens": 20})
        duplicate = ledger.settle("a", {"input_tokens": 1000, "output_tokens": 2000})
        self.assertEqual(first, duplicate)
        self.assertEqual(ledger.report()["used_calls"], 1)
        self.assertEqual(ledger.report()["charged_tokens"], 30)

    def test_cancellation_distinguishes_before_and_after_dispatch(self):
        ledger = Ledger(max_calls=3, max_tokens=100)
        ledger.reserve("before", 30)
        ledger.cancel("before")
        self.assertEqual(ledger.available(), {"tokens": 100, "calls": 3})
        with self.assertRaises(ResourceError):
            ledger.dispatch("before")
        ledger.reserve("after", 50)
        ledger.dispatch("after")
        ledger.cancel("after")
        ledger.cancel("after")
        self.assertEqual(ledger.report()["charged_tokens"], 50)
        self.assertEqual(ledger.report()["unknown_calls"], 1)
        self.assertEqual(ledger.available(), {"tokens": 50, "calls": 2})

    def test_cache_is_not_added_and_disjoint_reasoning_is_added(self):
        ledger = Ledger()
        for key, included, expected in (("included", True, 150), ("disjoint", False, 180)):
            ledger.reserve(key, 200)
            ledger.dispatch(key)
            entry = ledger.settle(key, {"input_tokens": 100, "cached_input_tokens": 80,
                                      "output_tokens": 50, "reasoning_tokens": 30,
                                      "reasoning_included": included})
            self.assertEqual(entry["charged_tokens"], expected)
            self.assertFalse(entry["unknown"])

    def test_unknown_reasoning_inclusion_keeps_reservation(self):
        ledger = Ledger()
        ledger.reserve("a", 200)
        ledger.dispatch("a")
        entry = ledger.settle("a", {"input_tokens": 100, "output_tokens": 50,
                                   "reasoning_tokens": 30})
        self.assertTrue(entry["unknown"])
        self.assertEqual(entry["charged_tokens"], 200)
        self.assertEqual(ledger.settle("a", {"input_tokens": 100, "output_tokens": 50,
                                           "reasoning_tokens": 30}), entry)

    def test_missing_output_keeps_reservation_and_observation_unknown(self):
        ledger = Ledger()
        ledger.reserve("a", 200)
        ledger.dispatch("a")
        entry = ledger.settle("a", {"input_tokens": 100})
        self.assertEqual(entry["charged_tokens"], 200)
        self.assertIsNone(entry["observed_total"])
        self.assertIsNone(entry["usage"]["output_tokens"])

    def test_reported_aggregate_with_unverified_accounting_keeps_reservation(self):
        ledger = Ledger()
        ledger.reserve("a", 200)
        ledger.dispatch("a")
        entry = ledger.settle("a", {"input_tokens": 100, "output_tokens": 50,
                                   "reasoning_tokens": None, "reasoning_included": None,
                                   "accounting_complete": False})
        self.assertEqual(entry["usage"]["output_tokens"], 50)
        self.assertEqual(entry["charged_tokens"], 200)
        self.assertIsNone(entry["observed_total"])
        self.assertTrue(entry["unknown"])

    def test_known_partial_overrun_is_not_discarded(self):
        ledger = Ledger(max_tokens=200)
        ledger.reserve("a", 200)
        ledger.dispatch("a")
        entry = ledger.settle("a", {"input_tokens": 250})
        self.assertEqual(entry["charged_tokens"], 250)
        self.assertTrue(entry["unknown"])
        self.assertTrue(ledger.paused)

    def test_overrun_records_observation_and_pauses_already_reserved_call(self):
        ledger = Ledger(max_calls=3, max_tokens=200)
        ledger.reserve("a", 100)
        ledger.reserve("future-return", 100)
        ledger.dispatch("a")
        ledger.settle("a", {"input_tokens": 90, "output_tokens": 60})
        self.assertEqual(ledger.report()["charged_tokens"], 150)
        self.assertEqual(ledger.available()["tokens"], -50)
        self.assertTrue(ledger.paused)
        with self.assertRaises(BudgetExceeded):
            ledger.dispatch("future-return")
        with self.assertRaises(BudgetExceeded):
            ledger.reserve("other", 1)

    def test_invalid_usage_never_creates_credit(self):
        for usage in ({"input_tokens": -100, "output_tokens": 0},
                      {"input_tokens": True, "output_tokens": 0},
                      {"input_tokens": 10, "output_tokens": 10, "cached_input_tokens": 30}):
            with self.subTest(usage=usage):
                ledger = Ledger()
                ledger.reserve("a", 100)
                ledger.dispatch("a")
                self.assertEqual(ledger.settle("a", usage)["charged_tokens"], 100)

    def test_restarted_ledger_retains_inflight_charge_and_future_reservations(self):
        ledger = Ledger(max_calls=4, max_tokens=200)
        ledger.reserve("a", 100)
        ledger.reserve("return", 100)
        ledger.dispatch("a")
        restored = Ledger(json.loads(json.dumps(ledger.data)))
        self.assertEqual(restored.available(), ledger.available())
        restored.cancel("a")
        self.assertEqual(restored.report()["unknown_calls"], 1)
        self.assertEqual(restored.report()["reserved_calls"], 1)

    def test_report_does_not_mutate_owned_state(self):
        ledger = Ledger()
        ledger.reserve("a", 100)
        ledger.report()["entries"]["a"]["amount"] = 0
        self.assertEqual(ledger.data["entries"]["a"]["amount"], 100)

    def test_undispatched_settlement_rejected(self):
        ledger = Ledger()
        ledger.reserve("a", 100)
        with self.assertRaises(ResourceError):
            ledger.settle("a", None)

    def test_late_reliable_usage_refines_unknown_and_known_duplicate_is_idempotent(self):
        ledger = Ledger()
        ledger.reserve("a", 200)
        ledger.dispatch("a")
        ledger.settle("a", None)
        result = ledger.settle("a", {"input_tokens": 50, "output_tokens": 30})
        self.assertFalse(result["unknown"])
        self.assertEqual(result["charged_tokens"], 80)
        self.assertEqual(result["prior_unknown_charge"], 200)
        self.assertEqual(ledger.settle("a", {"input_tokens": 500, "output_tokens": 300}), result)

    def test_late_reported_overrun_after_timeout_is_recorded(self):
        ledger = Ledger()
        ledger.reserve("a", 200)
        ledger.dispatch("a")
        ledger.settle("a", None)
        result = ledger.settle("a", {"input_tokens": 250, "output_tokens": 50})
        self.assertTrue(ledger.paused)
        self.assertEqual(result["charged_tokens"], 300)

    def test_conflicting_late_observation_does_not_refund_known_consumption(self):
        ledger = Ledger()
        ledger.reserve("a", 200)
        ledger.dispatch("a")
        ledger.settle("a", {"input_tokens": 250})
        result = ledger.settle("a", {"input_tokens": 10, "output_tokens": 20})
        self.assertTrue(result["unknown"])
        self.assertEqual(result["charged_tokens"], 250)
        self.assertTrue(result["usage"]["accounting_conflict"])


if __name__ == "__main__":
    unittest.main()
