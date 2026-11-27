"""AuditIA: aplicação local demonstrativa com fronteiras explícitas de operadora."""

import sys
from pathlib import Path

_MVP_DIR = Path(__file__).resolve().parent.parent
if str(_MVP_DIR) not in sys.path:
    sys.path.insert(0, str(_MVP_DIR))

from email.parser import BytesParser
from email.policy import default
import getpass
import hashlib
from html import unescape
from http.cookies import CookieError, SimpleCookie
import json
import mimetypes
import re
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode
import webbrowser
from wsgiref.simple_server import make_server

from backend import administracao, auth, config, consultas, fonte_ans, homologacao, parecer, regulatoria, relatorio, sigo_simulado, storage, tuss_rol, vigencia
from backend.config import BASE, DOCUMENT_ASSETS, REVIEW_LIMIT, ROOT, STATIC, TERM_VERSION
from backend.engine import analyze
from frontend import administracao as telas_admin
from frontend import documentacao, fila, painel_dut, telas, tuss_rol as painel_tuss
from frontend.telas import form, h, layout

failures = []
_sync_locks = {}
_analise_locks = set()
_analise_mutex = threading.Lock()


def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def app(env, start):
    path, method = env.get("PATH_INFO", "/"), env["REQUEST_METHOD"]
    api_request = path == "/api" or path.startswith("/api/")
    if api_request:
        path = path.removeprefix("/api") or "/"
    query = parse_qs(env.get("QUERY_STRING", ""), keep_blank_values=True)
    headers = [("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
               ("Content-Security-Policy",
                "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; "
                "form-action 'self'; base-uri 'none'")]

    def reply(body, status="200 OK", mime="text/html", extra=None):
        if api_request and mime == "text/html":
            clean = unescape(re.sub(r"<[^>]+>", " ", str(body)))
            clean = " ".join(clean.split())
            payload = {"ok": status.startswith("2"),
                       "message": "Operação realizada com sucesso." if status.startswith("2") else clean}
            body, mime = json.dumps(payload, ensure_ascii=False), "application/json"
        start(status, headers + [("Content-Type", mime + "; charset=utf-8")] + (extra or []))
        return [body.encode("utf-8")]

    def binary(body, mime, filename):
        start("200 OK", headers + [("Content-Type", mime),
              ("Content-Disposition", f'inline; filename="{filename}"'),
              ("X-Content-Type-Options", "nosniff"),
              ("Content-Length", str(len(body)))])
        return [body]

    def download_original(body,filename):
        start("200 OK",headers+[("Content-Type","application/octet-stream"),
              ("Content-Disposition",f'attachment; filename="{filename}"'),("Content-Length",str(len(body)))])
        return [body]

    def redirect(url):
        if api_request:
            return reply(json.dumps({"ok": True, "message": "Operação realizada com sucesso.",
                                     "redirect": url}, ensure_ascii=False), mime="application/json")
        return reply("", "303 See Other", extra=[("Location", url)])

    host = env.get("HTTP_HOST", "")
    allowed_hosts = {
        "127.0.0.1:8765", "localhost:8765",
        "127.0.0.1:5000", "localhost:5000",
        f"127.0.0.1:{config.PORT}", f"localhost:{config.PORT}"
    }
    if host not in allowed_hosts:
        return reply("Endereço inválido.", "400 Bad Request")
    if path == "/colar.js" and method == "GET":
        return reply((STATIC / "colar.js").read_text(encoding="utf-8"),mime="application/javascript")
    if path == "/fluxos.js" and method == "GET":
        return reply((STATIC / "fluxos.js").read_text(encoding="utf-8"),mime="application/javascript")
    if path == "/app.js" and method == "GET":
        return reply((STATIC / "app.js").read_text(encoding="utf-8"),mime="application/javascript")
    if path == "/bootstrap.min.css" and method == "GET":
        return reply((STATIC / "bootstrap.min.css").read_text(encoding="utf-8"),mime="text/css")
    if path == "/bootstrap.bundle.min.js" and method == "GET":
        return reply((STATIC / "bootstrap.bundle.min.js").read_text(encoding="utf-8"),mime="application/javascript")
    if path == "/estilo.css" and method == "GET":
        return reply((STATIC / "estilo.css").read_text(encoding="utf-8"), mime="text/css")
    if path == "/favicon.ico" and method == "GET":
        fav = STATIC / "favicon.ico"
        if fav.exists():
            return binary(fav.read_bytes(), "image/x-icon", "favicon.ico")
    if (path.startswith("/img/") or path.startswith("/static/img/")) and method == "GET":
        img_name = path.rsplit("/", 1)[-1]
        img_path = STATIC / "img" / img_name
        if img_path.exists() and img_path.is_file():
            ext = img_name.rsplit(".", 1)[-1].lower()
            mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "svg": "image/svg+xml", "ico": "image/x-icon"}
            return binary(img_path.read_bytes(), mime_map.get(ext, "application/octet-stream"), img_name)
    if (path.startswith("/fonts/") or path.startswith("/static/fonts/")) and method == "GET":
        font_name = path.rsplit("/", 1)[-1]
        font_path = STATIC / "fonts" / font_name
        if font_path.exists() and font_path.is_file() and font_name.endswith(".woff2"):
            return binary(font_path.read_bytes(), "font/woff2", font_name)
    cookies = SimpleCookie()
    try:
        cookies.load(env.get("HTTP_COOKIE", ""))
    except CookieError:
        pass
    sid = cookies["auditia"].value if "auditia" in cookies else ""
    current = time.time()

    def set_session(claims):
        token = auth.issue(claims)
        headers.append(("Set-Cookie", auth.cookie(token)))
        return claims, token

    session = auth.verify(sid)
    if method == "GET" and path in ("/landing", "/inicio"):
        return reply(telas.landing_page(session))
    if method == "GET" and path == "/" and ("auditia" not in cookies or (session and session.get("role") == "login")):
        return reply(telas.landing_page(session))
    if method == "GET" and path in ("/entrar", "/login"):
        if not session or session.get("role") != "login":
            session, sid = set_session({"user":"_login", "tenant":"_login", "tenant_name":"AuditIA",
                                        "role":"login", "csrf":secrets.token_urlsafe(32)})
        return reply(telas.login_page(session))
    if not session:
        return reply("Autenticação necessária.", "401 Unauthorized") if api_request else redirect("/entrar")
    if api_request and path == "/session" and method == "GET":
        return reply(json.dumps({"ok":True, "user":session.get("user"), "tenant":session.get("tenant"),
                                 "role":session.get("role")}, ensure_ascii=False), mime="application/json")
    data = {}
    anexos = []
    documentos_enviados = {}
    if method == "POST":
        try:
            size = int(env.get("CONTENT_LENGTH") or 0)
        except ValueError:
            return reply("Formulário inválido.", "400 Bad Request")
        if size < 1 or size > (5_000_000 if path in ("/parecer", "/caso/documentos") else 64000):
            return reply("Formulário inválido.", "400 Bad Request")
        raw = env["wsgi.input"].read(size)
        ctype = env.get("CONTENT_TYPE","")
        if path in ("/parecer", "/caso/documentos") and ctype.startswith("multipart/form-data"):
            if "\r" in ctype or "\n" in ctype:
                return reply("Formulário inválido.","400 Bad Request")
            msg = BytesParser(policy=default).parsebytes(("Content-Type: "+ctype+"\r\n\r\n").encode()+raw)
            for part in msg.iter_parts():
                name = part.get_param("name",header="content-disposition")
                filename = part.get_filename()
                if path == "/parecer" and filename and name == "anexo":
                    anexos.append((filename,part.get_payload(decode=True) or b""))
                elif path == "/caso/documentos" and filename and name in ("pedido_medico","anatomopatologico"):
                    if name in documentos_enviados:
                        return reply("Envie apenas um arquivo para cada tipo de documento.", "400 Bad Request")
                    documentos_enviados[name] = (filename,part.get_payload(decode=True) or b"")
                elif name in ("csrf","case_id"):
                    data[name] = part.get_content()
        else:
            data = {k:v[0] for k,v in parse_qs(raw.decode("utf-8","replace")).items()}
        if data.get("csrf") != session["csrf"]:
            return reply("Sessão inválida.", "403 Forbidden")
    with storage.connection() as conn:
        if method == "POST" and path in ("/entrar", "/login"):
            failures[:] = [t for t in failures if t > current - 60]
            if len(failures) >= 8:
                return reply("Aguarde um minuto.", "429 Too Many Requests")
            username = data.get("username", "")
            user = conn.execute("""SELECT users.*,tenants.name AS tenant_name FROM users
                JOIN tenants ON tenants.id=users.tenant_id WHERE username=?""",
                (username,)).fetchone()
            if not user or conn.execute("SELECT 1 FROM auditor_disabled WHERE username=?",(username,)).fetchone() or not storage.check_password(user, data.get("password", "")):
                failures.append(current)
                if user:
                    storage.audit(conn,user["tenant_id"],username,"login","session",username,"negado")
                return reply(telas.acesso_recusado(),
                             "401 Unauthorized")
            session, sid = set_session({"user":username, "tenant":user["tenant_id"],
                                        "tenant_name":user["tenant_name"], "role":user["role"],
                                        "csrf":secrets.token_urlsafe(32)})
            storage.audit(conn,session["tenant"],username,"login","session",username)
            return redirect("/" if user["role"]=="admin" else "/termo")
        if session.get("role") == "login":
            return reply("Autenticação necessária.", "401 Unauthorized") if api_request else redirect("/entrar")
        tenant, actor = session["tenant"], session["user"]
        current_user = conn.execute("SELECT role,tenant_id FROM users WHERE username=?",
                                    (actor,)).fetchone()
        if not current_user or current_user["tenant_id"] != tenant or conn.execute("SELECT 1 FROM auditor_disabled WHERE username=?",(actor,)).fetchone():
            headers.append(("Set-Cookie",auth.clear_cookie()))
            return reply("Autenticação expirada ou revogada.", "401 Unauthorized") if api_request else redirect("/entrar")
        session["role"] = current_user["role"]
        auditor = session["role"] == "auditor"
        admin = session["role"] == "admin"

        def denied(action, kind, obj, case_id=None):
            storage.audit(conn,tenant,actor,action,kind,obj,"negado",case_id)
            return reply("Acesso não permitido nesta operadora ou perfil.", "403 Forbidden")

        if not admin and session.get("termo") != TERM_VERSION:
            if path == "/termo" and method == "GET":
                return reply(telas.terms_page(session))
            if path == "/termo" and method == "POST":
                if data.get("recusa") == "1":
                    headers.append(("Set-Cookie",auth.clear_cookie()))
                    storage.audit(conn,tenant,actor,"recusa_termo_ia","term",TERM_VERSION)
                    return redirect("/entrar")
                if data.get("aceite") != "1":
                    return reply("O aceite explícito é necessário para continuar.", "400 Bad Request")
                conn.execute("INSERT INTO session_acceptances VALUES(?,?,?,?,?)",
                             (hashlib.sha256(sid.encode()).hexdigest(),tenant,actor,TERM_VERSION,storage.now()))
                storage.audit(conn,tenant,actor,"aceite_termo_ia","term",TERM_VERSION)
                conn.commit()
                session = {**session, "termo":TERM_VERSION}
                session, sid = set_session(session)
                return redirect("/")
            if path != "/sair":
                return redirect("/termo")
        if path == "/termo":
            return redirect("/")

        if path in ("/auditores","/telemetria","/trilha"):
            if not admin: return denied("administracao","perfil","admin")
            try:
                if path=="/auditores" and method=="POST":
                    cred = administracao.salvar_auditor(conn,session,data)
                    if cred:
                        session = {**session, "cred_auditor":cred}
                        session, sid = set_session(session)
                    return redirect("/auditores")
                if method!="GET": return reply("Método inválido.","405 Method Not Allowed")
                if path=="/trilha":
                    return reply(layout("Trilha de Auditoria e Governança",telas_admin.trilha_auditoria(conn,session,query),session))
                if path=="/telemetria":
                    return reply(layout("Telemetria da Auditoria",telas_admin.telemetria(conn,session,query),session))
                body=telas_admin.auditores(conn,session,query,form)
                cred=session.get("cred_auditor")
                if cred:
                    session = {key:value for key,value in session.items() if key != "cred_auditor"}
                    session, sid = set_session(session)
                if cred: body=telas.credencial_inicial(cred)+body
                return reply(layout("Gestão de Auditores",body,session))
            except ValueError as exc:
                return reply(h(exc),"400 Bad Request")
        if path.startswith("/regulatoria/guia/"):
            run=storage.run_for(conn,tenant,path.split("/")[-1])
            if not auditor or not run: return denied("conferencia_regulatoria","run","guia")
            try:
                if method=="POST":
                    regulatoria.conferir(conn,session,run,data)
                    return redirect(path+"?"+urlencode({"item":data["item"]}))
                if method=="GET":
                    return reply(layout("Conferência regulatória da guia",painel_dut.conferencia(conn,session,run,query.get("item",[""])[0],form),session))
            except ValueError as exc:
                return reply(h(exc),"400 Bad Request")
        if path=="/tuss-rol":
            if not admin: return denied("gestao_tuss_rol","correlacao","tuss-rol")
            try:
                if method=="GET": return reply(layout("Correlação TUSS × Rol",painel_tuss.painel(conn,session,form),session))
                if method!="POST": return reply("Método inválido.","405 Method Not Allowed")
                if data.get("acao")=="criar_revisao": tuss_rol.criar_revisao(conn,tenant,actor)
                elif data.get("acao")=="homologar": tuss_rol.homologar(conn,tenant,data.get("version_id"),actor,data.get("revisado")=="1")
                else: raise ValueError("Ação de correlação indisponível.")
                storage.audit(conn,tenant,actor,"gestao_tuss_rol","version",data.get("version_id","nova"))
                return redirect(path)
            except ValueError as exc:
                return reply(h(exc),"409 Conflict")
        if path=="/regulatoria" or path.startswith(("/regulatoria/original/","/regulatoria/criterios/")):
            if not admin: return denied("gestao_regulatoria","dut","60")
            try:
                if path=="/regulatoria" and method=="GET":
                    return reply(layout("Auditoria Regulatória — DUT 60",painel_dut.painel(conn,session,query,form),session))
                if method=="POST" and path=="/regulatoria":
                    if data.get("acao")=="consultar":
                        fonte_ans.consultar(conn,tenant,actor,data.get("url","").strip())
                    elif data.get("acao")=="finalizar":
                        regulatoria.finalizar(conn, tenant, data.get("doc"), actor, data.get("revisado")=="1")
                    else:
                        raise ValueError("Ação indisponível. Atualize o painel de revisão.")
                    return redirect(path)
                if method=="GET":
                    doc=path.split("/")[-1]
                    if path.startswith("/regulatoria/original/"):
                        original=conn.execute("""SELECT s.original FROM dut_documents d JOIN dut_sources s ON s.hash=d.source_hash
                            WHERE d.tenant=? AND d.id=?""",(tenant,doc)).fetchone()
                        if original:
                            ext="pdf" if original[0].startswith(b"%PDF-") else "html"
                            return download_original(original[0],f"dut-{int(doc)}.{ext}")
                    else:
                        regra=conn.execute("SELECT spec FROM regulatory_rules WHERE tenant=? AND doc=?",(tenant,doc)).fetchone()
                        if regra: return reply(regra[0],mime="application/json")
                    return reply("Versão indisponível.","404 Not Found")
            except (ValueError,TypeError) as exc:
                regulatoria.evento(conn,tenant,None,actor,"Operação regulatória recusada",type(exc).__name__)
                return reply(h(exc),"409 Conflict")
        if config.BETA:
            if path.startswith("/dut/arquivo/") and method=="GET":
                if not admin: return denied("consulta_dut","dut","60")
                doc=conn.execute("SELECT filename FROM dut_documents WHERE tenant=? AND id=?",(tenant,path.split("/")[-1])).fetchone()
                if not doc or not doc[0]: return reply("Arquivo indisponível.","404 Not Found")
                arquivo = fonte_ans.ARQUIVOS/doc[0]
                if not arquivo.is_file(): return reply("Arquivo indisponível.","404 Not Found")
                return reply(arquivo.read_text(encoding="utf-8"),mime="text/markdown",
                             extra=[("Content-Disposition",f'attachment; filename="{doc[0]}"')])
            if path == "/beta/vigencia":
                if not admin:
                    return denied("consulta_vigencia","dut","60")
                vigencia.preparar(conn,tenant)
                if method == "POST":
                    if not admin:
                        return denied("alteracao_vigencia","dut","60")
                    acao = data.get("acao")
                    if acao=="consultar":
                        try:
                            fonte_ans.consultar(conn,tenant,actor,data.get("url","").strip())
                        except ValueError as exc:
                            return reply(h(exc),"400 Bad Request")
                        return redirect(path)
                    if acao=="validar_documento":
                        try:
                            regulatoria.verificar(conn,tenant,data.get("documento"))
                        except ValueError as exc:
                            regulatoria.evento(conn,tenant,None,actor,"Validação documental recusada",type(exc).__name__)
                            return reply(h(exc),"409 Conflict")
                        mudou=conn.execute("""UPDATE dut_documents SET validated_by=?,status='Validado documentalmente'
                            WHERE tenant=? AND id=? AND filename IS NOT NULL AND validated_by IS NULL
                            AND NOT EXISTS (SELECT 1 FROM dut_documents d WHERE d.tenant=dut_documents.tenant
                                AND d.validated_by IS NOT NULL AND d.id>dut_documents.id)""",
                            (actor,tenant,data.get("documento"))).rowcount
                        if not mudou: return reply("Versão indisponível.","409 Conflict")
                        storage.audit(conn,tenant,actor,"validacao_documental","dut",data["documento"])
                        return redirect(path)
                    if acao == "propor":
                        try:
                            mudou = vigencia.propor(conn,tenant)
                        except ValueError as exc:
                            return reply(h(exc),"409 Conflict")
                    elif acao == "aprovar":
                        mudou = conn.execute("UPDATE dut_ensaio SET aprovado_por=? WHERE tenant=? AND inicio=? AND aprovado_por IS NULL",
                                             (actor,tenant,vigencia.NOVA)).rowcount
                    else:
                        return reply("Ação inválida.","400 Bad Request")
                    if mudou:
                        storage.audit(conn,tenant,actor,acao+"_dut_ficticia","dut","60")
                    return redirect("/beta/vigencia")
                nova=conn.execute("SELECT aprovado_por FROM dut_ensaio WHERE tenant=? AND inicio=?",(tenant,vigencia.NOVA)).fetchone()
                estado="Aprovada" if nova and nova[0] else ("Pendente de aprovação" if nova else "Ainda não proposta")
                body = telas.resumo_vigencia(path,session,nova,estado)
                try:
                    historico = documentacao.painel(conn,session,form,query)
                except ValueError as exc:
                    return reply(h(exc),"400 Bad Request")
                return reply(layout("Ensaio de vigência da DUT",body+historico,session))
            if path in ("/operadora","/caso/criar","/caso/alterar","/analisar","/sincronizar","/integracoes"):
                return reply("Função indisponível na homologação fechada.","403 Forbidden")
            if auditor and path == "/" and method == "GET":
                return redirect("/beta")
            if path == "/beta":
                if not auditor or method not in ("POST","GET"):
                    return denied("homologacao","bateria","beta")
                if method == "POST":
                    codigo = data.get("codigo","").strip()
                    estado = data.get("estado","")
                    guia = data.get("guia","").strip()
                    status_guia = data.get("status_guia","")
                    if data.get("limpar"):
                        codigo, estado, guia, status_guia = "", "", "", ""
                    if (not re.fullmatch(r"[\w.-]{0,64}",codigo) or not re.fullmatch(r"[\w.-]{0,64}",guia)
                        or estado not in ("",*homologacao.ESTADOS)
                        or status_guia not in ("","Pendente","Autorizada","Negada")):
                        return reply("Filtro inválido.","400 Bad Request")
                    session = {key:value for key,value in session.items() if key != "filtro"}
                    if not data.get("limpar"):
                        session["filtro"] = [codigo,estado,guia,status_guia]
                    session, sid = set_session(session)
                    return redirect("/beta")
                pagina = query.get("pagina",["1"])[0]
                if not re.fullmatch(r"[1-9][0-9]{0,6}",pagina):
                    return reply("Página inválida.","400 Bad Request")
                filtros = list(session.get("filtro",["","","",""]))
                filtros += [""] * (4-len(filtros))
                codigo,estado,guia,status_guia = filtros[:4]
                if (not re.fullmatch(r"[\w.-]{0,64}",codigo) or not re.fullmatch(r"[\w.-]{0,64}",guia)
                    or estado not in ("",*homologacao.ESTADOS)
                    or status_guia not in ("","Pendente","Autorizada","Negada")):
                    return reply("Filtro inválido.","400 Bad Request")
                filtro = telas.filtros_fila(session,codigo,estado,guia,status_guia)
                homologacao.carregar(conn,tenant,storage.now())
                return reply(layout("Painel de auditoria médica",fila.painel(conn,tenant,codigo,estado,guia,status_guia,int(pagina),filtro),session))
            if path == "/beta/resultados.csv":
                if not admin or method != "GET":
                    return denied("exportacao_beta","bateria","beta")
                homologacao.carregar(conn,tenant,storage.now())
                rows = homologacao.resultados(conn,tenant)
                storage.audit(conn,tenant,actor,"exportacao_beta","bateria","beta")
                return reply(homologacao.csv_resultados(rows),mime="text/csv",
                             extra=[("Content-Disposition","attachment; filename=auditia-beta.csv")])
        if method == "POST" and path == "/sair":
            storage.audit(conn,tenant,actor,"logout","session",actor)
            headers.append(("Set-Cookie",auth.clear_cookie()))
            return redirect("/entrar")
        if method == "GET" and path == "/":
            try:
                return reply(telas.cases_page(conn, session, query))
            except ValueError as exc:
                return reply(h(exc),"400 Bad Request")
        if method == "GET" and path == "/gerencia":
            return reply("Módulo gerencial desabilitado na versão Beta 0.2.", "404 Not Found")
        if method == "GET" and path == "/integracoes":
            if not admin:
                return denied("consulta_integracoes","connector","lista")
            return reply(telas.integrations_page(conn, session))
        if method == "POST" and path == "/sincronizar":
            if not (admin or auditor):
                return denied("sincronizacao","connector",data.get("connector",""))
            connector = data.get("connector", "")
            retry_text = data.get("retry_job", "")
            
            # REQ-12.1: Guarda de concorrência contra execuções simultâneas duplicadas
            lock_key = f"{tenant}:{connector}"
            agora_ts = time.time()
            if lock_key in _sync_locks and (agora_ts - _sync_locks[lock_key]) < 60:
                return reply("Sincronização em andamento. Aguarde a conclusão da execução atual.", "409 Conflict")
            
            _sync_locks[lock_key] = agora_ts
            try:
                retry_id = int(retry_text) if retry_text else None
                if connector.lower() == "sigo":
                    if data.get("simulate_failure") == "1":
                        storage.sync_demo(conn, tenant, actor, "sigo", fail=True, retry_of=retry_id)
                    else:
                        sigo_simulado.sincronizar_sigo_simulado(conn, tenant, actor=actor)
                else:
                    storage.sync_demo(conn, tenant, actor, connector,
                                      fail=data.get("simulate_failure") == "1", retry_of=retry_id)
            except (ValueError, OverflowError):
                return reply("Sincronização inválida.", "400 Bad Request")
            finally:
                _sync_locks.pop(lock_key, None)
            return redirect("/integracoes" if admin else "/")
        if method == "POST" and path == "/caso/assumir":
            cid = data.get("case_id", "")
            case = storage.case_for(conn, tenant, cid)
            if not auditor or not case:
                return denied("assuncao_caso", "case", cid)
            sucesso = storage.assumir_caso(conn, tenant, case["id"], actor, role=session.get("role", "auditor"))
            if not sucesso:
                return reply("Guia em análise por outro médico auditor.", "409 Conflict")
            return redirect(f"/caso/{cid}")
        if method == "POST" and path == "/caso/devolver":
            cid = data.get("case_id", "")
            case = storage.case_for(conn, tenant, cid)
            if not auditor or not case:
                return denied("devolucao_caso", "case", cid)
            sucesso = storage.devolver_caso_fila(conn, tenant, case["id"], actor, role=session.get("role", "auditor"))
            if not sucesso:
                return reply("Você não é o responsável ativo desta guia para devolvê-la.", "403 Forbidden")
            return redirect("/")
        if method == "POST" and path == "/caso/finalizar":
            cid = data.get("case_id","")
            case = storage.case_for(conn,tenant,cid)
            if not auditor or not case:
                return denied("alteracao_fluxo_caso","case",cid)
            # REQ-08 / REQ-09.1: Somente o auditor com posse válida e não expirada da trava pode finalizar
            if not storage.verificar_posse_trava(conn, tenant, case["id"], actor):
                # Se o caso estiver livre (ninguém assumiu), assume atomicamente
                if not storage.assumir_caso(conn, tenant, case["id"], actor, role=session.get("role", "auditor")):
                    return reply("Trava médica expirada ou caso assumido por outro auditor. Operação rejeitada.", "403 Forbidden")
            run = conn.execute("""SELECT r.* FROM runs r WHERE r.tenant_id=? AND r.case_id=?
                ORDER BY r.id DESC LIMIT 1""",(tenant,case["id"])).fetchone()
            status, run_id, action = "finalizado", run["id"] if run else None, "finalizacao_caso"
            conn.execute("""INSERT INTO case_workflow(tenant,case_id,status,run_id,actor,updated_at)
                VALUES(?,?,?,?,?,?) ON CONFLICT(tenant,case_id) DO UPDATE SET
                status=excluded.status,run_id=excluded.run_id,actor=excluded.actor,
                updated_at=excluded.updated_at""",
                (tenant,case["id"],status,run_id,actor,storage.now()))
            # Libera a trava ao finalizar
            conn.execute("UPDATE cases SET assumido_por=NULL, trava_expira_em=NULL, updated_at=? WHERE tenant_id=? AND id=?",
                         (storage.now(), tenant, case["id"]))
            storage.event(conn,tenant,case["id"],
                          "Finalização do caso",
                          actor,run["correlation"] if run and run["correlation"] else f'case-{case["id"]}')
            storage.audit(conn,tenant,actor,action,"case",case["id"],case_id=case["id"])
            return redirect("/")
        if method == "POST" and path == "/caso/criar":
            if not auditor:
                return denied("criacao_caso","case","novo")
            narrative = data.get("narrative","").strip() or "Consultar documentação anexa."
            if not 1 <= len(narrative) <= 6000:
                return reply("Resumo inválido.", "400 Bad Request")
            original = "MAN-" + secrets.token_hex(6).upper()
            created = storage.now()
            cur = conn.execute("""INSERT INTO cases
                (tenant_id,source_system,external_id,procedure,area,narrative,
                clinical_question,source_updated_at,last_imported_at,created_at,updated_at)
                VALUES(?,'MANUAL',?,'PET-CT oncológico (fictício)','Oncologia',?,?,?,?,?,?)""",
                (tenant, original, narrative, int(data.get("question") == "1"),
                 created,created,created,created))
            storage.event(conn,tenant,cur.lastrowid,"Entrada da guia",actor,f"entrada-{cur.lastrowid}")
            storage.audit(conn,tenant,actor,"criacao_caso","case",cur.lastrowid,case_id=cur.lastrowid)
            return redirect(f'/caso/{cur.lastrowid}')
        if method == "POST" and path == "/caso/documentos":
            cid = data.get("case_id","")
            case = storage.case_for(conn,tenant,cid)
            if not auditor or not case:
                return denied("recebimento_documental","case",cid)
            docs = consultas.documentos_da_guia(conn,tenant,case["id"])
            faltantes = storage.requisitos_documentais(docs, case=case)
            kinds = {doc["kind"] for doc in docs}
            tipos_faltantes = {"pedido_medico","anatomopatologico"} - kinds
            if not faltantes:
                return reply("Os documentos fundamentais deste caso já estão completos.", "409 Conflict")
            tipos_enviados = set(documentos_enviados)
            if not tipos_enviados:
                return reply("Selecione ao menos um documento para enviar.", "400 Bad Request")
            if tipos_enviados - tipos_faltantes:
                return reply("O tipo de documento selecionado já está vinculado ao caso.", "409 Conflict")
            if any(not raw for _, raw in documentos_enviados.values()):
                return reply("O arquivo selecionado está vazio.", "400 Bad Request")
            uploads = [(kind, documentos_enviados[kind]) for kind in ("pedido_medico","anatomopatologico")
                       if kind in documentos_enviados]
            try:
                extraidos = parecer.ler_anexos([arquivo for _, arquivo in uploads],tenant)
            except ValueError as exc:
                return reply(h(exc), "422 Unprocessable Entity")
            correlation = secrets.token_hex(10)
            stamp = storage.now()
            for (kind, (filename, raw)), extraido in zip(uploads,extraidos):
                nome = extraido["nome"]
                mime = mimetypes.guess_type(nome)[0] or "application/octet-stream"
                sha = hashlib.sha256(raw).hexdigest()
                ext_method = "PDF_DIGITAL" if mime == "application/pdf" else "OCR_IMAGEM"
                conn.execute("""INSERT INTO documents
                    (tenant_id,case_id,source_system,external_id,kind,name,source_updated_at,last_imported_at,
                     mime_type,content_text,content_blob,source_sha256,extraction_method,verification_status)
                    VALUES(?,?, 'AUDITORIA',?,?,?,?,?,?,?,?,?,?,'NAO_CONFERIDO')""",
                    (tenant,case["id"],f"UPLOAD-{secrets.token_urlsafe(18)}-{kind}",kind,nome,
                     stamp,stamp,mime,"\n\n".join(extraido["paginas"]),raw,sha,ext_method))
            storage.event(conn,tenant,case["id"],"Recebimento documental",actor,correlation,
                          detail=json.dumps({"tipos": [kind for kind, _ in uploads]},ensure_ascii=False))
            storage.marcar_novos_documentos_recebidos(conn, tenant, case["id"])
            storage.audit(conn,tenant,actor,"recebimento_documental","case",case["id"],case_id=case["id"])
            return redirect(f'/caso/{case["id"]}')
        if method == "POST" and path == "/caso/encaminhar-complementacao":
            cid = data.get("case_id", "")
            case = storage.case_for(conn, tenant, cid)
            if not auditor or not case:
                return denied("encaminhar_complementacao", "case", cid)
            if not storage.verificar_posse_trava(conn, tenant, case["id"], actor):
                if not storage.assumir_caso(conn, tenant, case["id"], actor, role=session.get("role", "auditor")):
                    return reply("Guia em análise por outro médico auditor.", "409 Conflict")
            storage.registrar_encaminhamento_complementacao(conn, tenant, case["id"], actor, role=session.get("role", "auditor"))
            storage.audit(conn, tenant, actor, "encaminhar_complementacao", "case", case["id"], case_id=case["id"])
            return redirect(f"/caso/{cid}")
        if method == "POST" and path == "/caso/alterar":
            cid = data.get("case_id","")
            case = storage.case_for(conn,tenant,cid)
            if not auditor or not case:
                return denied("alteracao_caso","case",cid)
            narrative = data.get("narrative","").strip()
            if not 1 <= len(narrative) <= 6000:
                return reply("Resumo inválido.", "400 Bad Request")
            conn.execute("""UPDATE cases SET narrative=?,clinical_question=?,updated_at=?
                WHERE tenant_id=? AND id=?""",
                (narrative,int(data.get("question") == "1"),storage.now(),tenant,cid))
            storage.audit(conn,tenant,actor,"alteracao_caso","case",cid,case_id=case["id"])
            return redirect(f'/caso/{cid}')
        if method == "GET" and path.startswith("/caso/"):
            cid = path.removeprefix("/caso/")
            case = storage.case_for(conn,tenant,cid)
            if not auditor or not case:
                return denied("consulta_caso","case",cid)
            storage.audit(conn,tenant,actor,"consulta_caso","case",cid,case_id=case["id"])
            transient = "revisao_salva" in session
            page = telas.case_page(conn,case,session)
            if transient:
                session = {key:value for key,value in session.items() if key != "revisao_salva"}
                session, sid = set_session(session)
            return reply(page)
        if method=="POST" and path=="/fora-rol":
            cid=data.get("case_id","")
            case=storage.case_for(conn,tenant,cid)
            if not auditor or not case: return denied("avaliacao_fora_rol","case",cid)
            try:
                tuss_rol.salvar_avaliacao(conn,session,case,data)
            except ValueError as exc:
                return reply(h(exc),"400 Bad Request")
            return redirect(f'/caso/{cid}')
        if method == "POST" and path == "/sigo/sincronizar":
            if not admin:
                return denied("administracao", "sigo", "admin")
            sigo_simulado.sincronizar_sigo_simulado(conn, tenant, actor=actor)
            return redirect("/trilha?acao=sincronizacao_sigo")
        if method == "POST" and path == "/documento/conferir":
            did = data.get("document_id", "")
            cid = data.get("case_id", "")
            doc = storage.document_for(conn, tenant, did)
            if not auditor or not doc:
                return denied("conferencia_documental", "document", did)
            status_conf = data.get("status", "CONFERIDO")
            divergences = data.get("divergences", "").strip()
            prof = conn.execute("SELECT crm, uf, name FROM auditor_profiles WHERE username=? AND tenant=?", (actor, tenant)).fetchone()
            medico_info = f"Dr(a). {prof['name']} (CRM {prof['crm']}/{prof['uf']})" if prof else actor
            try:
                storage.set_document_verification(conn, tenant, did, actor, status_conf, divergences, verified_by_info=medico_info)
            except ValueError as exc:
                return reply(h(exc), "400 Bad Request")
            return redirect(f"/caso/{cid}")
        if method == "POST" and path == "/documento/corrigir-transcricao":
            did = data.get("document_id", "")
            cid = data.get("case_id", "")
            doc = storage.document_for(conn, tenant, did)
            if not auditor or not doc:
                return denied("correcao_ocr", "document", did)
            content_text = data.get("content_text", "").strip()
            change_summary = data.get("change_summary", "").strip()
            if not content_text:
                return reply("Texto de transcrição não pode ser vazio.", "400 Bad Request")
            try:
                storage.save_document_transcription(conn, tenant, did, content_text, actor, "CORRECAO_MANUAL", change_summary, case_id=cid)
            except ValueError as exc:
                return reply(h(exc), "400 Bad Request")
            return redirect(f"/caso/{cid}")
        if method == "POST" and path == "/caso/evidencia/vincular":
            cid = data.get("case_id", "")
            case = storage.case_for(conn, tenant, cid)
            if not auditor or not case:
                return denied("vincular_evidencia", "case", cid)
            fact_key = data.get("fact_key", "").strip()
            fact_value = data.get("fact_value", "").strip()
            did = data.get("document_id") or None
            try:
                page = int(data.get("page_number") or 1)
            except ValueError:
                page = 1
            snippet = data.get("snippet", "").strip()
            status_ev = data.get("status", "NAO_CONFERIDO")
            storage.save_clinical_evidence(conn, tenant, cid, fact_key, fact_value, did, page, snippet, status_ev, actor=actor)
            return redirect(f"/caso/{cid}")
        if method == "POST" and path == "/caso/minuta/gerar":
            cid = data.get("case_id", "")
            case = storage.case_for(conn, tenant, cid)
            if not auditor or not case:
                return denied("gerar_minuta", "case", cid)
            if not storage.verificar_posse_trava(conn, tenant, case["id"], actor):
                if not storage.assumir_caso(conn, tenant, case["id"], actor, role=session.get("role", "auditor")):
                    return reply("Guia em análise por outro médico auditor.", "409 Conflict")
            else:
                storage.renovar_trava_caso(conn, tenant, case["id"], actor)
            modality = data.get("modality", "AUTOMATICO")
            mod_forcar = None if modality == "AUTOMATICO" else modality
            from backend import minutas
            try:
                minutas.gerar_e_salvar_minuta(conn, tenant, cid, actor=actor, modalidade_forcar=mod_forcar)
            except ValueError as exc:
                return reply(h(exc), "400 Bad Request")
            return redirect(f"/caso/{cid}")
        if method == "POST" and path == "/caso/minuta/acao":
            draft_id = data.get("draft_id", "")
            cid = data.get("case_id", "")
            case = storage.case_for(conn, tenant, cid)
            if not auditor or not case:
                return denied("acao_minuta", "regulatory_draft", draft_id)
            if not storage.verificar_posse_trava(conn, tenant, case["id"], actor):
                return reply("Trava médica expirada ou caso pertencente a outro auditor. Operação rejeitada.", "403 Forbidden")
            storage.renovar_trava_caso(conn, tenant, case["id"], actor)
            acao = data.get("acao", "")
            draft_text = data.get("draft_text", "")
            justification = data.get("justification", "").strip()
            draft = conn.execute("SELECT * FROM regulatory_drafts WHERE tenant_id=? AND id=?", (tenant, draft_id)).fetchone()
            if not draft:
                return reply("Minuta não encontrada.", "404 Not Found")
            if acao == "aprovar":
                status_novo = "APROVADO_MEDICO"
                prof = conn.execute("SELECT crm, uf, name FROM auditor_profiles WHERE username=? AND tenant=?", (actor, tenant)).fetchone()
                aprovador = f"Dr(a). {prof['name']} (CRM {prof['crm']}/{prof['uf']})" if prof else actor
                justif = justification or f"Minuta aprovada formalmente por {aprovador}. Documento interno de apoio à decisão."
            elif acao == "descartar":
                status_novo = "DESCARTADO"
                justif = justification or "Minuta descartada pelo médico auditor."
            elif acao == "editar":
                status_novo = "EM_EDICAO"
                justif = justification or "Edição manual do texto da minuta pelo médico auditor."
            else:
                return reply("Ação de minuta inválida.", "400 Bad Request")
            storage.save_regulatory_draft(
                conn, tenant, cid, draft["modality"], draft["title"], draft["normative_basis"],
                draft["clinical_summary"], draft["criteria_analysis"], draft["conclusion"],
                draft["reanalysis_conditions"], draft_text or draft["draft_text"], actor,
                status=status_novo, justification=justif
            )
            return redirect(f"/caso/{cid}")
        if method == "POST" and path == "/caso/protocolo":
            cid = data.get("case_id", "")
            case = storage.case_for(conn, tenant, cid)
            if not auditor or not case:
                return denied("ajuste_protocolo", "case", cid)
            nova_data = data.get("data_protocolo", "").strip()
            justificativa = data.get("justificativa", "").strip()
            if not nova_data or not justificativa:
                return reply("Nova data e justificativa obrigatória são necessárias.", "400 Bad Request")
            old_date = case["data_protocolo_operadora"]
            conn.execute("UPDATE cases SET data_protocolo_operadora=?, updated_at=? WHERE tenant_id=? AND id=?",
                         (nova_data, storage.now(), tenant, cid))
            storage.record_governance_event(
                conn, tenant, actor, "auditor", "ajuste_data_protocolo", "case", cid,
                case_id=cid, old_value=old_date, new_value=nova_data, justification=justificativa
            )
            return redirect(f"/caso/{cid}")
        if method == "GET" and path.startswith("/documento/"):
            sub = path.removeprefix("/documento/")
            is_visualizar = False
            if sub.endswith("/visualizar"):
                did = sub.removesuffix("/visualizar")
                is_visualizar = True
            else:
                did = sub
            if query.get("modo", [""])[0] == "inline" or query.get("visualizar", [""])[0] == "1":
                is_visualizar = True
            doc = storage.document_for(conn,tenant,did)
            if not auditor or not doc or not storage.case_for(conn,tenant,doc["case_id"]):
                return denied("consulta_documento","document",did)
            storage.audit(conn,tenant,actor,"consulta_documento","document",did,
                          case_id=doc["case_id"])
            if doc["content_blob"] is not None:
                extension = Path(doc["name"]).suffix.lower()
                filename = f'{doc["kind"]}{extension}'
                return binary(doc["content_blob"],doc["mime_type"] or "application/octet-stream",filename)
            if doc["local_path"]:
                target = (DOCUMENT_ASSETS / doc["local_path"]).resolve()
                if DOCUMENT_ASSETS.resolve() not in target.parents or not target.is_file():
                    return reply("Arquivo sintético indisponível.", "404 Not Found")
                return binary(target.read_bytes(),doc["mime_type"] or "application/octet-stream",target.name)
            if is_visualizar:
                return reply("Documento original não disponível para visualização.", "404 Not Found")
            return reply(telas.documento_page(doc,did,session))
        if method == "POST" and path in ("/parecer","/analisar"):
            cid = data.get("case_id","")
            case = storage.case_for(conn,tenant,cid)
            if not auditor or not case:
                return denied("analise","case",cid)
            # REQ-08 / REQ-10: Trava médica obrigatória antes da execução clínica do parecer/análise
            posse = storage.verificar_posse_trava(conn, tenant, case["id"], actor)
            if not posse:
                # Se não possuir, tenta assumir atomicamente
                if not storage.assumir_caso(conn, tenant, case["id"], actor, role=session.get("role", "auditor")):
                    return reply("Guia em análise por outro médico auditor. Acesso bloqueado para edição.", "409 Conflict")
            else:
                storage.renovar_trava_caso(conn, tenant, case["id"], actor)

            # Prevenção de execuções concorrentes e cliques consecutivos duplicados
            lock_key = (tenant, str(case["id"]))
            with _analise_mutex:
                if lock_key in _analise_locks:
                    return reply("Análise com IA já em andamento para esta guia. Aguarde a conclusão do processamento.", "409 Conflict")
                _analise_locks.add(lock_key)

            try:
                if config.BETA and case["source_system"] not in ("BETA","VIGENCIA","SIGO"):
                    return reply("Use a bateria fechada.","403 Forbidden")
                if path=="/parecer" and config.BETA:
                    rota=tuss_rol.registrar_triagem(conn,tenant,case,actor)
                    if rota["category"] not in ("dut60_direta","dut60_correlacionada") or rota["status"]!="triado":
                        return reply("A classificação TUSS × Rol exige revisão antes de aplicar a DUT 60.","409 Conflict")
                correlation = secrets.token_hex(10)
                ultimo = time.monotonic()
                def registrar(etapa, status="concluído", versao=None, detalhe=None):
                    nonlocal ultimo
                    instante = time.monotonic()
                    storage.event(conn,tenant,case["id"],etapa,actor,correlation,status,
                                  round((instante-ultimo)*1000),versao,detalhe)
                    ultimo = instante
                ck = storage.latest_approved(conn,tenant,"checklist")
                rf = storage.latest_approved(conn,tenant,"reference")
                if not ck or not rf:
                    registrar("Consulta às referências","bloqueado")
                    return reply("Não há versões aprovadas para análise.", "409 Conflict")
                docs = conn.execute("""SELECT * FROM documents WHERE tenant_id=? AND case_id=? ORDER BY id""",
                                    (tenant,case["id"])).fetchall()
                if path == "/parecer":
                    registrar("Identificação da DUT do fluxo",versao="DUT 60")
                    faltantes = storage.requisitos_documentais(docs, case=case)
                    registrar("Validação documental","pendência" if faltantes else "concluído")
                    if faltantes:
                        registrar("Identificação de pendências","documentação incompleta")
                        storage.audit(conn,tenant,actor,"pendencia_documental","case",cid,"bloqueado",case_id=cid)
                        missing_kinds = {"pedido_medico","anatomopatologico"} - {doc["kind"] for doc in docs}
                        page = telas.pendencia_documental(faltantes,cid,session,missing_kinds)
                        if api_request:
                            message = "Documentos obrigatórios ausentes: " + "; ".join(faltantes)
                            return reply(json.dumps({"ok":False,"message":message,
                                                     "redirect":f"/caso/{case['id']}"},
                                                    ensure_ascii=False),
                                         "422 Unprocessable Entity",mime="application/json")
                        return reply(page,"422 Unprocessable Entity")
                input_copy = {
                    "case": {key:case[key] for key in
                             ("id","tenant_id","source_system","external_id","procedure","tuss_code","associated_tuss_codes",
                              "area","narrative","clinical_question","source_updated_at","updated_at","guide_received_at")},
                    "documents": [{key:d[key] for key in
                                   ("id","case_id","tenant_id","source_system","external_id","kind","name","source_updated_at","content_text")}
                                  for d in docs],
                }
                if path == "/parecer":
                    registrar("Extração dos campos dos documentos importados")
                checklist, reference = json.loads(ck["content"]), json.loads(rf["content"])
                if path == "/parecer":
                    try:
                        fase = "Extração dos anexos"
                        input_copy["documentos_textuais"] = parecer.ler_anexos(anexos, tenant)
                        for complemento in input_copy["documentos_textuais"]:
                            complemento["case_id"] = case["id"]
                        if anexos:
                            registrar(fase)
                        fase = "Consulta à versão da DUT"
                        if config.BETA and case["source_system"] == "VIGENCIA":
                            dia = case["external_id"]
                            norma = vigencia.selecionar(conn,tenant,dia)
                            input_copy["vigencia_simulada"] = {"data_caso":dia,"inicio":norma["inicio"],"aprovado_por":norma["aprovado_por"]}
                        elif config.BETA:
                            c_dict = dict(case) if hasattr(case, "keys") else (case if isinstance(case, dict) else {})
                            dia = c_dict.get("guide_received_at") or c_dict.get("data_protocolo_operadora")
                            norma = regulatoria.selecionar(conn,tenant,dia)
                            if not norma:
                                registrar(fase,"REGRA_NAO_VALIDADA")
                                return reply(telas.regra_nao_validada(session),"409 Conflict")
                        else:
                            norma = None
                        registrar(fase,versao=norma["inicio"] if norma else parecer.FONTE)
                        fase = "Avaliação dos critérios e geração de recomendação"
                        output = parecer.gerar(input_copy,norma) if norma else parecer.gerar(input_copy)
                        if norma and "estrutura" in norma:
                            input_copy = {**input_copy,"regra_regulatoria":norma}
                        registrar(fase,versao=output.get("modelo"))
                        registrar("Identificação de pendências","avaliação incluída no parecer")
                    except (ValueError, Exception) as exc:
                        registrar(fase,"erro",detalhe=type(exc).__name__)
                        storage.audit(conn,tenant,actor,"parecer_indisponivel","case",cid,case_id=cid)
                        return reply(telas.parecer_pendente(exc, cid, session),"422 Unprocessable Entity")
                else:
                    output = analyze(input_copy["case"],input_copy["documents"],checklist,reference)
                    registrar("Avaliação do checklist histórico",versao=str(ck["version"]))
                    output["scope"] = "Checklist histórico, sem inferência. " + output["scope"]
                cur = conn.execute("""INSERT INTO runs(tenant_id,case_id,actor,created_at,input_snapshot,
                    checklist_version_id,checklist_snapshot,reference_version_id,reference_snapshot,original_output)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (tenant,case["id"],actor,storage.now(),dump(input_copy),
                     ck["id"],dump(checklist),rf["id"],dump(reference),dump(output)))
                conn.execute("UPDATE runs SET correlation=? WHERE id=?",(correlation,cur.lastrowid))
                if path=="/parecer":
                    regulatoria.registrar_guia(conn,tenant,storage.run_for(conn,tenant,cur.lastrowid),actor,output.get("item_dut",""))
                    uso = output.get("uso_tokens")
                    if uso:
                        detalhe = json.dumps({k:uso.get(k) for k in ("promptTokenCount","candidatesTokenCount",
                                              "totalTokenCount","cachedContentTokenCount")},separators=(",",":"))
                        storage.event(conn,tenant,case["id"],"Consumo do Gemini",actor,correlation,
                                      duration=uso.get("duracao_ms"),version=uso.get("modelo"),detail=detalhe)
                registrar("Disponibilização para revisão médica")
                storage.audit(conn,tenant,actor,"analise","run",cur.lastrowid,case_id=case["id"])
                anchor = f'#parecer-{cur.lastrowid}' if path == "/parecer" else ""
                return redirect(f'/caso/{cid}{anchor}')
            finally:
                with _analise_mutex:
                    _analise_locks.discard(lock_key)
        if method == "POST" and path == "/revisar":
            rid = data.get("run_id","")
            run = storage.run_for(conn,tenant,rid)
            if not auditor or not run:
                return denied("revisao","run",rid)
            # REQ-08 / REQ-09.1: Somente o médico com posse válida da trava pode salvar revisão
            if not storage.verificar_posse_trava(conn, tenant, run["case_id"], actor):
                return reply("Trava médica expirada ou caso assumido por outro auditor. Operação rejeitada.", "403 Forbidden")
            storage.renovar_trava_caso(conn, tenant, run["case_id"], actor)
            position = data.get("position")
            conformity = data.get("conformity")
            note = data.get("note","").strip()
            if position not in ("Concordo","Discordo") or conformity not in ("Conforme","Não conforme") or not 1<=len(note)<=REVIEW_LIMIT:
                return reply("Informe conformidade, concordância e observação médica.","400 Bad Request")
            created = storage.now()
            existing = conn.execute("""SELECT id FROM reviews WHERE tenant_id=? AND run_id=?
                AND stage='conclusao' ORDER BY id DESC LIMIT 1""",(tenant,run["id"])).fetchone()
            if existing:
                review_id = existing["id"]
                conn.execute("""UPDATE reviews SET actor=?,created_at=?,position=?,note=?,
                    corrected_suggestion='',conformity_status=? WHERE tenant_id=? AND id=?""",
                    (actor,created,position,note,conformity,tenant,review_id))
            else:
                cur=conn.execute("""INSERT INTO reviews(tenant_id,run_id,actor,created_at,stage,position,note,corrected_suggestion,conformity_status)
                    VALUES(?,?,?,?,'conclusao',?,?,?,?)""",
                    (tenant,run["id"],actor,created,position,note,"",conformity))
                review_id = cur.lastrowid
            storage.audit(conn,tenant,actor,"conclusao_revisada","review",review_id,case_id=run["case_id"])
            etapas = ["Conformidade registrada","Conduta médica registrada"]
            for etapa in etapas:
                storage.event(conn,tenant,run["case_id"],etapa,actor,run["correlation"] or f'run-{run["id"]}',detail="Revisão médica confirmada")
            conn.commit()
            session = {**session, "revisao_salva":run["case_id"]}
            session, sid = set_session(session)
            return redirect(f'/caso/{run["case_id"]}')
        if method=="GET" and path.startswith("/pacote/"):
            return reply("Módulo gerencial desabilitado na versão Beta 0.2.", "404 Not Found")
        if method == "POST" and path == "/gerencia":
            return reply("Módulo gerencial desabilitado na versão Beta 0.2.", "404 Not Found")
        if method == "POST" and path == "/operadora":
            run = storage.run_for(conn,tenant,data.get("run_id",""))
            if not auditor or not run:
                return denied("desfecho","run",data.get("run_id",""))
            tecnico=consultas.status_regulatorio(conn,tenant,run["id"])
            if config.BETA and tecnico and tecnico[0] in ("DIVERGENCIA_IDENTIFICADA","REGRA_NAO_VALIDADA"):
                return reply("A execução requer revisão técnica antes de qualquer encaminhamento.","409 Conflict")
            out = json.loads(run["original_output"])
            rev = conn.execute("SELECT * FROM reviews WHERE tenant_id=? AND run_id=? ORDER BY id DESC LIMIT 1",
                (tenant,run["id"])).fetchone()
            if "parecer" not in out or not rev or rev["stage"] != "conclusao":
                return reply("Conclua a revisão médica do parecer de IA.","409 Conflict")
            decisao = data.get("decisao","")
            motivo = data.get("justificativa","").strip()
            if decisao not in ("Autorizar","Negar") or not 1 <= len(motivo) <= 2000:
                return reply("Selecione a decisão e informe a justificativa.","400 Bad Request")
            conn.execute("""CREATE TABLE IF NOT EXISTS decisoes_demo
                (tenant TEXT, case_id INTEGER, run_id INTEGER, review_id INTEGER, actor TEXT,
                 decisao TEXT, motivo TEXT, criado TEXT, PRIMARY KEY(tenant,case_id))""")
            cur = conn.execute("INSERT OR IGNORE INTO decisoes_demo VALUES(?,?,?,?,?,?,?,?)",
                (tenant,run["case_id"],run["id"],rev["id"],actor,decisao,motivo,storage.now()))
            if cur.rowcount:
                storage.event(conn,tenant,run["case_id"],"Encerramento no simulador",actor,run["correlation"] or f'run-{run["id"]}')
                storage.audit(conn,tenant,actor,"decisao_operadora_demo","run",run["id"],case_id=run["case_id"])
            registro = conn.execute("SELECT * FROM decisoes_demo WHERE tenant=? AND case_id=?",(tenant,run["case_id"])).fetchone()
            return reply(telas.decisao_page(registro, run, session))
        if method == "GET" and path == "/referencias":
            return reply(telas.versions_page(conn, session))
        if method == "POST" and path == "/referencias/rascunho":
            if not admin:
                return denied("criacao_rascunho","catalog_version","novo")
            kind = data.get("kind")
            title = data.get("title","").strip()
            url = data.get("source_url","").strip()
            if kind not in ("checklist","reference") or not 1 <= len(title) <= 120:
                return reply("Versão inválida.", "400 Bad Request")
            if kind == "reference":
                if not url.startswith("https://www.gov.br/ans/") or len(url)>300:
                    return reply("Use uma URL de consulta do portal oficial da ANS.", "400 Bad Request")
                content = {"title":title,"source_url":url,
                           "notice":"Referência de consulta; exige verificação médica de aplicabilidade."}
            else:
                content = {"title":title,"require_question":True,
                           "require_report":data.get("require_report")=="1",
                           "notice":"Checklist sintético, não normativo."}
            version = conn.execute("""SELECT COALESCE(MAX(version),0)+1 FROM catalog_versions
                WHERE tenant_id=? AND kind=?""",(tenant,kind)).fetchone()[0]
            cur = conn.execute("""INSERT INTO catalog_versions
                (tenant_id,kind,version,status,content,created_at,actor)
                VALUES(?,?,?,'rascunho',?,?,?)""",
                (tenant,kind,version,dump(content),storage.now(),actor))
            storage.audit(conn,tenant,actor,"criacao_rascunho","catalog_version",cur.lastrowid)
            return redirect("/referencias")
        if method == "POST" and path in ("/referencias/aprovar","/referencias/desativar"):
            vid = data.get("version_id","")
            if not admin:
                return denied("alteracao_referencia","catalog_version",vid)
            existing = conn.execute("""SELECT * FROM catalog_versions
                WHERE tenant_id=? AND id=?""",(tenant,vid)).fetchone()
            approval = path.endswith("/aprovar")
            if not existing or existing["status"] != ("rascunho" if approval else "aprovado"):
                return reply("Transição de versão inválida.", "409 Conflict")
            state = "aprovado" if approval else "desativado"
            conn.execute("""UPDATE catalog_versions SET status=?,approved_at=COALESCE(approved_at,?)
                WHERE tenant_id=? AND id=?""",(state,storage.now(),tenant,vid))
            storage.audit(conn,tenant,actor,"aprovacao_referencia" if approval
                          else "desativacao_referencia","catalog_version",vid)
            return redirect("/referencias")
        if method == "GET" and path == "/usuarios":
            if not admin:
                return denied("consulta_usuarios","user","lista")
            transient = "flash" in session
            page = telas.users_page(conn, session)
            if transient:
                session = {key:value for key,value in session.items() if key != "flash"}
                session, sid = set_session(session)
            return reply(page)
        if method == "POST" and path == "/usuarios/criar":
            if not admin:
                return denied("criacao_usuario","user",data.get("username",""))
            username,role = data.get("username",""),data.get("role")
            if not re.fullmatch(r"[a-z0-9-]{4,40}",username) or role not in ("auditor","admin"):
                return reply("Usuário ou perfil inválido.", "400 Bad Request")
            if conn.execute("SELECT 1 FROM users WHERE username=?",(username,)).fetchone():
                return reply("Usuário já existe.", "409 Conflict")
            password = secrets.token_urlsafe(15)
            salt = secrets.token_bytes(16)
            conn.execute("INSERT INTO users VALUES(?,?,?,?,?,?)",
                         (username,tenant,role,salt,storage.digest(password,salt),storage.now()))
            storage.audit(conn,tenant,actor,"criacao_usuario","user",username)
            session = {**session, "flash":[username,password]}
            session, sid = set_session(session)
            return redirect("/usuarios")
        if method == "POST" and path == "/usuarios/permissao":
            username,role = data.get("username",""),data.get("role")
            if not admin:
                return denied("alteracao_permissoes","user",username)
            user = conn.execute("SELECT * FROM users WHERE tenant_id=? AND username=?",
                                (tenant,username)).fetchone()
            if not user or role not in ("auditor","admin") or role==user["role"]:
                return reply("Alteração inválida.", "400 Bad Request")
            if username == actor or (user["role"]=="admin" and
                conn.execute("SELECT count(*) FROM users WHERE tenant_id=? AND role='admin'",
                             (tenant,)).fetchone()[0] <= 1):
                return reply("O administrador atual não pode perder seu próprio acesso.", "409 Conflict")
            conn.execute("UPDATE users SET role=? WHERE tenant_id=? AND username=?",
                         (role,tenant,username))
            storage.audit(conn,tenant,actor,"alteracao_permissoes","user",username)
            return redirect("/usuarios")
        if method == "GET" and path == "/auditoria":
            if not admin:
                return denied("consulta_auditoria","tenant",tenant)
            page = telas.audit_page(conn,session,query)
            return reply(page) if page else reply("Filtro não permitido.", "403 Forbidden")
        return reply("Recurso ou formulário inválido.", "404 Not Found")


def reset_password(username):
    with storage.connection() as conn:
        user = conn.execute("SELECT tenant_id FROM users WHERE username=?",(username,)).fetchone()
        if not user:
            raise SystemExit("Usuário inexistente.")
        password = getpass.getpass("Nova senha (mínimo 12 caracteres): ")
        storage.set_password(conn,username,password)
        storage.audit(conn,user["tenant_id"],"administrador-local","redefinicao_senha","user",username)
    print("Senha redefinida; credencial não foi escrita no log.")


def main():
    import sys
    if config.BETA:
        storage.DB = ROOT / "auditia-beta.sqlite3"
    credentials = storage.initialize()
    if credentials:
        print("Contas locais fictícias criadas. Anote estas senhas temporárias agora:")
        for username,password in credentials:
            print(f"  {username}: {password}")
        print("Estas senhas são exibidas somente na criação do banco.")
    if len(sys.argv) >= 2 and sys.argv[1] == "resetar-senha":
        if len(sys.argv) == 3:
            reset_password(sys.argv[2])
            raise SystemExit(0)
        else:
            raise SystemExit("Uso: python app.py resetar-senha NOME")
    port = config.PORT
    for arg in sys.argv[1:]:
        if arg.isdigit():
            port = int(arg)
        elif arg.startswith("--port="):
            port = int(arg.split("=", 1)[1])
    base_url = f"http://127.0.0.1:{port}"
    with make_server("127.0.0.1", port, app) as server:
        print(f"AuditIA em {base_url} · Ctrl+C para encerrar.")
        try:
            webbrowser.open(base_url)
        except Exception:
            pass
        server.serve_forever()


if __name__ == "__main__":
    main()
