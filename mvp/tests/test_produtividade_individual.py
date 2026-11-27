"""Testes direcionados da apuração de produtividade individual (REQ-01)."""

import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import app, auth, consultas, storage


class ProdutividadeIndividualTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = storage.DB
        storage.DB = Path(self.tmp.name) / "test_prod.sqlite3"
        self.passwords = dict(storage.initialize())
        app.failures.clear()

    def tearDown(self):
        storage.DB = self.old_db
        self.tmp.cleanup()

    def login(self, username, accept=True):
        _, headers, _ = self.request("GET", "/entrar")
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        csrf = auth.verify(cookie.split("=", 1)[1])["csrf"]
        status, headers, _ = self.request("POST", "/entrar", cookie,
                                          {"csrf": csrf, "username": username,
                                           "password": self.passwords[username]})
        self.assertEqual(status, 303)
        new_cookie = headers["Set-Cookie"].split(";", 1)[0]
        identity = [new_cookie, auth.verify(new_cookie.split("=", 1)[1])["csrf"]]
        if accept:
            self.post("/termo", identity, aceite="1")
        return identity

    def post(self, path, identity, **fields):
        cookie, csrf = identity
        response = self.request("POST", path, cookie, {"csrf": csrf, **fields})
        if "Set-Cookie" in response[1]:
            identity[0] = response[1]["Set-Cookie"].split(";", 1)[0]
            claims = auth.verify(identity[0].split("=", 1)[1])
            if claims:
                identity[1] = claims["csrf"]
        return response

    def request(self, method, path, cookie="", data=None):
        body = urlencode(data or {}).encode()
        env = {}
        setup_testing_defaults(env)
        env.update(REQUEST_METHOD=method, PATH_INFO=path.split("?")[0],
                   QUERY_STRING=path.split("?", 1)[1] if "?" in path else "",
                   HTTP_HOST="127.0.0.1:8765", HTTP_COOKIE=cookie,
                   CONTENT_LENGTH=str(len(body)), **{"wsgi.input": io.BytesIO(body)})
        response = {}

        def start(status, headers):
            response["status"] = int(status[:3])
            response["headers"] = dict(headers)

        body_out = b"".join(app.app(env, start)).decode("utf-8")
        return response.get("status"), response.get("headers", {}), body_out

    def _criar_caso(self, conn, tenant, external_id):
        stamp = storage.now()
        cur = conn.execute("""INSERT INTO cases
            (tenant_id,source_system,external_id,procedure,area,narrative,
             clinical_question,source_updated_at,last_imported_at,created_at,updated_at)
            VALUES(?, 'SIGO', ?, 'PET-CT oncológico', 'Oncologia', 'Caso teste', 1, ?, ?, ?, ?)""",
            (tenant, external_id, stamp, stamp, stamp, stamp))
        return cur.lastrowid

    def test_auditor_a_conclui_2_e_auditor_b_conclui_1(self):
        with storage.connection() as conn:
            c1 = self._criar_caso(conn, "aurora", "GUIA-A1")
            c2 = self._criar_caso(conn, "aurora", "GUIA-A2")
            c3 = self._criar_caso(conn, "aurora", "GUIA-B1")
            stamp = storage.now()

            # Auditor A finaliza c1 e c2
            conn.execute("INSERT INTO case_workflow(tenant,case_id,status,actor,updated_at) VALUES('aurora',?,'finalizado','auditor-aurora',?)", (c1, stamp))
            conn.execute("INSERT INTO case_workflow(tenant,case_id,status,actor,updated_at) VALUES('aurora',?,'finalizado','auditor-aurora',?)", (c2, stamp))

            # Auditor B finaliza c3
            conn.execute("INSERT INTO case_workflow(tenant,case_id,status,actor,updated_at) VALUES('aurora',?,'finalizado','auditor-aurora-2',?)", (c3, stamp))

            prod_a = consultas.produtividade_individual(conn, "aurora", "auditor-aurora")
            prod_b = consultas.produtividade_individual(conn, "aurora", "auditor-aurora-2")

            self.assertEqual(prod_a, 2)
            self.assertEqual(prod_b, 1)

    def test_isolamento_entre_operadoras(self):
        with storage.connection() as conn:
            c_aurora = self._criar_caso(conn, "aurora", "GUIA-AURORA-1")
            c_horizonte = self._criar_caso(conn, "horizonte", "GUIA-HORIZONTE-1")
            stamp = storage.now()

            # Auditor com mesmo username em tenants diferentes (ou atuação em horizonte)
            conn.execute("INSERT INTO case_workflow(tenant,case_id,status,actor,updated_at) VALUES('aurora',?,'finalizado','auditor-aurora',?)", (c_aurora, stamp))
            conn.execute("INSERT INTO case_workflow(tenant,case_id,status,actor,updated_at) VALUES('horizonte',?,'finalizado','auditor-horizonte',?)", (c_horizonte, stamp))

            # Aurora deve ver apenas o caso de aurora
            self.assertEqual(consultas.produtividade_individual(conn, "aurora", "auditor-aurora"), 1)
            self.assertEqual(consultas.produtividade_individual(conn, "horizonte", "auditor-aurora"), 0)
            self.assertEqual(consultas.produtividade_individual(conn, "horizonte", "auditor-horizonte"), 1)

    def test_ausencia_de_dupla_contagem_entre_workflow_e_reviews(self):
        with storage.connection() as conn:
            cid = self._criar_caso(conn, "aurora", "GUIA-DUP-1")
            stamp = storage.now()

            # Cria um run
            cur_run = conn.execute("""INSERT INTO runs
                (tenant_id,case_id,actor,created_at,input_snapshot,checklist_version_id,checklist_snapshot,reference_version_id,reference_snapshot,original_output)
                VALUES('aurora',?,'auditor-aurora',?,'{}',1,'{}',1,'{}','{}')""", (cid, stamp))
            rid = cur_run.lastrowid

            # Cria uma revisão conclusiva para o mesmo caso
            conn.execute("""INSERT INTO reviews
                (tenant_id,run_id,actor,created_at,stage,position,note,corrected_suggestion)
                VALUES('aurora',?,'auditor-aurora',?,'conclusao','Concordo','OK','')""", (rid, stamp))

            # Cria finalização no case_workflow para o mesmo caso
            conn.execute("""INSERT INTO case_workflow(tenant,case_id,status,run_id,actor,updated_at)
                VALUES('aurora',?,'finalizado',?,'auditor-aurora',?)""", (cid, rid, stamp))

            # Deve contar exatamente 1, sem duplicar
            self.assertEqual(consultas.produtividade_individual(conn, "aurora", "auditor-aurora"), 1)

    def test_auditor_sem_conclusoes_retorna_zero(self):
        with storage.connection() as conn:
            cid = self._criar_caso(conn, "aurora", "GUIA-OUTRO-1")
            stamp = storage.now()
            conn.execute("INSERT INTO case_workflow(tenant,case_id,status,actor,updated_at) VALUES('aurora',?,'finalizado','outro-auditor',?)", (cid, stamp))

            # Auditor novo sem nenhuma conclusão
            self.assertEqual(consultas.produtividade_individual(conn, "aurora", "auditor-sem-conclusoes"), 0)
            self.assertEqual(consultas.produtividade_individual(conn, "aurora", ""), 0)
            self.assertEqual(consultas.produtividade_individual(conn, "", "qualquer"), 0)

    def test_casos_nao_finalizados_nao_integram_produtividade(self):
        with storage.connection() as conn:
            c_ativo = self._criar_caso(conn, "aurora", "GUIA-ATIVA-1")
            c_gerencia = self._criar_caso(conn, "aurora", "GUIA-GERENCIA-1")
            c_so_review = self._criar_caso(conn, "aurora", "GUIA-SO-REVIEW-1")
            stamp = storage.now()

            # Caso ativo em workflow
            conn.execute("INSERT INTO case_workflow(tenant,case_id,status,actor,updated_at) VALUES('aurora',?,'ativo','auditor-aurora',?)", (c_ativo, stamp))

            # Caso em gerência em workflow
            conn.execute("INSERT INTO case_workflow(tenant,case_id,status,actor,updated_at) VALUES('aurora',?,'gerencia','auditor-aurora',?)", (c_gerencia, stamp))

            # Caso com revisão de conclusão mas workflow não finalizado (ainda na fila)
            cur_run = conn.execute("""INSERT INTO runs
                (tenant_id,case_id,actor,created_at,input_snapshot,checklist_version_id,checklist_snapshot,reference_version_id,reference_snapshot,original_output)
                VALUES('aurora',?,'auditor-aurora',?,'{}',1,'{}',1,'{}','{}')""", (c_so_review, stamp))
            rid = cur_run.lastrowid
            conn.execute("""INSERT INTO reviews
                (tenant_id,run_id,actor,created_at,stage,position,note,corrected_suggestion)
                VALUES('aurora',?,'auditor-aurora',?,'conclusao','Concordo','OK','')""", (rid, stamp))

            # Nenhum destes casos está 'finalizado', portanto produtividade deve ser 0
            self.assertEqual(consultas.produtividade_individual(conn, "aurora", "auditor-aurora"), 0)

    def test_card_concluidas_renderiza_produtividade_individual_no_dashboard(self):
        from backend import config
        with patch.object(config, "BETA", False):
            identity = self.login("auditor-aurora")

            # Cria e finaliza um caso para o auditor-aurora
            with storage.connection() as conn:
                cid = self._criar_caso(conn, "aurora", "GUIA-PROD-CARD-1")
                stamp = storage.now()
                conn.execute("INSERT INTO case_workflow(tenant,case_id,status,actor,updated_at) VALUES('aurora',?,'finalizado','auditor-aurora',?)", (cid, stamp))

            status, _, html = self.request("GET", "/", identity[0])
            self.assertEqual(status, 200)
            self.assertIn('<span class="kpi-label">Concluídas</span><span class="kpi-num">01</span>', html)


if __name__ == "__main__":
    unittest.main()
