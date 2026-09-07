"""Independent end-to-end regression probes for spec Parts II–VII and IX.

These cases inspect real controller dispatches and saved working state. The
participant remains a scripted prose fixture; these are not learning results.
"""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from open_inquiry.engine import Engine
from open_inquiry.providers import ProviderResult, ScriptedProvider


def usage(input_tokens=10, output_tokens=5):
    return {"input_tokens": input_tokens, "output_tokens": output_tokens,
            "cached_input_tokens": 0, "reasoning_tokens": 0,
            "reasoning_included": True}


def messages_text(dispatch):
    return "\n".join(item["content"] for item in dispatch["messages"])


class EngineIndependentAuditTests(unittest.TestCase):
    def make_engine(self, **policy):
        return Engine.create("Why do these independent references disagree?", policy=policy)

    def test_model_response_survives_observation_write_failure_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine.create("Investigate the reference.",
                                   policy={"run_profile": "research"}, directory=directory)
            original_record = engine.recorder.record

            def record(event):
                if event["kind"] == "model-response":
                    raise OSError("simulated observation destination failure")
                original_record(event)

            text = "The qualification in the original source may matter."
            with patch.object(engine.recorder, "record", side_effect=record):
                try:
                    engine.step(ScriptedProvider([text]))
                except OSError:
                    pass
            loaded = Engine.load(directory)
            retained = [item["text"] for item in loaded.collection.data["occurrences"].values()]
            self.assertIn(text, retained, "A separate recording failure must not lose retainable returned prose")
            self.assertTrue(loaded.state["recording_gap"])
            self.assertEqual(loaded.ledger.report()["used_calls"], 1)
            with self.assertRaises(ValueError):
                loaded.prepare(ScriptedProvider(["Further dispatch must pause."]))

    def test_attention_gate_off_keeps_unrelated_problem_trial_and_return(self):
        engine = self.make_engine(work_before_review=1, trial_calls=1,
                                  attention_learning="on", attention_review_every=2)
        provider = ScriptedProvider(["A difficulty.", "Try separating the reference conditions.",
                                     "Investigate the earlier calibration.", "Keep the revised question."])
        engine.step(provider)
        engine.step(provider)
        account = engine.accounts[0]
        self.assertEqual(account["trial"]["kind"], "problem")
        trial_id = account["trial"]["id"]
        engine.set_gate("off")
        self.assertIsNotNone(account["trial"], "The attention gate must not cancel problem revision")
        self.assertEqual(account["trial"]["id"], trial_id)
        engine.step(provider)
        engine.step(provider)
        self.assertEqual(engine.collection.get(account["focus"])["text"], "Keep the revised question.")

    def test_unfunded_nomination_does_not_consume_undelivered_originals(self):
        engine = self.make_engine(work_before_review=1, run_model_calls=1)
        provider = ScriptedProvider(["An original objection needing return."])
        engine.step(provider)
        account = engine.accounts[0]
        before = deepcopy(account["delivery_cursors"])
        self.assertEqual(engine.prepare(provider)["status"], "limit")
        self.assertEqual(account["delivery_cursors"], before,
                         "Selection without dispatch is not delivery of an original")
        engine.update_policy({"run_model_calls": 10})
        dispatch = engine.prepare(provider)
        self.assertIn("An original objection needing return.", messages_text(dispatch))

    def test_current_use_after_first_sixteen_bindings_has_real_prose_action_route(self):
        engine = self.make_engine()
        account = engine.accounts[0]
        for index in range(17):
            occurrence = engine.add_text(f"Reference-use material {index}.")
            identifier = engine.add_use(account["id"], occurrence, f"reference application {index}")
            if index < 16:
                engine.change_use(account["id"], identifier, "park", "This application is parked.")
        current = identifier
        provider = ScriptedProvider(["An initial thought.", "The reference may be dependent.",
                                     "Park the current use because its independence is unsupported."])
        engine.run(provider, steps=3)
        self.assertEqual(engine._use(account, current)["disposition"], "parked",
                         "A rotating current use must not fall outside a permanent first-sixteen grant")

    def test_granted_current_use_is_visible_in_its_actual_response_request(self):
        engine = self.make_engine()
        account = engine.accounts[0]
        occurrence = engine.add_text("CURRENT-REFERENCE-OPERAND: report B.")
        identifier = engine.add_use(account["id"], occurrence, "the current independent reference")
        provider = ScriptedProvider(["A draft answer.", "The draft may depend on the wrong reference."])
        engine.step(provider)
        engine.step(provider)
        dispatch = engine.prepare(provider)
        grant = engine.state["grants"][dispatch["grant"]]
        self.assertEqual(grant["current_use"], identifier)
        prompt = messages_text(dispatch)
        self.assertIn(identifier, prompt, "The operational meaning of 'current use' must be visible")
        self.assertIn("CURRENT-REFERENCE-OPERAND", prompt)

    def test_surfaced_reasons_survive_old_focus_anchors_into_trial_request(self):
        engine = self.make_engine(work_before_review=1, trial_calls=1,
                                  neighbour_items=0, neighbour_tokens=0)
        account = engine.accounts[0]
        account["focus_anchors"] = [engine.add_text(f"Earlier immediate referent {n}.") for n in range(4)]
        objection = "NEWLY-SURFACED-OBJECTION: the reference has a shared calibration."
        provider = ScriptedProvider([objection, "Try the independent-calibration question."])
        engine.step(provider)
        engine.step(provider)
        self.assertIsNotNone(account["trial"])
        dispatch = engine.prepare(provider)
        self.assertIn(objection, messages_text(dispatch),
                      "Four older anchors must not silently displace newly surfaced trial reasons")

    def test_gate_off_during_method_dispatch_retains_late_text_and_real_spend(self):
        engine = self.make_engine(work_before_review=1, trial_calls=1,
                                  attention_learning="on", attention_review_every=1)
        account = engine.accounts[0]
        baseline = account["method"]
        provider = ScriptedProvider(["A context difficulty.", "Use the broader view. Reopen the original qualification."])
        engine.step(provider)
        engine.step(provider)
        self.assertEqual(account["trial"]["kind"], "method")
        dispatch = engine.prepare(provider)
        engine.set_gate("off")
        result = engine.receive(dispatch["grant"], ProviderResult("Late candidate text remains available.", usage()),
                                counter=provider.count)
        self.assertEqual(result["status"], "retained-stale")
        self.assertEqual(account["method"], baseline)
        self.assertEqual(account["recipe"], "local")
        self.assertIsNone(account["trial"])
        self.assertEqual(engine.ledger.report()["used_calls"], 3)
        self.assertEqual(engine.ledger.report()["reserved_calls"], 0)
        self.assertEqual(engine.collection.get(result["occurrence"])["text"], "Late candidate text remains available.")

    def test_history_off_keeps_live_observation_without_archiving_completed_prompts(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine.create("Inspect these sources.", directory=directory,
                                   policy={"history": "off", "participant_history": "off"})
            observed = []
            engine.recorder.observers.append(observed.append)
            engine.run(ScriptedProvider(["An initial account.", "An objection to that account."]), steps=2)
            self.assertEqual(sum(event["kind"] == "dispatch-prepared" for event in observed), 2)
            for grant in engine.state["grants"].values():
                if grant["consumed"]:
                    self.assertFalse(grant["cut"].get("messages"),
                                     "Completed grant tombstones must not silently implement full prompt history")
            self.assertTrue(engine.state["last_dispatch"]["messages"])
            self.assertFalse((Path(directory) / "observations.jsonl").exists())
            self.assertFalse((Path(directory) / "observations.json").exists())

    def test_history_off_preserves_exact_pending_trial_cut_independently_of_grant_cleanup(self):
        engine = self.make_engine(history="off", work_before_review=1, trial_calls=2,
                                  attention_learning="on", attention_review_every=1)
        provider = ScriptedProvider(["A context problem.", "Use the broader view. Reopen the actual qualification.",
                                     "The source qualification changes this interpretation."])
        engine.run(provider, steps=3)
        trial = engine.accounts[0]["trial"]
        self.assertIsNotNone(trial)
        self.assertEqual(len(trial["cuts"]), 1)
        self.assertTrue(trial["cuts"][0].get("messages"),
                        "Pending return needs its actual trial view despite completed grant cleanup")
        self.assertEqual(trial["cuts"][0]["messages"], provider.calls[-1]["messages"])

    def test_known_independent_application_remains_available_during_dependency_work(self):
        engine = self.make_engine(dependency_slice=1)
        account = engine.accounts[0]
        premise = engine.add_use(account["id"], engine.add_text("A necessary input."), "premise")
        dependent = engine.add_use(account["id"], engine.add_text("An application requiring that input."), "dependent")
        independent = engine.add_use(account["id"], engine.add_text("INDEPENDENT-APPLICATION remains available."), "independent")
        engine.add_dependency(account["id"], dependent, premise)
        engine.change_use(account["id"], premise, "park", "Its source is unavailable.")
        account["use_cursor"] = 2
        dispatch = engine.prepare(ScriptedProvider(["Continue the independent application."]))
        self.assertEqual(dispatch["status"], "ready")
        grant = engine.state["grants"][dispatch["grant"]]
        self.assertEqual(grant["current_use"], independent,
                         "A declared-independent application needs no affected-graph propagation before use")
        self.assertIn("INDEPENDENT-APPLICATION", messages_text(dispatch))

    def test_prose_requested_nonlocal_read_works_with_attention_learning_off(self):
        engine = self.make_engine(attention_learning="off", neighbour_items=0,
                                  neighbour_tokens=0, nonlocal_every=100)
        source = engine.add_text("NONLOCAL-ORIGINAL: the temperature qualification is essential.",
                                 label="Calibration original")
        account = engine.accounts[0]
        old_method, old_recipe = account["method"], account["recipe"]
        provider = ScriptedProvider([f"Read {source}. The original qualification may change the question."])
        engine.step(provider)
        dispatch = engine.prepare(provider)
        self.assertIn("NONLOCAL-ORIGINAL", messages_text(dispatch),
                      "A one-off participant read must not depend on installed attention learning")
        self.assertEqual(account["method"], old_method)
        self.assertEqual(account["recipe"], old_recipe)


if __name__ == "__main__":
    unittest.main()
