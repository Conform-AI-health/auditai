"""Monta o pacote PDF sintético para discussão gerencial."""
from io import BytesIO
from pathlib import Path
from datetime import datetime, timezone
from html import escape
import json
import re

from backend.datas import data_br

def _styles():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.styles import getSampleStyleSheet

    fonts = Path("C:/Windows/Fonts")
    pdfmetrics.registerFont(TTFont("AuditIA", fonts / "arial.ttf"))
    pdfmetrics.registerFont(TTFont("AuditIA-Bold", fonts / "arialbd.ttf"))
    pdfmetrics.registerFont(TTFont("AuditIA-Italic", fonts / "ariali.ttf"))
    styles = getSampleStyleSheet()
    for name in ("Normal", "BodyText"):
        styles[name].fontName = "AuditIA"
    for name in ("Title", "Heading1", "Heading2", "Heading3"):
        styles[name].fontName = "AuditIA-Bold"
    styles["Italic"].fontName = "AuditIA-Italic"
    return styles


def _resumo(case, run, output, review, documents):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

    buffer = BytesIO()
    styles = _styles()
    snapshot = json.loads(run["input_snapshot"])
    norma = snapshot.get("vigencia_simulada", {})
    referencia = json.loads(run["reference_snapshot"])
    def paragrafo(valor, estilo="BodyText"):
        texto = str(valor)
        modelo = output.get("modelo")
        if modelo:
            texto = re.sub(re.escape(modelo), "AuditIA", texto, flags=re.I)
        texto = re.sub(r"\b(?:gemini|(?:chat)?gpt|claude)(?:[-.][\w.-]+)*\b","AuditIA",texto,flags=re.I)
        return Paragraph(escape(texto).replace("\n","<br/>"), styles[estilo])
    story = [
        Paragraph("AuditIA", styles["Title"]),
        Paragraph("Relatório Técnico de Apoio à Auditoria Médica", styles["Heading2"]),
        Paragraph("Discussão com Gerência Médica", styles["Heading3"]),
        paragrafo("Emitido em " + data_br(datetime.now(timezone.utc).isoformat())),
        Spacer(1, 5 * mm),
        Paragraph("Documento sintético para revisão humana antes de qualquer decisão na operadora.", styles["Italic"]),
        Spacer(1, 7 * mm),
        Paragraph(f"Caso {case['id']} | Execução {run['id']}", styles["Heading2"]),
        paragrafo(snapshot.get("case",{}).get("narrative",case["narrative"])),
        Spacer(1, 5 * mm),
        Paragraph("Análise preliminar da AuditIA", styles["Heading2"]),
        paragrafo(output["suggestion"],"Heading3"),
        paragrafo(f'DUT 60 · {referencia.get("title","Referência")} · registro {run["reference_version_id"]}'),
        paragrafo(referencia.get("source_url","Fonte não informada")),
        paragrafo("Versão documental da DUT (SHA-256): " + output.get("dut_sha256","Não informado")),
        paragrafo(output["scope"].replace(norma["inicio"],data_br(norma["inicio"])) if norma.get("inicio") else output["scope"]),
    ]
    for campo, titulo in (("sintese", "Síntese"), ("confronto", "Confronto com a DUT 60"),
                          ("pendencias", "Pendências"), ("confiabilidade", "Limitações")):
        story.extend((Paragraph(titulo, styles["Heading3"]),
                      paragrafo(output["parecer"][campo])))
    story.extend((Spacer(1, 5 * mm), Paragraph("Revisão médica", styles["Heading2"]),
                  paragrafo(f"{review['actor']} · {data_br(review['created_at'])}"),
                  paragrafo(f"{review['position']} - {review['conformity_status'] or review['corrected_suggestion']}"),
                  paragrafo(review["note"]), PageBreak(),
                  Paragraph("Documentos importados", styles["Title"])))
    for doc in documents:
        story.extend((paragrafo(doc["name"],"Heading2"),
                      paragrafo(doc["content_text"] or "Conteúdo não transcrito.")))
    SimpleDocTemplate(buffer, pagesize=A4, rightMargin=18*mm, leftMargin=18*mm,
                      topMargin=18*mm, bottomMargin=18*mm).build(story)
    return buffer.getvalue()


def pacote(case, run, output, review, documents, assets_root):
    import pymupdf

    final = pymupdf.open()
    with pymupdf.open(stream=_resumo(case, run, output, review, documents), filetype="pdf") as summary:
        final.insert_pdf(summary)
    for doc in documents:
        if doc["content_blob"] is not None:
            suffix = Path(doc["name"]).suffix.lower()
            if suffix not in (".pdf",".png",".jpg",".jpeg",".webp",".bmp",".tif",".tiff"):
                continue
            with pymupdf.open(stream=doc["content_blob"],filetype=suffix[1:]) as source:
                if suffix == ".pdf":
                    final.insert_pdf(source)
                else:
                    with pymupdf.open(stream=source.convert_to_pdf(),filetype="pdf") as image_pdf:
                        final.insert_pdf(image_pdf)
            continue
        relative = doc["local_path"]
        if not relative:
            continue
        path = (assets_root / relative).resolve()
        if assets_root.resolve() not in path.parents or not path.is_file():
            continue
        if path.suffix.lower() == ".pdf":
            with pymupdf.open(path) as source:
                final.insert_pdf(source)
        else:
            with pymupdf.open(path) as image:
                pdf_bytes = image.convert_to_pdf()
            with pymupdf.open(stream=pdf_bytes, filetype="pdf") as source:
                final.insert_pdf(source)
    data = final.tobytes(garbage=4, deflate=True)
    final.close()
    return data
