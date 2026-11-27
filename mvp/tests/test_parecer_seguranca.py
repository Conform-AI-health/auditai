"""Controles sintéticos de segurança, minimização e consumo do Gemini."""
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import parecer


class Resposta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class Opener:
    def __init__(self, envelope):
        self.envelope = envelope
        self.request = None

    def open(self, request, timeout):
        self.request = request
        return Resposta(json.dumps(self.envelope).encode())


def entrada_base():
    return {
        "case": {"id": 9, "tenant_id": "aurora", "external_id": "SEGREDO-9",
                 "procedure": "PET-CT", "area": "Oncologia",
                 "narrative": "Há diagnóstico confirmado e indicação clínica.",
                 "clinical_question": "Critérios da DUT 60?", "guide_received_at": "2026-01-01"},
        "documents": [{"id": 81, "case_id": 9, "tenant_id": "aurora", "kind": "laudo",
                       "name": "laudo.pdf", "content_text": "Anatomopatológico confirma linfoma."}],
        "documentos_textuais": [],
    }


class ParecerSeguranca(unittest.TestCase):
    def setUp(self):
        parecer.limpar_cache_extracao()

    def test_contexto_minimo_remove_identificadores_e_preserva_clinica(self):
        entrada = entrada_base()
        minimo = parecer.contexto_minimo(entrada)
        serializado = json.dumps(minimo, ensure_ascii=False)
        self.assertNotIn("tenant_id", serializado)
        self.assertNotIn("external_id", serializado)
        self.assertNotIn("SEGREDO-9", serializado)
        self.assertIn("diagnóstico confirmado", serializado)
        self.assertIn("Anatomopatológico confirma linfoma", serializado)
        self.assertLess(len(serializado), len(json.dumps(entrada, ensure_ascii=False)))

    def test_selecao_literal_preserva_negativas_e_contradicoes(self):
        filler = " ".join(f"Conteúdo administrativo geral número {i}." for i in range(260))
        clinico = ("Diagnóstico de linfoma confirmado. Não há metástase distante. "
                   "Laudo anatomopatológico contradiz o pedido médico quanto ao estadiamento.")
        trechos = parecer.trechos_relevantes(filler + " " + clinico)
        unidos = " ".join(trechos)
        self.assertIn("Diagnóstico de linfoma confirmado.", unidos)
        self.assertIn("Não há metástase distante.", unidos)
        self.assertIn("contradiz o pedido médico", unidos)
        self.assertLess(len(unidos), len(filler + " " + clinico))

    def test_telemetria_limite_e_payload_minimo(self):
        corpo = {k: "conteúdo válido" for k in parecer.FIELDS}
        corpo["conclusao"] = parecer.STATUS[2]
        envelope = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(corpo)}]}}],
                    "usageMetadata": {"promptTokenCount": 123, "candidatesTokenCount": 45,
                                      "totalTokenCount": 168}, "modelVersion": "gemini-teste"}
        opener = Opener(envelope)
        with patch.object(parecer, "chave_gemini", return_value="chave-teste"), \
             patch.object(parecer, "build_opener", return_value=opener), \
             patch.dict("os.environ", {"AUDITIA_MAX_OUTPUT_TOKENS": "2048"}, clear=False):
            saida = parecer.gerar(entrada_base())
        payload = json.loads(opener.request.data)
        texto = payload["contents"][0]["parts"][0]["text"]
        self.assertEqual(payload["generationConfig"]["maxOutputTokens"], 2048)
        self.assertNotIn("tenant_id", texto)
        self.assertNotIn("SEGREDO-9", texto)
        self.assertEqual(saida["uso_tokens"]["totalTokenCount"], 168)
        self.assertEqual(saida["uso_tokens"]["modelo"], "gemini-teste")

    def test_resposta_truncada_e_inconclusiva(self):
        envelope = {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": []}}]}
        with patch.object(parecer, "chave_gemini", return_value="chave-teste"), \
             patch.object(parecer, "build_opener", return_value=Opener(envelope)):
            with self.assertRaisesRegex(parecer.AnaliseInconclusiva, "inconclusiva"):
                parecer.gerar(entrada_base())

    def test_hash_deduplica_extracao_sem_cruzar_operadoras(self):
        visual = [("Texto clínico suficientemente legível para análise.", "ocr")]
        with patch("backend.leitura.paginas_visuais", return_value=iter(visual)) as extrair:
            primeiro = parecer.ler_anexos([("imagem.png", b"mesmo-conteudo")], "aurora")[0]
        with patch("backend.leitura.paginas_visuais", side_effect=AssertionError("não deve reprocessar")):
            segundo = parecer.ler_anexos([("imagem.png", b"mesmo-conteudo")], "aurora")[0]
        with patch("backend.leitura.paginas_visuais", return_value=iter(visual)) as outra_operadora:
            parecer.ler_anexos([("imagem.png", b"mesmo-conteudo")], "horizonte")
        self.assertEqual(extrair.call_count, 1)
        self.assertEqual(outra_operadora.call_count, 1)
        self.assertEqual(primeiro["sha256"], segundo["sha256"])
        self.assertIsNone(primeiro["case_id"])


if __name__ == "__main__":
    unittest.main()
