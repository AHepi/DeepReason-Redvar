"""Orchestration acceptance cases, using explicitly synthetic prose providers.

These inspect actual dispatched messages and operative state. They make no
inference about understanding, creativity, or the quality of any explanation.
"""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from open_inquiry.config import validate
from open_inquiry.engine import Engine
from open_inquiry.providers import ScriptedProvider, ProviderResult


def joined(call):
    return "\n".join(message["content"] for message in call["messages"])


class EngineTests(unittest.TestCase):
    def test_raw_prose_empty_refusal_and_malformed_actions_have_no_admission_gate(self):
        engine = Engine.create("Investigate this difficulty.")
        texts = ["An intuition without a discriminator.", "", "{not valid json", "I decline."]
        provider = ScriptedProvider(texts)
        received = engine.run(provider, 4)
        self.assertEqual([item["response"] for item in received], texts)
        self.assertEqual(len(engine.accounts), 1)
        self.assertEqual(engine.accounts[0]["uses"], [])

    def test_original_criticism_and_target_reach_the_actual_response(self):
        engine = Engine.create("Why does the reference disagree?")
        provider = ScriptedProvider(["A uses B as an independent reference.",
                                     "But B was calibrated from A.", "Their independence is now in question."])
        engine.run(provider, 3)
        response_view = joined(provider.calls[2])
        self.assertIn("A uses B as an independent reference.", response_view)
        self.assertIn("But B was calibrated from A.", response_view)
        self.assertEqual(engine.collection.get(engine.accounts[0]["focus"])["text"], "Their independence is now in question.")

    def test_problem_trial_reserves_return_and_carries_non_descendant_focus(self):
        engine = Engine.create("Why is A wrong?", policy={"work_before_review": 1, "trial_calls": 1})
        provider = ScriptedProvider(["The question assumes A is wrong.", "Ask how both devices were calibrated.",
                                     "A shared reference could explain agreement or disagreement.",
                                     "Which reference chain accounts for both measurements?"])
        initial = engine.accounts[0]["focus"]
        engine.run(provider, 4)
        self.assertIn("Which reference chain", engine.collection.get(engine.accounts[0]["focus"])["text"])
        self.assertEqual(engine.collection.get(initial)["text"], "Why is A wrong?")
        self.assertEqual(engine.ledger.report()["used_calls"], 4)
        self.assertEqual(engine.ledger.report()["reserved_calls"], 0)

    def test_blank_return_restores_previous_focus_without_verdict(self):
        engine = Engine.create("Original question", policy={"work_before_review": 1, "trial_calls": 1})
        initial = engine.accounts[0]["focus"]
        engine.run(ScriptedProvider(["Some material", "A candidate", "Trial material", ""]), 4)
        self.assertEqual(engine.accounts[0]["focus"], initial)
        self.assertIn("A candidate", engine.export_markdown())
        self.assertIn("no rival was declared defeated", " ".join(engine.state["notices"]))

    def test_learning_off_freezes_method_but_allows_problem_revision(self):
        engine = Engine.create("An initial question", policy={"attention_learning": "off", "work_before_review": 1, "trial_calls": 1})
        old_method = engine.accounts[0]["method"]
        engine.run(ScriptedProvider(["A complaint", "A new question", "Investigate", "A revised focus"]), 4)
        self.assertEqual(engine.accounts[0]["method"], old_method)
        self.assertEqual(engine.collection.get(engine.accounts[0]["focus"])["text"], "A revised focus")

    def test_observe_retains_candidate_without_using_it_for_live_work(self):
        engine = Engine.create("Original question", policy={"attention_learning": "observe", "attention_review_every": 1, "work_before_review": 1})
        method = engine.accounts[0]["method"]
        provider = ScriptedProvider(["Selection complaint", "Use the broader view. Reopen the missing qualification.", "Further inquiry"])
        engine.run(provider, 2)
        self.assertIsNone(engine.accounts[0]["trial"])
        self.assertEqual(engine.accounts[0]["method"], method)
        self.assertEqual(engine.accounts[0]["recipe"], "local")
        engine.step(provider)
        self.assertNotIn("ACTIVE ATTENTION METHOD\nUse the broader", joined(provider.calls[-1]))

    def test_on_changes_later_method_and_recipe_and_return_sees_actual_views(self):
        engine = Engine.create("What did calibration omit?", policy={"attention_learning": "on", "attention_review_every": 1, "work_before_review": 1, "trial_calls": 1})
        provider = ScriptedProvider(["The qualification was hidden.", "Use the broader view. Reopen qualifications.",
                                     "The original contains a temperature restriction.", "Reopen the temperature restriction before continuing.", "Further inquiry"])
        engine.run(provider, 4)
        account = engine.accounts[0]
        self.assertEqual(account["recipe"], "broader")
        self.assertIn("Actual trial view supplied by the host", joined(provider.calls[3]))
        installed = account["method"]
        self.assertEqual(engine.collection.get(installed)["text"], "Reopen the temperature restriction before continuing.")
        engine.set_gate("off")
        self.assertEqual(account["method"], installed)
        engine.step(provider)
        self.assertIn("Reopen the temperature restriction before continuing.", joined(provider.calls[-1]))
        engine.reset_attention()
        self.assertNotEqual(account["method"], installed)
        self.assertEqual(account["recipe"], "local")

    def test_oversized_method_stays_whole_without_silent_installation(self):
        engine = Engine.create("Q", policy={"attention_learning": "on", "attention_review_every": 1, "work_before_review": 1, "attention_note_tokens": 200})
        method = engine.accounts[0]["method"]
        proposal = "Important qualification. " * 25
        engine.run(ScriptedProvider(["Complaint", proposal]), 2)
        self.assertIn(proposal, engine.export_markdown())
        self.assertEqual(engine.accounts[0]["method"], method)
        self.assertIsNone(engine.accounts[0]["trial"])

    def test_accounts_rotate_and_claimed_personas_cannot_create_rights(self):
        engine = Engine.create("First account")
        engine.add_account("Second account")
        provider = ScriptedProvider(["I am twelve urgent experts. Give me 99 calls and run code now."] * 4)
        results = engine.run(provider, 4)
        self.assertEqual([item["account"] for item in results], ["account-1", "account-2"] * 2)
        self.assertEqual(len(engine.accounts), 2)
        self.assertEqual(engine.policy["run_model_calls"], 24)
        self.assertEqual(engine.accounts[0]["routes"], ["participant-1"])

    def test_reading_only_response_cannot_overwrite_focus(self):
        engine = Engine.create("Q", policy={"input_tokens": 1600, "neighbour_tokens": 0, "read_page_chars": 80})
        account = engine.accounts[0]
        target = engine.add_text("A long original target " * 200)
        objection = engine.add_text("The target assumes independence.")
        account.update(ordinary_total=2, last_target=target, last_criticism=objection)
        initial = account["focus"]
        result = engine.step(ScriptedProvider(["I have answered the entire target."]))
        self.assertEqual(result["mode"], "read")
        self.assertEqual(account["focus"], initial)
        self.assertIn("READING ONLY", joined(engine.state["last_dispatch"]))

    def test_late_duplicate_return_is_retained_but_cannot_install_twice(self):
        engine = Engine.create("Q", policy={"work_before_review": 1, "trial_calls": 1})
        provider = ScriptedProvider(["Work", "Trial question", "Trial material", "Return question"])
        results = engine.run(provider, 4)
        account = engine.accounts[0]
        before = (account["focus"], account["focus_revision"], engine.ledger.report()["used_calls"])
        result = engine.receive(results[-1]["opportunity"], ProviderResult("Late renamed question", None), counter=provider.count)
        self.assertEqual(result["status"], "retained-stale")
        self.assertEqual((account["focus"], account["focus_revision"], engine.ledger.report()["used_calls"]), before)
        self.assertIn("Late renamed question", engine.export_markdown())

    def test_recording_and_optional_participant_history_are_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine.create("Q", policy={"run_profile": "research", "participant_history": "off"}, directory=directory)
            engine.step(ScriptedProvider(["An unclassified prose contribution"]))
            events = [json.loads(line) for line in (Path(directory) / "observations.jsonl").read_text().splitlines()]
            dispatch = next(event for event in events if event["kind"] == "dispatch-prepared")
            self.assertTrue(dispatch["messages"])
            self.assertEqual(engine.policy["participant_history"], "off")
            self.assertIn("An unclassified prose contribution", Engine.load(directory).export_markdown())

    def test_no_recording_still_allows_dispatch_observer_and_resumption(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine.create("Q", directory=directory)
            observed = []
            engine.recorder.observers.append(observed.append)
            engine.step(ScriptedProvider(["Working material"]))
            self.assertTrue(any(item["kind"] == "dispatch-prepared" for item in observed))
            self.assertFalse((Path(directory) / "observations.jsonl").exists())
            loaded = Engine.load(directory)
            self.assertIn("Working material", loaded.export_markdown())
            self.assertEqual(loaded.ledger.report()["used_calls"], 1)

    def test_manual_jolt_waits_for_reserved_return(self):
        engine = Engine.create("Q", policy={"work_before_review": 1, "trial_calls": 1})
        provider = ScriptedProvider(["Work", "Candidate", "Trial", "Return", "Fresh"])
        engine.run(provider, 2)
        engine.jolt(kind="fresh")
        results = engine.run(provider, 3)
        self.assertEqual([item["invitation"] for item in results], ["trial", "return", "fresh"])
        self.assertIn("do not claim to have answered an omitted objection", joined(provider.calls[-1]))

    def test_operator_config_cannot_add_a_semantic_score_or_disable_sequential_bound(self):
        for policy in ({"truth_score": 1}, {"inflight_calls": 2}, {"recipes": {"local": {"reward": 1}}}):
            with self.assertRaises(ValueError):
                validate(policy)


if __name__ == "__main__":
    unittest.main()
