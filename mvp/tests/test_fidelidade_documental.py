"""Suíte de testes de Fidelidade Documental e MVP Documental (Fase 1 — Alternativa C).
Verifica a preservação de bytes originais, integridade binária, transcrição integral,
segurança na visualização inline, isolamento multi-tenant e integridade da DUT 60 e do SLA.
"""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import app, auth, config, consultas, criterios_dut, datas, homologacao, leitura, storage
from PIL import Image, ImageDraw, ImageFont
import pymupdf


class FidelidadeDocumentalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = storage.DB
        storage.DB = Path(self.tmp.name) / "test_mvp_doc.sqlite3"
        self.passwords = dict(storage.initialize())
        app.failures.clear()

    def tearDown(self):
        storage.DB = self.old_db
        self.tmp.cleanup()

    def fixture_imagem(self, fmt="PNG", texto="Pedido médico sintético: PET-CT para estadiamento oncológico."):
        im = Image.new("RGB", (1200, 300), "white")
        try:
            font = ImageFont.truetype("arial.ttf", 36)
        except OSError:
            try:
                font = ImageFont.truetype("DejaVuSans.ttf", 36)
            except OSError:
                font = ImageFont.load_default()
        ImageDraw.Draw(im).multiline_text((30, 30), texto, font=font, fill="black")
        out = io.BytesIO()
        im.save(out, fmt)
        return out.getvalue()

    def fixture_pdf_digital(self, texto="Pedido médico sintético com indicação clínica e justificativa formal."):
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((40, 60), texto)
            return pdf.tobytes()

    def fixture_pdf_digitalizado(self, texto="Laudo anatomopatológico digitalizado via scanner hospitalar."):
        with pymupdf.open() as pdf:
            p = pdf.new_page(width=800, height=400)
            p.insert_image(p.rect, stream=self.fixture_imagem("PNG", texto))
            return pdf.tobytes()

    def request(self, method, path, cookie="", data=None, api=False):
        body = urlencode(data or {}).encode() if data else b""
        env = {}
        setup_testing_defaults(env)
        env.update(REQUEST_METHOD=method, PATH_INFO=path.split("?")[0],
                   QUERY_STRING=path.split("?", 1)[1] if "?" in path else "",
                   HTTP_HOST="127.0.0.1:8765", HTTP_COOKIE=cookie,
                   CONTENT_LENGTH=str(len(body)), **{"wsgi.input": io.BytesIO(body)})
        if api:
            env["HTTP_X_REQUESTED_WITH"] = "XMLHttpRequest"
        response = {}

        def start(status, headers):
            response["status"] = int(status[:3])
            response["headers"] = dict(headers)

        raw = b"".join(app.app(env, start))
        ctype = response.get("headers", {}).get("Content-Type", "")
        if "application/pdf" in ctype or "image/" in ctype or "application/octet-stream" in ctype:
            result = raw
        else:
            try:
                result = raw.decode("utf-8")
            except UnicodeDecodeError:
                result = raw
        return response.get("status", 500), response.get("headers", {}), result

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
            body = urlencode({"csrf": identity[1], "aceite": "1"}).encode()
            env = {}
            setup_testing_defaults(env)
            env.update(REQUEST_METHOD="POST", PATH_INFO="/termo", HTTP_HOST="127.0.0.1:8765",
                       HTTP_COOKIE=identity[0], CONTENT_LENGTH=str(len(body)),
                       CONTENT_TYPE="application/x-www-form-urlencoded", **{"wsgi.input": io.BytesIO(body)})
            response = {}
            def start(s, h):
                response["status"] = int(s[:3])
                response["headers"] = dict(h)
            b"".join(app.app(env, start))
            if "Set-Cookie" in response["headers"]:
                identity[0] = response["headers"]["Set-Cookie"].split(";", 1)[0]
        return identity

    def criar_caso_com_documento(self, tenant="aurora", blob=None, filename="pedido.pdf",
                                  mime="application/pdf", text=None, ext_method=None,
                                  verification_status="NAO_CONFERIDO"):
        stamp = storage.now()
        with storage.connection() as conn:
            cur = conn.execute("""INSERT INTO cases
                (tenant_id,source_system,external_id,procedure,area,narrative,clinical_question,
                 source_updated_at,last_imported_at,created_at,updated_at,guide_received_at,
                 beneficiary_code,tuss_code,data_protocolo_operadora)
                VALUES(?, 'TESTE_DOC', ?, 'PET-CT oncológico', 'Oncologia', 'Caso para validação documental',
                       1, ?, ?, ?, ?, ?, ?, '40708128', ?)""",
                (tenant, f"GUIA-{stamp[-6:]}", stamp, stamp, stamp, stamp,
                 stamp, "BENEF-001", stamp))
            cid = cur.lastrowid
            sha = hashlib.sha256(blob).hexdigest() if blob else None
            doc_cur = conn.execute("""INSERT INTO documents
                (tenant_id,case_id,source_system,external_id,kind,name,source_updated_at,
                 last_imported_at,mime_type,content_blob,content_text,source_sha256,
                 extraction_method,verification_status)
                VALUES(?,?, 'TESTE_DOC', ?,'pedido_medico',?,?,?,?,?,?,?,?,?)""",
                (tenant, cid, f"DOC-{stamp[-6:]}", filename, stamp, stamp,
                 mime, blob, text, sha, ext_method, verification_status))
            did = doc_cur.lastrowid
        return cid, did

    def test_01_importacao_pdf_digital_preservacao_blob(self):
        """Cenário 1: Importação de PDF digital sintético e preservação de blob."""
        texto_original = "Indicação clínica: Linfoma Hodgkin com biópsia comprovada."
        raw_pdf = self.fixture_pdf_digital(texto_original)
        record = {
            "tenant_id": "aurora",
            "source_system": "TESTE",
            "external_id": "GUIA-PDF-DIGITAL",
            "procedure": "PET-CT oncológico",
            "area": "Oncologia",
            "narrative": "Avaliação de PDF digital",
            "clinical_question": True,
            "source_updated_at": storage.now(),
            "documents": [{
                "external_id": "DOC-PDF-DIGITAL",
                "kind": "pedido_medico",
                "name": "pedido_digital.pdf",
                "source_updated_at": storage.now(),
                "content_blob": raw_pdf,
                "mime_type": "application/pdf",
            }],
        }
        with storage.connection() as conn:
            storage.import_records(conn, "aurora", [record])
            doc = conn.execute("SELECT * FROM documents WHERE external_id='DOC-PDF-DIGITAL'").fetchone()
            self.assertIsNotNone(doc)
            self.assertEqual(doc["content_blob"], raw_pdf)
            self.assertEqual(doc["mime_type"], "application/pdf")
            self.assertEqual(doc["extraction_method"], "PDF_DIGITAL")
            self.assertIn("Linfoma Hodgkin", doc["content_text"])

    def test_02_importacao_pdf_digitalizado_execucao_ocr(self):
        """Cenário 2: Importação de PDF digitalizado sintético e execução de OCR."""
        if not (leitura.localizar_tesseract() and leitura.obter_tessdata_dir()):
            self.skipTest("Tesseract OCR não disponível no ambiente")
        raw_pdf_scan = self.fixture_pdf_digitalizado("Exame de biópsia digitalizado hospitalar.")
        record = {
            "tenant_id": "aurora",
            "source_system": "TESTE",
            "external_id": "GUIA-PDF-SCAN",
            "procedure": "PET-CT oncológico",
            "area": "Oncologia",
            "narrative": "Avaliação de PDF scan",
            "clinical_question": True,
            "source_updated_at": storage.now(),
            "documents": [{
                "external_id": "DOC-PDF-SCAN",
                "kind": "pedido_medico",
                "name": "pedido_digitalizado.pdf",
                "source_updated_at": storage.now(),
                "content_blob": raw_pdf_scan,
                "mime_type": "application/pdf",
            }],
        }
        with storage.connection() as conn:
            storage.import_records(conn, "aurora", [record])
            doc = conn.execute("SELECT * FROM documents WHERE external_id='DOC-PDF-SCAN'").fetchone()
            self.assertIsNotNone(doc)
            self.assertEqual(doc["content_blob"], raw_pdf_scan)
            self.assertEqual(doc["extraction_method"], "OCR_DIGITALIZADO")
            self.assertIn("biópsia", doc["content_text"].lower())

    def test_03_importacao_imagem_sintetica_execucao_ocr(self):
        """Cenário 3: Importação de imagem sintética (PNG/JPEG) e execução de OCR."""
        if not (leitura.localizar_tesseract() and leitura.obter_tessdata_dir()):
            self.skipTest("Tesseract OCR não disponível no ambiente")
        raw_img = self.fixture_imagem("PNG", "Relatório de imagem com indicação clínica oncológica.")
        record = {
            "tenant_id": "aurora",
            "source_system": "TESTE",
            "external_id": "GUIA-IMG",
            "procedure": "PET-CT oncológico",
            "area": "Oncologia",
            "narrative": "Avaliação de imagem",
            "clinical_question": True,
            "source_updated_at": storage.now(),
            "documents": [{
                "external_id": "DOC-IMG",
                "kind": "pedido_medico",
                "name": "pedido_print.png",
                "source_updated_at": storage.now(),
                "content_blob": raw_img,
                "mime_type": "image/png",
            }],
        }
        with storage.connection() as conn:
            storage.import_records(conn, "aurora", [record])
            doc = conn.execute("SELECT * FROM documents WHERE external_id='DOC-IMG'").fetchone()
            self.assertIsNotNone(doc)
            self.assertEqual(doc["content_blob"], raw_img)
            self.assertEqual(doc["extraction_method"], "OCR_IMAGEM")
            self.assertIn("indicação", doc["content_text"].lower())

    def test_04_extracao_e_preservacao_texto_integral(self):
        """Cenário 4: Extração e preservação do texto integral em content_text."""
        texto_completo = "Solicitação de PET-CT. Diagnóstico: Nódulo pulmonar 14mm espiculado. Justificativa clínica completa."
        raw_pdf = self.fixture_pdf_digital(texto_completo)
        cid, did = self.criar_caso_com_documento(tenant="aurora", blob=raw_pdf, text=texto_completo, ext_method="PDF_DIGITAL")
        with storage.connection() as conn:
            doc = storage.document_for(conn, "aurora", did)
            self.assertEqual(doc["content_text"], texto_completo)

    def test_05_integridade_binaria_blob_equiv_orig(self):
        """Cenário 5: Integridade binária exata (B_salvo == B_orig)."""
        raw_pdf = self.fixture_pdf_digital("Verificação rigorosa de integridade binária byte a byte.")
        cid, did = self.criar_caso_com_documento(tenant="aurora", blob=raw_pdf)
        with storage.connection() as conn:
            doc = storage.document_for(conn, "aurora", did)
            self.assertEqual(doc["content_blob"], raw_pdf)
            self.assertEqual(len(doc["content_blob"]), len(raw_pdf))

    def test_06_calculo_e_validacao_hash_sha256(self):
        """Cenário 6: Cálculo e validação do hash SHA-256."""
        raw_pdf = self.fixture_pdf_digital("Documento para validação de hash criptográfico SHA-256.")
        esperado_hash = hashlib.sha256(raw_pdf).hexdigest()
        cid, did = self.criar_caso_com_documento(tenant="aurora", blob=raw_pdf)
        with storage.connection() as conn:
            doc = storage.document_for(conn, "aurora", did)
            self.assertEqual(doc["source_sha256"], esperado_hash)

    def test_07_vinculacao_documento_guia_beneficiario(self):
        """Cenário 7: Vinculação correta entre documento, guia e caso."""
        raw_pdf = self.fixture_pdf_digital("Vinculação de documento à guia e beneficiário.")
        cid, did = self.criar_caso_com_documento(tenant="aurora", blob=raw_pdf)
        with storage.connection() as conn:
            doc = storage.document_for(conn, "aurora", did)
            case = storage.case_for(conn, "aurora", doc["case_id"])
            self.assertEqual(doc["case_id"], cid)
            self.assertEqual(case["beneficiary_code"], "BENEF-001")
            self.assertEqual(doc["tenant_id"], case["tenant_id"])

    def test_08_acesso_visualizacao_inline_auditor_mesma_operadora(self):
        """Cenário 8: Acesso à rota de visualização inline por auditor da mesma operadora."""
        raw_pdf = self.fixture_pdf_digital("Conteúdo confidencial para auditoria inline.")
        cid, did = self.criar_caso_com_documento(tenant="aurora", blob=raw_pdf, filename="laudo.pdf", mime="application/pdf")
        identity = self.login("auditor-aurora")
        status, headers, body = self.request("GET", f"/documento/{did}/visualizar", cookie=identity[0])
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/pdf")
        self.assertIn("inline", headers["Content-Disposition"])
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(body, raw_pdf)

    def test_09_bloqueio_acesso_cross_tenant(self):
        """Cenário 9: Bloqueio de acesso por auditor de operadora distinta (cross-tenant)."""
        raw_pdf = self.fixture_pdf_digital("Documento exclusivo da Aurora Saúde.")
        cid, did = self.criar_caso_com_documento(tenant="aurora", blob=raw_pdf)
        identity = self.login("auditor-horizonte")
        status, _, _ = self.request("GET", f"/documento/{did}/visualizar", cookie=identity[0])
        self.assertEqual(status, 403)

    def test_10_bloqueio_acesso_usuario_nao_autenticado(self):
        """Cenário 10: Bloqueio de acesso por usuário não autenticado."""
        raw_pdf = self.fixture_pdf_digital("Documento protegido sem acesso público.")
        cid, did = self.criar_caso_com_documento(tenant="aurora", blob=raw_pdf)
        status, headers, _ = self.request("GET", f"/documento/{did}/visualizar", cookie="")
        self.assertIn(status, (303, 401))

    def test_11_status_inicial_nao_conferido(self):
        """Cenário 11: Presença do status inicial 'NAO_CONFERIDO'."""
        raw_pdf = self.fixture_pdf_digital("Documento com status de conferência padrão.")
        cid, did = self.criar_caso_com_documento(tenant="aurora", blob=raw_pdf, text="Texto para conferência")
        with storage.connection() as conn:
            doc = storage.document_for(conn, "aurora", did)
            self.assertEqual(doc["verification_status"], "NAO_CONFERIDO")
        identity = self.login("auditor-aurora")
        status, _, html = self.request("GET", f"/caso/{cid}", cookie=identity[0])
        self.assertEqual(status, 200)
        self.assertIn("Não conferido", html)

    def test_12_comportamento_ausencia_documento_original(self):
        """Cenário 12: Comportamento na ausência do original (transcrição + aviso de limitação)."""
        texto_apenas = "Apenas transcrição preservada, arquivo físico não disponível."
        cid, did = self.criar_caso_com_documento(tenant="aurora", blob=None, text=texto_apenas)
        identity = self.login("auditor-aurora")
        status, _, html = self.request("GET", f"/caso/{cid}", cookie=identity[0])
        self.assertEqual(status, 200)
        self.assertIn("Documento original não disponível", html)
        self.assertIn(texto_apenas, html)
        status_viz, _, _ = self.request("GET", f"/documento/{did}/visualizar", cookie=identity[0])
        self.assertEqual(status_viz, 404)

    def test_13_resiliencia_arquivo_corrompido(self):
        """Cenário 13: Resiliência a arquivo corrompido ou ilegível."""
        bytes_corrompidos = b"%PDF-1.4\ncorrompido_invalido_bytes_aleatorios_12345"
        with self.assertRaises(ValueError):
            list(leitura.paginas_visuais("arquivo_corrompido.pdf", bytes_corrompidos))

    def test_14_preservacao_casos_b01_b02_b07(self):
        """Cenário 14: Preservação dos casos B01, B02 e B07 com documentos e blobs."""
        with storage.connection() as conn:
            homologacao.carregar(conn, "aurora", storage.now())
            for codigo in ("B01", "B02", "B07"):
                case = conn.execute("SELECT id FROM cases WHERE tenant_id='aurora' AND source_system='BETA' AND external_id=?",
                                    (codigo,)).fetchone()
                self.assertIsNotNone(case, f"Caso {codigo} não encontrado")
                docs = conn.execute("SELECT * FROM documents WHERE tenant_id='aurora' AND case_id=?",
                                    (case["id"],)).fetchall()
                self.assertGreaterEqual(len(docs), 1, f"Caso {codigo} sem documentos")
                pedido = [d for d in docs if d["kind"] == "pedido_medico"][0]
                self.assertIsNotNone(pedido["content_blob"], f"Caso {codigo} sem content_blob")
                self.assertIsNotNone(pedido["source_sha256"], f"Caso {codigo} sem source_sha256")
                self.assertEqual(pedido["verification_status"], "NAO_CONFERIDO")
                self.assertIsNotNone(pedido["content_text"], f"Caso {codigo} sem content_text")

    def test_15_nao_interferencia_motor_dut60(self):
        """Cenário 15: Não interferência no motor determinístico da DUT 60."""
        case = {
            "external_id": "TESTE-B01",
            "procedure": "PET-CT oncológico",
            "tuss_code": "40708128",
            "narrative": "PET-CT para estadiamento primário. Relatório: linfoma confirmado por anatomopatológico.",
        }
        docs = [{"kind": "pedido_medico"}, {"kind": "anatomopatologico"}]
        fatos = {"Linfoma": True, "Estadiamento primário": True}
        res_a = criterios_dut.avaliar_eixo_a("2", fatos)
        self.assertEqual(res_a["conclusao"], criterios_dut.CONCLUSAO_ATENDIDO)
        self.assertIs(res_a["resultado_booleano"], True)

        res_estruturado = criterios_dut.gerar_resultado_estruturado(case, docs, fatos)
        self.assertEqual(res_estruturado["conclusao_agente"]["conclusao"], criterios_dut.CONCLUSAO_ATENDIDO)
        self.assertEqual(res_estruturado["avaliacao_clinica_eixo_b"]["status_suficiencia"], criterios_dut.DOC_SUFICIENTE)

    def test_16_nao_interferencia_calculo_sla(self):
        """Cenário 16: Não interferência no cálculo determinístico do SLA."""
        data_protocolo = "2026-11-03T10:00:00-03:00"
        limite = datas.adicionar_dias_uteis(data_protocolo, dias_uteis=10)
        self.assertEqual(limite.strftime("%Y-%m-%d"), "2026-11-17")
        case = {
            "data_protocolo_operadora": data_protocolo,
            "data_cadastro_sigo": "2026-11-04T10:00:00-03:00",
            "data_importacao_auditia": "2026-11-05T10:00:00-03:00",
            "guide_received_at": "2026-11-04T10:00:00-03:00",
        }
        sla_info = datas.calcular_sla(case["data_protocolo_operadora"], data_referencia="2026-11-10T10:00:00-03:00")
        self.assertEqual(sla_info["status"], datas.STATUS_NO_PRAZO)
        self.assertEqual(sla_info["dias_uteis_restantes"], 5)

    def test_17_integridade_referencial_e_migracao_idempotente(self):
        """Cenário 17: Verificação de integridade referencial e migração idempotente."""
        with storage.connection() as conn:
            cols_antes = {r[1] for r in conn.execute("PRAGMA table_info(documents)")}
            self.assertIn("source_sha256", cols_antes)
            self.assertIn("extraction_method", cols_antes)
            self.assertIn("verification_status", cols_antes)
        # Executar inicialização novamente sobre o mesmo banco
        storage.initialize()
        with storage.connection() as conn:
            cols_depois = {r[1] for r in conn.execute("PRAGMA table_info(documents)")}
            self.assertEqual(cols_antes, cols_depois)


if __name__ == "__main__":
    unittest.main()
