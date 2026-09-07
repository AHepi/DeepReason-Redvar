"""Transport contract checks with local mocks only; no credentials or live APIs."""

import io
import json
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from open_inquiry.providers import DemoProvider, OllamaProvider, ProviderError, ProviderResult, ScriptedProvider


MESSAGES = [{"role": "system", "content": "Read the supplied material."},
            {"role": "user", "content": "Some prose is sufficient."}]


def body(**changes):
    value = {"message": {"content": "An answer.", "thinking": "hidden trace must not be retained"},
             "done": True, "prompt_eval_count": 100, "prompt_eval_cached_count": 70,
             "eval_count": 20, "total_duration": 2000}
    value.update(changes)
    return json.dumps(value).encode()


class FixtureTests(unittest.TestCase):
    def test_fixture_counts_complete_messages_and_discloses_synthetic_units(self):
        provider = ScriptedProvider(["A meaningful response."])
        result = provider.generate(MESSAGES, max_tokens=100, timeout=1)
        self.assertGreater(provider.count(MESSAGES), sum(len(m["content"]) for m in MESSAGES))
        self.assertEqual(provider.count_kind, "fixture")
        self.assertEqual(result.usage["input_tokens"], provider.count(MESSAGES))
        self.assertIn("not production", result.metadata["accounting"])

    def test_fixture_generation_limit_respects_utf8_boundaries(self):
        provider = ScriptedProvider(["ééé"])
        result = provider.generate([], max_tokens=3, timeout=1)
        self.assertEqual(result.text, "é")
        self.assertEqual(result.usage["output_tokens"], 2)
        self.assertTrue(result.metadata["generation_truncated"])

    def test_explicit_results_can_represent_unknown_usage_and_exhaustion(self):
        provider = ScriptedProvider([ProviderResult("late text", usage=None)])
        self.assertIsNone(provider.generate([], max_tokens=10, timeout=1).usage)
        with self.assertRaisesRegex(ProviderError, "no remaining response"):
            provider.generate([], max_tokens=10, timeout=1)

    def test_demo_is_deterministic_across_instances(self):
        left, right = DemoProvider(), DemoProvider()
        for _ in range(3):
            self.assertEqual(left.generate(MESSAGES, max_tokens=1024, timeout=1),
                             right.generate(MESSAGES, max_tokens=1024, timeout=1))


