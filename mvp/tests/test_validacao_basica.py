import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("AUDITIA_JWT_SECRET", "test-only-validation-secret")

from backend import app, auth, config, storage


class ValidacaoBasicaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = storage.DB
        storage.DB = Path(self.tmp.name) / "validation.sqlite3"
        self.passwords = dict(storage.initialize())
        app.failures.clear()

    def tearDown(self):
        storage.DB = self.old_db
        self.tmp.cleanup()

    def request(self, method, path, cookie="", data=None):
        body = urlencode(data or {}).encode()
        env = {}
        setup_testing_defaults(env)
        env.update(REQUEST_METHOD=method, PATH_INFO=path, HTTP_HOST="127.0.0.1:5000",
                   HTTP_COOKIE=cookie, CONTENT_LENGTH=str(len(body)),
                   CONTENT_TYPE="application/x-www-form-urlencoded",
                   **{"wsgi.input": io.BytesIO(body)})
        response = {}

        def start(status, headers):
            response["status"] = int(status[:3])
            response["headers"] = dict(headers)

        payload = b"".join(app.app(env, start)).decode("utf-8")
        return response["status"], response["headers"], payload

    def test_analysis_is_blocked_without_calling_model(self):
        _, headers, _ = self.request("GET", "/entrar")
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        csrf = auth.verify(cookie.split("=", 1)[1])["csrf"]
        status, headers, _ = self.request("POST", "/entrar", cookie, {
            "csrf": csrf,
            "username": "admin-aurora",
            "password": self.passwords["admin-aurora"],
        })
        self.assertEqual(status, 303)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        csrf = auth.verify(cookie.split("=", 1)[1])["csrf"]

        with patch.object(config, "AI_ENABLED", False), \
             patch.object(app.parecer, "gerar") as generate:
            status, _, _ = self.request("POST", "/parecer", cookie, {
                "csrf": csrf,
                "case_id": "1",
            })

        self.assertEqual(status, 503)
        generate.assert_not_called()
