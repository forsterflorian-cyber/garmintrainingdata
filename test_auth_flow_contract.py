from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent


class AuthFlowContractTests(unittest.TestCase):
    def test_backend_exposes_auth_callback_shell_route(self):
        source = (REPO_ROOT / "app.py").read_text(encoding="utf-8")

        self.assertIn('@app.get("/auth/callback")', source)
        self.assertIn("def auth_callback_view()", source)

    def test_auth_template_exposes_real_google_login_action(self):
        source = (REPO_ROOT / "templates" / "_auth_view.html").read_text(encoding="utf-8")

        self.assertIn('data-auth-provider="google"', source)
        self.assertIn("Continue with Google", source)

    def test_frontend_uses_explicit_oauth_callback_flow(self):
        source = (REPO_ROOT / "static" / "dashboard" / "main.js").read_text(encoding="utf-8")

        self.assertIn('flowType: "pkce"', source)
        self.assertIn("signInWithOAuth", source)
        self.assertIn("exchangeCodeForSession", source)
        self.assertIn("verifyOtp", source)
        self.assertIn('authCallback: "/auth/callback"', source)


if __name__ == "__main__":
    unittest.main()
