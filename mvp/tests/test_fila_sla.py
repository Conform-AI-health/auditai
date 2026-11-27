"""Testes automatizados da Fila de Auditoria e SLA de Resposta Conclusiva (Etapa 2B.1).

Cobre:
1. Ordenação da fila: casos vencidos primeiro, seguidos dos mais próximos do vencimento.
2. Agrupamento de casos sem protocolo em grupo de pendências (PROTOCOLO_AUSENTE).
3. Marco inicial estritamente em data_protocolo_operadora (cadastro/importação não reiniciam prazo).
4. Ausência de data de protocolo não presume data de cadastro no SIGO.
5. Independência entre cálculo de SLA e parecer clínico/status documental.
6. Indicadores de pendência documental (Completa, Falta laudo, Falta pedido, Falta pedido e laudo).
7. Segregação de perfis: auditor médico tem visão estritamente operacional; rotas administrativas
   e trilha de auditoria (/auditoria, /telemetria) são bloqueadas (403 Forbidden) para auditor.
"""
import io
import re
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlencode
from unittest.mock import patch
from wsgiref.util import setup_testing_defaults

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import app, datas, storage, consultas
from frontend import telas, fila


class FilaSLATests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = storage.DB
        storage.DB = Path(self.tmp.name) / "test_fila_sla.sqlite3"
        self.passwords = dict(storage.initialize())
        app.failures.clear()

    def tearDown(self):
        storage.DB = self.old_db
        self.tmp.cleanup()

    def request(self, method, path, cookie="", data=None):
        body = urlencode(data or {}).encode()
        env = {}
        setup_testing_defaults(env)
        env.update(
            REQUEST_METHOD=method,
            PATH_INFO=path.split("?")[0],
            QUERY_STRING=path.split("?", 1)[1] if "?" in path else "",
            HTTP_HOST="127.0.0.1:8765",
            HTTP_COOKIE=cookie,
            CONTENT_LENGTH=str(len(body)),
            **{"wsgi.input": io.BytesIO(body)},
        )
        response = {}

        def start(status, headers):
            response["status"] = int(status[:3])
            response["headers"] = dict(headers)

        raw = b"".join(app.app(env, start))
        result = raw.decode("utf-8", "replace")
        return response["status"], response["headers"], result

    def login(self, username, password=None):
        pwd = password or self.passwords[username]
        _, headers, _ = self.request("GET", "/entrar")
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        from backend import auth
        csrf = auth.verify(cookie.split("=", 1)[1])["csrf"]
        status, headers, _ = self.request("POST", "/entrar", cookie=cookie,
                                          data={"csrf": csrf, "username": username, "password": pwd})
        self.assertEqual(status, 303)
        new_cookie = headers["Set-Cookie"].split(";", 1)[0]
        new_csrf = auth.verify(new_cookie.split("=", 1)[1])["csrf"]
        if "auditor" in username:
            _, term_headers, _ = self.request("POST", "/termo", cookie=new_cookie, data={"csrf": new_csrf, "aceite": "1"})
            if "Set-Cookie" in term_headers:
                new_cookie = term_headers["Set-Cookie"].split(";", 1)[0]
        return new_cookie

    def test_ordenacao_vencidos_antes_dos_no_prazo(self):
        """Casos vencidos (protocolo antigo) devem preceder casos no prazo."""
        with storage.connection() as conn:
            conn.execute("DELETE FROM cases WHERE tenant_id='aurora'")
            # Caso 1: Entrada recente (no prazo)
            conn.execute("""INSERT INTO cases
                (tenant_id, source_system, external_id, procedure, area, narrative,
                 clinical_question, source_updated_at, last_imported_at, created_at, updated_at,
                 data_protocolo_operadora)
                VALUES('aurora', 'SISTEMA', 'GUIA-NO-PRAZO', 'PET-CT oncológico', 'Onco',
                       'Caso recente', 1, '2026-11-20', '2026-11-20', '2026-11-20', '2026-11-20',
                       '2026-11-20T10:00:00-03:00')""")
            # Caso 2: Entrada antiga (vencido)
            conn.execute("""INSERT INTO cases
                (tenant_id, source_system, external_id, procedure, area, narrative,
                 clinical_question, source_updated_at, last_imported_at, created_at, updated_at,
                 data_protocolo_operadora)
                VALUES('aurora', 'SISTEMA', 'GUIA-VENCIDA', 'PET-CT oncológico', 'Onco',
                       'Caso antigo', 1, '2026-11-01', '2026-11-01', '2026-11-01', '2026-11-01',
                       '2026-11-01T10:00:00-03:00')""")

            casos = consultas.casos_da_operadora(conn, "aurora", pagina=1)
            ids_ordenados = [c["external_id"] for c in casos]
            self.assertEqual(ids_ordenados[0], "GUIA-VENCIDA")
            self.assertEqual(ids_ordenados[1], "GUIA-NO-PRAZO")

    def test_ordenacao_proximos_do_vencimento(self):
        """Entre casos vigentes, o mais próximo do vencimento deve vir antes."""
        with storage.connection() as conn:
            conn.execute("DELETE FROM cases WHERE tenant_id='aurora'")
            # Caso 1: entrada 18/11/2026 (expira mais tarde)
            conn.execute("""INSERT INTO cases
                (tenant_id, source_system, external_id, procedure, area, narrative,
                 clinical_question, source_updated_at, last_imported_at, created_at, updated_at,
                 data_protocolo_operadora)
                VALUES('aurora', 'SISTEMA', 'GUIA-PRAZO-LONGO', 'PET-CT', 'Onco', 'N', 1, '2026', '2026', '2026', '2026',
                       '2026-11-18T10:00:00-03:00')""")
            # Caso 2: entrada 12/11/2026 (expira mais cedo)
            conn.execute("""INSERT INTO cases
                (tenant_id, source_system, external_id, procedure, area, narrative,
                 clinical_question, source_updated_at, last_imported_at, created_at, updated_at,
                 data_protocolo_operadora)
                VALUES('aurora', 'SISTEMA', 'GUIA-PRAZO-CURTO', 'PET-CT', 'Onco', 'N', 1, '2026', '2026', '2026', '2026',
                       '2026-11-12T10:00:00-03:00')""")

            casos = consultas.casos_da_operadora(conn, "aurora", pagina=1)
            ids_ordenados = [c["external_id"] for c in casos]
            self.assertEqual(ids_ordenados[0], "GUIA-PRAZO-CURTO")
            self.assertEqual(ids_ordenados[1], "GUIA-PRAZO-LONGO")

    def test_grupo_pendencias_protocolo_ausente(self):
        """Casos sem data de protocolo devem figurar ao final da fila, agrupados em pendência."""
        with storage.connection() as conn:
            conn.execute("DELETE FROM cases WHERE tenant_id='aurora'")
            # Caso sem protocolo
            conn.execute("""INSERT INTO cases
                (tenant_id, source_system, external_id, procedure, area, narrative,
                 clinical_question, source_updated_at, last_imported_at, created_at, updated_at,
                 data_protocolo_operadora)
                VALUES('aurora', 'SISTEMA', 'GUIA-SEM-PROTOCOLO', 'PET-CT', 'Onco', 'N', 1, '2026', '2026', '2026', '2026',
                       NULL)""")
            # Caso com protocolo
            conn.execute("""INSERT INTO cases
                (tenant_id, source_system, external_id, procedure, area, narrative,
                 clinical_question, source_updated_at, last_imported_at, created_at, updated_at,
                 data_protocolo_operadora)
                VALUES('aurora', 'SISTEMA', 'GUIA-COM-PROTOCOLO', 'PET-CT', 'Onco', 'N', 1, '2026', '2026', '2026', '2026',
                       '2026-11-15T10:00:00-03:00')""")

            casos = consultas.casos_da_operadora(conn, "aurora", pagina=1)
            ids_ordenados = [c["external_id"] for c in casos]
            self.assertEqual(ids_ordenados[0], "GUIA-COM-PROTOCOLO")
            self.assertEqual(ids_ordenados[1], "GUIA-SEM-PROTOCOLO")

    def test_independencia_datas_cadastro_e_importacao(self):
        """Datas de cadastro no SIGO ou importação não reiniciam prazo e não são presumidas como protocolo."""
        with storage.connection() as conn:
            # Caso com protocolo original antigo e cadastro SIGO posterior:
            # O SLA deve contar a partir do protocolo original (01/11/2026), não do cadastro SIGO (15/11/2026)
            conn.execute("""INSERT INTO cases
                (tenant_id, source_system, external_id, procedure, area, narrative,
                 clinical_question, source_updated_at, last_imported_at, created_at, updated_at,
                 data_protocolo_operadora, data_cadastro_sigo, data_importacao_auditia)
                VALUES('aurora', 'SIGO', 'GUIA-SIGO-PRAZO', 'PET-CT', 'Onco', 'N', 1, '2026', '2026', '2026', '2026',
                       '2026-11-01T10:00:00-03:00', '2026-11-15T10:00:00-03:00', '2026-11-16T10:00:00-03:00')""")

            # Caso do SIGO com protocolo ausente:
            # A data do cadastro SIGO NÃO pode ser presumida como data de protocolo
            conn.execute("""INSERT INTO cases
                (tenant_id, source_system, external_id, procedure, area, narrative,
                 clinical_question, source_updated_at, last_imported_at, created_at, updated_at,
                 data_protocolo_operadora, data_cadastro_sigo, data_importacao_auditia)
                VALUES('aurora', 'SIGO', 'GUIA-SIGO-SEM-PROTO', 'PET-CT', 'Onco', 'N', 1, '2026', '2026', '2026', '2026',
                       NULL, '2026-11-15T10:00:00-03:00', '2026-11-16T10:00:00-03:00')""")

            caso_com_proto = conn.execute("SELECT * FROM cases WHERE external_id='GUIA-SIGO-PRAZO'").fetchone()
            caso_sem_proto = conn.execute("SELECT * FROM cases WHERE external_id='GUIA-SIGO-SEM-PROTO'").fetchone()

        sla_com_proto = datas.calcular_sla(
            caso_com_proto["data_protocolo_operadora"],
            data_referencia="2026-11-20"
        )
        self.assertEqual(sla_com_proto["status"], datas.STATUS_VENCIDO)
        self.assertEqual(sla_com_proto["data_protocolo"], date(2026, 11, 1))

        sla_sem_proto = datas.calcular_sla(
            caso_sem_proto["data_protocolo_operadora"],
            data_referencia="2026-11-20"
        )
        self.assertEqual(sla_sem_proto["status"], datas.STATUS_PROTOCOLO_AUSENTE)
        self.assertIsNone(sla_sem_proto["data_limite"])

    def test_independencia_sla_e_status_clinico_documental(self):
        """O SLA deve ser calculado independentemente da avaliação clínica e documental."""
        proto = "2026-11-10T10:00:00-03:00"
        ref = "2026-11-23"
        sla = datas.calcular_sla(proto, data_referencia=ref)

        # O SLA é idêntico quer a guia tenha parecer gerado, discordância ou documentos faltantes
        self.assertEqual(sla["status"], datas.STATUS_ALERTA)
        self.assertEqual(sla["dias_uteis_restantes"], 2)

    def test_indicadores_pendencia_documental(self):
        """Verifica a renderização correta de pendências documentais."""
        self.assertIn("Completa", telas.badge_pendencia_docs(2, 1, 1))
        self.assertIn("Falta laudo", telas.badge_pendencia_docs(1, 1, 0))
        self.assertIn("Falta pedido", telas.badge_pendencia_docs(1, 0, 1))
        self.assertIn("Falta pedido e laudo", telas.badge_pendencia_docs(0, 0, 0))

    def test_segregacao_perfis_auditor_vs_admin(self):
        """Médico auditor tem visão operacional e não acessa trilha de auditoria administrativa."""
        cookie_auditor = self.login("auditor-aurora")
        cookie_admin = self.login("admin-aurora")

        # Auditor tentando acessar trilha de auditoria e telemetria: 403 Forbidden
        status_audit, _, _ = self.request("GET", "/auditoria", cookie=cookie_auditor)
        self.assertEqual(status_audit, 403)

        status_telem, _, _ = self.request("GET", "/telemetria", cookie=cookie_auditor)
        self.assertEqual(status_telem, 403)

        # Administrador tem acesso à trilha de auditoria: 200 OK
        status_admin_audit, _, _ = self.request("GET", "/auditoria", cookie=cookie_admin)
        self.assertEqual(status_admin_audit, 200)

        # Interface operacional do auditor contém colunas do SLA
        with patch.object(app.config, "BETA", False):
            status_cases, _, html = self.request("GET", "/", cookie=cookie_auditor)
            self.assertEqual(status_cases, 200)
            for coluna in ("Nº guia", "Procedimento", "Entrada", "Data limite", "Dias restantes",
                           "Situação SLA", "Status análise", "Pendência documental", "Médico resp.", "Ações"):
                self.assertIn(coluna, html)
            # Não exibe logs administrativos ou de telemetria na fila operacional
            self.assertNotIn("telemetry", html.lower())
            self.assertNotIn("trilha de auditoria", html.lower())

    def test_protocolo_original_ausente_com_guide_received_at_preenchido(self):
        """Garante que guide_received_at JAMAIS é utilizado como fallback na ausência de data_protocolo_operadora."""
        with storage.connection() as conn:
            conn.execute("DELETE FROM cases WHERE tenant_id='aurora'")
            conn.execute("""INSERT INTO cases
                (tenant_id, source_system, external_id, procedure, area, narrative,
                 clinical_question, source_updated_at, last_imported_at, created_at, updated_at,
                 guide_received_at, data_protocolo_operadora)
                VALUES('aurora', 'LEGADO', 'GUIA-LEGADO-01', 'PET-CT', 'Onco', 'Narrativa',
                       1, '2026-11-01', '2026-11-01', '2026-11-01', '2026-11-01',
                       '2026-11-01T10:00:00-03:00', NULL)""")
            caso = conn.execute("SELECT * FROM cases WHERE external_id='GUIA-LEGADO-01'").fetchone()

            # O cálculo determinístico utiliza estritamente data_protocolo_operadora
            sla = datas.calcular_sla(caso["data_protocolo_operadora"])
            self.assertEqual(sla["status"], datas.STATUS_PROTOCOLO_AUSENTE)
            self.assertIsNone(sla["data_protocolo"])
            self.assertIsNone(sla["data_limite"])
            self.assertIsNone(sla["dias_uteis_restantes"])

            # Na consulta da fila da operadora, a guia aparece como Protocolo ausente
            casos = consultas.casos_da_operadora(conn, "aurora", pagina=1)
            self.assertEqual(len(casos), 1)
            self.assertIsNone(casos[0]["data_protocolo_operadora"])

    def test_guia_importada_apos_solicitacao_original(self):
        """Datas de cadastro administrativo ou importação no AuditIA posteriores não postergam nem reiniciam prazo."""
        proto = "2026-11-03T10:00:00-03:00"
        sigo = "2026-11-10T10:00:00-03:00"
        importacao = "2026-11-12T10:00:00-03:00"

        with storage.connection() as conn:
            conn.execute("DELETE FROM cases WHERE tenant_id='aurora'")
            conn.execute("""INSERT INTO cases
                (tenant_id, source_system, external_id, procedure, area, narrative,
                 clinical_question, source_updated_at, last_imported_at, created_at, updated_at,
                 data_protocolo_operadora, data_cadastro_sigo, data_importacao_auditia)
                VALUES('aurora', 'SIGO', 'GUIA-IMPORTADA-02', 'PET-CT', 'Onco', 'Narrativa',
                       1, '2026-11-10', '2026-11-12', '2026-11-12', '2026-11-12',
                       ?, ?, ?)""", (proto, sigo, importacao))
            caso = conn.execute("SELECT * FROM cases WHERE external_id='GUIA-IMPORTADA-02'").fetchone()

        sla = datas.calcular_sla(caso["data_protocolo_operadora"], data_referencia="2026-11-13")
        # Contagem: 10 dias úteis a partir de 03/11/2026 (terça-feira) -> vence em 17/11/2026
        self.assertEqual(sla["data_protocolo"], date(2026, 11, 3))
        self.assertEqual(sla["data_limite"], date(2026, 11, 17))
        self.assertEqual(sla["status"], datas.STATUS_ALERTA)
        self.assertEqual(sla["dias_uteis_restantes"], 2)

    def test_petct_criterio_dispensa_anatomopatologico(self):
        """PET-CT para nódulo pulmonar solitário (DUT 60.4) não exige universalmente anatomopatológico."""
        caso_nodulo = {
            "procedure": "PET-CT oncológico",
            "narrative": "PET-CT para nódulo pulmonar solitário de 14 mm, não espiculado e sem calcificações. TC inconclusiva.",
            "tuss_code": "40708128",
            "tem_pedido": 1,
            "tem_anatomo": 0,
        }
        res_nodulo = telas.avaliar_documentacao_caso(caso_nodulo)
        self.assertIn("60.4", res_nodulo["criterio"])
        self.assertNotIn("Laudo anatomopatológico", res_nodulo["necessarios"])
        self.assertIn("Pedido médico", res_nodulo["necessarios"])
        self.assertEqual(len(res_nodulo["nao_recebidos"]), 0)
        self.assertEqual(res_nodulo["status_rotulo"], "Completa")
        self.assertIn("Completa", res_nodulo["badge_html"])

        # Para CPCP (DUT 60.10), o laudo anatomopatológico é exigência expressa da DUT
        caso_cpcp = {
            "procedure": "PET-CT oncológico",
            "narrative": "PET-CT para estadiamento de câncer pulmonar de pequenas células.",
            "tuss_code": "40708128",
            "tem_pedido": 1,
            "tem_anatomo": 0,
        }
        res_cpcp = telas.avaliar_documentacao_caso(caso_cpcp)
        self.assertIn("Laudo anatomopatológico", res_cpcp["necessarios"])
        self.assertIn("Laudo anatomopatológico", res_cpcp["nao_recebidos"])
        self.assertIn("Falta laudo", res_cpcp["badge_html"])

        # Indicação não determinada não presume completude nem falta universal de documentos
        caso_indeterminado = {
            "procedure": "PET-CT solicitado",
            "narrative": "",
            "tuss_code": "40708128",
            "tem_pedido": 1,
            "tem_anatomo": 0,
        }
        res_indet = telas.avaliar_documentacao_caso(caso_indeterminado)
        self.assertTrue(res_indet["indeterminado"])
        self.assertIn("A determinar", res_indet["badge_html"])

    def test_revisao_medica_finalizada_sem_resposta_ao_beneficiario(self):
        """Finalização da revisão médica NÃO encerra SLA nem presume cumprimento do prazo."""
        proto = "2026-11-03T10:00:00-03:00"
        # Prazo venceu em 18/11/2026. Revisão médica concluída em 10/11/2026.
        # Resposta ao beneficiário NÃO foi enviada (data_resposta_beneficiario is None).
        # Em consulta feita no dia 23/11/2026 (após vencimento):
        sla = datas.calcular_sla(
            proto,
            data_referencia="2026-11-23",
            data_encerramento=None  # Sem evidência de resposta disponibilizada
        )
        self.assertEqual(sla["status"], datas.STATUS_VENCIDO)
        self.assertTrue(sla["em_atraso"])
        self.assertLess(sla["dias_uteis_restantes"], 0)

    def test_resposta_conclusiva_registrada_dentro_e_fora_do_prazo(self):
        """SLA é encerrado exclusivamente com a resposta conclusiva, distinguindo cumprimento do prazo."""
        proto = "2026-11-03T10:00:00-03:00" # Limite: 18/11/2026

        # Caso A: resposta disponibilizada no prazo (16/11/2026)
        sla_no_prazo = datas.calcular_sla(
            proto,
            data_encerramento="2026-11-16T15:00:00-03:00"
        )
        self.assertEqual(sla_no_prazo["status"], datas.STATUS_CONCLUIDO_NO_PRAZO)
        self.assertEqual(sla_no_prazo["rotulo_status"], "Concluído no prazo")
        self.assertFalse(sla_no_prazo["em_atraso"])

        # Caso B: resposta disponibilizada fora do prazo (24/11/2026)
        sla_fora_prazo = datas.calcular_sla(
            proto,
            data_encerramento="2026-11-24T10:00:00-03:00"
        )
        self.assertEqual(sla_fora_prazo["status"], datas.STATUS_CONCLUIDO_FORA_PRAZO)
        self.assertEqual(sla_fora_prazo["rotulo_status"], "Concluído fora do prazo")
        self.assertTrue(sla_fora_prazo["em_atraso"])


if __name__ == "__main__":
    unittest.main()
