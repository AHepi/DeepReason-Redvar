"""Actual controller/resource/persistence boundaries, with no live providers.

These tests distinguish promised future opportunities, attempted network work,
stale textual contributions, and measured or unknown resource consumption.
"""

import json
from pathlib import Path
import tempfile
import unittest

from open_inquiry.engine import Engine
from open_inquiry.providers import ProviderResult, ScriptedProvider


class EstimatedFixture(ScriptedProvider):
    count_kind = "estimated"


def fixture_usage(input_tokens=20, output_tokens=30, **changes):
    return {"input_tokens": input_tokens, "output_tokens": output_tokens,
            "cached_input_tokens": 0, "reasoning_tokens": 0,
            "reasoning_included": True, **changes}


class EngineResourceTests(unittest.TestCase):
    def create(self, **policy):
        return Engine.create("What assumptions connect this claim to the observation?",
                             policy={"history": "off", **policy})

    def test_strict_fixture_is_explicitly_synthetic_and_actual_units_settle(self):
        engine = self.create()
        provider = ScriptedProvider(["A freely worded contribution."])
        events = []
        engine.recorder.observers.append(events.append)
        outcome = engine.step(provider)
        self.assertEqual(outcome["status"], "received")
        preparation = next(event for event in events if event["kind"] == "dispatch-prepared")
        self.assertEqual(preparation["count_kind"], "fixture")
        report = engine.ledger.report()
        actual = provider.count(provider.calls[0]["messages"]) + len(outcome["response"].encode())
        self.assertEqual(report["charged_tokens"], actual)
        self.assertEqual(report["reserved_tokens"], 0)
        self.assertEqual(report["unknown_calls"], 0)

    def test_strict_estimated_route_fails_before_any_provider_call_or_reservation(self):
        engine = self.create()
        provider = EstimatedFixture(["No dispatch should occur."])
        before = json.loads(json.dumps(engine.state))
        with self.assertRaisesRegex(ValueError, "allow estimates"):
            engine.step(provider)
        self.assertEqual(provider.calls, [])
        self.assertEqual(engine.state, before)
        engine.update_policy({"strict_tokens": False})
        self.assertEqual(engine.step(provider)["status"], "received")

    def test_full_trial_and_return_are_reserved_before_first_trial_dispatch(self):
        engine = self.create(work_before_review=1, run_model_calls=5)
        provider = ScriptedProvider(["Opening contribution.", "Try this question.",
                                     "First trial.", "Second trial.", "Qualified return."])
        engine.run(provider, steps=2)
        trial = engine.accounts[0]["trial"]
        self.assertIsNotNone(trial)
        report = engine.ledger.report()
        self.assertEqual(report["used_calls"], 2)
        self.assertEqual(report["reserved_calls"], 3)
        self.assertEqual(report["reserved_tokens"], 3 * (8192 + 1024))
        self.assertEqual(report["remaining_calls"], 0)
        self.assertTrue(all(report["entries"][key]["status"] == "reserved" for key in trial["reservations"]))
        outcomes = engine.run(provider, steps=4)
        self.assertEqual([outcome.get("invitation") for outcome in outcomes[:3]], ["trial", "trial", "return"])
        self.assertEqual(outcomes[-1]["status"], "limit")
        self.assertEqual(engine.ledger.report()["used_calls"], 5)
        self.assertEqual(engine.ledger.report()["reserved_calls"], 0)

    def test_insufficient_future_calls_keeps_proposal_without_partial_trial(self):
        engine = self.create(work_before_review=1, run_model_calls=4)
        provider = ScriptedProvider(["Initial contribution.", "An unfunded proposal."])
        results = engine.run(provider, steps=2)
        self.assertIsNone(engine.accounts[0]["trial"])
        self.assertEqual(engine.collection.get(results[-1]["occurrence"])["text"], "An unfunded proposal.")
        self.assertEqual(engine.ledger.report()["reserved_calls"], 0)
        self.assertEqual(engine.ledger.report()["used_calls"], 2)

    def test_insufficient_future_volume_keeps_proposal_without_partial_trial(self):
        engine = self.create(work_before_review=1, run_token_volume=20000)
        provider = ScriptedProvider(["Initial contribution.", "An unfunded proposal."])
        engine.run(provider, steps=2)
        self.assertIsNone(engine.accounts[0]["trial"])
        self.assertEqual(engine.ledger.report()["reserved_tokens"], 0)
        self.assertEqual(engine.ledger.report()["reserved_calls"], 0)

    def test_timeout_consumes_one_call_keeps_unknown_charge_and_does_not_retry(self):
        engine = self.create()
        provider = ScriptedProvider([TimeoutError("sensitive provider detail"), "Must not retry."])
        result = engine.run(provider, steps=8)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["status"], "provider-error")
        self.assertEqual(len(provider.calls), 1)
        report = engine.ledger.report()
        entry = next(iter(report["entries"].values()))
        self.assertEqual(report["unknown_calls"], 1)
        self.assertEqual(report["used_calls"], 1)
        self.assertEqual(entry["charged_tokens"], entry["amount"])
        self.assertIsNone(engine.state["inflight"])
        self.assertNotIn("sensitive provider detail", json.dumps(engine.state))

    def test_unknown_reasoning_keeps_counter_observations_and_reservation(self):
        engine = self.create()
        result = ProviderResult("Some visible prose.", fixture_usage(
            input_tokens=100, output_tokens=50, reasoning_tokens=None,
            reasoning_included=None, accounting_complete=False))
        engine.step(ScriptedProvider([result]))
        entry = next(iter(engine.ledger.report()["entries"].values()))
        self.assertEqual(entry["usage"]["input_tokens"], 100)
        self.assertEqual(entry["usage"]["output_tokens"], 50)
        self.assertEqual(entry["charged_tokens"], entry["amount"])
        self.assertTrue(entry["unknown"])

    def test_cancelling_trial_releases_only_undispatched_future_opportunities(self):
        engine = self.create(work_before_review=1, attention_learning="on", attention_review_every=1)
        provider = ScriptedProvider(["Initial contribution.", "Trial proposal.", "Late trial result."])
        engine.run(provider, steps=2)
        trial = engine.accounts[0]["trial"]
        keys = list(trial["reservations"])
        prepared = engine.prepare(provider)
        old_focus = trial["old_focus"]
        engine.update_policy({"attention_learning": "off"})
        entries = engine.ledger.data["entries"]
        self.assertEqual(entries[keys[0]]["status"], "dispatched")
        self.assertTrue(all(entries[key]["status"] == "cancelled" for key in keys[1:]))
        result = provider.generate(prepared["messages"], max_tokens=1024, timeout=1)
        outcome = engine.receive(prepared["grant"], result, counter=provider.count)
        self.assertEqual(outcome["status"], "retained-stale")
        self.assertEqual(engine.accounts[0]["focus"], old_focus)
        self.assertEqual(entries[keys[0]]["status"], "settled")
        self.assertEqual(engine.ledger.report()["reserved_calls"], 0)

    def test_inflight_snapshot_recovers_unknown_and_never_redispatches_old_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine.create("A question.", directory=directory)
            provider = ScriptedProvider(["A new contribution after recovery."])
            prepared = engine.prepare(provider)
            self.assertEqual(provider.calls, [])
            saved = json.loads((Path(directory) / "state.json").read_text())
            self.assertEqual(saved["inflight"], prepared["grant"])
            restored = Engine.load(directory)
            self.assertIsNone(restored.state["inflight"])
            self.assertEqual(restored.ledger.report()["unknown_calls"], 1)
            self.assertTrue(restored.state["grants"][prepared["grant"]]["cancelled"])
            self.assertEqual(restored.step(provider)["status"], "received")
            self.assertEqual(restored.ledger.report()["used_calls"], 2)
            self.assertEqual(len(provider.calls), 1)

    def test_readonly_load_observes_live_inflight_without_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine.create("A question.", directory=directory)
            prepared = engine.prepare(ScriptedProvider([]))
            observer = Engine.load(directory, recover=False)
            self.assertEqual(observer.state["inflight"], prepared["grant"])
            self.assertEqual(observer.ledger.report()["unknown_calls"], 0)
            self.assertEqual(observer.state, engine.state)

    def test_operator_cannot_shrink_envelope_below_uncertain_inflight_work(self):
        engine = self.create()
        prepared = engine.prepare(ScriptedProvider([]))
        reservation = engine.state["grants"][prepared["grant"]]["reservation"]
        amount = engine.ledger.data["entries"][reservation]["amount"]
        before = json.loads(json.dumps(engine.state))
        with self.assertRaisesRegex(ValueError, "spent resources"):
            engine.update_policy({"run_token_volume": amount - 1})
        self.assertEqual(engine.state, before)

    def test_malformed_stale_result_cannot_erase_a_newer_inflight_dispatch(self):
        engine = self.create()
        old = engine.step(ScriptedProvider(["First completed contribution."]))
        newer = engine.prepare(ScriptedProvider([]))
        before = json.loads(json.dumps(engine.accounts[0]))
        with self.assertRaisesRegex(ValueError, "raw text"):
            engine.receive(old["opportunity"], "not a ProviderResult")
        self.assertEqual(engine.state["inflight"], newer["grant"])
        self.assertEqual(engine.accounts[0], before)

    def test_late_usage_after_timeout_records_overrun_without_reactivating_grant(self):
        engine = self.create()
        provider = ScriptedProvider([])
        prepared = engine.prepare(provider)
        focus = engine.accounts[0]["focus"]
        engine.fail(prepared["grant"])
        outcome = engine.receive(prepared["grant"], ProviderResult(
            "A late response.", fixture_usage(input_tokens=10000, output_tokens=3000)), counter=provider.count)
        self.assertEqual(outcome["status"], "retained-stale")
        self.assertEqual(engine.accounts[0]["focus"], focus)
        self.assertEqual(engine.ledger.report()["charged_tokens"], 13000)
        self.assertTrue(engine.ledger.paused)

    def test_nomination_overrun_is_retained_without_attempting_unfundable_trial(self):
        engine = self.create(work_before_review=1)
        provider = ScriptedProvider(["Initial contribution.", ProviderResult(
            "Overrun proposal still deserves to remain readable.", fixture_usage(input_tokens=10000, output_tokens=3000))])
        engine.step(provider)
        result = engine.step(provider)
        self.assertEqual(result["status"], "received")
        self.assertIsNone(engine.accounts[0]["trial"])
        self.assertTrue(engine.ledger.paused)
        self.assertTrue(engine.state["grants"][result["opportunity"]]["consumed"])
        self.assertEqual(engine.step(provider)["status"], "paused")

    def test_generation_overrun_cannot_hide_inside_unused_input_allowance(self):
        engine = self.create()
        provider = ScriptedProvider([ProviderResult("Short visible answer.", fixture_usage(
            input_tokens=1, output_tokens=1025))])
        result = engine.step(provider)
        self.assertEqual(result["status"], "received")
        entry = next(iter(engine.ledger.data["entries"].values()))
        self.assertLess(entry["charged_tokens"], entry["amount"])
        self.assertTrue(engine.ledger.paused)
        self.assertEqual(engine.step(provider)["status"], "paused")


if __name__ == "__main__":
    unittest.main()
