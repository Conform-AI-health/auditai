"""Consulta documental da DUT 60. As regras do motor ficam em vigencia.py."""
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
from http.client import HTTPSConnection, HTTPException
import ipaddress
from pathlib import Path
import re
import socket
import ssl
from urllib.parse import urlsplit, urljoin, unquote

from backend.config import ROOT

import pymupdf
from backend import criterios_dut
from backend import regulatoria

ARQUIVOS = ROOT / "versoes_documentais"
MAX_BYTES = 16 * 1024 * 1024


def destino(url):
    p = urlsplit(url)
    if (p.scheme!="https" or p.netloc.lower()!="www.gov.br" or not p.path.startswith("/ans/")
        or any(v in unquote(p.path) for v in ("..","\\","//")) or p.query or p.fragment
        or len(url)>1500 or not url.isascii() or any(ord(c)<33 for c in url)):
        raise ValueError("Informe uma URL HTTPS direta em www.gov.br/ans/.")
    return p


def baixar(url):
    for _ in range(4):
        p=destino(url)
        ips=socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM)
        if not ips or not all(ipaddress.ip_address(i[4][0]).is_global for i in ips):
            raise ValueError("Destino de rede não permitido.")
        contexto=ssl.create_default_context()
        conn=HTTPSConnection(p.hostname,timeout=12,context=contexto)
        try:
            with socket.create_connection((ips[0][4][0],443),timeout=12) as tcp:
                conn.sock=contexto.wrap_socket(tcp,server_hostname=p.hostname)
                conn.request("GET",p.path,headers={"User-Agent":"AuditIA-Beta/1.0","Accept-Encoding":"identity"})
                with conn.getresponse() as response:
                    if response.status in (301,302,303,307,308):
                        url=urljoin(url,response.getheader("Location",""))
                        continue
                    if response.status!=200:
                        raise ValueError(f"Fonte respondeu HTTP {response.status}.")
                    raw=response.read(MAX_BYTES+1)
                    if len(raw)>MAX_BYTES:
                        raise ValueError("Fonte excede o limite de 16 MiB.")
                    return url,response.headers.get_content_type(),raw
        finally:
            conn.close()
    raise ValueError("Número excessivo de redirecionamentos.")


class TextoHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.texto=[]
        self.oculto=False

    def handle_starttag(self,tag,attrs):
        if tag in ("script","style"): self.oculto=True
        if tag in ("p","div","br","li","h1","h2","h3","h4","tr"): self.texto.append("\n")

    def handle_endtag(self,tag):
        if tag in ("script","style"): self.oculto=False
        if tag in ("p","div","li","h1","h2","h3","h4","tr"): self.texto.append("\n")

    def handle_data(self,data):
        if not self.oculto: self.texto.append(data)


def extrair(tipo,raw):
    if raw.startswith(b"%PDF-"):
        with pymupdf.open(stream=raw,filetype="pdf") as pdf:
            if pdf.needs_pass or len(pdf)>600: raise ValueError("PDF indisponível para extração.")
            texto="\n".join(p.get_text() for p in pdf)
    elif tipo=="text/html":
        parser=TextoHTML()
        parser.feed(raw.decode("utf-8-sig"))
        texto="".join(parser.texto)
    else:
        raise ValueError("Use HTML ou PDF textual do anexo oficial.")
    if len(texto)>4_000_000:
        raise ValueError("Texto da fonte excede o limite de extração.")
    texto=re.sub(r"[ \t\xa0]+"," ",texto.replace("\f","\n"))
    partes=list(re.finditer(r"(?im)^ *60\s*[.\-–]\s*PET[ -]CT ONCOL[ÓO]GICO *\r?$",texto))
    if len(partes)!=1: raise ValueError("Cabeçalho da DUT 60 ausente ou ambíguo.")
    secao=texto[partes[0].start():]
    fim=re.search(r"(?im)^ *61\s*[.\-–]\s*[A-ZÀ-Ü]",secao)
    if not fim or not re.search(r"(?i)cobertura obrigat[óo]ria",secao[:fim.start()]):
        raise ValueError("Delimitação da diretriz incompleta. Necessária revisão.")
    secao=secao[:fim.start()].strip()
    if len(secao)>100_000:
        raise ValueError("Extensão atípica da DUT 60. Necessária revisão.")
    return secao,texto


