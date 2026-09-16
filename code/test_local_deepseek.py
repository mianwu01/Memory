"""Credential selection and route/model isolation; no API calls."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from run_with_local_deepseek import local_environment


class LocalRouteTests(unittest.TestCase):
    def test_explicit_api_key_wins_and_stale_route_model_are_replaced(self):
        key = "sk_tr_" + "x" * 24
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "route.env"
            path.write_text("sess_" + "s" * 24 + "\nold bo-" + "b" * 24 +
                            "\nOPENAI_API_KEY=" + key +
                            "\nOPENAI_BASE_URL=https://example.test/v1/\nOPENAI_MODEL=test-flash\n")
            with patch.dict(os.environ, {"OPENAI_BASE_URL": "https://old.test/v1",
                                        "OPENAI_MODEL": "old-model"}):
                env = local_environment(path)
            for name in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
                self.assertEqual(env[name], key)
            for name in ("OPENAI_BASE_URL", "OPENAI_API_BASE", "DEEPSEEK_BASE_URL"):
                self.assertEqual(env[name], "https://example.test/v1")
            for name in ("OPENAI_MODEL", "DEEPSEEK_MODEL"):
                self.assertEqual(env[name], "test-flash")
            override = local_environment(path, "https://override.test/v1", "test-pro")
            self.assertEqual(override["OPENAI_BASE_URL"], "https://override.test/v1")
            self.assertEqual(override["OPENAI_MODEL"], "test-pro")

    def test_session_and_invalid_explicit_credentials_fail_closed(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "route.env"
            for content in ("sess_" + "s" * 24,
                            "OPENAI_API_KEY=invalid\nold bo-" + "b" * 24):
                path.write_text(content)
                with self.assertRaises(ValueError):
                    local_environment(path)

    def test_legacy_key_still_loads(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "route.env"
            for prefix in ("sk-", "bo-", "sk_tr_"):
                key = prefix + "x" * 24
                path.write_text("API key: " + key)
                self.assertEqual(local_environment(path)["OPENAI_API_KEY"], key)


if __name__ == "__main__":
    unittest.main()
