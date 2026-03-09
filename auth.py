import os
import secrets
from functools import wraps

from flask import Response, request

USERNAME = os.getenv("DASH_USER", "admin")
PASSWORD = os.getenv("DASH_PASS", "secret")


def check_auth(username: str | None, password: str | None) -> bool:
    if username is None or password is None:
        return False
    return secrets.compare_digest(username, USERNAME) and secrets.compare_digest(password, PASSWORD)


def authenticate() -> Response:
    return Response(
        "Login required",
        401,
        {"WWW-Authenticate": 'Basic realm="Login Required"'},
    )


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)

    return decorated
