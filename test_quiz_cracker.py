"""Automated verification tests for Quiz Cracker & Universal AI Providers."""

import io
import json
import unittest
from unittest.mock import patch, MagicMock
import urllib.error
import tkinter as tk
from PIL import Image

import ai_providers as ap
import quiz_cracker as qc


def _make_http_error(code: int, body_dict: dict):
    raw = json.dumps(body_dict).encode("utf-8")
    return urllib.error.HTTPError(
        url="https://example.test",
        code=code,
        msg=f"HTTP {code}",
        hdrs={},
        fp=io.BytesIO(raw),
    )


class TestProviderAutoDetection(unittest.TestCase):
    def test_detect_all_major_key_prefixes(self):
        cases = {
            "AIzaSyD1234567890": "gemini",
            "gsk_abc123def456": "groq",
            "sk-or-v1-999999": "openrouter",
            "sk-ant-api03-xyz": "anthropic",
            "sk-proj-abc123": "openai",
            "sk-live-12345": "openai",
            "xai-abcdef123": "xai",
            "nvapi-123456": "nvidia",
            "hf_abcdefgh": "huggingface",
            "fw_12345678": "fireworks",
            "tgp_v1_abcdef": "together",
            "Bearer AIzaSyWithBearer": "gemini",
            '"gsk_quoted_key"\n': "groq",
        }
        for key, expected in cases.items():
            self.assertEqual(ap.detect_provider_from_key(key), expected, f"Failed for {key}")