class OllamaTests(unittest.TestCase):
    def test_request_limits_and_usage_provenance(self):
        provider = OllamaProvider("selected-model", think="low", context_window=16384)
        with patch.object(provider._opener, "open", return_value=io.BytesIO(body())) as opened:
            result = provider.generate(MESSAGES, max_tokens=250, timeout=2)
        req = opened.call_args.args[0]
        sent = json.loads(req.data)
        self.assertEqual(req.full_url, "http://localhost:11434/api/chat")
        self.assertEqual(sent["options"], {"num_predict": 250, "num_ctx": 16384})
        self.assertEqual(sent["messages"], MESSAGES)
        self.assertEqual(sent["think"], "low")
        self.assertFalse(sent["stream"])
        self.assertEqual(result.usage["input_tokens"], 100)
        self.assertEqual(result.usage["cached_input_tokens"], 70)
        self.assertEqual(result.usage["output_tokens"], 20)
        self.assertIsNone(result.usage["reasoning_tokens"])
        self.assertIsNone(result.usage["reasoning_included"])
        self.assertFalse(result.usage["accounting_complete"])
        self.assertNotIn("hidden trace", repr(result))
        self.assertFalse(result.metadata["generation_limit_verified"])
        self.assertEqual(provider.count_kind, "estimated")

    def test_missing_counters_are_not_fabricated(self):
        provider = OllamaProvider("model")
        with patch.object(provider, "_request", return_value=body(prompt_eval_count=None, eval_count=None)):
            result = provider.generate(MESSAGES, max_tokens=250, timeout=2)
        self.assertIsNone(result.usage["input_tokens"])
        self.assertIsNone(result.usage["output_tokens"])

    def test_incomplete_reply_keeps_output_consumption_unknown(self):
        provider = OllamaProvider("model")
        with patch.object(provider, "_request", return_value=body(done=False)):
            result = provider.generate(MESSAGES, max_tokens=250, timeout=2)
        self.assertIsNone(result.usage["output_tokens"])
        self.assertEqual(result.text, "An answer.")

    def test_direct_cloud_reads_key_only_for_transport(self):
        provider = OllamaProvider("model", base_url="https://ollama.com/api", api_key_env="TEST_OLLAMA_KEY")
        with patch.dict("os.environ", {"TEST_OLLAMA_KEY": "test-secret-value"}), \
                patch.object(provider, "_request", return_value=body()) as sent:
            result = provider.generate(MESSAGES, max_tokens=250, timeout=2)
        req = sent.call_args.args[0]
        self.assertEqual(req.full_url, "https://ollama.com/api/chat")
        self.assertEqual(req.get_header("Authorization"), "Bearer test-secret-value")
        self.assertNotIn("test-secret-value", repr(result))
        self.assertNotIn("test-secret-value", req.data.decode())

    def test_http_error_body_and_exception_never_leak_credentials(self):
        provider = OllamaProvider("model")
        faults = [HTTPError("https://user:test-secret-value@example.org", 401,
                            "test-secret-value", {}, io.BytesIO(b"test-secret-value")),
                  ProviderError("test-secret-value"), RuntimeError("test-secret-value")]
        for fault in faults:
            with self.subTest(fault=type(fault).__name__), patch.object(provider, "_request", side_effect=fault):
                with self.assertRaises(ProviderError) as caught:
                    provider.generate(MESSAGES, max_tokens=250, timeout=2)
                self.assertNotIn("test-secret-value", str(caught.exception))

    def test_provider_error_response_is_not_exposed(self):
        provider = OllamaProvider("model")
        with patch.object(provider, "_request", return_value=b'{"error":"test-secret-value"}'):
            with self.assertRaises(ProviderError) as caught:
                provider.generate(MESSAGES, max_tokens=250, timeout=2)
        self.assertNotIn("test-secret-value", str(caught.exception))

    def test_response_byte_limit_is_enforced(self):
        provider = OllamaProvider("model", max_response_bytes=20)
        with patch.object(provider._opener, "open", return_value=io.BytesIO(body())):
            with self.assertRaisesRegex(ProviderError, "byte limit"):
                provider.generate(MESSAGES, max_tokens=250, timeout=2)

    def test_total_timeout_retires_adapter_without_retry(self):
        provider = OllamaProvider("model")
        release = threading.Event()

        def delayed(*_):
            release.wait(1)
            return body()

        try:
            with patch.object(provider, "_request", side_effect=delayed) as transport:
                with self.assertRaisesRegex(ProviderError, "timed out"):
                    provider.generate(MESSAGES, max_tokens=250, timeout=0.02)
                with self.assertRaisesRegex(ProviderError, "retired"):
                    provider.generate(MESSAGES, max_tokens=250, timeout=1)
                self.assertEqual(transport.call_count, 1)
        finally:
            release.set()

    def test_invalid_operator_endpoint_and_think_are_rejected(self):
        for endpoint in ("file:///tmp/a", "https://name:secret@example.org", "https://example.org?key=secret"):
            with self.subTest(endpoint=endpoint), self.assertRaises(ProviderError):
                OllamaProvider("model", base_url=endpoint)
        with self.assertRaises(ProviderError):
            OllamaProvider("model", think={"bad": "value"})

    def test_local_endpoint_does_not_receive_cloud_key(self):
        provider = OllamaProvider("model", api_key_env="TEST_OLLAMA_KEY")
        with patch.dict("os.environ", {"TEST_OLLAMA_KEY": "test-secret-value"}), \
                patch.object(provider, "_request", return_value=body()) as sent:
            provider.generate(MESSAGES, max_tokens=250, timeout=2)
        self.assertIsNone(sent.call_args.args[0].get_header("Authorization"))


if __name__ == "__main__":
    unittest.main()
