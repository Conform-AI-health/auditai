"""Triagem sintética TUSS × Rol; não constitui homologação clínica."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import storage,tuss_rol

class TussRolTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Path(self.tmp.name)/"test.db"
        self.patch=patch.object(storage,"DB",self.db); self.patch.start(); storage.initialize()
    def tearDown(self): self.patch.stop(); self.tmp.cleanup()

    def caso(self,code,procedure,narrative="Indicação clínica sintética",associated=None,date="2026-11-10"):
        with storage.connection() as c:
            cur=c.execute("""INSERT INTO cases(tenant_id,source_system,external_id,procedure,area,narrative,clinical_question,
            source_updated_at,last_imported_at,created_at,updated_at,guide_received_at,tuss_code,associated_tuss_codes)
            VALUES('aurora','TESTE',?,?,?,?,1,?,?,?,?,?,?,?)""",(code+procedure,procedure,"Oncologia",narrative,storage.now(),storage.now(),storage.now(),storage.now(),date,code,__import__('json').dumps(associated or [])))
            return dict(storage.case_for(c,"aurora",cur.lastrowid)),tuss_rol.triagem(c,"aurora",storage.case_for(c,"aurora",cur.lastrowid))

    def test_01_40708128_dut60(self): self.assertEqual(self.caso("40708128","PET dedicado oncológico")[1]["category"],"dut60_direta")
    def test_02_41001222_preserva_codigo(self):
        case,r=self.caso("41001222","TC para PET dedicado oncológico"); self.assertEqual((case["tuss_code"],r["category"]),("41001222","dut60_correlacionada"))
    def test_03_40708144_revisao(self): self.assertEqual(self.caso("40708144","Revisão de PET-CT por procedimento")[1]["category"],"conferencia_petct")
    def test_04_40708152_laudo(self): self.assertEqual(self.caso("40708152","Laudo evolutivo de PET-CT por procedimento")[1]["category"],"conferencia_petct")
    def test_05_neurologico_fora_rol(self): self.assertEqual(self.caso("41001311","PET-CT neurológico","Demência cerebral")[1]["category"],"avaliacao_fora_rol")
    def test_06_infeccao_fora_rol(self): self.assertEqual(self.caso("41001303","PET-CT infecção")[1]["category"],"avaliacao_fora_rol")
    def test_07_cardiologico_fora_rol(self): self.assertEqual(self.caso("41001290","PET-CT cardiológico")[1]["category"],"avaliacao_fora_rol")
    def test_08_codigo_desconhecido(self): self.assertEqual(self.caso("00000000","PET-CT")[1]["status"],"codigo_desconhecido")
    def test_09_codigo_descricao_divergente(self): self.assertEqual(self.caso("40708128","PET-CT neurológico","Demência")[1]["status"],"divergente")
    def test_10_codigos_associados_preservados(self): self.assertEqual(self.caso("41001222","PET oncológico",associated=["40708128"])[1]["associated_codes"],["40708128"])
    def test_11_versao_desatualizada(self): self.assertEqual(self.caso("40708128","PET oncológico",date="2026-01-01")[1]["status"],"fonte_nao_homologada")
    def test_12_guia_dut60_nao_desaparece(self): self.assertIn(self.caso("41001222","PET oncológico")[1]["category"],("dut60_direta","dut60_correlacionada"))
    def test_13_indicacao_fora_dut_vai_revisao(self): self.assertEqual(self.caso("40708128","PET neurológico","Demência cerebral")[1]["status"],"divergente")
    def test_14_ausencia_correlacao_nao_e_negativa(self): self.assertIn("antes de qualquer negativa",self.caso("41001311","PET neurológico")[1]["reason"])
    def test_15_requisitos_juridicos_incompletos(self):
        case,_=self.caso("41001311","PET neurológico","Demência cerebral")
        data={k:"nao_verificado" for k,_ in tuss_rol.LEGAL_ITEMS}|{"justificativa":"Fundamentação sintética ainda incompleta para decisão."}
        with storage.connection() as c:
            tuss_rol.salvar_avaliacao(c,{"tenant":"aurora","user":"auditor-aurora"},case,data)
            self.assertEqual(c.execute("SELECT result FROM out_of_rol_assessments").fetchone()[0],"Revisão jurídica e documental necessária")
    def test_16_bloqueio_negativa_automatica(self):
        case,_=self.caso("41001311","PET neurológico","Demência cerebral")
        data={k:"atendido" for k,_ in tuss_rol.LEGAL_ITEMS}|{"justificativa":"Elementos sintéticos avaliados e sem impedimento identificado."}
        with storage.connection() as c:
            tuss_rol.salvar_avaliacao(c,{"tenant":"aurora","user":"auditor-aurora"},case,data)
            self.assertIn("negativa não recomendada",c.execute("SELECT result FROM out_of_rol_assessments").fetchone()[0])
    def test_17_revisao_medica_obrigatoria(self):
        case,_=self.caso("41001311","PET neurológico","Demência cerebral")
        data={k:("nao_atendido" if k=="evidencia" else "atendido") for k,_ in tuss_rol.LEGAL_ITEMS}|{"justificativa":"Evidência científica não confirmada no conjunto documental sintético."}
        with storage.connection() as c:
            tuss_rol.salvar_avaliacao(c,{"tenant":"aurora","user":"auditor-aurora"},case,data)
            row=c.execute("SELECT result,medical_reviewed FROM out_of_rol_assessments").fetchone()
            self.assertTrue(row[0].startswith("Sugestão")); self.assertEqual(row[1],0)

if __name__=="__main__": unittest.main()
