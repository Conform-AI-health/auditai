import io
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import leitura, parecer
from PIL import Image, ImageDraw, ImageFont
import pymupdf

TESSERACT_DISPONIVEL = bool(leitura.localizar_tesseract() and leitura.obter_tessdata_dir())

@unittest.skipUnless(TESSERACT_DISPONIVEL, "Requer Tesseract e dados de idioma instalados")
class LeituraDocumentos(unittest.TestCase):
    def setUp(self):
        parecer.limpar_cache_extracao()

    def fixture_imagem(self, fmt="PNG", texto="Guia para auditoria\nPET para estadiamento de linfoma."):
        im = Image.new("RGB", (1300, 300), "white")
        try:
            font = ImageFont.truetype("arial.ttf", 40)
        except OSError:
            try:
                font = ImageFont.truetype("DejaVuSans.ttf", 40)
            except OSError:
                font = ImageFont.load_default()
        ImageDraw.Draw(im).multiline_text((40, 40), texto, font=font, fill="black")
        out = io.BytesIO()
        im.save(out, fmt)
        return out.getvalue()

    def fixture_pdf_digital(self, texto="Laudo anatomopatológico de lesão comprovada."):
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((40, 60), texto)
            return pdf.tobytes()

    def fixture_pdf_digitalizado(self, texto="Guia digitalizada para auditoria médica sintética."):
        with pymupdf.open() as pdf:
            p = pdf.new_page(width=800, height=400)
            p.insert_image(p.rect, stream=self.fixture_imagem("PNG", texto))
            return pdf.tobytes()

    def test_print_foto(self):
        for fmt, ext in [("PNG", "png"), ("JPEG", "jpg"), ("WEBP", "webp")]:
            with self.subTest(fmt=fmt):
                doc = parecer.ler_anexos([("guia." + ext, self.fixture_imagem(fmt))], "aurora")[0]
                self.assertIn("linfoma", doc["paginas"][0].lower())
                self.assertEqual(doc["metodo_por_pagina"], ["ocr"])

    def test_pdf_digital_preserva_extracao_texto(self):
        raw = self.fixture_pdf_digital("Pedido médico de PET-CT para linfoma de Hodgkin.")
        doc = parecer.ler_anexos([("pedido.pdf", raw)], "aurora")[0]
        self.assertEqual(doc["metodo_por_pagina"], ["texto"])
        self.assertIn("linfoma", doc["paginas"][0].lower())

    def test_pdf_digitalizado_executa_ocr(self):
        raw = self.fixture_pdf_digitalizado("Laudo anatomopatológico digitalizado com diagnóstico de linfoma.")
        doc = parecer.ler_anexos([("laudo_scan.pdf", raw)], "aurora")[0]
        self.assertEqual(doc["metodo_por_pagina"], ["ocr"])
        self.assertIn("linfoma", doc["paginas"][0].lower())

    def test_pdf_misto(self):
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((35, 50), "Guia de PET digital")
            p = pdf.new_page(width=800, height=400)
            p.insert_image(p.rect, stream=self.fixture_imagem("PNG", "Laudo com diagnóstico de linfoma."))
            raw = pdf.tobytes()
        doc = parecer.ler_anexos([("guia_mista.pdf", raw)], "aurora")[0]
        self.assertEqual(doc["metodo_por_pagina"], ["texto", "ocr"])
        self.assertIn("linfoma", doc["paginas"][1].lower())

    def test_imagem_sem_texto_ou_ilegivel(self):
        buf = io.BytesIO()
        Image.new("L", (400, 400), 255).save(buf, "PNG")
        with self.assertRaisesRegex(ValueError, "não contém texto clínico legível"):
            parecer.ler_anexos([("vazio.png", buf.getvalue())], "aurora")

    def test_documento_vazio(self):
        with self.assertRaisesRegex(ValueError, "Arquivo vazio"):
            list(leitura.paginas_visuais("documento.pdf", b""))
        with self.assertRaisesRegex(ValueError, "Arquivo vazio"):
            list(leitura.paginas_visuais("documento.png", b""))

    def test_documento_corrompido(self):
        with self.assertRaisesRegex(ValueError, "corrompido"):
            list(leitura.paginas_visuais("corrompido.pdf", b"%PDF-1.4 corrompido sem trailer"))
        with self.assertRaisesRegex(ValueError, "corrompido"):
            list(leitura.paginas_visuais("corrompido.png", b"\x89PNG\r\n\x1a\ncorrompido"))

    def test_localizacao_portavel_tesseract(self):
        exe = leitura.localizar_tesseract()
        self.assertIsNotNone(exe)
        self.assertTrue(Path(exe).is_file())
        tessdata = leitura.obter_tessdata_dir()
        self.assertIsNotNone(tessdata)
        self.assertTrue((Path(tessdata) / "por.traineddata").is_file())


class LeituraPDFHibrido(unittest.TestCase):
    def test_texto_incorporado_e_reutilizado_quando_pagina_tem_imagem(self):
        from backend import leitura
        imagem = io.BytesIO()
        Image.new("RGB", (20, 20), "white").save(imagem, "PNG")
        with pymupdf.open() as pdf:
            page = pdf.new_page()
            page.insert_text((35, 50), "Laudo anatomopatológico confirma neoplasia. Pedido médico indica PET-CT para estadiamento primário do linfoma.")
            page.insert_image(pymupdf.Rect(35, 80, 55, 100), stream=imagem.getvalue())
            raw = pdf.tobytes()
        with patch.object(leitura, "ocr", side_effect=AssertionError("OCR desnecessário")):
            paginas = list(leitura.paginas_visuais("hibrido.pdf", raw))
        self.assertEqual(paginas[0][1], "texto")
        self.assertIn("anatomopatológico", paginas[0][0])