def consultar(conn,tenant,actor,url):
    destino(url)
    stamp=datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute("SAVEPOINT consulta_documental")
    try:
        final,tipo,raw=baixar(url)
        origem=hashlib.sha256(raw).hexdigest()
        conn.execute("INSERT OR IGNORE INTO dut_sources VALUES(?,?,?)",(origem,tipo,raw))
        trecho,original=extrair(tipo,raw)
        digest=hashlib.sha256(trecho.encode()).hexdigest()
        origem=hashlib.sha256(raw).hexdigest()
        anterior=conn.execute("SELECT body,id FROM dut_documents WHERE tenant=? AND validated_by IS NOT NULL ORDER BY id DESC LIMIT 1",(tenant,)).fetchone()
        base=anterior[0] if anterior else Path(__file__).with_name("DUT60.txt").read_text(encoding="utf-8").strip()
        status="Sem alteração" if trecho==base else "Aguardando validação"
        def meta(padrao):
            valores=set(re.findall(padrao,original,re.I))
            return valores.pop() if len(valores)==1 else "Não confirmada"
        ato=meta(r"(?:Resolução Normativa|RN)\s*(?:n[º°o.]*)?\s*(\d{2,4}(?:/\d{4})?)")
        publicacao=meta(r"publica[çc][aã]o\s*:\s*(\d{2}/\d{2}/\d{4})")
        inicio=meta(r"vig[êe]ncia\s*:\s*(\d{2}/\d{2}/\d{4})")
        cur=conn.execute("""INSERT INTO dut_documents(tenant,consulted,url,actor,status,source_hash,content_hash,body,baseline_id)
            VALUES(?,?,?,?,?,?,?,?,?)""",(tenant,stamp,final,actor,status,origem,digest,trecho,anterior[1] if anterior else None))
        nome=f"dut_60_{stamp[:10]}_{cur.lastrowid}_{digest[:12]}.md"
        ARQUIVOS.mkdir(exist_ok=True)
        md=(f"# DUT 60 · PET-CT oncológico\n\nVersão documental {digest}\n\nFonte oficial ANS: {final}\n\n"
            f"Consulta: {stamp}\n\nAto identificado: {ato}\n\nPublicação: {publicacao}\n\nVigência: {inicio}\n\n"
            f"URL solicitada: {url}\n\nSHA-256 da fonte: {origem}\n\nExtração textual sujeita à conferência humana.\n\n{trecho}\n")
        with (ARQUIVOS/nome).open("x",encoding="utf-8") as arquivo:
            arquivo.write(md)
        conn.execute("UPDATE dut_documents SET filename=? WHERE id=?",(nome,cur.lastrowid))
        spec=criterios_dut.estruturar(trecho,final,digest)
        regulatoria.capturar(conn,tenant,cur.lastrowid,actor,spec)
        conn.execute("RELEASE consulta_documental")
    except (ValueError,OSError,HTTPException,RuntimeError) as exc:
        conn.execute("ROLLBACK TO consulta_documental")
        conn.execute("RELEASE consulta_documental")
        hash_falha = None
        if "raw" in locals():
            hash_falha=hashlib.sha256(raw).hexdigest()
            conn.execute("INSERT OR IGNORE INTO dut_sources VALUES(?,?,?)",(hash_falha,tipo,raw))
        doc=conn.execute("INSERT INTO dut_documents(tenant,consulted,url,actor,status,source_hash) VALUES(?,?,?,?,?,?)",
                     (tenant,stamp,url,actor,"Falha na extração · revisar fonte",hash_falha)).lastrowid
        regulatoria.evento(conn,tenant,doc,actor,"Consulta à fonte oficial")
        if hash_falha:
            regulatoria.evento(conn,tenant,doc,actor,"Capturada")
        regulatoria.evento(conn,tenant,doc,actor,"Falha de consulta ou extração",type(exc).__name__)
        return "Consulta falhou. Confira URL, acesso e delimitação do documento."
    return status
