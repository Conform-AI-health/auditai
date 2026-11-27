import unittest
import os
import sys
import tempfile
import time
import io
import urllib.parse
from pathlib import Path
from wsgiref.util import setup_testing_defaults

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import storage, sigo_simulado, tuss_rol, consultas, app, auth

class TestFase1Integracao(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_fase1.sqlite3"
        self.orig_db = storage.DB
        storage.DB = self.db_path
        self.credentials = dict(storage.initialize())
        app.failures.clear()
        app._sync_locks.clear()

    def tearDown(self):
        storage.DB = self.orig_db
        self.temp_dir.cleanup()

    def _login(self, username, password):
        # 1. GET /entrar
        status, headers, _ = self.request("GET", "/entrar")
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        token = cookie.split("=", 1)[1]
        csrf = auth.verify(token)["csrf"]
        # 2. POST /entrar
        status, headers, _ = self.request("POST", "/entrar", cookie, {"csrf": csrf, "username": username, "password": password})
        self.assertEqual(status, 303)
        new_cookie = headers["Set-Cookie"].split(";", 1)[0]
        new_token = new_cookie.split("=", 1)[1]
        new_csrf = auth.verify(new_token)["csrf"]
        identity = [new_cookie, new_csrf]
        
        # 3. Aceita o termo se for auditor
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

    def test_req04_ingestao_amm_e_rejeicao_aud_e_amop_novo(self):
        """Novo caso só entra por AMM. AUD é rejeitado. AMOP novo é rejeitado."""
        tenant = "aurora"
        now_str = storage.now()
        with storage.connection() as conn:
            # 1. Registro em AUD deve ser ignorado
            reg_aud = [{
                "tenant_id": tenant,
                "source_system": "SIGO",
                "external_id": "SIGO-AUD-01",
                "beneficiary_code": "BEN-AUD",
                "procedure": "PET-CT oncológico",
                "area": "Oncologia",
                "narrative": "PET-CT oncológico",
                "clinical_question": True,
                "localizacao_sigo": "AUD",
                "fila": "AUD",
                "source_updated_at": now_str,
                "documents": []
            }]
            ins, dup, docs = storage.import_records(conn, tenant, reg_aud)
            self.assertEqual(ins, 0)

            c_aud = conn.execute("SELECT * FROM cases WHERE tenant_id = ? AND external_id = ?", (tenant, "SIGO-AUD-01")).fetchone()
            self.assertIsNone(c_aud)

            # 2. Novo caso que chega exclusivamente por AMOP deve ser rejeitado
            reg_amop_novo = [{
                "tenant_id": tenant,
                "source_system": "SIGO",
                "external_id": "SIGO-AMOP-01",
                "beneficiary_code": "BEN-AMOP",
                "procedure": "PET-CT oncológico",
                "area": "Oncologia",
                "narrative": "PET-CT oncológico",
                "clinical_question": True,
                "localizacao_sigo": "AMOP",
                "fila": "AMOP",
                "source_updated_at": now_str,
                "documents": []
            }]
            ins_amop, _, _ = storage.import_records(conn, tenant, reg_amop_novo)
            self.assertEqual(ins_amop, 0)

            c_amop = conn.execute("SELECT * FROM cases WHERE tenant_id = ? AND external_id = ?", (tenant, "SIGO-AMOP-01")).fetchone()
            self.assertIsNone(c_amop)

            # 3. Novo caso via AMM é aceito
            reg_amm = [{
                "tenant_id": tenant,
                "source_system": "SIGO",
                "external_id": "SIGO-AMM-01",
                "beneficiary_code": "BEN-AMM",
                "procedure": "PET-CT oncológico",
                "area": "Oncologia",
                "narrative": "PET-CT oncológico",
                "clinical_question": True,
                "localizacao_sigo": "AMM",
                "fila": "AMM",
                "source_updated_at": now_str,
                "documents": []
            }]
            ins_amm, _, _ = storage.import_records(conn, tenant, reg_amm)
            self.assertEqual(ins_amm, 1)

            c_amm = conn.execute("SELECT * FROM cases WHERE tenant_id = ? AND external_id = ?", (tenant, "SIGO-AMM-01")).fetchone()
            self.assertIsNotNone(c_amm)
            self.assertEqual(c_amm["localizacao_sigo"], "AMM")

    def test_req12_consolidacao_registro_unico_amm_amop(self):
        """Caso existente que transita de AMM para AMOP atualiza localização sem duplicar registro."""
        tenant = "aurora"
        now_str = storage.now()
        with storage.connection() as conn:
            # Inicia em AMM
            reg_amm = [{
                "tenant_id": tenant,
                "source_system": "SIGO",
                "external_id": "SIGO-TRANS-01",
                "beneficiary_code": "BEN-01",
                "procedure": "PET-CT oncológico inicial",
                "area": "Oncologia",
                "narrative": "PET-CT oncológico inicial",
                "clinical_question": True,
                "localizacao_sigo": "AMM",
                "fila": "AMM",
                "source_updated_at": now_str,
                "documents": []
            }]
            storage.import_records(conn, tenant, reg_amm)
            case_id_orig = conn.execute("SELECT id, localizacao_sigo FROM cases WHERE tenant_id = ? AND external_id = ?", (tenant, "SIGO-TRANS-01")).fetchone()
            self.assertEqual(case_id_orig["localizacao_sigo"], "AMM")

            # Transita para AMOP
            reg_amop = [{
                "tenant_id": tenant,
                "source_system": "SIGO",
                "external_id": "SIGO-TRANS-01",
                "beneficiary_code": "BEN-01",
                "procedure": "PET-CT oncológico inicial",
                "area": "Oncologia",
                "narrative": "PET-CT oncológico inicial",
                "clinical_question": True,
                "localizacao_sigo": "AMOP",
                "fila": "AMOP",
                "source_updated_at": now_str,
                "documents": []
            }]
            storage.import_records(conn, tenant, reg_amop)

            # Verifica unicidade
            rows = conn.execute("SELECT id, localizacao_sigo FROM cases WHERE tenant_id = ? AND external_id = ?", (tenant, "SIGO-TRANS-01")).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["id"], case_id_orig["id"])
            self.assertEqual(rows[0]["localizacao_sigo"], "AMOP")

    def test_req16_1_saida_fila_quando_ausente_amm_e_amop(self):
        """Ausência bilateral em AMM e AMOP marca caso como removido e o retira de casos_da_operadora()."""
        tenant = "aurora"
        with storage.connection() as conn:
            # Sincroniza conjunto sintético inicial (4 casos)
            sigo_simulado.sincronizar_sigo_simulado(conn, tenant, actor="sistema")
            # 4 casos demonstrativos ativos sincronizados do SIGO
            casos_ativos = consultas.casos_da_operadora(conn, tenant)
            self.assertEqual(len(casos_ativos), 4)

            # Sincroniza lote contendo apenas o caso 1 e 2 do SIGO
            casos_orig = sigo_simulado.gerar_lote_sigo_sintetico(tenant)
            lote_reduzido = [casos_orig[0], casos_orig[1]]
            sigo_simulado.sincronizar_sigo_simulado(conn, tenant, actor="sistema", registros_custom=lote_reduzido)

            # Casos 3 e 4 devem ter sido marcados com removido_origem_em
            c3 = conn.execute("SELECT removido_origem_em FROM cases WHERE tenant_id = ? AND external_id = ?", (tenant, casos_orig[2]["external_id"])).fetchone()
            self.assertIsNotNone(c3["removido_origem_em"])
            c4 = conn.execute("SELECT removido_origem_em FROM cases WHERE tenant_id = ? AND external_id = ?", (tenant, casos_orig[3]["external_id"])).fetchone()
            self.assertIsNotNone(c4["removido_origem_em"])

            # Fila ativa não deve conter c3 e c4
            casos_apos = consultas.casos_da_operadora(conn, tenant)
            ids_apos = [c["external_id"] for c in casos_apos]
            self.assertIn(casos_orig[0]["external_id"], ids_apos)
            self.assertIn(casos_orig[1]["external_id"], ids_apos)
            self.assertNotIn(casos_orig[2]["external_id"], ids_apos)
            self.assertNotIn(casos_orig[3]["external_id"], ids_apos)

    def test_req16_2_reativacao_cumulativa_e_divergencia(self):
        """Reativação requer os 5 critérios cumulativos (incluindo hash dos dados do pedido)."""
        tenant = "aurora"
        now_str = storage.now()
        reg = [{
            "tenant_id": tenant,
            "source_system": "SIGO",
            "external_id": "SIGO-REACT-01",
            "beneficiary_code": "BEN-R1",
            "procedure": "PET-CT nódulo pulmonar",
            "area": "Oncologia",
            "narrative": "PET-CT nódulo pulmonar",
            "clinical_question": True,
            "data_protocolo_operadora": "2026-03-01",
            "localizacao_sigo": "AMM",
            "fila": "AMM",
            "source_updated_at": now_str,
            "documents": []
        }]
        with storage.connection() as conn:
            storage.import_records(conn, tenant, reg)
            c = conn.execute("SELECT id FROM cases WHERE tenant_id = ? AND external_id = ?", (tenant, "SIGO-REACT-01")).fetchone()
            case_id = c["id"]

            # Marca como removido
            conn.execute("UPDATE cases SET removido_origem_em = '2026-03-02 10:00:00' WHERE id = ?", (case_id,))
            conn.commit()

            # Tentativa 1: Reativação com dados idênticos -> Sucesso, removido_origem_em é limpo
            storage.import_records(conn, tenant, reg)
            c_check1 = conn.execute("SELECT removido_origem_em FROM cases WHERE id = ?", (case_id,)).fetchone()
            self.assertIsNone(c_check1["removido_origem_em"])

            # Marca como removido novamente
            conn.execute("UPDATE cases SET removido_origem_em = '2026-03-03 10:00:00' WHERE id = ?", (case_id,))
            conn.commit()

            # Tentativa 2: Reativação com dados divergentes (narrativa clínica alterada sem ser mesmo pedido)
            reg_divergente = [{
                "tenant_id": tenant,
                "source_system": "SIGO",
                "external_id": "SIGO-REACT-01",
                "beneficiary_code": "BEN-R1",
                "procedure": "PET-CT nódulo pulmonar",
                "area": "Oncologia",
                "narrative": "PET-CT controle pós quimioterapia linfoma", # diferente
                "clinical_question": True,
                "data_protocolo_operadora": "2026-03-01",
                "localizacao_sigo": "AMM",
                "fila": "AMM",
                "source_updated_at": now_str,
                "documents": []
            }]
            storage.import_records(conn, tenant, reg_divergente)
            c_check2 = conn.execute("SELECT removido_origem_em, divergence_detected FROM cases WHERE id = ?", (case_id,)).fetchone()
            # Não pode ter sido reativado!
            self.assertIsNotNone(c_check2["removido_origem_em"])
            self.assertEqual(int(c_check2["divergence_detected"]), 1)

    def test_req02_triagem_variantes_petct(self):
        """Variantes de PET-CT são identificadas na triagem mesmo com grafias diversas."""
        tenant = "aurora"
        with storage.connection() as conn:
            # 1. Com código oficial 40708128 (mapeado na DUT 60)
            case1 = {
                "tuss_code": "40708128",
                "guide_received_at": "2026-11-01",
                "procedure": "PET-CT",
                "narrative": "Solicito pet scan corpo inteiro",
                "associated_tuss_codes": "[]"
            }
            res1 = tuss_rol.triagem(conn, tenant, case1)
            self.assertIn("category", res1)
            self.assertNotEqual(res1["status"], "variante_textual_sem_codigo")

            # 2. Sem código oficial, apenas texto 'pet-tc' com indicação oncológica sugerindo 40708128
            case2 = {
                "tuss_code": "",
                "guide_received_at": "2026-11-01",
                "procedure": "Exame de pet-tc",
                "narrative": "Indicacao de pet-tc para estadiamento de tumor",
                "associated_tuss_codes": "[]"
            }
            res2 = tuss_rol.triagem(conn, tenant, case2)
            self.assertEqual(res2["code"], "40708128")
            self.assertIn("category", res2)

            # 3. Termo variante sem código e sem termo oncológico/neuro/cardio
            case3 = {
                "tuss_code": "",
                "guide_received_at": "2026-11-01",
                "procedure": "Tomografia por emissao de positrons",
                "narrative": "Exame diagnostico especializado",
                "associated_tuss_codes": "[]"
            }
            res3 = tuss_rol.triagem(conn, tenant, case3)
            self.assertEqual(res3["status"], "variante_textual_sem_codigo")

    def test_req12_1_bloqueio_concorrencia_sincronizacao(self):
        """Duas requisições de sincronização concorrentes para o mesmo tenant disparam 409 Conflict."""
        tenant = "aurora"
        identity = self._login(f"auditor-{tenant}", self.credentials[f"auditor-{tenant}"])
        cookie, csrf = identity

        app._sync_locks[f"{tenant}:sigo"] = time.time() # Lock ativo

        status, headers, body = self.request("POST", "/sincronizar", cookie, {"connector": "sigo", "csrf": csrf})
        self.assertEqual(status, 409)
        self.assertIn(b"Sincronizacao em andamento", body.replace(b"\xc3\xa7\xc3\xa3", b"ca"))

        # Libera lock
        del app._sync_locks[f"{tenant}:sigo"]
        status_ok, headers_ok, body_ok = self.request("POST", "/sincronizar", cookie, {"connector": "sigo", "csrf": csrf})
        self.assertIn(status_ok, [303, 200])

    def test_req11_3_preservacao_binarios_e_hash(self):
        """Verifica se os documentos binários (PDFs, imagens) mantêm SHA-256 e bytes íntegros."""
        tenant = "aurora"
        with storage.connection() as conn:
            sigo_simulado.sincronizar_sigo_simulado(conn, tenant, actor="sistema")
            docs = conn.execute("SELECT id, name, mime_type, content_blob, source_sha256 FROM documents WHERE tenant_id=?", (tenant,)).fetchall()
            self.assertTrue(len(docs) > 0)
            
            docs_com_blob = [d for d in docs if d["content_blob"] is not None]
            self.assertTrue(len(docs_com_blob) > 0)
            for d in docs_com_blob:
                import hashlib
                calc_sha = hashlib.sha256(d["content_blob"]).hexdigest()
                self.assertEqual(calc_sha, d["source_sha256"])

if __name__ == "__main__":
    unittest.main()
