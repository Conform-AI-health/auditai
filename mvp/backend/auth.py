"""JWT assinado para autenticação local sem estado no servidor."""

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import time
from backend.config import ENV_FILE


ALGORITHM = "HS256"
TTL_SECONDS = 1800


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _secret():
    configured = os.environ.get("AUDITIA_JWT_SECRET", "").strip()
    env_file = ENV_FILE
    lines = []
    if env_file.exists():
        lines = env_file.read_text(encoding="utf-8-sig").splitlines()
        for line in lines:
            name, separator, value = line.partition("=")
            if separator and name.strip() == "AUDITIA_JWT_SECRET" and value.strip():
                return value.strip().encode()
    if configured:
        return configured.encode()
    generated = secrets.token_urlsafe(48)
    ending = "" if not lines else "\n"
    with env_file.open("a", encoding="utf-8") as target:
        target.write(f"{ending}AUDITIA_JWT_SECRET={generated}\n")
    return generated.encode()


SECRET = _secret()


def issue(claims):
    now = int(time.time())
    payload = {**claims, "iat": now, "exp": now + TTL_SECONDS, "jti": secrets.token_urlsafe(12)}
    header = {"alg": ALGORITHM, "typ": "JWT"}
    encoded = ".".join((_b64(json.dumps(header, separators=(",", ":")).encode()),
                        _b64(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode())))
    signature = _b64(hmac.new(SECRET, encoded.encode(), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def verify(token):
    try:
        header, payload, signature = token.split(".")
        signed = f"{header}.{payload}"
        expected = _b64(hmac.new(SECRET, signed.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        parsed_header = json.loads(_decode(header))
        claims = json.loads(_decode(payload))
        if parsed_header != {"alg": ALGORITHM, "typ": "JWT"} or int(claims["exp"]) <= int(time.time()):
            return None
        required = ("user", "tenant", "tenant_name", "role", "csrf")
        return claims if all(claims.get(field) for field in required) else None
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, binascii.Error):
        return None


def cookie(token):
    return f"auditia={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={TTL_SECONDS}"


def clear_cookie():
    return "auditia=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"
