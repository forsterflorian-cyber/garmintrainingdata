from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from runtime_config import assert_required_env, missing_env_vars, require_env, validate_server_runtime


class RuntimeConfigTests(unittest.TestCase):
    def test_missing_env_vars_treats_blank_values_as_missing(self):
        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": " ",
                "SUPABASE_SERVICE_ROLE_KEY": "service-role",
                "APP_SECRET_KEY": "",
            },
            clear=True,
        ):
            self.assertEqual(
                ["SUPABASE_URL", "APP_SECRET_KEY"],
                missing_env_vars(("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "APP_SECRET_KEY")),
            )

    def test_require_env_returns_trimmed_value(self):
        with patch.dict(os.environ, {"APP_SECRET_KEY": "  secret-value  "}, clear=True):
            self.assertEqual(
                "secret-value",
                require_env("APP_SECRET_KEY", context="tests"),
            )

    def test_validate_server_runtime_raises_clear_message(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError) as context:
                validate_server_runtime()

        self.assertIn("application startup", str(context.exception))
        self.assertIn("SUPABASE_URL", str(context.exception))
        self.assertIn("SUPABASE_SERVICE_ROLE_KEY", str(context.exception))
        self.assertIn("APP_SECRET_KEY", str(context.exception))
        self.assertIn(".env.example", str(context.exception))

    def test_assert_required_env_names_the_missing_keys(self):
        with patch.dict(os.environ, {"SUPABASE_URL": "https://example.supabase.co"}, clear=True):
            with self.assertRaises(RuntimeError) as context:
                assert_required_env(
                    ("SUPABASE_URL", "SUPABASE_ANON_KEY"),
                    context="frontend auth bootstrap",
                )

        self.assertIn("frontend auth bootstrap", str(context.exception))
        self.assertIn("SUPABASE_ANON_KEY", str(context.exception))


if __name__ == "__main__":
    unittest.main()
