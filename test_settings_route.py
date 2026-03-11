from __future__ import annotations

import unittest
from functools import wraps

from flask import Flask, jsonify, request

from backend.routes.settings import create_settings_blueprint
from observability import ServiceError


class FakeAccountService:
    def __init__(self, response=None):
        self.response = response or {
            "status": "deleted",
            "redirectTo": "/auth",
            "signOut": True,
            "authUserDeleted": True,
        }
        self.calls = []

    def delete_account(self, user_id: str, *, confirmation_text: str | None):
        self.calls.append({"user_id": user_id, "confirmation_text": confirmation_text})
        return dict(self.response)


def fake_require_user(handler):
    @wraps(handler)
    def wrapper(*args, **kwargs):
        request.user_id = "user-1"
        request.auth_payload = {"sub": "user-1", "email": "athlete@example.com"}
        return handler(*args, **kwargs)

    return wrapper


def reject_require_user(handler):
    @wraps(handler)
    def wrapper(*args, **kwargs):
        return jsonify({"error": "missing token"}), 401

    return wrapper


def create_test_app(*, service, require_user_decorator=None):
    app = Flask(__name__)

    @app.errorhandler(ServiceError)
    def handle_service_error(exc):
        return jsonify({"error": exc.public_message}), exc.status_code

    if require_user_decorator is None:
        app.register_blueprint(create_settings_blueprint(account_service=service))
    else:
        app.register_blueprint(
            create_settings_blueprint(
                account_service=service,
                require_user_decorator=require_user_decorator,
            )
        )
    return app


class SettingsRouteTests(unittest.TestCase):
    def test_authenticated_delete_returns_sign_out_payload(self):
        service = FakeAccountService()
        app = create_test_app(service=service, require_user_decorator=fake_require_user)
        client = app.test_client()

        response = client.post("/api/account/delete", json={"confirmationText": "DELETE"})

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            {
                "status": "deleted",
                "redirectTo": "/auth",
                "signOut": True,
                "authUserDeleted": True,
            },
            response.get_json(),
        )
        self.assertEqual(
            [{"user_id": "user-1", "confirmation_text": "DELETE"}],
            service.calls,
        )

    def test_unauthenticated_delete_is_rejected(self):
        service = FakeAccountService()
        app = create_test_app(service=service, require_user_decorator=reject_require_user)
        client = app.test_client()

        response = client.post("/api/account/delete", json={"confirmationText": "DELETE"})

        self.assertEqual(401, response.status_code)
        self.assertEqual({"error": "missing token"}, response.get_json())
        self.assertEqual([], service.calls)


if __name__ == "__main__":
    unittest.main()
