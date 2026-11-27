"""Parecer preliminar com Gemini, independente do checklist histórico."""
import hashlib
import json
import os
import re
import threading
import time
import unicodedata
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, build_opener, Request
from backend.config import ENV_FILE, ROOT as APP_ROOT

ROOT = Path(__file__).resolve().parent
FONTE = "Anexo II RN 465/2021, arquivo do projeto consolidado até RN 683/2026, pp. 66–68"
TUSS = {"40708128":"PET dedicado oncológico","41001222":"TC para PET dedicado oncológico",
        "40708152":"Laudo evolutivo de PET-CT por procedimento","40708144":"Revisão de PET-CT por procedimento"}
PROMPT = (ROOT / "INSTRUCOES.md").read_text(encoding="utf-8")
STATUS = ["Critérios demonstrados","Critério não atendido","Dados insuficientes para concluir","Fora do escopo configurado"]
FIELDS = ["conclusao","sintese","confronto","pendencias","confiabilidade","minuta"]
SCHEMA = {"type":"object","properties":{k:{"type":"string"} for k in FIELDS},"required":FIELDS}
SCHEMA["properties"]["conclusao"]["enum"] = STATUS
EXTRACTOR_VERSION = "documentos-v2"
_EXTRACTION_CACHE = OrderedDict()
_CACHE_LOCK = threading.Lock()
_CACHE_LIMIT = 64


class AnaliseInconclusiva(ValueError):
    pass


def _normal(texto):
    return "".join(c for c in unicodedata.normalize("NFKD", texto).lower()
                   if not unicodedata.combining(c))


def trechos_relevantes(texto):
    """Seleciona blocos literais conservadores sem resumir a evidência."""
    blocos = [b.strip() for b in re.split(r"\n\s*\n|(?<=\.)\s*(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])", texto) if b.strip()]
    if len(texto) <= 4000 or len(blocos) < 3:
        return blocos or [texto]
    termos = ("diagnostic", "neoplas", "carcin", "linfom", "tumor", "nodul", "metasta",
              "biops", "anatomopat", "pet", "estadi", "recidiv", "indicacao", "justific",
              "tratamento", "radiofarm", "resultado", "laudo", "pedido medico", "nao ",
              "sem ", "ausencia", "nega", "contrad", "exceto", "criterio")
    encontrados = {i for i, bloco in enumerate(blocos) if any(t in _normal(bloco) for t in termos)}
    if not encontrados:
        return blocos
    indices = {j for i in encontrados for j in (i - 1, i, i + 1) if 0 <= j < len(blocos)}
    return [blocos[i] for i in sorted(indices)]


def contexto_minimo(entrada):
    caso = entrada["case"]
    contexto = {"case": {k:caso.get(k) for k in ("procedure", "area", "narrative",
                "clinical_question", "guide_received_at")}}
    contexto["documents"] = [{"documento":str(d["id"]), "origem":"sistema_operadora",
        "tipo":d.get("kind"), "nome":d.get("name"),
        "trechos":trechos_relevantes(d.get("content_text") or "")} for d in entrada["documents"]]
    contexto["documentos_textuais"] = []
    for doc in entrada.get("documentos_textuais", []):
        paginas = [{"pagina":i, "metodo":doc["metodo_por_pagina"][i-1],
                    "trechos":trechos_relevantes(texto)}
                   for i, texto in enumerate(doc["paginas"], 1)]
        contexto["documentos_textuais"].append({k:doc[k] for k in
            ("documento", "nome", "origem", "substitui_documento_obrigatorio", "sha256")} | {"paginas":paginas})
    return contexto


def limpar_cache_extracao():
    with _CACHE_LOCK:
        _EXTRACTION_CACHE.clear()

