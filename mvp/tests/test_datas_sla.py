"""Testes automatizados do modelo temporal e cálculo determinístico de prazos/SLA."""
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import datas, storage


class ModeloTemporalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test_temporal.sqlite3"
        self.patch = patch.object(storage, "DB", self.db_path)
        self.patch.start()
        storage.initialize()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_migracao_repetida_idempotente(self):
        """Verifica que a migração é idempotente e pode ser executada repetidamente sem erros."""
        for _ in range(3):
            storage.initialize()

        with storage.connection() as conn:
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(cases)").fetchall()}

        for col in ("data_protocolo_operadora", "data_cadastro_sigo", "data_importacao_auditia", "guide_received_at"):
            self.assertIn(col, cols)

    def test_preservacao_registros_historicos(self):
        """Garante que registros inseridos no esquema anterior mantêm seus dados e novos campos como None."""
        with storage.connection() as conn:
            conn.execute("""INSERT INTO cases(tenant_id, source_system, external_id, procedure, area, narrative,
                            clinical_question, source_updated_at, last_imported_at, created_at, updated_at, guide_received_at)
                            VALUES('aurora', 'LEGADO', 'GUIA-LEGADA-01', 'PET-CT', 'Oncologia', 'Caso histórico',
                            1, '2026-11-01', '2026-11-01', '2026-11-01', '2026-11-01', '2026-11-01T10:00:00-03:00')""")

        # Executa migração novamente
        storage.initialize()

        with storage.connection() as conn:
            row = conn.execute("SELECT * FROM cases WHERE external_id='GUIA-LEGADA-01'").fetchone()
            self.assertEqual(row["procedure"], "PET-CT")
            self.assertEqual(row["guide_received_at"], "2026-11-01T10:00:00-03:00")
            self.assertIsNone(row["data_protocolo_operadora"])
            self.assertIsNone(row["data_cadastro_sigo"])
            self.assertIsNone(row["data_importacao_auditia"])

    def test_protocolo_ausente(self):
        """Garante que a ausência de protocolo original resulta em PROTOCOLO_AUSENTE sem presumir datas."""
        for valor in (None, "", "   ", "data-invalida"):
            with self.subTest(valor=valor):
                res = datas.calcular_sla(valor)
                self.assertEqual(res["status"], datas.STATUS_PROTOCOLO_AUSENTE)
                self.assertIsNone(res["data_protocolo"])
                self.assertIsNone(res["data_limite"])
                self.assertIsNone(res["dias_uteis_decorridos"])
                self.assertIsNone(res["dias_uteis_restantes"])
                self.assertFalse(res["em_atraso"])

    def test_nao_presumir_data_sigo_como_protocolo(self):
        """Garante que a data do SIGO jamais é presumida como data de protocolo."""
        with storage.connection() as conn:
            conn.execute("""INSERT INTO cases(tenant_id, source_system, external_id, procedure, area, narrative,
                            clinical_question, source_updated_at, last_imported_at, created_at, updated_at,
                            data_cadastro_sigo, data_protocolo_operadora)
                            VALUES('aurora', 'SIGO', 'GUIA-SIGO-01', 'PET-CT', 'Oncologia', 'Caso sem protocolo',
                            1, '2026-11-20', '2026-11-20', '2026-11-20', '2026-11-20',
                            '2026-11-20T14:00:00-03:00', NULL)""")
            case = conn.execute("SELECT * FROM cases WHERE external_id='GUIA-SIGO-01'").fetchone()

        # O cálculo deve respeitar a data_protocolo_operadora (None) e retornar PROTOCOLO_AUSENTE
        res = datas.calcular_sla(case["data_protocolo_operadora"])
        self.assertEqual(res["status"], datas.STATUS_PROTOCOLO_AUSENTE)

    def test_contagem_fins_de_semana(self):
        """Verifica a regra de contagem de dias úteis com entrada em dia útil vs fim de semana."""
        # Sexta-feira útil (27/11/2026): contagem inicia na segunda (30/11)
        proto_sexta = "2026-11-27"
        limite_1_dia = datas.adicionar_dias_uteis(proto_sexta, 1)
        self.assertEqual(limite_1_dia, date(2026, 11, 30))  # Segunda-feira

        # Sábado (28/11/2026): recebimento considerado na segunda (30/11), dia 1 na terça (01/12)
        proto_sabado = "2026-11-28"
        limite_sab = datas.adicionar_dias_uteis(proto_sabado, 1)
        self.assertEqual(limite_sab, date(2026, 12, 1))

        # Domingo (29/11/2026): recebimento considerado na segunda (30/11), dia 1 na terça (01/12)
        proto_domingo = "2026-11-29"
        limite_dom = datas.adicionar_dias_uteis(proto_domingo, 1)
        self.assertEqual(limite_dom, date(2026, 12, 1))

    def test_contagem_feriados_nacionais(self):
        """Verifica que feriados nacionais suspendem a contagem (ex: 20/11 Dia da Consciência Negra)."""
        # 20/11/2026 é sexta-feira (feriado nacional)
        # Recebimento passa para segunda (23/11), início contagem terça (24/11)
        proto = "2026-11-20"
        limite_10 = datas.adicionar_dias_uteis(proto, 10)
        self.assertEqual(limite_10, date(2026, 12, 7))

    def test_calendario_feriados_configuravel(self):
        """Garante que feriados adicionais (locais ou contratuais) podem ser configurados."""
        proto = "2026-11-23"
        # Sem feriado extra: 10 dias úteis vencem em 07/12/2026
        limite_padrao = datas.adicionar_dias_uteis(proto, 10)
        self.assertEqual(limite_padrao, date(2026, 12, 7))

        # Adiciona feriado local em 01/12/2026
        feriados_com_local = datas.obter_calendario_feriados(
            feriados_adicionais={date(2026, 12, 1): "Feriado Municipal"}
        )
        limite_com_feriado = datas.adicionar_dias_uteis(proto, 10, feriados=feriados_com_local)
        # Deve prorrogar em 1 dia útil: 08/12/2026
        self.assertEqual(limite_com_feriado, date(2026, 12, 8))

    def test_diferenciacao_resposta_conclusiva_vs_garantia_atendimento(self):
        """Verifica a distinção conceitual e quantitativa entre resposta conclusiva e garantia de atendimento."""
        proto = "2026-11-23"
        sla_resposta = datas.calcular_sla(proto, tipo_prazo="resposta_conclusiva", prazo_dias_uteis=10)
        sla_garantia = datas.calcular_sla(proto, tipo_prazo="garantia_atendimento", prazo_dias_uteis=21)

        self.assertIn("RN 623/2024", sla_resposta["tipo_prazo"])
        self.assertIn("RN 566/2022", sla_garantia["tipo_prazo"])
        self.assertEqual(sla_resposta["prazo_dias_uteis"], 10)
        self.assertEqual(sla_garantia["prazo_dias_uteis"], 21)
        self.assertNotEqual(sla_resposta["data_limite"], sla_garantia["data_limite"])

    def test_transicoes_status_sla(self):
        """Testa todas as transições de status do SLA (NO_PRAZO, ALERTA, VENCIDO, CONCLUIDO)."""
        proto = "2026-11-23"  # Vence em 07/12/2026 (10 dias úteis)

        # 25/11: 8 dias úteis restantes -> NO_PRAZO
        res_no_prazo = datas.calcular_sla(proto, data_referencia="2026-11-25")
        self.assertEqual(res_no_prazo["status"], datas.STATUS_NO_PRAZO)
        self.assertEqual(res_no_prazo["dias_uteis_restantes"], 8)
        self.assertFalse(res_no_prazo["em_atraso"])

        # 04/12: 1 dia útil restante -> ALERTA
        res_alerta = datas.calcular_sla(proto, data_referencia="2026-12-04")
        self.assertEqual(res_alerta["status"], datas.STATUS_ALERTA)
        self.assertEqual(res_alerta["dias_uteis_restantes"], 1)

        # 08/12: -1 dia útil restante -> VENCIDO
        res_vencido = datas.calcular_sla(proto, data_referencia="2026-12-08")
        self.assertEqual(res_vencido["status"], datas.STATUS_VENCIDO)
        self.assertTrue(res_vencido["em_atraso"])

        # Concluído dentro do prazo
        res_concluido_ok = datas.calcular_sla(proto, data_encerramento="2026-12-04")
        self.assertEqual(res_concluido_ok["status"], datas.STATUS_CONCLUIDO_NO_PRAZO)

        # Concluído fora do prazo
        res_concluido_atraso = datas.calcular_sla(proto, data_encerramento="2026-12-08")
        self.assertEqual(res_concluido_atraso["status"], datas.STATUS_CONCLUIDO_FORA_PRAZO)

    def test_fuso_horario_sao_paulo(self):
        """Garante que horários em UTC são convertidos corretamente para o fuso America/Sao_Paulo."""
        self.assertEqual(datas.FUSO.key, "America/Sao_Paulo")
        # 15:00 UTC = 12:00 em São Paulo (-03:00)
        utc_str = "2026-11-23T15:00:00Z"
        local = datas._data_local(utc_str)
        self.assertEqual(local.hour, 12)
        self.assertEqual(datas.data_br(utc_str), "23/11/2026 12:00")
        self.assertEqual(datas.data_guia(utc_str), "23/11/2026")

    def test_nao_persistencia_contadores_volateis(self):
        """Garante que a tabela cases armazena apenas datas pontuais e não contadores mutáveis de dias."""
        with storage.connection() as conn:
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(cases)").fetchall()}

        # Contadores que mudam com a passagem do tempo NÃO devem ser colunas da tabela
        for col_volatil in ("dias_uteis_decorridos", "dias_uteis_restantes", "status_sla"):
            self.assertNotIn(col_volatil, cols)
