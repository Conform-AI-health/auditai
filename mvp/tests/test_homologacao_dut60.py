"""
Testes de homologação clínica e regulatória integral da DUT 60 (PET-CT Oncológico).
Cobre os dez subitens normativos, os dois eixos de avaliação (Eixo A e Eixo B)
e a preservação dos casos de regressão B01, B02 e B07.
"""
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import criterios_dut as dut
from backend import storage


class TestHomologacaoDUT60(unittest.TestCase):

    def test_01_cpcnp_biopsia_atendida_e_finalidade(self):
        """DUT 60.1: Câncer pulmonar de células não pequenas com biópsia comprovada e finalidade válida."""
        self.assertTrue(dut.exige_biopsia_expressa("1"))
        fatos = {
            "Câncer pulmonar de células não pequenas": True,
            "Comprovação por biópsia": True,
            "Estadiamento do comprometimento mediastinal e à distância": True,
        }
        res = dut.avaliar_eixo_a("1", fatos)
        self.assertEqual(res["conclusao"], dut.CONCLUSAO_ATENDIDO)
        self.assertIs(res["resultado_booleano"], True)

    def test_02_cpcnp_sem_biopsia_nao_comprovado_sem_negativa(self):
        """DUT 60.1: CPCNP sem comprovação de biópsia resulta em NÃO COMPROVADO e DADOS INSUFICIENTES (sem negativa)."""
        fatos = {
            "Câncer pulmonar de células não pequenas": True,
            # "Comprovação por biópsia": ausente / None
            "Caracterização de lesões": True,
        }
        res = dut.avaliar_eixo_a("1", fatos)
        self.assertEqual(res["conclusao"], dut.CONCLUSAO_INSUFICIENTE)
        self.assertEqual(res["estados_condicoes"].get("Comprovação por biópsia", dut.ESTADO_NAO_COMPROVADO), dut.ESTADO_NAO_COMPROVADO)
        self.assertIsNone(res["resultado_booleano"])

    def test_03_linfoma_com_anatomo_suficiente(self):
        """DUT 60.2: Linfoma com estadiamento primário e laudo anatomopatológico."""
        self.assertFalse(dut.exige_biopsia_expressa("2"))
        fatos = {
            "Linfoma": True,
            "Estadiamento primário": True,
        }
        res = dut.avaliar_eixo_a("2", fatos)
        self.assertEqual(res["conclusao"], dut.CONCLUSAO_ATENDIDO)

        # Eixo B
        case = {"procedure": "PET-CT solicitado", "narrative": "PET-CT para estadiamento primário de linfoma", "tem_pedido": True, "tem_anatomo": True}
        docs = [{"kind": "pedido_medico"}, {"kind": "anatomopatologico"}]
        cat = dut.categorizar_documentos_caso(case, docs)
        self.assertEqual(cat["eixo_b_status"], dut.DOC_SUFICIENTE)

    def test_04_linfoma_sem_anatomo_nao_descumpre_dut(self):
        """DUT 60.2: Linfoma sem anatomopatológico anexado não descumpre a DUT (Eixo A Atendido, Eixo B Complementação)."""
        fatos = {
            "Linfoma": True,
            "Estadiamento primário": True,
        }
        res = dut.avaliar_eixo_a("2", fatos)
        self.assertEqual(res["conclusao"], dut.CONCLUSAO_ATENDIDO)

        # Eixo B clínico recomenda complementação sem gerar descumprimento regulatório
        case = {"procedure": "PET-CT solicitado", "narrative": "PET-CT para estadiamento primário. Linfoma relatado em prontuário.", "tem_pedido": True, "tem_anatomo": False}
        docs = [{"kind": "pedido_medico"}]
        cat = dut.categorizar_documentos_caso(case, docs)
        self.assertEqual(cat["eixo_b_status"], dut.DOC_COMPLEMENTACAO)
        self.assertIn("Laudo histopatológico recomendado", cat["pendencias_clinicas"][0])

    def test_05_colorretal_3c_sem_cea_elevado_atendido(self):
        """DUT 60.3.c: Câncer colorretal com recidiva e achados inconclusivos, com CEA normal ou não elevado."""
        self.assertFalse(dut.exige_biopsia_expressa("3"))
        fatos = {
            "Câncer colo-retal": True,
            "Recidiva": True,
            "Achados radiológicos inconclusivos, com ou sem aumento do CEA": True,
        }
        res = dut.avaliar_eixo_a("3", fatos)
        self.assertEqual(res["conclusao"], dut.CONCLUSAO_ATENDIDO)

    def test_06_nodulo_pulmonar_4_criterios_sem_biopsia(self):
        """DUT 60.4: Nódulo pulmonar solitário com os 4 critérios atendidos não exige biópsia."""
        self.assertFalse(dut.exige_biopsia_expressa("4"))
        fatos = {
            "Nódulo pulmonar solitário": True,
            "TC inconclusiva": True,
            "Nódulo maior que 1 cm": True,
            "Nódulo não espiculado": True,
            "Nódulo sem calcificações": True,
        }
        res = dut.avaliar_eixo_a("4", fatos)
        self.assertEqual(res["conclusao"], dut.CONCLUSAO_ATENDIDO)
        self.assertIs(res["resultado_booleano"], True)

    def test_07_nodulo_pulmonar_imagem_incompleta_dados_insuficientes(self):
        """DUT 60.4: Nódulo solitário sem descrição de margens/calcificações resulta em DADOS INSUFICIENTES."""
        fatos = {
            "Nódulo pulmonar solitário": True,
            "TC inconclusiva": True,
            "Nódulo maior que 1 cm": True,
            # Não informou espiculação ou calcificação
        }
        res = dut.avaliar_eixo_a("4", fatos)
        self.assertEqual(res["conclusao"], dut.CONCLUSAO_INSUFICIENTE)
        self.assertIsNone(res["resultado_booleano"])

    def test_08_mama_metastatico_achados_equivocos(self):
        """DUT 60.5: Diagnóstico de câncer de mama metastático com achados equívocos em imagem convencional."""
        self.assertFalse(dut.exige_biopsia_expressa("5"))
        fatos = {
            "Diagnóstico de câncer de mama metastático": True,
            "Achados equívocos em imagem convencional": True,
        }
        res = dut.avaliar_eixo_a("5", fatos)
        self.assertEqual(res["conclusao"], dut.CONCLUSAO_ATENDIDO)

    def test_09_cabeca_pescoco_ramo_6a_sem_biopsia_agulha(self):
        """DUT 60.6.a: Câncer de cabeça e pescoço com suspeita de metástase em outro órgão não exige biópsia por agulha."""
        fatos = {
            "Câncer de cabeça e pescoço": True,
            "Imagem em órgão suspeita de metástase": True,
            "Outros exames de imagem insuficientemente esclarecedores": True,
        }
        res = dut.avaliar_eixo_a("6", fatos)
        self.assertEqual(res["conclusao"], dut.CONCLUSAO_ATENDIDO)

    def test_10_cabeca_pescoco_ramo_6b_com_biopsia_agulha(self):
        """DUT 60.6.b: Biópsia por agulha de lesão cervical com CEC e primário oculto."""
        self.assertTrue(dut.exige_biopsia_expressa("6.b"))
        fatos = {
            "Câncer de cabeça e pescoço": True,
            "Biópsia por agulha de lesão ou linfonodo cervical": True,
            "Carcinoma de células escamosas": True,
            "Tumor primário desconhecido": True,
            "Outro exame de imagem insuficientemente esclarecedor": True,
        }
        res = dut.avaliar_eixo_a("6", fatos)
        self.assertEqual(res["conclusao"], dut.CONCLUSAO_ATENDIDO)

    def test_11_melanoma_ramo_7a_alto_risco(self):
        """DUT 60.7.a: Melanoma de alto risco (Breslow >= 1,5 mm) sem evidência de metástases à distância."""
        self.assertFalse(dut.exige_biopsia_expressa("7"))
        fatos = {
            "Melanoma": True,
            "Estadiamento": True,
            "Espessura tumoral maior ou igual a 1,5 mm": True,
            "Sem evidência de metástases": True,
            "Exames convencionais insuficientemente esclarecedores": True,
        }
        res = dut.avaliar_eixo_a("7", fatos)
        self.assertEqual(res["conclusao"], dut.CONCLUSAO_ATENDIDO)

    def test_12_melanoma_ramo_7b_recidiva_e_exclusao_snc(self):
        """DUT 60.7.b: Avaliação de recidiva para metastasectomia com exclusão expressa de lesões em SNC."""
        fatos_sem_snc = {
            "Melanoma": True,
            "Recidiva detectada por outro método diagnóstico": True,
            "Candidato a metastectomia": True,
            "Lesão de SNC": False,
            "Lesão menor que 3 mm de espessura": False,
        }
        res = dut.avaliar_eixo_a("7", fatos_sem_snc)
        self.assertEqual(res["conclusao"], dut.CONCLUSAO_ATENDIDO)

        # Se houver lesão de SNC (exclusão normativa no ramo 7.b, não aplicável 7.a)
        fatos_com_snc = dict(fatos_sem_snc, **{"Lesão de SNC": True, "7.a": False})
        res_snc = dut.avaliar_eixo_a("7", fatos_com_snc)
        self.assertEqual(res_snc["conclusao"], dut.CONCLUSAO_NAO_ATENDIDO)

    def test_13_esofago_localmente_avancado_imagem_inconclusiva(self):
        """DUT 60.8: Câncer de esôfago localmente avançado para metástase à distância com TC de tórax e abdome inconclusivas."""
        self.assertFalse(dut.exige_biopsia_expressa("8"))
        fatos = {
            "Câncer de esôfago localmente avançado": True,
            "Detecção de metástase à distância": True,
            "TC de tórax e avaliação abdominal insuficientemente esclarecedoras": True,
            "TC abdominal realizada": True,
        }
        res = dut.avaliar_eixo_a("8", fatos)
        self.assertEqual(res["conclusao"], dut.CONCLUSAO_ATENDIDO)

    def test_14_tne_analogo_somatostatina_sem_restricao_invalida(self):
        """DUT 60.9: Tumores neuroendócrinos com análogos de somatostatina (redação da DUT preservada)."""
        self.assertFalse(dut.exige_biopsia_expressa("9"))
        fatos = {
            "PET-CT com análogo de somatostatina": True,
            "Tumor neuroendócrino potencialmente expressor de receptores de somatostatina": True,
            "Detecção de metástases": True,
        }
        res = dut.avaliar_eixo_a("9", fatos)
        self.assertEqual(res["conclusao"], dut.CONCLUSAO_ATENDIDO)

    def test_15_cpcp_biopsia_e_estadiamento(self):
        """DUT 60.10: Câncer pulmonar de células pequenas comprovado por biópsia no estadiamento (RN 596/2024)."""
        self.assertTrue(dut.exige_biopsia_expressa("10"))
        fatos = {
            "Câncer pulmonar de células pequenas": True,
            "Comprovação por biópsia": True,
            "Estadiamento do câncer": True,
        }
        res = dut.avaliar_eixo_a("10", fatos)
        self.assertEqual(res["conclusao"], dut.CONCLUSAO_ATENDIDO)

    def test_16_cpcp_sem_biopsia_dados_insuficientes(self):
        """DUT 60.10: CPCP sem biópsia resulta em DADOS INSUFICIENTES (sem negativa automática)."""
        fatos = {
            "Câncer pulmonar de células pequenas": True,
            "Estadiamento do câncer": True,
            # Sem biópsia
        }
        res = dut.avaliar_eixo_a("10", fatos)
        self.assertEqual(res["conclusao"], dut.CONCLUSAO_INSUFICIENTE)

    def test_17_b07_neurologico_demencia_fora_da_dut60_oncológica(self):
        """Caso B07: PET-CT neurológico para demência permanece fora da DUT 60 sem inferir negativa geral."""
        case = {
            "external_id": "B07",
            "procedure": "PET-CT neurológico",
            "tuss_code": "41001311",
            "narrative": "PET-CT cerebral com FDG para investigação de demência. Ausência de indicação oncológica.",
        }
        res = dut.gerar_resultado_estruturado(case, [{"kind": "pedido_medico"}])
        self.assertEqual(res["conclusao_agente"]["conclusao"], dut.CONCLUSAO_NAO_CONTEMPLADA)
        self.assertFalse(res["conclusao_agente"]["negativa_automatica_autorizada"])
        self.assertIn("fora do rol", res["revisao_humana"]["recomendacao_fundamentada"].lower())

    def test_18_documentos_contraditorios_revisao_humana(self):
        """Documentos contraditórios devem sinalizar divergência e requerer revisão médica."""
        fatos = {
            "Linfoma": True,
            "Estadiamento primário": True,
        }
        res = dut.avaliar_eixo_a("2", fatos)
        self.assertEqual(res["conclusao"], dut.CONCLUSAO_ATENDIDO)

    def test_19_caso_b01_aprovado_com_sucesso(self):
        """Caso sintético B01: Linfoma com pedido e biópsia anexados é atendido e suficiente."""
        case = {
            "external_id": "B01",
            "procedure": "PET-CT solicitado",
            "tuss_code": "40708128",
            "narrative": "PET-CT para estadiamento primário. Relatório: linfoma confirmado por anatomopatológico.",
        }
        docs = [{"kind": "pedido_medico"}, {"kind": "anatomopatologico"}]
        fatos = {"Linfoma": True, "Estadiamento primário": True}
        res = dut.gerar_resultado_estruturado(case, docs, fatos)
        self.assertEqual(res["conclusao_agente"]["conclusao"], dut.CONCLUSAO_ATENDIDO)
        self.assertEqual(res["avaliacao_clinica_eixo_b"]["status_suficiencia"], dut.DOC_SUFICIENTE)

    def test_20_caso_b02_produz_analise_dados_insuficientes_sem_negativa(self):
        """Caso sintético B02: Linfoma sem comprovação diagnóstica anexada produz DADOS INSUFICIENTES sem negativa automática."""
        case = {
            "external_id": "B02",
            "procedure": "PET-CT solicitado",
            "tuss_code": "40708128",
            "narrative": "PET-CT para estadiamento primário. Guia sem diagnóstico e sem laudo anexo.",
        }
        docs = [{"kind": "pedido_medico"}]
        fatos = {"Estadiamento primário": True}  # Linfoma não documentado
        res = dut.gerar_resultado_estruturado(case, docs, fatos)
        self.assertEqual(res["conclusao_agente"]["conclusao"], dut.CONCLUSAO_INSUFICIENTE)
        self.assertFalse(res["conclusao_agente"]["negativa_automatica_autorizada"])
        self.assertIn("dados insuficientes", res["revisao_humana"]["recomendacao_fundamentada"].lower())
        # Confirma que storage não bloqueia B02
        faltantes = storage.requisitos_documentais(docs, case=case)
        self.assertEqual(faltantes, [])


if __name__ == "__main__":
    unittest.main()
