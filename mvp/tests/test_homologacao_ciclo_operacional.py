import unittest
import tempfile
import sys
from pathlib import Path
from datetime import datetime, date
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import storage, sigo_simulado, consultas, datas, app, auth, config

class TestHomologacaoCicloOperacional(unittest.TestCase):
    """
    Homologação do ciclo operacional do AuditIA (Microimplementação 01.3).
    Valida as regras de transição de filas, ingestão, rejeição, complementação,
    saída de fila (REQ-16.1), reativação (REQ-16.2), tolerância a falhas e isolamento.
    Executa exclusivamente em banco temporário isolado.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test_homologacao.sqlite3"
        self.old_db = storage.DB
        storage.DB = self.db_path
        self.credentials = dict(storage.initialize(seed_demo_cases=False))
        self.tenant = "aurora"
        app.failures.clear()
        app._sync_locks.clear()

    def tearDown(self):
        storage.DB = self.old_db
        self.tmp.cleanup()

    def test_01_aud_nao_importar(self):
        """1. Guia na fila AUD é ignorada e não ingressa na base nem na fila ativa."""
        now_str = storage.now()
        with storage.connection() as conn:
            reg_aud = [{
                "tenant_id": self.tenant,
                "source_system": "SIGO",
                "external_id": "SIGO-AUD-TEST",
                "beneficiary_code": "BENEF-AUD",
                "procedure": "PET-CT oncológico",
                "area": "Oncologia",
                "narrative": "PET-CT oncológico em fila AUD",
                "clinical_question": True,
                "localizacao_sigo": "AUD",
                "fila": "AUD",
                "source_updated_at": now_str,
                "documents": []
            }]
            ins, dup, docs = storage.import_records(conn, self.tenant, reg_aud)
            self.assertEqual(ins, 0, "Nenhum caso deveria ser inserido para localização AUD")
            
            c_check = conn.execute("SELECT * FROM cases WHERE tenant_id=? AND external_id=?", 
                                   (self.tenant, "SIGO-AUD-TEST")).fetchone()
            self.assertIsNone(c_check, "Guia em AUD não deve existir na tabela cases")
            
            ativos = consultas.casos_da_operadora(conn, self.tenant)
            self.assertEqual(len(ativos), 0)

    def test_02_amop_sem_passagem_anterior_amm_nao_importar(self):
        """2. Guia inédita que surge diretamente na AMOP sem histórico de AMM não é importada (REQ-04)."""
        now_str = storage.now()
        with storage.connection() as conn:
            reg_amop = [{
                "tenant_id": self.tenant,
                "source_system": "SIGO",
                "external_id": "SIGO-AMOP-INEDITO",
                "beneficiary_code": "BENEF-AMOP-1",
                "procedure": "PET-CT oncológico",
                "area": "Oncologia",
                "narrative": "Guia inédita direto na AMOP",
                "clinical_question": True,
                "localizacao_sigo": "AMOP",
                "fila": "AMOP",
                "source_updated_at": now_str,
                "documents": []
            }]
            ins, dup, docs = storage.import_records(conn, self.tenant, reg_amop)
            self.assertEqual(ins, 0, "Guia inédita na AMOP não deve ser inserida")
            
            c_check = conn.execute("SELECT * FROM cases WHERE tenant_id=? AND external_id=?", 
                                   (self.tenant, "SIGO-AMOP-INEDITO")).fetchone()
            self.assertIsNone(c_check, "Guia inédita na AMOP não deve ser gravada em cases")

    def test_03_primeira_entrada_amm_importar(self):
        """3. Primeira entrada na fila AMM é importada com sucesso."""
        now_str = storage.now()
        with storage.connection() as conn:
            reg_amm = [{
                "tenant_id": self.tenant,
                "source_system": "SIGO",
                "external_id": "SIGO-AMM-ENTRADA",
                "beneficiary_code": "BENEF-AMM-1",
                "procedure": "PET-CT oncológico inicial",
                "area": "Oncologia",
                "narrative": "Primeira entrada regular na AMM",
                "clinical_question": True,
                "localizacao_sigo": "AMM",
                "fila": "AMM",
                "data_protocolo_operadora": "2026-11-20T10:00:00+00:00",
                "source_updated_at": now_str,
                "documents": []
            }]
            ins, dup, docs = storage.import_records(conn, self.tenant, reg_amm)
            self.assertEqual(ins, 1, "Guia na AMM deve ser inserida com sucesso")
            
            c_check = conn.execute("SELECT * FROM cases WHERE tenant_id=? AND external_id=?", 
                                   (self.tenant, "SIGO-AMM-ENTRADA")).fetchone()
            self.assertIsNotNone(c_check)
            self.assertEqual(c_check["localizacao_sigo"], "AMM")
            self.assertEqual(c_check["data_protocolo_operadora"], "2026-11-20T10:00:00+00:00")
            
            ativos = consultas.casos_da_operadora(conn, self.tenant)
            self.assertEqual(len(ativos), 1)
            self.assertEqual(ativos[0]["external_id"], "SIGO-AMM-ENTRADA")

    def test_04_transicao_amm_para_amop_manter_acompanhamento(self):
        """4. Guia previamente importada que transita de AMM para AMOP mantém acompanhamento sem duplicidade (REQ-12)."""
        now_str = storage.now()
        with storage.connection() as conn:
            # Entrada inicial em AMM
            reg1 = [{
                "tenant_id": self.tenant,
                "source_system": "SIGO",
                "external_id": "SIGO-FLUXO-01",
                "beneficiary_code": "BENEF-F1",
                "procedure": "PET-CT estadiamento",
                "area": "Oncologia",
                "narrative": "Caso em trânsito de filas",
                "clinical_question": True,
                "localizacao_sigo": "AMM",
                "fila": "AMM",
                "data_protocolo_operadora": "2026-11-15T10:00:00+00:00",
                "source_updated_at": now_str,
                "documents": []
            }]
            storage.import_records(conn, self.tenant, reg1)
            case_orig = conn.execute("SELECT id, localizacao_sigo FROM cases WHERE external_id='SIGO-FLUXO-01'").fetchone()
            self.assertEqual(case_orig["localizacao_sigo"], "AMM")

            # Transição para AMOP
            reg2 = [{
                "tenant_id": self.tenant,
                "source_system": "SIGO",
                "external_id": "SIGO-FLUXO-01",
                "beneficiary_code": "BENEF-F1",
                "procedure": "PET-CT estadiamento",
                "area": "Oncologia",
                "narrative": "Caso em trânsito de filas",
                "clinical_question": True,
                "localizacao_sigo": "AMOP",
                "fila": "AMOP",
                "data_protocolo_operadora": "2026-11-15T10:00:00+00:00",
                "source_updated_at": now_str,
                "documents": []
            }]
            ins, dup, _ = storage.import_records(conn, self.tenant, reg2)
            self.assertEqual(ins, 0, "Transição para AMOP não deve criar novo registro")
            self.assertEqual(dup, 1)

            cases_total = conn.execute("SELECT id, localizacao_sigo FROM cases WHERE external_id='SIGO-FLUXO-01'").fetchall()
            self.assertEqual(len(cases_total), 1, "Unicidade estrita do registro da guia")
            self.assertEqual(cases_total[0]["id"], case_orig["id"])
            self.assertEqual(cases_total[0]["localizacao_sigo"], "AMOP")

            # Permanece visível na fila para acompanhamento médico
            ativos = consultas.casos_da_operadora(conn, self.tenant)
            self.assertEqual(len(ativos), 1)
            self.assertEqual(ativos[0]["id"], case_orig["id"])

    def test_05_transicao_amop_para_amm_sem_duplicidade(self):
        """5. Guia que retorna da AMOP para a AMM atualiza localização mantendo registro único."""
        now_str = storage.now()
        with storage.connection() as conn:
            # 1. Ingressa em AMM
            reg = [{
                "tenant_id": self.tenant,
                "source_system": "SIGO",
                "external_id": "SIGO-RETORNO-01",
                "beneficiary_code": "BENEF-RET-1",
                "procedure": "PET-CT",
                "area": "Oncologia",
                "narrative": "Teste retorno",
                "clinical_question": True,
                "localizacao_sigo": "AMM",
                "source_updated_at": now_str,
                "documents": []
            }]
            storage.import_records(conn, self.tenant, reg)
            cid = conn.execute("SELECT id FROM cases WHERE external_id='SIGO-RETORNO-01'").fetchone()["id"]

            # 2. Vai para AMOP
            reg[0]["localizacao_sigo"] = "AMOP"
            storage.import_records(conn, self.tenant, reg)
            self.assertEqual(conn.execute("SELECT localizacao_sigo FROM cases WHERE id=?", (cid,)).fetchone()["localizacao_sigo"], "AMOP")

            # 3. Retorna para AMM
            reg[0]["localizacao_sigo"] = "AMM"
            ins, dup, _ = storage.import_records(conn, self.tenant, reg)
            self.assertEqual(ins, 0)
            self.assertEqual(dup, 1)

            c_final = conn.execute("SELECT id, localizacao_sigo FROM cases WHERE external_id='SIGO-RETORNO-01'").fetchall()
            self.assertEqual(len(c_final), 1)
            self.assertEqual(c_final[0]["id"], cid)
            self.assertEqual(c_final[0]["localizacao_sigo"], "AMM")

    def test_06_complementacao_documental_preserva_historico(self):
        """6. Inserção de novos documentos complementares preserva os documentos anteriores e o histórico."""
        now_str = storage.now()
        with storage.connection() as conn:
            # Ingestão com 1 documento inicial (pedido)
            reg = [{
                "tenant_id": self.tenant,
                "source_system": "SIGO",
                "external_id": "SIGO-DOCS-01",
                "beneficiary_code": "BENEF-DOCS",
                "procedure": "PET-CT oncológico",
                "area": "Oncologia",
                "narrative": "Caso para complementação documental",
                "clinical_question": True,
                "localizacao_sigo": "AMM",
                "source_updated_at": now_str,
                "documents": [{
                    "external_id": "DOC-PEDIDO-01",
                    "kind": "pedido_medico",
                    "name": "pedido_inicial.pdf",
                    "source_updated_at": now_str,
                    "content_text": "Texto pedido médico inicial",
                    "content_blob": b"%PDF-1.4 pedido",
                    "mime_type": "application/pdf"
                }]
            }]
            storage.import_records(conn, self.tenant, reg)
            cid = conn.execute("SELECT id FROM cases WHERE external_id='SIGO-DOCS-01'").fetchone()["id"]
            
            docs1 = conn.execute("SELECT * FROM documents WHERE case_id=?", (cid,)).fetchall()
            self.assertEqual(len(docs1), 1)
            self.assertEqual(docs1[0]["name"], "pedido_inicial.pdf")

            # Nova sincronização traz um segundo documento (laudo de biópsia) preservando o anterior
            reg[0]["documents"].append({
                "external_id": "DOC-BIOP-01",
                "kind": "anatomopatologico",
                "name": "laudo_biopsia.pdf",
                "source_updated_at": now_str,
                "content_text": "Texto do anatomopatológico",
                "content_blob": b"%PDF-1.4 laudo",
                "mime_type": "application/pdf"
            })
            storage.import_records(conn, self.tenant, reg)

            docs2 = conn.execute("SELECT * FROM documents WHERE case_id=? ORDER BY id", (cid,)).fetchall()
            self.assertEqual(len(docs2), 2, "Ambos os documentos devem coexistir no caso")
            self.assertEqual(docs2[0]["external_id"], "DOC-PEDIDO-01")
            self.assertEqual(docs2[1]["external_id"], "DOC-BIOP-01")
            self.assertEqual(docs2[0]["content_text"], "Texto pedido médico inicial")
            self.assertEqual(docs2[1]["content_text"], "Texto do anatomopatológico")

    def test_07_ausencia_simultanea_amm_amop_retira_fila_ativa(self):
        """7. Ausência bilateral em AMM e AMOP retira guia da fila ativa (REQ-16.1), preservando integridade."""
        tenant = self.tenant
        with storage.connection() as conn:
            # Sincroniza conjunto inicial de 4 casos
            sigo_simulado.sincronizar_sigo_simulado(conn, tenant, actor="sistema")
            casos_iniciais = consultas.casos_da_operadora(conn, tenant)
            self.assertEqual(len(casos_iniciais), 4)

            # Lote subsequente contém apenas os casos B01 e B02 (B07 e B08 ausentes em ambas as filas)
            lote_completo = sigo_simulado.gerar_lote_sigo_sintetico(tenant)
            lote_parcial = [lote_completo[0], lote_completo[1]]

            sigo_simulado.sincronizar_sigo_simulado(conn, tenant, actor="sistema", registros_custom=lote_parcial)

            # Casos B07 e B08 devem ter removido_origem_em preenchido
            c_b07 = conn.execute("SELECT removido_origem_em FROM cases WHERE external_id=?", (lote_completo[2]["external_id"],)).fetchone()
            c_b08 = conn.execute("SELECT removido_origem_em FROM cases WHERE external_id=?", (lote_completo[3]["external_id"],)).fetchone()
            self.assertIsNotNone(c_b07["removido_origem_em"])
            self.assertIsNotNone(c_b08["removido_origem_em"])

            # Fila ativa agora contém estritamente os 2 casos presentes
            ativos_apos = consultas.casos_da_operadora(conn, tenant)
            ids_apos = [c["external_id"] for c in ativos_apos]
            self.assertEqual(len(ativos_apos), 2)
            self.assertIn(lote_completo[0]["external_id"], ids_apos)
            self.assertIn(lote_completo[1]["external_id"], ids_apos)
            self.assertNotIn(lote_completo[2]["external_id"], ids_apos)
            self.assertNotIn(lote_completo[3]["external_id"], ids_apos)

            # Histórico e referências dos casos retirados permanecem no banco
            all_cases = conn.execute("SELECT count(*) FROM cases WHERE tenant_id=?", (tenant,)).fetchone()[0]
            self.assertEqual(all_cases, 4, "Nenhum caso é deletado do SQLite")

    def test_08_falha_de_sincronizacao_preserva_guias(self):
        """8. Falha na sincronização não altera nem expurga as guias da fila ativa."""
        tenant = self.tenant
        with storage.connection() as conn:
            sigo_simulado.sincronizar_sigo_simulado(conn, tenant, actor="sistema")
            antes = consultas.casos_da_operadora(conn, tenant)
            self.assertEqual(len(antes), 4)

            # Tentativa de sincronização que falha
            storage.sync_demo(conn, tenant, "sistema", "sigo", fail=True)

            # Verifica fila após a falha: permanece 100% intacta
            depois = consultas.casos_da_operadora(conn, tenant)
            self.assertEqual(len(depois), 4)
            for c_antes, c_depois in zip(antes, depois):
                self.assertEqual(c_antes["id"], c_depois["id"])
                self.assertIsNone(c_depois["removido_origem_em"])

    def test_09_reativacao_confere_identidade_e_preserva_protocolo_sla_historico(self):
        """9. Reativação cumpre 5 critérios cumulativos e restaura guia preservando protocolo, SLA e dados (REQ-16.2)."""
        tenant = self.tenant
        now_str = storage.now()
        data_proto = "2026-11-10T10:00:00+00:00"
        
        reg_original = [{
            "tenant_id": tenant,
            "source_system": "SIGO",
            "external_id": "SIGO-REAT-TEST",
            "beneficiary_code": "BENEF-REAT-001",
            "procedure": "PET-CT oncológico para estadiamento",
            "area": "Oncologia",
            "narrative": "Avaliação de nódulo mediastinal confirmado",
            "clinical_question": True,
            "data_protocolo_operadora": data_proto,
            "localizacao_sigo": "AMM",
            "fila": "AMM",
            "source_updated_at": now_str,
            "documents": [{
                "external_id": "DOC-REAT-01",
                "kind": "pedido_medico",
                "name": "pedido_reativacao.pdf",
                "source_updated_at": now_str,
                "content_text": "Texto original do pedido",
                "content_blob": b"%PDF-1.4 pedido reat"
            }]
        }]

        with storage.connection() as conn:
            # 1. Ingestão inicial
            storage.import_records(conn, tenant, reg_original)
            c = conn.execute("SELECT id, data_protocolo_operadora FROM cases WHERE external_id='SIGO-REAT-TEST'").fetchone()
            cid = c["id"]
            self.assertEqual(c["data_protocolo_operadora"], data_proto)

            # 2. Guia sai da fila (simulando ausência bilateral confirmada)
            conn.execute("UPDATE cases SET removido_origem_em=? WHERE id=?", (storage.now(), cid))
            conn.commit()
            self.assertEqual(len(consultas.casos_da_operadora(conn, tenant)), 0)

            # 3. Tentativa A: Dados divergentes (código de beneficiário diferente)
            reg_divergente = [dict(reg_original[0])]
            reg_divergente[0] = dict(reg_divergente[0])
            reg_divergente[0]["beneficiary_code"] = "BENEF-OUTRO"
            storage.import_records(conn, tenant, reg_divergente)

            c_div = conn.execute("SELECT removido_origem_em, divergence_detected FROM cases WHERE id=?", (cid,)).fetchone()
            self.assertIsNotNone(c_div["removido_origem_em"], "Não pode reativar com divergência cadastral")
            self.assertEqual(int(c_div["divergence_detected"]), 1)
            self.assertEqual(len(consultas.casos_da_operadora(conn, tenant)), 0, "Guia divergente não entra na fila ativa")

            # 4. Tentativa B: Dados idênticos legítimos nos 5 critérios
            storage.import_records(conn, tenant, reg_original)
            c_reativado = conn.execute("SELECT removido_origem_em, data_protocolo_operadora, localizacao_sigo FROM cases WHERE id=?", (cid,)).fetchone()
            self.assertIsNone(c_reativado["removido_origem_em"], "Guia deve ser reativada com sucesso")
            self.assertEqual(c_reativado["data_protocolo_operadora"], data_proto, "Data de protocolo original permanece inalterada")
            self.assertEqual(c_reativado["localizacao_sigo"], "AMM")

            # Fila ativa volta a conter a guia
            ativos = consultas.casos_da_operadora(conn, tenant)
            self.assertEqual(len(ativos), 1)
            self.assertEqual(ativos[0]["id"], cid)

            # Cálculo de SLA preserva o marco inicial original da data_protocolo_operadora
            ref_date = date(2026, 11, 20)
            prazo = datas.calcular_sla(c_reativado["data_protocolo_operadora"], data_referencia=ref_date)
            self.assertEqual(prazo["status"], "NO_PRAZO")

    def test_10_isolamento_multi_tenant_apenas_aurora_aparece(self):
        """10. Auditor da Aurora enxerga exclusivamente casos da Aurora Saúde; Horizonte permanece inacessível."""
        with storage.connection() as conn:
            # Sincroniza Aurora (4 casos)
            sigo_simulado.sincronizar_sigo_simulado(conn, "aurora", actor="sistema")
            # Insere caso na Horizonte
            reg_horiz = [{
                "tenant_id": "horizonte",
                "source_system": "SIGO",
                "external_id": "SIGO-HORIZ-01",
                "beneficiary_code": "BEN-HORIZ-1",
                "procedure": "PET-CT Horizonte",
                "area": "Oncologia",
                "narrative": "Caso Horizonte",
                "clinical_question": True,
                "localizacao_sigo": "AMM",
                "fila": "AMM",
                "source_updated_at": storage.now(),
                "documents": []
            }]
            storage.import_records(conn, "horizonte", reg_horiz)

            # Consulta com auditor da Aurora
            casos_aurora = consultas.casos_da_operadora(conn, "aurora")
            self.assertEqual(len(casos_aurora), 4)
            for c in casos_aurora:
                self.assertEqual(c["tenant_id"], "aurora")
                self.assertNotEqual(c["external_id"], "SIGO-HORIZ-01")

            # Consulta com auditor da Horizonte
            casos_horiz = consultas.casos_da_operadora(conn, "horizonte")
            self.assertEqual(len(casos_horiz), 1)
            self.assertEqual(casos_horiz[0]["tenant_id"], "horizonte")
            self.assertEqual(casos_horiz[0]["external_id"], "SIGO-HORIZ-01")

            # Isolamento direto por case_for
            cid_horiz = casos_horiz[0]["id"]
            self.assertIsNone(storage.case_for(conn, "aurora", cid_horiz), "Auditor da Aurora não pode acessar caso da Horizonte")
            self.assertIsNotNone(storage.case_for(conn, "horizonte", cid_horiz))


if __name__ == "__main__":
    unittest.main()
