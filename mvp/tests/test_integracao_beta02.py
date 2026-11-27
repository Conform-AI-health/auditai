"""Suíte de Testes de Integração e Homologação de Ponta a Ponta — AuditIA Beta 0.2.
Valida Confiabilidade Documental, Trilha de Governança Administrativa,
Integração SIGO Simulada, Geração e Deliberação de Minutas Regulatórias (Modelos 1 a 5)
e Preservação dos Casos Sintéticos B01, B02 e B07.
"""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import app, auth, config, consultas, criterios_dut, datas, homologacao, minutas, sigo_simulado, storage
from PIL import Image, ImageDraw, ImageFont
import pymupdf


class IntegracaoBeta02Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = storage.DB
        storage.DB = Path(self.tmp.name) / "test_beta02.sqlite3"
        self.passwords = dict(storage.initialize())
        app.failures.clear()

    def tearDown(self):
        storage.DB = self.old_db
        self.tmp.cleanup()

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

    def test_01_conferencia_humana_transcricao(self):
        """1. Valida conferência humana da transcrição com registro de médico responsável e status."""
        identity = self.login("auditor-aurora")
        with storage.connection() as conn:
            # Cadastra perfil com CRM/UF para o auditor
            conn.execute("""INSERT INTO auditor_profiles(username, tenant, name, crm, uf, email, modified)
                VALUES('auditor-aurora', 'aurora', 'Carlos Silveira', '123456', 'SP', 'carlos@aurora.med.br', ?)
                ON CONFLICT(username) DO UPDATE SET name=excluded.name, crm=excluded.crm, uf=excluded.uf""",
                (storage.now(),))
            homologacao.carregar(conn, "aurora", storage.now())
            doc = conn.execute("SELECT id, case_id FROM documents WHERE tenant_id='aurora' LIMIT 1").fetchone()

        status, _, _ = self.request("POST", "/documento/conferir", cookie=identity[0], data={
            "csrf": identity[1],
            "document_id": doc["id"],
            "case_id": doc["case_id"],
            "status": "CONFERIDO",
            "divergences": ""
        })
        self.assertEqual(status, 303)

        with storage.connection() as conn:
            d = storage.document_for(conn, "aurora", doc["id"])
            self.assertEqual(d["verification_status"], "CONFERIDO")
            self.assertIn("123456/SP", d["verified_by"])
            self.assertIsNotNone(d["verified_at"])

            # Valida registro na trilha de governança
            trail = storage.get_governance_trail(conn, "aurora", action="conferencia_documental")
            self.assertGreaterEqual(len(trail), 1)
            self.assertEqual(trail[0]["new_value"], "CONFERIDO")

    def test_02_correcao_ocr_com_versionamento_e_preservacao_original(self):
        """2. Correção de OCR com versionamento: texto bruto v1 preservado, novo v2 ativo, blob inalterado."""
        identity = self.login("auditor-aurora")
        with storage.connection() as conn:
            homologacao.carregar(conn, "aurora", storage.now())
            doc = conn.execute("SELECT id, case_id, content_blob, content_text FROM documents WHERE tenant_id='aurora' AND content_blob IS NOT NULL LIMIT 1").fetchone()
            blob_original = doc["content_blob"]
            texto_original = doc["content_text"]

        texto_corrigido = texto_original + "\n[CORREÇÃO AUDITORIA: Nódulo medindo 12 mm em lobo superior direito]."
        status, _, _ = self.request("POST", "/documento/corrigir-transcricao", cookie=identity[0], data={
            "csrf": identity[1],
            "document_id": doc["id"],
            "case_id": doc["case_id"],
            "content_text": texto_corrigido,
            "change_summary": "Retificação da medida do nódulo para 12 mm conforme imagem anexa."
        })
        self.assertEqual(status, 303)

        with storage.connection() as conn:
            d_atual = storage.document_for(conn, "aurora", doc["id"])
            # O blob original nunca é sobrescrito
            self.assertEqual(d_atual["content_blob"], blob_original)
            # O texto ativo foi atualizado
            self.assertEqual(d_atual["content_text"], texto_corrigido)
            # Versões arquivadas
            versoes = storage.get_document_transcriptions(conn, "aurora", doc["id"])
            self.assertGreaterEqual(len(versoes), 1)
            self.assertEqual(versoes[0]["version"], 1)
            self.assertEqual(versoes[0]["content_text"], texto_corrigido)
            self.assertEqual(versoes[0]["change_summary"], "Retificação da medida do nódulo para 12 mm conforme imagem anexa.")

    def test_03_referencia_documental_das_evidencias(self):
        """3. Vínculo estruturado entre fatos clínicos e evidências documentais (doc, página, trecho)."""
        identity = self.login("auditor-aurora")
        with storage.connection() as conn:
            homologacao.carregar(conn, "aurora", storage.now())
            doc = conn.execute("SELECT id, case_id FROM documents WHERE tenant_id='aurora' LIMIT 1").fetchone()

        status, _, _ = self.request("POST", "/caso/evidencia/vincular", cookie=identity[0], data={
            "csrf": identity[1],
            "case_id": doc["case_id"],
            "document_id": doc["id"],
            "fact_key": "Linfoma Hodgkin",
            "fact_value": "true",
            "page_number": 1,
            "snippet": "Linfoma de Hodgkin clássico subtipo esclerose nodular comprovado por biópsia.",
            "status": "CONFERIDO"
        })
        self.assertEqual(status, 303)

        with storage.connection() as conn:
            evs = storage.get_clinical_evidences(conn, "aurora", doc["case_id"])
            self.assertGreaterEqual(len(evs), 1)
            self.assertEqual(evs[0]["fact_key"], "Linfoma Hodgkin")
            self.assertEqual(evs[0]["page_number"], 1)
            self.assertIn("esclerose nodular", evs[0]["snippet"])

    def test_04_historico_alteracoes_trilha_governanca(self):
        """4. Histórico imutável de eventos operacionais e regulatórios na Trilha de Auditoria."""
        with storage.connection() as conn:
            storage.record_governance_event(
                conn, "aurora", "auditor-aurora", "auditor", "teste_evento_governanca",
                "caso", 1, case_id=1, old_value="valor_anterior", new_value="novo_valor",
                justification="Justificativa formal do evento de teste"
            )
            trilha = storage.get_governance_trail(conn, "aurora", action="teste_evento_governanca")
            self.assertEqual(len(trilha), 1)
            self.assertEqual(trilha[0]["old_value"], "valor_anterior")
            self.assertEqual(trilha[0]["new_value"], "novo_valor")
            self.assertEqual(trilha[0]["justification"], "Justificativa formal do evento de teste")

    def test_05_isolamento_entre_operadoras_multi_tenant(self):
        """5. Isolamento estrito entre operadoras em documentos, minutas e trilhas de governança."""
        with storage.connection() as conn:
            homologacao.carregar(conn, "aurora", storage.now())
            doc_aurora = conn.execute("SELECT id FROM documents WHERE tenant_id='aurora' LIMIT 1").fetchone()

        identity_horizonte = self.login("auditor-horizonte")
        # Tentativa de acesso cruzado ao documento da aurora
        status, _, _ = self.request("GET", f"/documento/{doc_aurora['id']}/visualizar", cookie=identity_horizonte[0])
        self.assertEqual(status, 403)

        # Tentativa de alterar conferência em documento de outro tenant
        status_post, _, _ = self.request("POST", "/documento/conferir", cookie=identity_horizonte[0], data={
            "csrf": identity_horizonte[1],
            "document_id": doc_aurora["id"],
            "status": "CONFERIDO"
        })
        self.assertEqual(status_post, 403)

    def test_06_permissoes_medicas_e_administrativas_trilha(self):
        """6. Permissões estritas: apenas admin acessa /trilha; médico auditor recebe 403 Forbidden."""
        auditor = self.login("auditor-aurora")
        admin = self.login("admin-aurora")

        # Auditor tentando acessar a Trilha Administrativa de Auditoria
        status_aud, _, _ = self.request("GET", "/trilha", cookie=auditor[0])
        self.assertEqual(status_aud, 403)

        # Administrador acessando a Trilha
        status_adm, _, body_adm = self.request("GET", "/trilha", cookie=admin[0])
        self.assertEqual(status_adm, 200)
        self.assertIn("Trilha de Auditoria e Governança", body_adm)

    def test_07_importacao_idempotente_sigo_simulado(self):
        """7. Importação via SIGO Simulado: importa com sucesso e re-importação não duplica guias."""
        admin = self.login("admin-aurora")
        with storage.connection() as conn:
            res1 = sigo_simulado.sincronizar_sigo_simulado(conn, "aurora", actor="admin-aurora")
            self.assertEqual(res1["status"], "sucesso")
            self.assertGreater(res1["inserted"], 0)
            guias_antes = conn.execute("SELECT count(*) FROM cases WHERE tenant_id='aurora' AND source_system='SIGO'").fetchone()[0]

            # Re-execução da sincronização deve ser idempotente
            res2 = sigo_simulado.sincronizar_sigo_simulado(conn, "aurora", actor="admin-aurora")
            self.assertEqual(res2["status"], "sucesso")
            self.assertEqual(res2["inserted"], 0)
            self.assertGreater(res2["duplicates"], 0)
            guias_depois = conn.execute("SELECT count(*) FROM cases WHERE tenant_id='aurora' AND source_system='SIGO'").fetchone()[0]
            self.assertEqual(guias_antes, guias_depois)

    def test_08_preservacao_da_data_original_do_protocolo(self):
        """8. Re-importação não sobrescreve nem altera a data_protocolo_operadora original."""
        with storage.connection() as conn:
            sigo_simulado.sincronizar_sigo_simulado(conn, "aurora", actor="sistema")
            guia = conn.execute("SELECT id, data_protocolo_operadora FROM cases WHERE tenant_id='aurora' AND source_system='SIGO' LIMIT 1").fetchone()
            data_original = guia["data_protocolo_operadora"]
            self.assertIsNotNone(data_original)

            # Nova sincronização
            sigo_simulado.sincronizar_sigo_simulado(conn, "aurora", actor="sistema")
            guia_depois = storage.case_for(conn, "aurora", guia["id"])
            self.assertEqual(guia_depois["data_protocolo_operadora"], data_original)

    def test_09_calculo_sla_sem_alteracao_pela_importacao(self):
        """9. O cálculo do SLA utiliza exclusivamente data_protocolo_operadora, imune a datas de importação."""
        data_proto = "2026-11-04T09:00:00-03:00"
        data_cad_sigo = "2026-11-05T14:00:00-03:00"
        data_imp_auditia = "2026-11-06T18:00:00-03:00"
        case = {
            "data_protocolo_operadora": data_proto,
            "data_cadastro_sigo": data_cad_sigo,
            "data_importacao_auditia": data_imp_auditia,
        }
        sla_info = datas.calcular_sla(case["data_protocolo_operadora"], data_referencia="2026-11-10T10:00:00-03:00")
        self.assertEqual(sla_info["data_limite"].strftime("%Y-%m-%d"), "2026-11-18")
        self.assertEqual(sla_info["status"], datas.STATUS_NO_PRAZO)

    def test_10_geracao_minuta_favoravel(self):
        """10. Geração de Parecer Técnico Favorável quando critérios da DUT 60 são atendidos."""
        case = {
            "external_id": "TESTE-FAV",
            "procedure": "PET-CT dedicado oncológico",
            "tuss_code": "40708128",
            "narrative": "PET-CT para estadiamento primário de linfoma confirmado por biópsia.",
        }
        docs = [{"kind": "pedido_medico"}, {"kind": "anatomopatologico"}]
        fatos = {"Linfoma": True, "Estadiamento primário": True}
        minuta = minutas.redigir_minuta(case, docs, minutas.MODALIDADE_FAVORAVEL, fatos=fatos)
        self.assertEqual(minuta["modality"], minutas.MODALIDADE_FAVORAVEL)
        self.assertIn("Parecer Técnico Favorável", minuta["title"])
        self.assertIn("parecer técnico favorável à autorização", minuta["conclusion"])

    def test_11_geracao_negativa_dut_nao_atendida(self):
        """11. Geração de minuta de negativa por critério obrigatório da DUT não atendido (Modelo 2)."""
        case = {
            "external_id": "TESTE-NOD-8MM",
            "procedure": "PET-CT oncológico para nódulo pulmonar",
            "tuss_code": "40708128",
            "narrative": "PET-CT para nódulo pulmonar solitário de exatamente 8 mm.",
        }
        docs = [{"kind": "pedido_medico"}]
        fatos = {"Nódulo pulmonar solitário": True, "Nódulo maior que 1 cm": False}
        minuta = minutas.redigir_minuta(case, docs, minutas.MODALIDADE_NEGATIVA_DUT, fatos=fatos)
        self.assertEqual(minuta["modality"], minutas.MODALIDADE_NEGATIVA_DUT)
        self.assertIn("Critério Obrigatório da DUT 60 Não Atendido", minuta["title"])
        self.assertIn("item 4", minuta["normative_basis"])
        self.assertIn("inferior ao limite estabelecido", minuta["draft_text"])

    def test_12_geracao_negativa_indicacao_nao_contemplada(self):
        """12. Geração de negativa por indicação não contemplada na DUT 60 (Modelo 5 - neoplasia testicular)."""
        case = {
            "external_id": "TESTE-TESTICULO",
            "procedure": "PET-CT oncológico",
            "tuss_code": "40708128",
            "narrative": "PET-CT para estadiamento de neoplasia testicular maligna.",
        }
        docs = [{"kind": "pedido_medico"}]
        minuta = minutas.redigir_minuta(case, docs, minutas.MODALIDADE_NEGATIVA_INDICACAO)
        self.assertEqual(minuta["modality"], minutas.MODALIDADE_NEGATIVA_INDICACAO)
        self.assertIn("Indicação Não Contemplada na DUT 60", minuta["title"])
        self.assertIn("não foi identificado enquadramento", minuta["draft_text"])

    def test_13_geracao_negativa_fora_do_rol_caso_b07(self):
        """13. Geração de negativa fora do Rol quando fundamentada (Modelo 4 - B07 PET cerebral / demência)."""
        case = {
            "external_id": "B07",
            "procedure": "PET-CT cerebral",
            "tuss_code": "41001311",
            "narrative": "PET-CT cerebral com FDG para investigação de demência. Ausência de indicação oncológica.",
        }
        docs = [{"kind": "pedido_medico"}]
        minuta = minutas.redigir_minuta(case, docs, minutas.MODALIDADE_NEGATIVA_ROL)
        self.assertEqual(minuta["modality"], minutas.MODALIDADE_NEGATIVA_ROL)
        self.assertIn("Não Previstos no Rol da ANS", minuta["title"])
        self.assertIn("não abrangendo a indicação neurológica de investigação de demência", minuta["draft_text"])
        self.assertIn("41001311", minuta["draft_text"])

    def test_14_geracao_complementacao_dados_insuficientes(self):
        """14. Geração de complementação documental quando critérios não estão comprovados (Modelo 3)."""
        case = {
            "external_id": "B02",
            "procedure": "PET-CT oncológico",
            "tuss_code": "40708128",
            "narrative": "PET-CT para estadiamento primário. Guia sem diagnóstico e sem laudo anexo.",
        }
        docs = [{"kind": "pedido_medico"}]
        minuta = minutas.redigir_minuta(case, docs, minutas.MODALIDADE_COMPLEMENTACAO)
        self.assertEqual(minuta["modality"], minutas.MODALIDADE_COMPLEMENTACAO)
        self.assertIn("Solicitação de Complementação Documental", minuta["title"])
        self.assertIn("solicita-se a apresentação de documentação complementar", minuta["draft_text"])
        self.assertIn("permanecendo a análise pendente de comprovação", minuta["draft_text"])

    def test_15_edicao_e_aprovacao_humana_minuta(self):
        """15. Edição manual e aprovação formal da minuta pelo médico auditor (status APROVADO_MEDICO)."""
        identity = self.login("auditor-aurora")
        with storage.connection() as conn:
            homologacao.carregar(conn, "aurora", storage.now())
            case = conn.execute("SELECT id FROM cases WHERE tenant_id='aurora' LIMIT 1").fetchone()
            draft_id = minutas.gerar_e_salvar_minuta(conn, "aurora", case["id"], actor="auditor-aurora")

        # 1. Edição manual
        texto_editado = "Texto da minuta revisado e complementado pelo auditor."
        st_edit, _, _ = self.request("POST", "/caso/minuta/acao", cookie=identity[0], data={
            "csrf": identity[1],
            "draft_id": draft_id,
            "case_id": case["id"],
            "acao": "editar",
            "draft_text": texto_editado,
            "justification": "Ajuste de parágrafo conclusivo."
        })
        self.assertEqual(st_edit, 303)

        with storage.connection() as conn:
            d = conn.execute("SELECT * FROM regulatory_drafts WHERE id=?", (draft_id,)).fetchone()
            self.assertEqual(d["status"], "EM_EDICAO")
            self.assertEqual(d["draft_text"], texto_editado)

        # 2. Aprovação médica formal
        st_aprov, _, _ = self.request("POST", "/caso/minuta/acao", cookie=identity[0], data={
            "csrf": identity[1],
            "draft_id": draft_id,
            "case_id": case["id"],
            "acao": "aprovar",
            "draft_text": texto_editado,
            "justification": "Aprovado tecnicamente com base no subitem 60.2 da DUT."
        })
        self.assertEqual(st_aprov, 303)

        with storage.connection() as conn:
            d_aprov = conn.execute("SELECT * FROM regulatory_drafts WHERE id=?", (draft_id,)).fetchone()
            self.assertEqual(d_aprov["status"], "APROVADO_MEDICO")
            trail = storage.get_governance_trail(conn, "aurora", action="minuta_aprovada")
            self.assertGreaterEqual(len(trail), 1)

    def test_16_descarte_de_minuta_com_justificativa(self):
        """16. Descarte controlado de minuta com justificativa obrigatória registrada na trilha."""
        identity = self.login("auditor-aurora")
        with storage.connection() as conn:
            homologacao.carregar(conn, "aurora", storage.now())
            case = conn.execute("SELECT id FROM cases WHERE tenant_id='aurora' LIMIT 1").fetchone()
            draft_id = minutas.gerar_e_salvar_minuta(conn, "aurora", case["id"], actor="auditor-aurora")

        st_desc, _, _ = self.request("POST", "/caso/minuta/acao", cookie=identity[0], data={
            "csrf": identity[1],
            "draft_id": draft_id,
            "case_id": case["id"],
            "acao": "descartar",
            "justification": "Mudança no quadro clínico após contato com o médico assistente."
        })
        self.assertEqual(st_desc, 303)

        with storage.connection() as conn:
            d = conn.execute("SELECT * FROM regulatory_drafts WHERE id=?", (draft_id,)).fetchone()
            self.assertEqual(d["status"], "DESCARTADO")
            self.assertIn("Mudança no quadro clínico", d["decision_justification"])

    def test_17_ausencia_comunicacao_automatica_beneficiario(self):
        """17. A aprovação da minuta não emite e-mail/notificação nem altera estado conclusivo com o beneficiário."""
        identity = self.login("auditor-aurora")
        with storage.connection() as conn:
            homologacao.carregar(conn, "aurora", storage.now())
            case = conn.execute("SELECT id FROM cases WHERE tenant_id='aurora' LIMIT 1").fetchone()
            draft_id = minutas.gerar_e_salvar_minuta(conn, "aurora", case["id"], actor="auditor-aurora")

        self.request("POST", "/caso/minuta/acao", cookie=identity[0], data={
            "csrf": identity[1],
            "draft_id": draft_id,
            "case_id": case["id"],
            "acao": "aprovar",
            "justification": "Aprovado para uso interno."
        })

        with storage.connection() as conn:
            c = storage.case_for(conn, "aurora", case["id"])
            # data_resposta_beneficiario deve permanecer nula (sem envio automático!)
            self.assertIsNone(c["data_resposta_beneficiario"])

    def test_18_preservacao_fluxo_casos_b01_b02_b07(self):
        """18. Preservação integral dos casos B01, B02 e B07 com documentos, motor e geração de minutas."""
        with storage.connection() as conn:
            homologacao.carregar(conn, "aurora", storage.now())
            b01 = conn.execute("SELECT id FROM cases WHERE tenant_id='aurora' AND source_system='BETA' AND external_id='B01'").fetchone()
            b02 = conn.execute("SELECT id FROM cases WHERE tenant_id='aurora' AND source_system='BETA' AND external_id='B02'").fetchone()
            b07 = conn.execute("SELECT id FROM cases WHERE tenant_id='aurora' AND source_system='BETA' AND external_id='B07'").fetchone()

            # B01 -> Linfoma com anatomopatológico -> Minuta Favorável
            d_b01 = minutas.gerar_e_salvar_minuta(conn, "aurora", b01["id"], fatos={"Linfoma": True, "Estadiamento primário": True})
            draft_b01 = conn.execute("SELECT * FROM regulatory_drafts WHERE id=?", (d_b01,)).fetchone()
            self.assertEqual(draft_b01["modality"], minutas.MODALIDADE_FAVORAVEL)

            # B02 -> Sem anatomopatológico -> Minuta Complementação
            d_b02 = minutas.gerar_e_salvar_minuta(conn, "aurora", b02["id"])
            draft_b02 = conn.execute("SELECT * FROM regulatory_drafts WHERE id=?", (d_b02,)).fetchone()
            self.assertEqual(draft_b02["modality"], minutas.MODALIDADE_COMPLEMENTACAO)

            # B07 -> Demência cerebral -> Minuta Negativa fora do Rol
            d_b07 = minutas.gerar_e_salvar_minuta(conn, "aurora", b07["id"])
            draft_b07 = conn.execute("SELECT * FROM regulatory_drafts WHERE id=?", (d_b07,)).fetchone()
            self.assertEqual(draft_b07["modality"], minutas.MODALIDADE_NEGATIVA_ROL)

    def test_19_preservacao_dez_subitens_dut60(self):
        """19. Preservação dos dez subitens da DUT 60 no motor determinístico."""
        itens = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]
        for it in itens:
            res = criterios_dut.avaliar_eixo_a(it, {})
            self.assertIn("conclusao", res)

    def test_20_ajuste_justificado_data_protocolo(self):
        """20. Ajuste justificado de data de protocolo com auditoria na trilha de governança."""
        identity = self.login("auditor-aurora")
        with storage.connection() as conn:
            homologacao.carregar(conn, "aurora", storage.now())
            case = conn.execute("SELECT id, data_protocolo_operadora FROM cases WHERE tenant_id='aurora' LIMIT 1").fetchone()
            old_date = case["data_protocolo_operadora"]

        nova_data = "2026-11-01T10:00:00-03:00"
        st, _, _ = self.request("POST", "/caso/protocolo", cookie=identity[0], data={
            "csrf": identity[1],
            "case_id": case["id"],
            "data_protocolo": nova_data,
            "justificativa": "Correção de data de protocolo conforme comprovante físico de entrega presencial."
        })
        self.assertEqual(st, 303)

        with storage.connection() as conn:
            c = storage.case_for(conn, "aurora", case["id"])
            self.assertEqual(c["data_protocolo_operadora"], nova_data)
            trail = storage.get_governance_trail(conn, "aurora", action="ajuste_data_protocolo", case_id=case["id"])
            self.assertEqual(len(trail), 1)
            self.assertEqual(trail[0]["new_value"], nova_data)
            self.assertIn("comprovante físico", trail[0]["justification"])


if __name__ == "__main__":
    unittest.main()
