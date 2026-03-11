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
        self.assertIn("detectSessionInUrl: false", source)
        self.assertIn("signInWithOAuth", source)
        self.assertIn("exchangeCodeForSession", source)
        self.assertIn("verifyOtp", source)
        self.assertIn('authCallback: "/auth/callback"', source)
        self.assertIn('return `${window.location.origin}${APP_ROUTE_PATHS.authCallback}`;', source)
        self.assertIn("storageKey: SUPABASE_AUTH_STORAGE_KEY", source)
        self.assertIn("storage: supabaseAuthStorage", source)

    def test_frontend_bootstraps_callback_before_location_sync(self):
        source = (REPO_ROOT / "static" / "dashboard" / "main.js").read_text(encoding="utf-8")

        self.assertIn("sessionRestorePending: isAuthCallbackPath(window.location.pathname)", source)
        self.assertIn(
            """async function bootstrapApplication() {
  state.activeView = resolveSurfaceView(requestedViewFromHash());
  bindEvents();
  resetAccountDeletionUi();
  setAuthUi(null);
  renderDashboard();
  renderSyncStatusPanel({}, "settingsSyncStatusPanel");

  if (isAuthCallbackPath()) {
    await restoreSession();
    return;
  }

  syncSurfaceUi({ syncHash: false });
  syncAppUi({ replaceHistory: false });
  await restoreSession();
}

void bootstrapApplication();""",
            source,
        )
        self.assertIn("secure login state was lost", source)


if __name__ == "__main__":
    unittest.main()
