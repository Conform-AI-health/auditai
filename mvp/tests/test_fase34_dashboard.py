import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import storage, app, consultas, datas


class TestDashboardFase34(unittest.TestCase):
    def setUp(self):
        storage.initialize()
        self.tenant = "aurora"
        self.actor = "auditor-aurora"

    def test_kpis_6_cards_dinamicos(self):
        with storage.connection() as conn:
            kpis = consultas.kpis_dashboard_medico(conn, self.tenant, self.actor, periodo="hoje")
            self.assertIn("solicitacoes", kpis)
            self.assertIn("aguardando", kpis)
            self.assertIn("em_analise", kpis)
            self.assertIn("pendencias_codificacao", kpis)
            self.assertIn("pendencias_documentais", kpis)
            self.assertIn("concluidas", kpis)
            self.assertIsInstance(kpis["solicitacoes"], int)
            self.assertIsInstance(kpis["concluidas"], int)

    def test_timer_48h_complementacao(self):
        agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
        rec_passado = agora - timedelta(hours=50)
        res_vencido = datas.calcular_prazo_complementacao_48h(rec_passado.isoformat())
        self.assertTrue(res_vencido["vencido"])
        self.assertEqual(res_vencido["horas_restantes"], 0.0)

        rec_recente = agora - timedelta(hours=10)
        res_no_prazo = datas.calcular_prazo_complementacao_48h(rec_recente.isoformat())
        self.assertFalse(res_no_prazo["vencido"])
        self.assertGreater(res_no_prazo["horas_restantes"], 35.0)

    def test_busca_beneficiario_e_filtro_card(self):
        with storage.connection() as conn:
            casos_todos = consultas.casos_da_operadora(conn, self.tenant, pagina=1)
            if casos_todos:
                primeiro = casos_todos[0]
                benef = primeiro["beneficiary_code"]
                if benef:
                    filtrados = consultas.casos_da_operadora(conn, self.tenant, busca_beneficiario=benef[:5])
                    self.assertTrue(any(c["beneficiary_code"] == benef for c in filtrados))

            # Filtro card aguardando
            aguardando = consultas.casos_da_operadora(conn, self.tenant, card_filtro="aguardando")
            for c in aguardando:
                self.assertIsNone(c["assumido_por"])

    def test_saudacao_personalizada(self):
        with storage.connection() as conn:
            # Cadastra perfil vinculado a auditor-aurora
            conn.execute("""
                INSERT OR REPLACE INTO auditor_profiles (username, tenant, name, crm, uf, email, modified, tratamento)
                VALUES ('auditor-aurora', 'aurora', 'Marina Silva', '12345', 'SP', 'marina@aurora.com', datetime('now'), 'Dra.')
            """)
            titulo, sub = storage.obter_saudacao_usuario(conn, 'aurora', 'auditor-aurora')
            self.assertEqual(titulo, "Olá, Dra. Marina!")
            self.assertIn("Bem-vinda ao AuditIA", sub)


if __name__ == "__main__":
    unittest.main()
