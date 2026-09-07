"""Subprocess evidence for the installed CLI contract, without a live model.

These cases exercise independent commands sharing a saved workspace, so a
successful in-memory engine fixture cannot conceal broken CLI persistence.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.workspace = self.directory / "inquiry"
        self.environment = os.environ.copy()
        self.environment["PYTHONPATH"] = str(ROOT / "src")

    def invoke(self, *arguments, expected=0, json_output=True):
        command = [sys.executable, "-m", "open_inquiry", "--workspace", str(self.workspace)]
        if json_output:
            command.append("--json")
        command.extend(str(argument) for argument in arguments)
        result = subprocess.run(command, cwd=self.directory, env=self.environment,
                                text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, expected, msg=result.stdout + result.stderr)
        if expected:
            self.assertNotIn("Traceback", result.stderr)
            return result
        return json.loads(result.stdout) if json_output else result.stdout

    def initialise(self):
        return self.invoke("init", "--brief", "Why do the balances disagree?")

    def test_help_is_available_without_a_workspace(self):
        output = self.invoke("--help", json_output=False)
        self.assertIn("init", output)
        self.assertIn("--workspace", output)
        self.assertFalse(self.workspace.exists())

    def test_brief_demo_resume_and_export_across_processes(self):
        brief = self.directory / "brief.txt"
        brief.write_text("An ordinary prose question without any typed fields.", encoding="utf-8")
        created = self.invoke("init", "--brief-file", brief)
        self.assertTrue(created["created"])
        first = self.invoke("run", "--provider", "demo", "--steps", "2")
        self.assertEqual(len(first["steps"]), 2)
        self.assertIn("fixture", first["counter"])
        second = self.invoke("run", "--provider", "demo", "--steps", "1")
        self.assertEqual(len(second["steps"]), 1)
        material = self.invoke("sources", "catalogue", "--limit", "30")
        self.assertGreater(len(material["items"]), 3)
        destination = self.directory / "report.md"
        self.invoke("export", "--output", destination)
        report = destination.read_text(encoding="utf-8")
        self.assertIn("ordinary prose question", report)
        self.assertFalse((self.workspace / ".writer.lock").exists())

    def test_source_read_search_and_prose_survive_separate_commands(self):
        self.initialise()
        source = self.directory / "source.txt"
        source.write_text("Earlier: B was zeroed against A. Later: an independent procedure.", encoding="utf-8")
        ingested = self.invoke("sources", "add", source)
        self.assertTrue(ingested["readable"])
        opened = self.invoke("sources", "read", ingested["id"], "--start", "0", "--limit", "8")
        self.assertEqual(opened["text"], "Earlier:")
        search = self.invoke("search", "B was zeroed", "--source", ingested["id"])
        self.assertIn("complete", search)
        prose = "I see a difficulty but cannot yet articulate it."
        added = self.invoke("contribute", "--text", prose)
        retained = self.invoke("read", added["occurrence"])
        self.assertEqual(retained["text"], prose)

    def test_policy_validation_and_learning_gates(self):
        self.initialise()
        policy = self.invoke("config", "set", "participant_history", "off")
        self.assertEqual(policy["participant_history"], "off")
        self.invoke("learning", "observe")
        gate = self.invoke("learning")
        self.assertEqual(gate["attention_learning"], "observe")
        self.invoke("learning", "on")
        reset = self.invoke("learning", "reset", "--account", "account-1")
        self.assertTrue(reset["reset"])
        self.invoke("learning", "off")
        rejected = self.invoke("config", "set", "truth_score", "1", expected=2)
        self.assertIn("Unknown", rejected.stderr)
        self.assertNotIn("truth_score", self.invoke("config", "show"))

    def test_source_command_discloses_unreadable_media(self):
        self.initialise()
        source = self.directory / "unread-image.png"
        source.write_bytes(b"\x89PNG\r\n\x1a\nfixture bytes, no interpretation")
        ingested = self.invoke("sources", "add", source)
        self.assertFalse(ingested["readable"])
        self.assertFalse(ingested["extraction_complete"])
        self.assertIn("No installed adapter", ingested["readability_note"])

    def test_explicit_use_parking_and_reactivation(self):
        self.initialise()
        occurrence = self.invoke("contribute", "--text", "B is our independent reference.")["occurrence"]
        created = self.invoke("use", "add", "--occurrence", occurrence,
                              "--purpose", "Independent calibration reference")
        use_id = created["use"]
        if isinstance(use_id, dict):
            use_id = use_id["id"]
        self.invoke("use", "park", "--use", use_id, "--reason", "Its independence is disputed.")
        uses = self.invoke("use", "list")["uses"]
        parked = next(use for use in uses if use["id"] == use_id)
        self.assertEqual(parked["disposition"], "parked")
        self.assertEqual(self.invoke("read", occurrence)["text"], "B is our independent reference.")
        self.invoke("use", "reactivate", "--use", use_id, "--reason", "Reconsider its qualified use.")
        uses = self.invoke("use", "list")["uses"]
        self.assertEqual(next(use for use in uses if use["id"] == use_id)["disposition"], "active")

    def test_existing_workspace_and_competing_writer_are_not_overwritten(self):
        self.initialise()
        self.invoke("init", "--brief", "Replacement", expected=2)
        lock = self.workspace / ".writer.lock"
        lock.write_text("another-process", encoding="utf-8")
        rejected = self.invoke("contribute", "--text", "Should not be written", expected=2)
        self.assertIn("locked", rejected.stderr)
        self.assertTrue(lock.exists())
        self.invoke("status")
        lock.unlink()

    def test_ollama_requires_model_and_explicit_estimate_admission_before_dispatch(self):
        self.initialise()
        missing_model = self.invoke("run", "--provider", "ollama", "--steps", "1", expected=2)
        self.assertIn("--model", missing_model.stderr)
        no_estimates = self.invoke("run", "--provider", "ollama", "--model", "uncontacted-fixture", "--steps", "1", expected=2)
        self.assertIn("--allow-estimates", no_estimates.stderr)
        self.assertTrue(self.invoke("config", "show")["strict_tokens"])

    def test_workspace_option_after_nested_command_and_toml_defaults(self):
        alternate = self.directory / "alternate"
        created = self.invoke("init", "--workspace", alternate, "--brief", "Alternate question")
        self.assertEqual(created["workspace"], str(alternate))
        policy_file = self.directory / "policy.toml"
        self.invoke("config", "defaults", "--output", policy_file)
        self.assertIn("attention_learning", policy_file.read_text(encoding="utf-8"))
        policy = self.invoke("config", "show", "--workspace", alternate)
        self.assertEqual(policy["attention_learning"], "off")

    def test_human_run_status_and_read_show_prose_without_json_escaping(self):
        self.initialise()
        result = self.invoke("run", "--steps", "1", json_output=False)
        self.assertIn("Demo contribution 1.", result)
        self.assertIn("Calls: 1/24", result)
        status = self.invoke("status", json_output=False)
        self.assertIn("attention: off", status)
        prose = "First qualification.\nSecond qualification."
        occurrence = self.invoke("contribute", "--text", prose)["occurrence"]
        opened = self.invoke("read", occurrence, json_output=False)
        self.assertIn(prose, opened)
        self.assertIn("End of the declared readable representation.", opened)

    def test_registered_condition_can_run_locally_without_a_model(self):
        self.initialise()
        source_file = self.directory / "calibration.txt"
        phrase = "B was zeroed against A."
        source_file.write_text(phrase, encoding="utf-8")
        source = self.invoke("sources", "add", source_file)["id"]
        occurrence = self.invoke("contribute", "--text", "Use B as independent.")["occurrence"]
        use_id = self.invoke("use", "add", "--occurrence", occurrence,
                             "--purpose", "Independent reference")["use"]
        binding = self.invoke("bind", "--use", use_id, "--source", source, "--phrase", phrase)
        self.assertEqual(binding["binding"]["use_id"], use_id)
        checked = self.invoke("checks", "advance")
        self.assertEqual(checked["model_calls"], 0)
        self.assertTrue(any(receipt["status"] == "matched" for receipt in checked["receipts"]))
        parked = next(use for use in self.invoke("use", "list")["uses"] if use["id"] == use_id)
        self.assertEqual(parked["disposition"], "parked")
        self.assertEqual(self.invoke("status")["resources"]["used_calls"], 0)
        self.assertGreater(len(self.invoke("checks")["receipts"]), 0)

    def test_account_pause_resume_and_dependency_command_wiring(self):
        self.initialise()
        self.invoke("accounts", "pause")
        paused_run = self.invoke("run", "--steps", "1", expected=1)
        self.assertEqual(json.loads(paused_run.stdout)["steps"][0]["status"], "paused")
        self.invoke("accounts", "resume")
        occurrence = self.invoke("contribute", "--text", "A shared passage.")["occurrence"]
        first = self.invoke("use", "add", "--occurrence", occurrence, "--purpose", "First application")["use"]
        second = self.invoke("use", "add", "--occurrence", occurrence, "--purpose", "Second application")["use"]
        self.invoke("use", "depend", "--use", second, "--on", first)
        self.invoke("checks", "advance")
        uses = self.invoke("use", "list")["uses"]
        self.assertIn(first, next(use for use in uses if use["id"] == second)["depends_on"])
        self.invoke("use", "undepend", "--use", second, "--on", first)
        self.invoke("checks", "advance")
        uses = self.invoke("use", "list")["uses"]
        self.assertNotIn(first, next(use for use in uses if use["id"] == second)["depends_on"])
        self.assertFalse(self.invoke("accounts")[0]["paused"])

    def test_read_only_inspection_does_not_recover_a_saved_inflight_request(self):
        self.initialise()
        script = ("import sys; from open_inquiry.engine import Engine; "
                  "from open_inquiry.providers import DemoProvider; "
                  "Engine.load(sys.argv[1]).prepare(DemoProvider())")
        prepared = subprocess.run([sys.executable, "-c", script, str(self.workspace)],
                                  env=self.environment, cwd=self.directory,
                                  capture_output=True, text=True, timeout=20)
        self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
        before = (self.workspace / "state.json").read_bytes()
        status = self.invoke("status")
        self.assertIsNotNone(status["inflight"])
        self.assertEqual(status["resources"]["unknown_calls"], 0)
        self.assertEqual((self.workspace / "state.json").read_bytes(), before)
        self.invoke("contribute", "--text", "Explicit mutation recovers the interrupted snapshot.")
        recovered = self.invoke("status")
        self.assertIsNone(recovered["inflight"])
        self.assertEqual(recovered["resources"]["unknown_calls"], 1)

    def test_repeating_estimate_admission_does_not_cancel_a_pending_trial(self):
        self.initialise()
        self.invoke("config", "set", "work_before_review", "1")
        self.invoke("run", "--provider", "demo", "--steps", "2", "--allow-estimates")
        before = self.invoke("show")
        trial_id = before["accounts"][0]["trial"]["id"]
        self.invoke("run", "--provider", "demo", "--steps", "1", "--allow-estimates")
        after = self.invoke("show")
        self.assertEqual(after["epoch"], before["epoch"])
        self.assertEqual(after["accounts"][0]["trial"]["id"], trial_id)
        self.assertEqual(after["accounts"][0]["trial"]["used_slots"], 1)


if __name__ == "__main__":
    unittest.main()
