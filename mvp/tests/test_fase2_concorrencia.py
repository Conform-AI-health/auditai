"""Testes direcionados da Fase 2 (REQ-07 a REQ-10):
- Assunção atômica de guias pelo auditor autenticado
- Concorrência de dois auditores com conexões independentes
- Isolamento estrito entre operadoras
- Expiração (60 min), renovação de trava e devolução voluntária à fila
- Rejeição de submissão/edição/finalização por auditor sem posse válida
- Preservação integral de rascunhos, histórico e pareceres
"""

import os
import sys
import tempfile
import time
import io
import urllib.parse
import sqlite3
import unittest
from pathlib import Path
from wsgiref.util import setup_testing_defaults

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import storage, app, auth, consultas

class TestFase2Concorrencia(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_fase2.sqlite3"
        self.orig_db = storage.DB
        storage.DB = self.db_path
        self.credentials = dict(storage.initialize(seed_demo_cases=True))
        app.failures.clear()
        app._sync_locks.clear()

    def tearDown(self):
        storage.DB = self.orig_db
        self.temp_dir.cleanup()

    def _login(self, username, password):
        status, headers, _ = self.request("GET", "/entrar")
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        token = cookie.split("=", 1)[1]
        csrf = auth.verify(token)["csrf"]
        status, headers, _ = self.request("POST", "/entrar", cookie, {"csrf": csrf, "username": username, "password": password})
        self.assertEqual(status, 303)
        new_cookie = headers["Set-Cookie"].split(";", 1)[0]
        new_token = new_cookie.split("=", 1)[1]
        new_csrf = auth.verify(new_token)["csrf"]
        identity = [new_cookie, new_csrf]
        if not username.startswith("admin"):
            status_termo, headers_termo, _ = self.request("POST", "/termo", identity[0], {"csrf": identity[1], "aceite": "1"})
            if "Set-Cookie" in headers_termo:
                identity[0] = headers_termo["Set-Cookie"].split(";", 1)[0]
                identity[1] = auth.verify(identity[0].split("=", 1)[1])["csrf"]
        return identity

    def request(self, method, path, cookie="", data=None):
        body = urllib.parse.urlencode(data or {}).encode()
        env = {}
        setup_testing_defaults(env)
        env.update(
            REQUEST_METHOD=method,
            PATH_INFO=path.split("?")[0],
            QUERY_STRING=path.split("?", 1)[1] if "?" in path else "",
            HTTP_HOST="127.0.0.1:8765",
            HTTP_COOKIE=cookie,
            CONTENT_LENGTH=str(len(body)),
            **{"wsgi.input": io.BytesIO(body)}
        )
        response = {}
        def start_response(status, response_headers, exc_info=None):
            response["status"] = int(status.split()[0])
            response["headers"] = dict(response_headers)
            response["raw_status"] = status
        result = app.app(env, start_response)
        return response["status"], response["headers"], b"".join(result)

    def test_assuncao_simultanea_conexoes_independentes(self):
        """Dois auditores tentando assumir simultaneamente a mesma guia com conexões independentes."""
        tenant = "aurora"
        with storage.connection() as conn:
            case = conn.execute("SELECT id FROM cases WHERE tenant_id=?", (tenant,)).fetchone()
            cid = case["id"]

        # Conexões independentes para simular processos/threads simultâneos
        conn1 = sqlite3.connect(self.db_path)
        conn1.row_factory = sqlite3.Row
        conn2 = sqlite3.connect(self.db_path)
        conn2.row_factory = sqlite3.Row

        try:
            # Auditor 1 tenta assumir
            res1 = storage.assumir_caso(conn1, tenant, cid, "auditor-aurora-1", role="auditor")
            conn1.commit()
            self.assertTrue(res1)

            # Auditor 2 tenta assumir a mesma guia imediatamente
            res2 = storage.assumir_caso(conn2, tenant, cid, "auditor-aurora-2", role="auditor")
            conn2.commit()
            self.assertFalse(res2)

            # Verifica quem é o responsável ativo
            c = conn1.execute("SELECT assumido_por FROM cases WHERE id=?", (cid,)).fetchone()
            self.assertEqual(c["assumido_por"], "auditor-aurora-1")
        finally:
            conn1.close()
            conn2.close()

    def test_isolamento_entre_operadoras_na_assuncao_e_trava(self):
        """Auditor de uma operadora não pode assumir ou interferir em caso de outra operadora."""
        with storage.connection() as conn:
            c_horizonte = conn.execute("SELECT id FROM cases WHERE tenant_id='horizonte'").fetchone()
            cid_h = c_horizonte["id"]

            # Auditor da Aurora tentando assumir caso da Horizonte
            res = storage.assumir_caso(conn, "aurora", cid_h, "auditor-aurora", role="auditor")
            self.assertFalse(res)

            # Guia da Horizonte permanece livre
            c_check = conn.execute("SELECT assumido_por FROM cases WHERE id=?", (cid_h,)).fetchone()
            self.assertIsNone(c_check["assumido_por"])

    def test_expiracao_60_min_e_renovacao_de_trava(self):
        """Trava expira após 60 min de inatividade e pode ser renovada mediante atividade clínica."""
        tenant = "aurora"
        with storage.connection() as conn:
            case = conn.execute("SELECT id FROM cases WHERE tenant_id=?", (tenant,)).fetchone()
            cid = case["id"]

            # Assumir caso
            self.assertTrue(storage.assumir_caso(conn, tenant, cid, "auditor-1", role="auditor"))
            self.assertTrue(storage.verificar_posse_trava(conn, tenant, cid, "auditor-1"))

            # Simular inatividade retroativa de 61 minutos
            passado = "2026-03-01T10:00:00"
            conn.execute("UPDATE cases SET trava_expira_em=? WHERE id=?", (passado, cid))
            conn.commit()

            # Posse deve ser considerada expirada/inválida
            self.assertFalse(storage.verificar_posse_trava(conn, tenant, cid, "auditor-1"))

            # Outro médico agora consegue assumir normalmente
            self.assertTrue(storage.assumir_caso(conn, tenant, cid, "auditor-2", role="auditor"))
            c_novo = conn.execute("SELECT assumido_por, responsavel_anterior FROM cases WHERE id=?", (cid,)).fetchone()
            self.assertEqual(c_novo["assumido_por"], "auditor-2")
            self.assertEqual(c_novo["responsavel_anterior"], "auditor-1")

            # Auditor 2 renova a trava
            self.assertTrue(storage.renovar_trava_caso(conn, tenant, cid, "auditor-2"))

    def test_devolucao_voluntaria_a_fila(self):
        """Devolução voluntária libera a trava e preserva histórico."""
        tenant = "aurora"
        with storage.connection() as conn:
            case = conn.execute("SELECT id FROM cases WHERE tenant_id=?", (tenant,)).fetchone()
            cid = case["id"]

            storage.assumir_caso(conn, tenant, cid, "auditor-1", role="auditor")
            self.assertTrue(storage.verificar_posse_trava(conn, tenant, cid, "auditor-1"))

            # Tentativa de auditor não-responsável devolver é rejeitada
            self.assertFalse(storage.devolver_caso_fila(conn, tenant, cid, "auditor-outro", role="auditor"))

            # Auditor responsável devolve
            self.assertTrue(storage.devolver_caso_fila(conn, tenant, cid, "auditor-1", role="auditor", motivo="Pausa médica"))

            c = conn.execute("SELECT assumido_por, responsavel_anterior FROM cases WHERE id=?", (cid,)).fetchone()
            self.assertIsNone(c["assumido_por"])
            self.assertEqual(c["responsavel_anterior"], "auditor-1")

    def test_rejeicao_de_submissao_sem_posse_valida(self):
        """Tentativa de finalizar caso por auditor sem posse válida da trava é rejeitada (403/409)."""
        tenant = "aurora"
        # Cria um segundo auditor em aurora
        with storage.connection() as conn:
            salt = b"1234567890123456"
            pwd_hash = storage.digest("SenhaForte123!", salt)
            conn.execute("INSERT OR REPLACE INTO users VALUES(?,?,?,?,?,?)",
                         ("auditor-aurora-2", tenant, "auditor", salt, pwd_hash, storage.now()))
            conn.commit()

        # Auditor 1 faz login e assume o caso
        identity1 = self._login(f"auditor-{tenant}", self.credentials[f"auditor-{tenant}"])
        cookie1, csrf1 = identity1

        with storage.connection() as conn:
            case = conn.execute("SELECT id FROM cases WHERE tenant_id=?", (tenant,)).fetchone()
            cid = case["id"]
            storage.assumir_caso(conn, tenant, cid, f"auditor-{tenant}", role="auditor")

        # Auditor 2 faz login e tenta finalizar o caso
        identity2 = self._login("auditor-aurora-2", "SenhaForte123!")
        cookie2, csrf2 = identity2

        status, headers, body = self.request("POST", "/caso/finalizar", cookie2, {"case_id": cid, "csrf": csrf2})
        self.assertEqual(status, 403)
        self.assertIn(b"Trava", body)

    def test_preservacao_de_rascunhos_e_historico(self):
        """Ao devolver ou expirar a trava, rascunhos de minutas e revisões anteriores são rigorosamente preservados."""
        tenant = "aurora"
        with storage.connection() as conn:
            case = conn.execute("SELECT id FROM cases WHERE tenant_id=?", (tenant,)).fetchone()
            cid = case["id"]
            storage.assumir_caso(conn, tenant, cid, "auditor-1", role="auditor")

            # Salva minuta
            draft_id = storage.save_regulatory_draft(
                conn, tenant, cid, "AUTOMATICO", "Minuta Inicial", "RN 465",
                "Quadro clínico", "Critérios", "Favorável", None,
                "Texto do rascunho preservado", "auditor-1", status="RASCUNHO_IA"
            )

            # Devolve caso à fila
            storage.devolver_caso_fila(conn, tenant, cid, "auditor-1", role="auditor")

            # Auditor 2 assume
            storage.assumir_caso(conn, tenant, cid, "auditor-2", role="auditor")

            # Minuta permanece íntegra
            drafts = storage.get_regulatory_drafts(conn, tenant, cid)
            self.assertEqual(len(drafts), 1)
            self.assertEqual(drafts[0]["draft_text"], "Texto do rascunho preservado")
            self.assertEqual(drafts[0]["actor_created"], "auditor-1")

if __name__ == "__main__":
    unittest.main()