class TestUniversalSolverProtocols(unittest.TestCase):
    def setUp(self):
        img = Image.new("RGB", (64, 64), (30, 30, 30))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        self.img_bytes = buf.getvalue()

    @patch("ai_providers._http_json")
    def test_gemini_fallback_on_404_and_429(self, mock_http):
        # First model -> 404, second -> 429, third -> success!
        mock_http.side_effect = [
            _make_http_error(404, {"error": {"message": "Model not found"}}),
            _make_http_error(429, {"error": {"message": "Quota exceeded"}}),
            {"candidates": [{"content": {"parts": [{"text": '{"option": "B", "answer": "Water", "reason": "H2O is water."}'}]}}]},
        ]
        res = ap.solve_mcq_with_provider(self.img_bytes, "auto", "AIzaSyTestKey")
        self.assertEqual(res["provider"], "gemini")
        self.assertEqual(res["option"], "B")
        self.assertEqual(res["answer"], "Water")
        self.assertEqual(mock_http.call_count, 3)

    @patch("ai_providers._http_json")
    def test_openai_compatible_groq_payload(self, mock_http):
        mock_http.return_value = {
            "choices": [{"message": {"content": '{"option": "C", "answer": "Mars", "reason": "The Red Planet."}'}}]
        }
        res = ap.solve_mcq_with_provider(self.img_bytes, "auto", "gsk_test123")
        self.assertEqual(res["provider"], "groq")
        self.assertEqual(res["option"], "C")
        called_url = mock_http.call_args[0][0]
        called_headers = mock_http.call_args[1]["headers"]
        self.assertIn("api.groq.com/openai/v1/chat/completions", called_url)
        self.assertEqual(called_headers["Authorization"], "Bearer gsk_test123")

    @patch("ai_providers._http_json")
    def test_anthropic_claude_payload(self, mock_http):
        mock_http.return_value = {
            "content": [{"type": "text", "text": '{"option": "A", "answer": "Paris", "reason": "Capital of France."}'}]
        }
        res = ap.solve_mcq_with_provider(self.img_bytes, "auto", "sk-ant-api03-test")
        self.assertEqual(res["provider"], "anthropic")
        self.assertEqual(res["option"], "A")
        called_headers = mock_http.call_args[1]["headers"]
        self.assertEqual(called_headers["x-api-key"], "sk-ant-api03-test")
        self.assertIn("anthropic-version", called_headers)

    @patch("ai_providers._http_json")
    def test_openrouter_headers_and_free_models(self, mock_http):
        mock_http.return_value = {
            "choices": [{"message": {"content": '{"option": "D", "answer": "Oxygen", "reason": "O2 gas."}'}}]
        }
        res = ap.solve_mcq_with_provider(self.img_bytes, "auto", "sk-or-v1-test")
        self.assertEqual(res["provider"], "openrouter")
        self.assertEqual(res["option"], "D")
        called_headers = mock_http.call_args[1]["headers"]
        self.assertIn("HTTP-Referer", called_headers)
        self.assertIn("X-Title", called_headers)

    @patch("ai_providers._http_json")
    def test_backup_provider_failover(self, mock_http):
        # Primary OpenAI key gets 401 -> automatically fails over to saved Groq backup key!
        mock_http.side_effect = [
            _make_http_error(401, {"error": {"message": "Invalid API key"}}),
            {"choices": [{"message": {"content": '{"option": "A", "answer": "Newton", "reason": "Laws of motion."}'}}]},
        ]
        res = ap.solve_mcq_with_provider(
            self.img_bytes,
            provider_id="openai",
            api_key="sk-bad-key",
            backup_keys={"groq": "gsk_good_backup"},
        )
        self.assertEqual(res["provider"], "groq")
        self.assertEqual(res["option"], "A")

    @patch("ai_providers._http_json")
    def test_live_model_discovery_on_test_key(self, mock_http):
        # First call is GET /models (discovery), second is POST ping
        mock_http.side_effect = [
            {"models": [{"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]}]},
            {"candidates": [{"content": {"parts": [{"text": "OK"}]}}]},
        ]
        ok, pid, mdl, models, msg = ap.test_provider_key("auto", "AIzaSyLiveTest")
        self.assertTrue(ok)
        self.assertEqual(pid, "gemini")
        self.assertEqual(mdl, "gemini-2.5-flash")
        self.assertIn("gemini-2.5-flash", models)


class TestMouseGestureWatcher(unittest.TestCase):
    def test_horizontal_wiggle_triggers(self):
        w = qc.MouseGestureWatcher()
        w.sensitivity = "medium"
        points = [
            (500, 500, 10.00),
            (590, 502, 10.10),
            (500, 498, 10.22),
            (595, 501, 10.35),
            (505, 500, 10.48),
        ]
        results = [w.feed_position(x, y, t) for x, y, t in points]
        self.assertEqual(results[-1], "wiggle")
        self.assertNotIn("wiggle", results[:-1])

    def test_vertical_wiggle_triggers(self):
        w = qc.MouseGestureWatcher()
        w.sensitivity = "medium"
        points = [
            (300, 400, 20.00),
            (302, 490, 20.10),
            (299, 400, 20.22),
            (301, 495, 20.34),
            (300, 405, 20.46),
        ]
        results = [w.feed_position(x, y, t) for x, y, t in points]
        self.assertEqual(results[-1], "wiggle")

    def test_normal_linear_movement_does_not_trigger(self):
        w = qc.MouseGestureWatcher()
        triggered = False
        for i in range(50):
            if w.feed_position(100 + i * 25, 300 + i * 2, 10.0 + i * 0.03):
                triggered = True
        self.assertFalse(triggered)

    def test_cooldown_prevents_double_trigger(self):
        w = qc.MouseGestureWatcher()
        w.cooldown_sec = 3.0
        for x, y, t in [(500, 500, 10.0), (590, 500, 10.1), (500, 500, 10.2), (590, 500, 10.3), (500, 500, 10.4)]:
            w.feed_position(x, y, t)
        res = None
        for x, y, t in [(500, 500, 10.9), (590, 500, 11.0), (500, 500, 11.1), (590, 500, 11.2), (500, 500, 11.3)]:
            r = w.feed_position(x, y, t)
            if r:
                res = r
        self.assertIsNone(res)

    def test_corner_dwell_trigger(self):
        w = qc.MouseGestureWatcher()
        w.wiggle_enabled = False
        w.corner_enabled = True
        bounds = (0, 0, 1920, 1080)
        self.assertIsNone(w.feed_position(1915, 5, 50.0, bounds))
        self.assertIsNone(w.feed_position(1916, 4, 50.4, bounds))
        self.assertEqual(w.feed_position(1918, 2, 50.7, bounds), "corner")


class TestResponseParsing(unittest.TestCase):
    def test_clean_json(self):
        out = ap.parse_mcq_response('{"option": "B", "answer": "Mitochondria", "reason": "Produces ATP."}')
        self.assertEqual(out["option"], "B")
        self.assertEqual(out["answer"], "Mitochondria")

    def test_fenced_json(self):
        raw = '```json\n{"option": "C", "answer": "42", "reason": "6 times 7 equals 42."}\n```'
        out = ap.parse_mcq_response(raw)
        self.assertEqual(out["option"], "C")
        self.assertEqual(out["answer"], "42")

    def test_plain_text_fallback(self):
        out = ap.parse_mcq_response("B - Oxygen is released during photosynthesis")
        self.assertEqual(out["option"], "✓")
        self.assertIn("Oxygen", out["answer"])


class TestScreenCapture(unittest.TestCase):
    def test_jpeg_downscale(self):
        big = Image.new("RGB", (3840, 2160), (20, 30, 40))
        data = qc.encode_pil_to_jpeg(big, max_width=1920, quality=85)
        decoded = Image.open(io.BytesIO(data))
        self.assertEqual(decoded.width, 1920)
        self.assertEqual(decoded.height, 1080)

    def test_live_monitor_capture(self):
        data = qc.capture_monitor_at_cursor()
        self.assertGreater(len(data), 1000)
        img = Image.open(io.BytesIO(data))
        self.assertGreater(img.width, 100)


class TestOverlayGUI(unittest.TestCase):
    def test_overlay_state_transitions_and_subtle_opacity(self):
        root = tk.Tk()
        try:
            app = qc.QuizCrackerApp(root)
            root.update()
            self.assertEqual(app.mode, "idle")
            self.assertLess(float(root.attributes("-alpha")), 0.50)

            app._set_mode("scanning")
            root.update()
            self.assertEqual(app.mode, "scanning")

            app._on_answer_ready({
                "option": "B",
                "answer": "Photosynthesis",
                "reason": "Plants convert light to glucose.",
                "provider": "groq",
            })
            root.update()
            self.assertEqual(app.mode, "answer")
            self.assertEqual(app.badge_lbl.cget("text"), "B")
            self.assertLessEqual(float(root.attributes("-alpha")), 0.75)

            app._show_error("Test error", "Detail message")
            root.update()
            self.assertEqual(app.mode, "error")

            app._set_mode("idle")
            root.update()
            self.assertEqual(app.mode, "idle")
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    def test_settings_dialog_auto_detects_provider_on_key_entry(self):
        root = tk.Tk()
        try:
            app = qc.QuizCrackerApp(root)
            root.update()
            app._open_settings()
            root.update()
            dlg = app._settings_win
            self.assertIsNotNone(dlg)

            # Entering a Groq key auto-switches provider to Groq & updates models
            dlg.key_var.set("gsk_demo_key_12345")
            root.update()
            self.assertEqual(dlg._current_provider_id(), "groq")

            # Entering an Anthropic key auto-switches provider to Anthropic
            dlg.key_var.set("sk-ant-api03-demo")
            root.update()
            self.assertEqual(dlg._current_provider_id(), "anthropic")

            # Entering a Gemini key auto-switches provider to Gemini
            dlg.key_var.set("AIzaSyDemoKey123")
            root.update()
            self.assertEqual(dlg._current_provider_id(), "gemini")

            # Ensure dialog auto-sized cleanly
            self.assertGreaterEqual(dlg.winfo_width(), 480)
            self.assertGreaterEqual(dlg.winfo_height(), 420)

            dlg.destroy()
            root.update()
            self.assertIsNone(app._settings_win)
        finally:
            try:
                root.destroy()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
