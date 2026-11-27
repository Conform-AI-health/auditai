"""Leitura local de imagens e PDFs, com localização por página."""
import io
import os
import shutil
import subprocess
import sys
from pathlib import Path


def texto_adequado(texto):
    palavras = texto.split()
    return len(palavras) >= 5 or sum(c.isalnum() for c in texto) >= 40


def localizar_tesseract():
    """Localiza o binário do Tesseract de maneira portátil no sistema."""
    custom = os.environ.get("AUDITIA_TESSERACT")
    if custom and Path(custom).is_file():
        return str(Path(custom).resolve())

    no_path = shutil.which("tesseract") or shutil.which("tesseract.exe")
    if no_path:
        return str(Path(no_path).resolve())

    if sys.platform == "win32":
        candidatos = [
            Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Tesseract-OCR/tesseract.exe",
            Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Tesseract-OCR/tesseract.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Tesseract-OCR/tesseract.exe",
            Path(__file__).resolve().parents[1] / ".runtime" / "tesseract" / "tesseract.exe",
        ]
        for c in candidatos:
            if c.is_file():
                return str(c.resolve())
    else:
        for c in [Path("/usr/bin/tesseract"), Path("/usr/local/bin/tesseract"), Path("/opt/homebrew/bin/tesseract")]:
            if c.is_file():
                return str(c.resolve())
    return None


def obter_tessdata_dir():
    """Localiza o diretório tessdata com o modelo de idioma português."""
    prefixo = os.environ.get("TESSDATA_PREFIX")
    if prefixo and Path(prefixo).is_dir():
        return str(Path(prefixo).resolve())

    local = Path(__file__).resolve().parents[1] / ".runtime" / "tessdata"
    if local.is_dir() and (local / "por.traineddata").is_file():
        return str(local.resolve())

    binario = localizar_tesseract()
    if binario:
        tessdata_bin = Path(binario).parent / "tessdata"
        if tessdata_bin.is_dir() and (tessdata_bin / "por.traineddata").is_file():
            return str(tessdata_bin.resolve())

    return None


def ocr(image):
    from PIL import ImageOps
    image = ImageOps.exif_transpose(image).convert("L")
    image.thumbnail((3200, 3200))
    buf = io.BytesIO()
    ImageOps.autocontrast(image).save(buf, format="PNG")
    binary = localizar_tesseract()
    if not binary:
        raise ValueError("Leitor OCR indisponível. Confira a instalação do Tesseract ou envie imagem mais nítida.")
    comando = [binary, "stdin", "stdout"]
    tessdata_dir = obter_tessdata_dir()
    if tessdata_dir:
        comando.extend(["--tessdata-dir", tessdata_dir])
    comando.extend(["-l", os.environ.get("AUDITIA_OCR_LANG", "por"), "--psm", "3"])
    try:
        result = subprocess.run(comando, input=buf.getvalue(), capture_output=True, timeout=35)
    except (OSError, subprocess.TimeoutExpired) as err:
        raise ValueError("Leitor OCR indisponível. Confira a instalação do Tesseract ou envie imagem mais nítida.") from err
    if result.returncode:
        erro = result.stderr.decode("utf-8", errors="replace").lower()
        if not tessdata_dir and any(m in erro for m in ("failed loading language", "error opening data file", "could not initialize tesseract")):
            raise ValueError("OCR indisponível. Confira o idioma português instalado no Tesseract.")
        raise ValueError("A imagem não contém texto clínico legível para complementar a análise.")
    text = result.stdout.decode("utf-8").strip()
    if len(text) < 8:
        raise ValueError("A imagem não contém texto clínico legível para complementar a análise.")
    return text


def paginas_visuais(nome, raw):
    try:
        import pymupdf
        from PIL import Image
    except ImportError as err:
        raise ValueError("Instale as dependências listadas em requirements.txt.") from err
    if not raw:
        raise ValueError("Arquivo vazio. Forneça um documento com conteúdo legível.")
    nome_lower = nome.lower()
    if nome_lower.endswith(".pdf"):
        try:
            pdf = pymupdf.open(stream=raw, filetype="pdf")
        except Exception as err:
            raise ValueError("Arquivo PDF corrompido ou inválido.") from err
        with pdf:
            if pdf.needs_pass or not 1 <= len(pdf) <= 30:
                raise ValueError("Envie um PDF sem senha, com até 30 páginas.")
            for page in pdf:
                text = page.get_text().strip()
                if text and (not page.get_image_info() or texto_adequado(text)):
                    yield text, "texto"
                else:
                    scale = min(3, 3000 / max(page.rect.width, page.rect.height))
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csGRAY, alpha=False)
                    yield ocr(Image.frombytes("L", (pix.width, pix.height), pix.samples)), "ocr"
    else:
        try:
            im = Image.open(io.BytesIO(raw))
        except Exception as err:
            raise ValueError("Arquivo de imagem corrompido ou em formato inválido.") from err
        with im:
            if im.format not in {"PNG", "JPEG", "WEBP", "BMP", "TIFF"} or im.width * im.height > 25000000:
                raise ValueError("Use PNG, JPEG, WebP, BMP ou TIFF de até 25 megapixels.")
            yield ocr(im), "ocr"