class SemRedirecionamento(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None

def chave_gemini():
    chave = os.environ.get("GEMINI_API_KEY", "").strip()
    if chave:
        return chave
    for arquivo in (ENV_FILE, APP_ROOT / ".env"):
        try:
            linhas = arquivo.read_text(encoding="utf-8-sig").splitlines()
        except FileNotFoundError:
            continue
        except (OSError, UnicodeError) as err:
            raise ValueError("Confira se o arquivo .env pode ser lido como UTF-8.") from err
        for linha in linhas:
            nome, separador, valor = linha.partition("=")
            if separador and nome.strip() == "GEMINI_API_KEY":
                chave = valor.strip()
                if len(chave) >= 2 and chave[0] == chave[-1] and chave[0] in ("'", '"'):
                    chave = chave[1:-1].strip()
                if chave:
                    return chave
    raise ValueError("Preencha GEMINI_API_KEY no arquivo .env na raiz do projeto.")

def modelo_gemini():
    m = os.environ.get("AUDITIA_MODELO", "").strip()
    if m:
        return m
    for arquivo in (ENV_FILE, APP_ROOT / ".env"):
        try:
            for linha in arquivo.read_text(encoding="utf-8-sig").splitlines():
                k, s, v = linha.partition("=")
                if s and k.strip() == "AUDITIA_MODELO" and v.strip():
                    return v.strip().strip("'\"")
        except Exception:
            pass
    return "gemini-3-flash-preview"

def gerar(entrada, norma=None):
    dut = norma["texto"] if norma else (ROOT / "DUT60.txt").read_text(encoding="utf-8")
    fonte = FONTE if norma is None else norma.get("fonte","Ensaio fictício de vigência desde " + norma["inicio"])
    modelo = modelo_gemini()
    chave = chave_gemini()
    contexto = {"fonte": fonte, "dut": dut, "tuss": TUSS, "caso": contexto_minimo(entrada)}
    schema = SCHEMA
    if norma and "estrutura" in norma:
        def registros(campos):
            return {"type":"array","items":{"type":"object","properties":{k:{"type":"string"} for k in campos},"required":campos}}
        citacao_campos = ["criterio","fato","documento","trecho","valor"]
        citacao_props = {k:{"type":"string"} for k in
                         [*citacao_campos,"origem","pagina","hash","metodo"]}
        adicionais={"item_dut":{"type":"string"},"citacoes":{"type":"array","items":{"type":"object",
                    "properties":citacao_props,"required":citacao_campos}},
                    "estados_criterios":registros(["criterio","estado"])}
        schema={"type":"object","properties":{**SCHEMA["properties"],**adicionais},"required":[*FIELDS,*adicionais]}
        contexto["criterios_homologados"]=norma["estrutura"]["criterios"]
        contexto["logica_dos_itens"]=norma["estrutura"]["grupos"]
    try:
        max_output_tokens = int(os.environ.get("AUDITIA_MAX_OUTPUT_TOKENS", "4096"))
    except ValueError as err:
        raise ValueError("AUDITIA_MAX_OUTPUT_TOKENS deve ser um número inteiro.") from err
    if not 512 <= max_output_tokens <= 8192:
        raise ValueError("AUDITIA_MAX_OUTPUT_TOKENS deve ficar entre 512 e 8192.")
    payload = {
        "systemInstruction": {"parts": [{"text": PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(contexto, ensure_ascii=False)}]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens":max_output_tokens,
                             "responseMimeType": "application/json",
                             "responseJsonSchema": schema},
    }
    url = "https://generativelanguage.googleapis.com/v1beta/models/" + quote(modelo, safe="") + ":generateContent"
    request = Request(url, method="POST", data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json", "x-goog-api-key": chave})
    inicio = time.monotonic()
    try:
        with build_opener(SemRedirecionamento()).open(request, timeout=240) as resposta:
            envelope = json.load(resposta)
        candidato = envelope["candidates"][0]
        if candidato["finishReason"] != "STOP":
            raise AnaliseInconclusiva("A análise ficou inconclusiva porque a resposta do modelo não foi finalizada.")
        partes = candidato["content"]["parts"]
        p = json.loads("".join(parte["text"] for parte in partes if not parte.get("thought")))
        if (not isinstance(p,dict) or any(not isinstance(p.get(k),str) or not p[k].strip() for k in FIELDS)
            or p["conclusao"] not in STATUS):
            raise ValueError()
    except AnaliseInconclusiva:
        raise
    except (URLError,OSError,ValueError,KeyError,IndexError,TypeError,AttributeError) as err:
        raise ValueError("Parecer indisponível. Confira a conexão, a chave, a cota e o modelo Gemini configurado. Tente novamente.") from err
    usage = envelope.get("usageMetadata") or {}
    uso_tokens = {k:usage.get(k) for k in ("promptTokenCount", "candidatesTokenCount",
                  "totalTokenCount", "cachedContentTokenCount")}
    uso_tokens.update(modelo=envelope.get("modelVersion", modelo),
                      duracao_ms=round((time.monotonic()-inicio)*1000))
    auditoria = {k:p.get(k) for k in ("item_dut","estados_criterios","citacoes") if k in schema["properties"]}
    return {**auditoria,"suggestion":p["conclusao"],"criteria":[],"scope":fonte,"parecer":{k:p[k] for k in FIELDS},
        "modelo":envelope.get("modelVersion",modelo),"modelo_solicitado":modelo,
        "versao_modelo":envelope.get("modelVersion"),"prompt":PROMPT,"dut_sha256":hashlib.sha256(dut.encode()).hexdigest(),
        "fonte_integral":dut,"tuss_consultada":TUSS,"review_required":True,"uso_tokens":uso_tokens}

def ler_anexos(anexos, tenant):
    if not tenant:
        raise ValueError("Operadora necessária para processar os anexos.")
    if len(anexos)>8:
        raise ValueError("Use até oito documentos por caso.")
    fontes=[]
    total=0
    for i,(nome,raw) in enumerate(anexos,1):
        nome_seguro = Path(nome).name[:120]
        if not nome_seguro:
            raise ValueError("Arquivo complementar sem nome.")
        digest = hashlib.sha256(raw).hexdigest()
        suffix = Path(nome_seguro).suffix.lower()
        cache_key = (tenant, digest, suffix, EXTRACTOR_VERSION,
                     os.environ.get("AUDITIA_OCR_LANG", "por"),
                     os.environ.get("AUDITIA_TESSERACT", "tesseract"))
        with _CACHE_LOCK:
            cached = _EXTRACTION_CACHE.get(cache_key)
            if cached:
                _EXTRACTION_CACHE.move_to_end(cache_key)
        if cached:
            paginas, metodos = deepcopy(cached)
        else:
            metodos = []
        if not cached and nome_seguro.lower().endswith((".pdf",".png",".jpg",".jpeg",".webp",".bmp",".tif",".tiff")):
            from backend.leitura import paginas_visuais
            paginas=[]
            try:
                for texto,metodo in paginas_visuais(nome_seguro,raw):
                    paginas.append(texto)
                    metodos.append(metodo)
            except ValueError:
                raise
            except Exception as err:
                raise ValueError("Arquivo ilegível. Envie uma cópia nítida em formato suportado.") from err
        elif not cached and nome_seguro.lower().endswith(".txt"):
            metodos=["texto"]
            try:
                paginas=[raw.decode("utf-8-sig").strip()]
            except UnicodeError as err:
                raise ValueError("Salve o TXT em UTF-8.") from err
        elif not cached:
            raise ValueError("Use PNG, JPEG, WebP, PDF ou TXT em UTF-8.")
        if not cached:
            with _CACHE_LOCK:
                _EXTRACTION_CACHE[cache_key] = deepcopy((paginas, metodos))
                _EXTRACTION_CACHE.move_to_end(cache_key)
                while len(_EXTRACTION_CACHE) > _CACHE_LIMIT:
                    _EXTRACTION_CACHE.popitem(last=False)
        if not paginas or any(not p for p in paginas):
            raise ValueError("Documento com página sem texto. Forneça transcrição do documento sintético.")
        total+=sum(map(len,paginas))
        if total>18000:
            raise ValueError("Documentação extensa para este protótipo. Use um caso sintético menor.")
        fontes.append({"documento":f"C{i}","case_id":None,"nome":nome_seguro,"origem":"complemento_medico_auditor",
                       "substitui_documento_obrigatorio":False,"paginas":paginas,
                       "metodo_por_pagina":metodos,"sha256":digest})
    return fontes
