"""Gera anexos clínicos exclusivamente fictícios usados na demonstração."""
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

DESTINO = Path(__file__).with_name("assets") / "documentos"


def fonte(tamanho):
    for nome in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(nome, tamanho)
        except OSError:
            pass
    return ImageFont.load_default()


def pedido(extensao):
    imagem = Image.new("RGB", (1400, 980), "#f7f4ec")
    desenho = ImageDraw.Draw(imagem)
    desenho.rectangle((55, 55, 1345, 925), outline="#34495e", width=4)
    desenho.text((100, 95), "PEDIDO MEDICO - EXEMPLO FICTICIO", font=fonte(44), fill="#243342")
    linhas = [
        "Procedimento: PET-CT oncologico",
        "Indicacao clinica: estadiamento de neoplasia confirmada.",
        "Justificativa: definir extensao da doenca para planejamento.",
        "Paciente: CASO SINTETICO - SEM IDENTIFICADORES REAIS",
        "Medico solicitante ficticio - CRM 000000",
    ]
    y = 220
    for linha in linhas:
        desenho.text((105, y), linha, font=fonte(30), fill="#1f2933")
        y += 105
    caminho = DESTINO / f"pedido-medico.{extensao}"
    formato = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}[extensao]
    imagem.save(caminho, formato, quality=92)


def anatomopatologico():
    caminho = DESTINO / "laudo-anatomopatologico.pdf"
    pdfmetrics.registerFont(TTFont("AuditIA", "C:/Windows/Fonts/arial.ttf"))
    pdfmetrics.registerFont(TTFont("AuditIA-Bold", "C:/Windows/Fonts/arialbd.ttf"))
    estilos = getSampleStyleSheet()
    estilos["BodyText"].fontName = "AuditIA"
    estilos["Title"].fontName = "AuditIA-Bold"
    historia = [
        Paragraph("LAUDO ANATOMOPATOLÓGICO - EXEMPLO FICTÍCIO", estilos["Title"]),
        Spacer(1, 8 * mm),
        Paragraph("Material: biópsia de lesão tumoral.", estilos["BodyText"]),
        Spacer(1, 4 * mm),
        Paragraph("Diagnóstico: neoplasia maligna confirmada por exame histopatológico.", estilos["BodyText"]),
        Spacer(1, 4 * mm),
        Paragraph("Observação: documento sintético, sem dados de paciente e sem valor clínico.", estilos["BodyText"]),
    ]
    SimpleDocTemplate(str(caminho), pagesize=A4, rightMargin=22*mm, leftMargin=22*mm,
                      topMargin=22*mm, bottomMargin=22*mm).build(historia)


def main():
    DESTINO.mkdir(parents=True, exist_ok=True)
    for extensao in ("png", "jpg", "jpeg", "webp"):
        pedido(extensao)
    anatomopatologico()


if __name__ == "__main__":
    main()
