from __future__ import annotations

from typing import Callable

from flask import Blueprint, jsonify, request

from backend.services.account_service import AccountService


def create_settings_blueprint(
    *,
    account_service: AccountService,
    require_user_decorator: Callable | None = None,
) -> Blueprint:
    blueprint = Blueprint("settings_api", __name__)
    require_user_decorator = require_user_decorator or _default_require_user()

    @blueprint.post("/api/account/delete")
    @require_user_decorator
    def delete_account():
        payload = request.get_json(silent=True) or {}
        response = account_service.delete_account(
            request.user_id,
            confirmation_text=payload.get("confirmationText"),
        )
        return jsonify(response)

    return blueprint


def _default_require_user():
    from auth_supabase import require_user

    return require_user
