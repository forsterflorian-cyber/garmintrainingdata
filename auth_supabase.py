import os
import jwt
from functools import wraps
from flask import request, jsonify

SUPABASE_JWT_SECRET = os.environ["SUPABASE_JWT_SECRET"]

def require_user(f):
    @wraps(f)
    def wrapper(*args, **kwargs):

        auth = request.headers.get("Authorization")

        if not auth:
            return jsonify({"error": "missing token"}), 401

        token = auth.replace("Bearer ", "")

        try:
            payload = jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"]
            )

        except Exception:
            return jsonify({"error": "invalid token"}), 401

        request.user_id = payload["sub"]

        return f(*args, **kwargs)

    return wrapper