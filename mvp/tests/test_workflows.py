"""Testes de comportamento nas fronteiras de operadora e rastreabilidade."""

import io
import re
import pymupdf
import json
import sys
import tempfile
import unittest
from datetime import date
from unittest.mock import patch
from pathlib import Path
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import app, auth
from backend import storage
from backend.datas import data_br


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = storage.DB
        storage.DB = Path(self.tmp.name) / "demo.sqlite3"
        self.passwords = dict(storage.initialize(seed_demo_cases=True))
        app.failures.clear()

    def tearDown(self):
        storage.DB = self.old_db
        self.tmp.cleanup()

    def request(self, method, path, cookie="", data=None):
        body = urlencode(data or {}).encode()
        env = {}
        setup_testing_defaults(env)
        env.update(REQUEST_METHOD=method, PATH_INFO=path.split("?")[0],
                   QUERY_STRING=path.split("?", 1)[1] if "?" in path else "",
                   HTTP_HOST="127.0.0.1:8765", HTTP_COOKIE=cookie,
                   CONTENT_LENGTH=str(len(body)), **{"wsgi.input": io.BytesIO(body)})
        response = {}

        def start(status, headers):
            response["status"] = int(status[:3])
            response["headers"] = dict(headers)

        raw = b"".join(app.app(env,start))
        result = raw if response["headers"]["Content-Type"]=="application/pdf" else raw.decode()
        return response["status"], response["headers"], result

    def post_multipart(self, path, identity, fields, filename=None, content=None,
                       mime="application/pdf", files=None):
        boundary = "----AuditIATestBoundary"
        parts = []
        for name, value in {"csrf":identity[1], **fields}.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        uploads = files or [("anexo", filename, content, mime)]
        for field, upload_name, upload_content, upload_mime in uploads:
            parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{upload_name}"\r\n'
                          f'Content-Type: {upload_mime}\r\n\r\n').encode() + upload_content + b"\r\n")
        parts.append(f'--{boundary}--\r\n'.encode())
        body = b"".join(parts)
        env = {}
        setup_testing_defaults(env)
        env.update(REQUEST_METHOD="POST", PATH_INFO=path, HTTP_HOST="127.0.0.1:8765",
                   HTTP_COOKIE=identity[0], CONTENT_TYPE=f"multipart/form-data; boundary={boundary}",
                   CONTENT_LENGTH=str(len(body)), **{"wsgi.input":io.BytesIO(body)})
        response = {}
        def start(status, headers):
            response["status"] = int(status[:3])
            response["headers"] = dict(headers)
        raw = b"".join(app.app(env, start))
        return response["status"], response["headers"], raw.decode()

    def login(self, username, accept=True):
        _, headers, _ = self.request("GET", "/entrar")
        cookie = headers["Set-Cookie"].split(";",1)[0]
        csrf = auth.verify(cookie.split("=",1)[1])["csrf"]
        status, headers, _ = self.request("POST", "/entrar", cookie,
                                          {"csrf":csrf, "username":username,
                                           "password":self.passwords[username]})
        self.assertEqual(status,303)
        new_cookie = headers["Set-Cookie"].split(";",1)[0]
        identity = [new_cookie, auth.verify(new_cookie.split("=",1)[1])["csrf"]]
        if accept:
            self.post("/termo",identity,aceite="1")
        return identity

    def post(self, path, identity, **fields):
        cookie, csrf = identity
        response = self.request("POST", path, cookie, {"csrf":csrf, **fields})
        if "Set-Cookie" in response[1]:
            identity[0] = response[1]["Set-Cookie"].split(";",1)[0]
            claims = auth.verify(identity[0].split("=",1)[1])
            if claims:
                identity[1] = claims["csrf"]
        return response

    def add_required_docs(self, case_id, tenant="aurora"):
        with storage.connection() as conn:
            for suffix,kind in (("PEDIDO","pedido_medico"),("ANATOMO","anatomopatologico")):
                conn.execute("""INSERT INTO documents
                    (tenant_id,case_id,source_system,external_id,kind,name,source_updated_at,last_imported_at,content_text)
                    VALUES(?,?, 'TESTE',?,?,?,?,?,?)""",
                    (tenant,case_id,f"{case_id}-{suffix}",kind,suffix,storage.now(),storage.now(),"Documento sintético"))

    def test_jwt_rest_e_bootstrap(self):
        identity = self.login("auditor-aurora")
        token = identity[0].split("=", 1)[1]
        self.assertEqual(len(token.split(".")), 3)
        self.assertEqual(auth.verify(token)["user"], "auditor-aurora")

        status, headers, body = self.request("GET", "/api/session", identity[0])
        self.assertEqual((status, headers["Content-Type"]), (200, "application/json; charset=utf-8"))
        self.assertEqual(json.loads(body)["role"], "auditor")

        forged = token[:-1] + ("A" if token[-1] != "A" else "B")
        status, _, body = self.request("GET", "/api/session", "auditia=" + forged)
        self.assertEqual(status, 401)
        self.assertFalse(json.loads(body)["ok"])

        page = self.request("GET", "/", identity[0])[2]
        self.assertIn('href="/bootstrap.min.css"', page)
        self.assertIn('src="/app.js"', page)
        self.assertIn("position-fixed top-0 end-0", page)
        self.assertNotIn('href="/gerencia"', page)
        self.assertNotIn('href="/integracoes">Integrações</a>',page)
        script = self.request("GET", "/app.js", identity[0])[2]
        self.assertIn('showAlert("Processando…", "info", 0, true)', script)
        self.assertIn("duration = 5000", script)
        styles = self.request("GET", "/estilo.css", identity[0])[2]
        self.assertIn(".alert-container .btn-close", styles)
        self.assertIn(".alert-container .alert-success .btn-close:hover", styles)
        status, _, body = self.request("POST", "/api/sincronizar", identity[0],
                                       {"csrf":identity[1], "connector":"sigo"})
        response = json.loads(body)
        self.assertEqual(status, 200)
        self.assertTrue(response["ok"])
        self.assertEqual(response["redirect"], "/")

    def test_auditor_accepts_ai_terms_before_access(self):
        with patch.object(app.config,"BETA",True):
            identity = self.login("auditor-aurora",accept=False)
            status,headers,_ = self.request("GET","/beta",identity[0])
            self.assertEqual((status,headers["Location"]),(303,"/termo"))
            self.assertIn("Resolução CFM nº 2.454/2026",self.request("GET","/termo",identity[0])[2])
            self.assertEqual(self.post("/termo",identity,aceite="1")[0],303)
            self.assertEqual(self.request("GET","/beta",identity[0])[0],200)

    def test_vigencia_na_rota_de_parecer(self):
        with patch.object(app.config,"BETA",True):
            auditor=self.login("auditor-aurora")
            admin=self.login("admin-aurora")
            self.assertEqual(self.request("GET","/beta/vigencia",auditor[0])[0],403)
            self.assertEqual(self.request("GET","/beta/vigencia",admin[0])[0],200)
            self.assertEqual(self.post("/beta/vigencia",admin,acao="propor")[0],303)
            with storage.connection() as conn, self.assertRaises(ValueError):
                app.vigencia.selecionar(conn,"aurora",app.vigencia.NOVA)
            self.assertEqual(self.post("/beta/vigencia",admin,acao="aprovar")[0],303)

    def test_termo_por_sessao_do_auditor(self):
        for nome in ("auditor-aurora","auditor-horizonte"):
            primeira = self.login(nome)
            for _ in range(2):
                self.assertEqual(self.request("GET","/",primeira[0])[0],200)
            segunda = self.login(nome,accept=False)
            for _ in range(2):
                self.assertEqual(self.request("GET","/auditoria",segunda[0])[1]["Location"],"/termo")
            pagina = self.request("GET","/termo",segunda[0])[2]
            self.assertNotIn("checked",pagina)
            self.assertIn("disabled",pagina)
            self.assertEqual(self.post("/termo",segunda)[0],400)
            self.assertEqual(self.post("/termo",segunda,recusa="1")[1]["Location"],"/entrar")
            self.assertEqual(self.request("GET","/",segunda[0])[1]["Location"],"/entrar")
            self.login(nome)
            with storage.connection() as conn:
                registros = conn.execute("SELECT session_ref FROM session_acceptances WHERE username=?",(nome,)).fetchall()
                self.assertEqual(len(set(r[0] for r in registros)),2)

    def test_fila_datas_e_filtros(self):
        with patch.object(app.config,"BETA",True):
            auditor = self.login("auditor-aurora")
            def pagina(n):
                return self.request("GET",f"/beta?pagina={n}",auditor[0])[2]
            def codigos(html):
                return re.findall(r'/caso/\d+">(B\d+)</a>',html)
            self.assertEqual(codigos(pagina(1))+codigos(pagina(2)),
                ["B01","B02","B03","B04","B05","B06","B07","B08","B09","B10"])
            self.assertIn("Status da guia",pagina(1))
            self.assertIn("Status da análise",pagina(1))
            self.assertIn("<td>Pendente</td>",pagina(1))
            self.assertIn('class="api-form case-filter-search"',pagina(1))
            self.assertIn(">Pesquisar</button>",pagina(1))
            self.post("/beta",auditor,guia="B03",status_guia="Pendente")
            self.assertEqual(codigos(pagina(1)),["B03"])
            self.assertEqual(self.post("/beta",auditor,status_guia="Inválido")[0],400)
            self.post("/beta",auditor,limpar="1")
            self.post("/beta",auditor,codigo="000005",estado="Falta de documentos")
            self.assertEqual(codigos(pagina(1)),["B05"])
            self.assertIn("05/11/2026",pagina(1))
            with patch("frontend.fila.datetime") as relogio:
                relogio.now.return_value.date.return_value = date(2026,11,22)
                fila = pagina(1)
                self.assertIn(">SLA</th>",fila)
                self.assertIn("<td>05/11/2026</td><td>10 dias úteis</td>",fila)
            self.post("/beta",auditor,codigo="000005",estado="Pendente")
            self.assertIn("Nenhum caso",pagina(1))
            self.post("/beta",auditor,limpar="1")
            self.assertEqual(len(codigos(pagina(1))),5)
        self.assertEqual(data_br("2026-11-22T02:15:00Z"),"21/11/2026 23:15")
        self.assertEqual(data_br("2026-11-22"),"22/11/2026")
        for valor in (None,"inválida"):
            self.assertEqual(data_br(valor),"Não informado")
        from backend.datas import sla_guia
        segunda = date(2026,11,23)
        self.assertEqual(sla_guia("2026-11-23",segunda),"0 dias úteis")
        self.assertEqual(sla_guia("2026-11-20T01:00:00Z",segunda),"1 dia útil")
        self.assertEqual(sla_guia("2026-11-19",date(2026,11,22)),"0 dias úteis")
        self.assertEqual(sla_guia(None,segunda),"Não informado")
        from backend.adapters import read_demo
        with storage.connection() as conn:
            lote = read_demo("sigo","aurora")
            storage.import_records(conn,"aurora",lote)
            consulta = "SELECT guide_received_at FROM cases WHERE source_system='SIGO'"
            self.assertIsNone(conn.execute(consulta).fetchone()[0])
            lote[0]["guide_received_at"] = "2026-10-02"
            storage.import_records(conn,"aurora",lote)
            lote[0]["guide_received_at"] = None
            lote[0]["source_updated_at"] = "2026-12-01"
            storage.import_records(conn,"aurora",lote)
            self.assertEqual(conn.execute(consulta).fetchone()[0],"2026-10-02")

    def test_cursor_auditoria(self):
        admin = self.login("admin-aurora")
        with storage.connection() as conn:
            for i in range(57):
                storage.audit(conn,"aurora","admin-aurora","ensaio","case",i)
            storage.audit(conn,"horizonte","admin-horizonte","ensaio","case","OUTRA")
        url = "/auditoria?action=ensaio"
        primeira = self.request("GET",url,admin[0])[2]
        ids = lambda html: re.findall(r"<tr><td>(\d+)</td>",html)
        self.assertEqual(len(ids(primeira)),50)
        with storage.connection() as conn:
            storage.audit(conn,"aurora","admin-aurora","ensaio","case","NOVO")
        segunda = self.request("GET",url+"&antes="+ids(primeira)[-1],admin[0])[2]
        self.assertEqual(len(set(ids(primeira)+ids(segunda))),57)
        self.assertNotIn("OUTRA",primeira+segunda)
        self.assertNotIn("NOVO",segunda)
        self.assertIn("action=ensaio&amp;antes=",primeira)
        self.assertEqual(self.request("GET",url,self.login("auditor-aurora")[0])[0],403)

    def test_rodada_beta_isolada_e_sem_recontagem(self):
        from unittest.mock import patch
        with patch.object(app.config,"BETA",True):
            auditor=self.login("auditor-aurora")
            for _ in range(2):
                self.assertEqual(self.request("GET","/beta",auditor[0])[0],200)
            with storage.connection() as conn:
                cases=conn.execute("SELECT id FROM cases WHERE tenant_id='aurora' AND source_system='BETA' ORDER BY id").fetchall()
            self.assertEqual(len(cases),10)
            tela=self.request("GET",f"/caso/{cases[0][0]}",auditor[0])[2]
            self.assertIn("Apoio decisório",tela)
            self.assertIn("Gerar parecer",tela)
            self.assertNotIn("Arquivos complementares",tela)
            self.assertNotIn("image/tiff",tela)
            self.assertIn("Data de entrada da guia</dt><dd>01/11/2026</dd>",tela)
            self.assertEqual(self.post("/operadora",auditor,run_id="1")[0],403)
            self.assertEqual(self.post("/caso/alterar",auditor,case_id=cases[0][0])[0],403)
            self.assertEqual(self.post("/parecer",auditor,case_id=cases[0][0])[0],409)
            admin=self.login("admin-aurora")
            from backend import fonte_ans, criterios_dut
            from html import escape
            url=app.regulatoria.FONTE
            html=("<pre>"+escape(criterios_dut.BASE.read_text(encoding="utf-8"))+"\n61. Seguinte</pre>").encode()
            with patch.object(fonte_ans,"ARQUIVOS",Path(self.tmp.name)), patch.object(fonte_ans,"baixar",return_value=(url,"text/html",html)):
                self.assertEqual(self.post("/regulatoria",admin,acao="consultar",url=url)[0],303)
                self.assertEqual(self.request("GET","/regulatoria",auditor[0])[0],403)
                self.assertEqual(self.post("/regulatoria",admin,acao="ativar",doc=1)[0],409)
                painel = self.request("GET", "/regulatoria", admin[0])[2]
                self.assertIn('name="revisado"', painel)
                self.assertNotIn('name="gabarito"', painel)
                self.assertEqual(self.post("/regulatoria", auditor, acao="finalizar", doc=1, revisado="1")[0], 403)
                self.assertEqual(self.post("/regulatoria", admin, acao="finalizar", doc=1)[0], 409)
                self.assertEqual(self.post("/regulatoria", admin, acao="finalizar", doc=1, revisado="1")[0], 303)
                painel = self.request("GET", "/regulatoria", admin[0])[2]
                self.assertIn("Documento 1 · Ativa", painel)
                self.assertNotIn('name="revisado"', painel)
                self.assertEqual(self.request("GET","/regulatoria/criterios/1",self.login("admin-horizonte")[0])[0],404)
            output={"suggestion":"Critérios demonstrados","scope":"DUT 60","criteria":[],
                    "modelo":"teste","parecer":dict.fromkeys(app.parecer.FIELDS,"Síntese fictícia")}
            with patch("backend.parecer.gerar",return_value=output) as model:
                with pymupdf.open() as pdf:
                    pdf.new_page().insert_text((36, 52), "Exame complementar fictício para análise")
                    complemento = pdf.tobytes()
                self.assertEqual(self.post_multipart("/parecer",auditor,{"case_id":cases[0][0]},
                                                     "exame-complementar.pdf",complemento)[0],303)
                self.assertEqual(self.post("/parecer",auditor,case_id=cases[0][0])[0],303)
                entrada = model.call_args_list[0].args[0]
                self.assertNotIn("gabarito",json.dumps(entrada).lower())
                self.assertEqual(entrada["documentos_textuais"][0]["origem"],"complemento_medico_auditor")
                self.assertFalse(entrada["documentos_textuais"][0]["substitui_documento_obrigatorio"])
                self.assertEqual(entrada["documentos_textuais"][0]["documento"],"C1")
            with storage.connection() as conn:
                rid=conn.execute("SELECT min(id) FROM runs").fetchone()[0]
            caso_renderizado = self.request("GET",f"/caso/{cases[0][0]}",auditor[0])[2]
            self.assertNotIn("Revisão técnica necessária", caso_renderizado)
            self.assertIn("Síntese fictícia", caso_renderizado)
            self.assertEqual(self.post("/gerencia",auditor,run_id=rid)[0],404)
            caminho=f"/regulatoria/guia/{rid}"
            self.assertEqual(self.request("GET",caminho+"?item=2",auditor[0])[0],200)
            self.assertEqual(self.post(caminho,auditor,acao="vincular",item="2",fato="2|Linfoma",documento="9999",trecho="alheio",valor="sim")[0],400)
            self.assertEqual(self.request("GET",caminho,self.login("auditor-horizonte")[0])[0],403)
            self.assertIn("1/10 com parecer",self.request("GET","/beta",auditor[0])[2])
            self.assertIn("0/10 com parecer",self.request("GET","/beta",self.login("auditor-horizonte")[0])[2])
            self.assertEqual(self.request("GET","/beta/resultados.csv",auditor[0])[0],403)
            self.assertIn("B10",self.request("GET","/beta/resultados.csv",self.login("admin-aurora")[0])[2])

    def test_fluxo_parecer_revisao_desfechos(self):
        from unittest.mock import patch
        auditor = self.login("auditor-aurora")
        with storage.connection() as conn:
            cid = conn.execute("SELECT id FROM cases WHERE tenant_id='aurora'").fetchone()[0]
        self.add_required_docs(cid)
        with patch("backend.parecer.gerar", side_effect=ValueError("Modelo indisponível")):
            self.assertEqual(self.post("/parecer",auditor,case_id=cid)[0],422)
        output = {"suggestion":"Complementação necessária","scope":"DUT 60","criteria":[],
                  "modelo":"teste","parecer":dict.fromkeys(app.parecer.FIELDS,"Exemplo sintético")}
        with patch("backend.parecer.gerar",return_value=output):
            status, headers, _ = self.post("/parecer",auditor,case_id=cid)
            self.assertEqual(status,303)
        with storage.connection() as conn:
            rid = conn.execute("SELECT id FROM runs").fetchone()[0]
        self.assertTrue(headers["Location"].endswith(f"#parecer-{rid}"))
        tela_parecer = self.request("GET",headers["Location"].split("#",1)[0],auditor[0])[2]
        parecer = f"Parecer da execução {rid}"
        execucao = f"Execução {rid}"
        self.assertLess(tela_parecer.index(parecer),tela_parecer.index(execucao,tela_parecer.index(parecer)+len(parecer)))
        self.assertIn(f'id="parecer-{rid}"',tela_parecer)
        self.assertNotIn('data-bs-toggle="tab"',tela_parecer)
        self.assertEqual(self.post("/gerencia",auditor,run_id=rid)[0],404)
        self.assertEqual(self.post("/operadora",auditor,run_id=rid)[0],409)
        campos = dict(run_id=rid,note="Fundamentação sintética",conformity="Conforme")
        self.assertEqual(self.post("/revisar",auditor,**campos)[0],400)
        self.assertEqual(self.post("/revisar",auditor,position="Discordo",**dict(campos,note=" "))[0],400)
        status, review_headers, _ = self.post("/revisar",auditor,position="Discordo",**campos)
        self.assertEqual(status,303)
        self.assertEqual(review_headers["Location"],f"/caso/{cid}")
        self.assertEqual(self.post("/revisar",auditor,position="Discordo",
                                   **dict(campos,note="Fundamentação atualizada"))[0],303)
        with storage.connection() as conn:
            reviews = conn.execute("SELECT * FROM reviews WHERE tenant_id='aurora' AND run_id=?",
                                   (rid,)).fetchall()
            workflow = conn.execute("SELECT * FROM case_workflow WHERE tenant='aurora' AND case_id=?",
                                    (cid,)).fetchone()
        self.assertEqual(len(reviews),1)
        self.assertEqual(reviews[0]["note"],"Fundamentação atualizada")
        self.assertIsNone(workflow)
        tela = self.request("GET",f"/caso/{cid}",auditor[0])[2]
        for item in ("Revisão médica registrada com sucesso","Registrar revisão médica","Revisão — Discordo","Conforme","Fundamentação atualizada"):
            self.assertIn(item,tela)
        self.assertEqual(self.request("GET","/gerencia",auditor[0])[0],404)
        self.assertEqual(self.request("GET",f"/pacote/{rid}",auditor[0])[0],404)
        self.assertEqual(self.post("/caso/gerencia",auditor,case_id=cid)[0],404)
        casos = self.request("GET","/",auditor[0])[2]
        for item in ("Nº guia","Cód. beneficiário","Procedimento",
                     "Entrada","Status análise",
                     "Médico resp.","Ações"):
            self.assertIn(item,casos)
        self.assertIn("Revisão — Discordo",casos)
        self.assertNotIn("case-management",casos)
        self.assertIn("Finalizar caso",casos)
        self.assertIn("Importar casos fictícios — SIGO",casos)
        from backend.config import DOCUMENT_ASSETS
        from backend import relatorio
        with storage.connection() as conn:
            case_obj = storage.case_for(conn,"aurora",cid)
            run_obj = storage.run_for(conn,"aurora",rid)
            rev_obj = conn.execute("SELECT * FROM reviews WHERE tenant_id='aurora' AND run_id=?",(rid,)).fetchone()
            docs_obj = conn.execute("SELECT * FROM documents WHERE tenant_id='aurora' AND case_id=?",(cid,)).fetchall()
        pdf = relatorio.pacote(case_obj,run_obj,output,rev_obj,docs_obj,DOCUMENT_ASSETS)
        with pymupdf.open(stream=pdf,filetype="pdf") as doc:
            texto = "".join(page.get_text() for page in doc)
        for item in ("AuditIA","DUT 60","auditor-aurora","Emitido em","Fundamentação atualizada"):
            self.assertIn(item,texto)
        self.assertNotRegex(texto,r"(?i)gemini|claude|\bgpt")
        with storage.connection() as conn:
            original = conn.execute("SELECT original_output FROM runs WHERE id=?",(rid,)).fetchone()[0]
            self.assertEqual(json.loads(original)["modelo"],output["modelo"])
        self.assertEqual(self.post("/operadora",auditor,run_id=rid,decisao="Autorizar",justificativa="teste")[0],200)
        self.post("/operadora",auditor,run_id=rid,decisao="Negar",justificativa="teste")
        admin = self.login("admin-aurora",accept=False)
        historico = self.request("GET",f"/telemetria?guia={cid}",admin[0])[2]
        for etapa in ("Conformidade registrada","Encerramento no simulador"):
            self.assertIn(etapa,historico)
        self.assertNotIn("Fundamentação sintética",historico)
        with storage.connection() as conn:
            rev = conn.execute("SELECT conformity_status,position,note FROM reviews WHERE run_id=?",(rid,)).fetchone()
            self.assertEqual(tuple(rev),("Conforme","Discordo","Fundamentação atualizada"))
            corrente = conn.execute("SELECT correlation FROM runs WHERE id=?",(rid,)).fetchone()[0]
            eventos = [e[0] for e in conn.execute("SELECT stage FROM telemetry WHERE correlation=? ORDER BY id",(corrente,))]
            self.assertLess(eventos.index("Disponibilização para revisão médica"),eventos.index("Conformidade registrada"))
            self.assertLess(eventos.index("Conformidade registrada"),eventos.index("Conduta médica registrada"))
        with storage.connection() as conn:
            self.assertEqual(conn.execute("SELECT decisao FROM decisoes_demo").fetchall()[0][0],"Autorizar")
        self.assertEqual(self.post("/gerencia",self.login("auditor-horizonte"),run_id=rid)[0],404)

    def test_tenant_boundaries_include_direct_case_document_and_audit_urls(self):
        aurora = self.login("auditor-aurora")
        horizon = self.login("auditor-horizonte")
        admin = self.login("admin-aurora")
        with storage.connection() as conn:
            own = conn.execute("SELECT id FROM cases WHERE tenant_id='aurora' LIMIT 1").fetchone()[0]
            foreign = conn.execute("SELECT id FROM cases WHERE tenant_id='horizonte' LIMIT 1").fetchone()[0]
        status, _, own_page = self.request("GET","/",aurora[0])
        self.assertEqual(status,200)
        self.assertIn(f'/caso/{own}',own_page)
        self.assertIn("Gerar parecer",own_page)
        self.assertIn(f'name="case_id" value="{own}"',own_page)
        self.assertNotIn(f'/caso/{foreign}',own_page)
        self.assertNotIn(f'name="case_id" value="{foreign}"',own_page)
        status, _, foreign_page = self.request("GET",f"/caso/{foreign}",aurora[0])
        self.assertEqual(status,403)
        self.assertNotIn("Caso sintético inicial da operadora horizonte",foreign_page)
        self.assertEqual(self.request("GET",f"/caso/{own}",horizon[0])[0],403)
        self.assertEqual(self.request("GET",f"/caso/{own}",admin[0])[0],403)
        self.assertEqual(self.request("GET","/auditoria?tenant=horizonte",admin[0])[0],403)
        self.post("/sincronizar",aurora,connector="sigo")
        with storage.connection() as conn:
            doc = conn.execute("SELECT id FROM documents WHERE tenant_id='aurora'").fetchone()[0]
        self.assertEqual(self.request("GET",f"/documento/{doc}",horizon[0])[0],403)
        self.assertEqual(self.request("GET",f"/documento/{doc}",admin[0])[0],403)

    def test_auditor_cases_page_hides_prototype_and_case_creation_ui(self):
        with patch.object(app.config, "BETA", False):
            auditor = self.login("auditor-aurora")
            status, _, page = self.request("GET", "/", auditor[0])
            self.assertEqual(status, 200)
            for text in ("PROTÓTIPO LOCAL", "DADOS 100% FICTÍCIOS",
                         "Mesa de auditoria", "Ambiente demonstrativo",
                         "Novo caso sintético"):
                self.assertNotIn(text, page)
            self.assertNotIn('href="/referencias">Versões</a>', page)
            self.assertNotIn('href="/auditoria">Auditoria</a>', page)
            self.assertIn("Gerar parecer", page)
            self.assertIn("Importação de casos fictícios", page)

            with storage.connection() as conn:
                case_id = conn.execute(
                    "SELECT id FROM cases WHERE tenant_id='aurora' ORDER BY id LIMIT 1").fetchone()[0]
                external_id = conn.execute(
                    "SELECT external_id FROM cases WHERE id=?",(case_id,)).fetchone()[0]
            self.assertIn(external_id,page)
            self.assertEqual(self.post("/caso/finalizar",auditor,case_id=case_id)[0],303)
            self.assertNotIn(external_id,self.request("GET","/",auditor[0])[2])
            self.assertEqual(self.post("/caso/finalizar",other := self.login("auditor-horizonte"),
                                       case_id=case_id)[0],403)

            admin = self.login("admin-aurora")
            _, _, admin_page = self.request("GET", "/", admin[0])
            self.assertIn('href="/referencias">Versões</a>', admin_page)
            self.assertIn('href="/auditoria">Auditoria</a>', admin_page)

    def test_cases_page_uses_compact_actions_and_server_pagination(self):
        with patch.object(app.config, "BETA", False):
            auditor = self.login("auditor-aurora")
            stamp = storage.now()
            with storage.connection() as conn:
                conn.executemany("""INSERT INTO cases
                    (tenant_id,source_system,external_id,procedure,area,narrative,
                     clinical_question,source_updated_at,last_imported_at,created_at,updated_at)
                    VALUES('aurora','PAGINACAO',?,'Procedimento fictício','Teste',
                           'Caso sintético de paginação',1,?,?,?,?)""",
                    [(f"PAG-{numero:02d}",stamp,stamp,stamp,stamp) for numero in range(1,26)])
            pagina_um = self.request("GET","/",auditor[0])[2]
            self.assertIn('class="cases-table"',pagina_um)
            self.assertIn('class="case-actions"',pagina_um)
            for item in ("Nº guia","Cód. beneficiário","Médico resp.",
                         "case-open","case-opinion","case-finish"):
                self.assertIn(item,pagina_um)
            self.assertNotIn("case-management",pagina_um)
            self.assertIn("PAG-01",pagina_um)
            self.assertNotIn("PAG-20",pagina_um)
            self.assertIn("Próxima",pagina_um)
            pagina_dois = self.request("GET","/?pagina=2",auditor[0])[2]
            self.assertIn("PAG-20",pagina_dois)
            self.assertIn("Anterior",pagina_dois)
            self.assertEqual(self.request("GET","/?pagina=zero",auditor[0])[0],400)

    def test_case_document_upload_fills_pending_types_and_allows_opinion(self):
        from backend import parecer
        with patch.object(app.config, "BETA", False):
            auditor = self.login("auditor-aurora")
            other_auditor = self.login("auditor-horizonte")
            with storage.connection() as conn:
                case_id = conn.execute(
                    "SELECT id FROM cases WHERE tenant_id='aurora' LIMIT 1").fetchone()[0]

            def make_pdf(text):
                with pymupdf.open() as pdf:
                    pdf.new_page().insert_text((36, 52), text)
                    return pdf.tobytes()

            pedido = make_pdf("Pedido médico. Indicação clínica e justificativa para exame PET-CT.")
            anatomopatologico = make_pdf("Laudo de biópsia. Anatomopatológico confirma neoplasia.")
            page = self.request("GET", f"/caso/{case_id}", auditor[0])[2]
            self.assertNotIn('role="tablist"', page)
            self.assertNotIn('data-bs-toggle="tab"', page)
            self.assertIn('name="pedido_medico"', page)
            self.assertIn('name="anatomopatologico"', page)
            pending_status, _, pending_page = self.request(
                "POST", "/parecer", auditor[0],
                {"csrf":auditor[1], "case_id":case_id})
            self.assertEqual(pending_status, 422)
            self.assertIn('action="/caso/documentos"', pending_page)
            api_status, _, api_pending = self.request(
                "POST", "/api/parecer", auditor[0],
                {"csrf":auditor[1], "case_id":case_id})
            self.assertEqual(api_status, 422)
            self.assertEqual(json.loads(api_pending)["redirect"], f"/caso/{case_id}")

            files = [("pedido_medico", "pedido.pdf", pedido, "application/pdf")]
            denied = self.post_multipart(
                "/caso/documentos", other_auditor, {"case_id": case_id}, files=files)
            self.assertEqual(denied[0], 403)

            first = self.post_multipart(
                "/caso/documentos", auditor, {"case_id": case_id}, files=files)
            self.assertEqual(first[0], 303)
            partial_page = self.request("GET", f"/caso/{case_id}", auditor[0])[2]
            self.assertNotIn('name="pedido_medico"', partial_page)
            self.assertIn('name="anatomopatologico"', partial_page)

            second = self.post_multipart(
                "/caso/documentos", auditor, {"case_id": case_id},
                files=[("anatomopatologico", "laudo.pdf", anatomopatologico, "application/pdf")])
            self.assertEqual(second[0], 303)
            complete_page = self.request("GET", f"/caso/{case_id}", auditor[0])[2]
            self.assertIn("Documentação fundamental presente", complete_page)
            self.assertNotIn('name="pedido_medico"', complete_page)
            self.assertNotIn('name="anatomopatologico"', complete_page)

            with storage.connection() as conn:
                docs = conn.execute(
                    "SELECT id,kind,content_text,content_blob FROM documents WHERE tenant_id='aurora' AND case_id=?",
                    (case_id,)).fetchall()
            self.assertEqual({doc["kind"] for doc in docs},
                             {"pedido_medico", "anatomopatologico"})
            self.assertTrue(all(doc["content_text"] and doc["content_blob"] for doc in docs))
            status, headers, original = self.request("GET", f'/documento/{docs[0]["id"]}', auditor[0])
            self.assertEqual((status, headers["Content-Type"]), (200, "application/pdf"))
            self.assertTrue(original.startswith(b"%PDF-"))

            output = {
                "suggestion": "Dados insuficientes para concluir",
                "scope": "DUT 60",
                "criteria": [],
                "modelo": "teste",
                "parecer": dict.fromkeys(parecer.FIELDS, "Texto sintético para teste"),
            }
            with patch("backend.parecer.gerar", return_value=output):
                generated = self.post("/parecer", auditor, case_id=case_id)
            self.assertEqual(generated[0], 303)
            with storage.connection() as conn:
                self.assertEqual(conn.execute(
                    "SELECT count(*) FROM runs WHERE tenant_id='aurora' AND case_id=?",
                    (case_id,)).fetchone()[0], 1)

    def test_repeated_import_and_failed_sync_retry(self):
        admin = self.login("admin-aurora",accept=False)
        self.assertEqual(self.post("/sincronizar",admin,connector="sigo")[0],303)
        self.assertEqual(self.post("/sincronizar",admin,connector="sigo")[0],303)
        self.assertEqual(self.post("/sincronizar",admin,connector="mv",
                                   simulate_failure="1")[0],303)
        with storage.connection() as conn:
            failed = conn.execute("SELECT * FROM sync_jobs WHERE status='falha'").fetchone()
            self.assertEqual(failed["error_code"],"FALHA_SINTETICA_ORIGEM_INDISPONIVEL")
            self.assertEqual(conn.execute("""SELECT count(*) FROM cases WHERE tenant_id='aurora'
                AND source_system='SIGO' AND external_id='SIGO-B01-AURORA'""").fetchone()[0],1)
            self.assertEqual(conn.execute("""SELECT count(*) FROM documents WHERE
                tenant_id='aurora' AND source_system='SIGO'""").fetchone()[0],9)
            repeated = conn.execute("SELECT * FROM sync_jobs WHERE id=2").fetchone()
            self.assertEqual((repeated["inserted"],repeated["duplicates"]),(0,4))
        self.assertEqual(self.post("/sincronizar",admin,connector="mv",
                                   retry_job=str(failed["id"]))[0],303)
        status, _, page = self.request("GET","/integracoes",admin[0])
        self.assertEqual(status,200)
        self.assertIn("FALHA_SINTETICA_ORIGEM_INDISPONIVEL",page)
        self.assertIn("Mapeamento para o formato interno",page)
        with storage.connection() as conn:
            retried = conn.execute("SELECT * FROM sync_jobs WHERE retry_of=?",
                                   (failed["id"],)).fetchone()
            self.assertEqual((retried["status"],retried["inserted"]),("sucesso",1))
            self.assertEqual(conn.execute("""SELECT count(*) FROM audit_events WHERE
                tenant_id='aurora' AND action='sincronizacao'""").fetchone()[0],4)

    def test_version_update_preserves_old_input_output_and_completed_export(self):
        auditor = self.login("auditor-aurora")
        admin = self.login("admin-aurora")
        with storage.connection() as conn:
            cid = conn.execute("SELECT id FROM cases WHERE tenant_id='aurora'").fetchone()[0]
        self.assertEqual(self.post("/analisar",auditor,case_id=str(cid))[0],303)
        with storage.connection() as conn:
            first = conn.execute("SELECT * FROM runs ORDER BY id LIMIT 1").fetchone()
            first_output = first["original_output"]
            first_input = first["input_snapshot"]
        self.post("/referencias/rascunho",admin,kind="checklist",
                  title="Checklist revisado",require_report="1")
        with storage.connection() as conn:
            draft = conn.execute("""SELECT id FROM catalog_versions WHERE tenant_id='aurora'
                AND kind='checklist' AND status='rascunho'""").fetchone()[0]
        self.post("/referencias/aprovar",admin,version_id=str(draft))
        status, _, version_page = self.request("GET","/referencias",admin[0])
        self.assertEqual(status,200)
        self.assertIn("Checklist revisado",version_page)
        self.post("/caso/alterar",auditor,case_id=str(cid),
                  narrative="Outro resumo sintético",question="1")
        self.post("/analisar",auditor,case_id=str(cid))
        status, _, case_page = self.request("GET",f"/caso/{cid}",auditor[0])
        self.assertEqual(status,200)
        self.assertNotIn("Recuperar entradas e versões desta execução",case_page)
        with storage.connection() as conn:
            runs = conn.execute("SELECT * FROM runs WHERE tenant_id='aurora' ORDER BY id").fetchall()
            self.assertEqual(len(runs),2)
            self.assertEqual(runs[0]["original_output"],first_output)
            self.assertEqual(runs[0]["input_snapshot"],first_input)
            self.assertFalse(json.loads(runs[0]["checklist_snapshot"])["require_report"])
            self.assertTrue(json.loads(runs[1]["checklist_snapshot"])["require_report"])
            self.assertNotEqual(runs[0]["checklist_version_id"],runs[1]["checklist_version_id"])
            self.assertNotEqual(json.loads(first_input)["case"]["narrative"],
                                json.loads(runs[1]["input_snapshot"])["case"]["narrative"])
        with storage.connection() as conn:
            anterior = conn.execute("""INSERT INTO reviews(tenant_id,run_id,actor,created_at,stage,position,note,corrected_suggestion)
                VALUES('aurora',?,'auditor-aurora',?,'correcao','Discordo','Ressalva sintética.','Aguardar relatório sintético.')""",
                (first["id"],storage.now()))
            storage.audit(conn,"aurora","auditor-aurora","correcao_medica","review",anterior.lastrowid)
        self.post("/revisar",auditor,run_id=str(first["id"]),stage="conclusao",
                  position="Discordo",note="Conclusão de ensaio.",conformity="Não conforme")
        self.assertIn("Ressalva sintética.",self.request("GET",f"/caso/{cid}",auditor[0])[2])
        self.assertEqual(self.post("/exportar",auditor,run_id=str(first["id"]))[0],404)
        self.assertEqual(self.post("/referencias/desativar",admin,
                                   version_id=str(first["reference_version_id"]))[0],303)
        with storage.connection() as conn:
            actions = [r[0] for r in conn.execute("""SELECT action FROM audit_events
                WHERE tenant_id='aurora'""")]
            self.assertEqual(conn.execute("SELECT original_output FROM runs WHERE id=?",
                                          (first["id"],)).fetchone()[0],first_output)
        for expected in ("analise","alteracao_caso","aprovacao_referencia",
                         "correcao_medica","conclusao_revisada",
                         "desativacao_referencia"):
            self.assertIn(expected,actions)
        self.assertEqual(self.post("/analisar",auditor,case_id=str(cid))[0],409)
        self.assertEqual(self.request("GET","/auditoria?action=exportacao",admin[0])[0],200)

    def test_admin_crud_isolamento_e_inativacao(self):
        admin = self.login("admin-aurora",accept=False)
        outro = self.login("admin-horizonte",accept=False)
        auditor = self.login("auditor-aurora")
        self.assertEqual(self.request("GET","/",admin[0])[0],200)
        self.assertEqual(self.request("GET","/termo",admin[0])[1]["Location"],"/")
        self.assertEqual(self.post("/parecer",admin,case_id=1)[0],403)
        dados = dict(username="beta-auditor",name="Auditor Fictício",email="exemplo@example.org",uf="SP",crm="1200")
        for path in ("/auditores","/telemetria"):
            self.assertEqual(self.request("GET",path,auditor[0])[0],403)
        self.assertEqual(self.post("/auditores",auditor,acao="criar",**dados)[0],403)
        self.assertEqual(self.post("/auditores",admin,acao="criar",role="admin",**dados)[0],303)
        html = self.request("GET","/auditores?busca=beta-auditor",admin[0])[2]
        self.passwords[dados["username"]] = re.search(r"<code>([^<]+)</code>",html).group(1)
        identidade = self.login(dados["username"])
        self.assertEqual(self.request("GET","/telemetria",identidade[0])[0],403)
        self.assertEqual(self.post("/auditores",admin,acao="criar",**dados)[0],400)
        self.assertEqual(self.post("/auditores",admin,acao="editar",**dict(dados,email="inválido"))[0],400)
        self.assertEqual(self.post("/auditores",outro,acao="editar",**dados)[0],400)
        self.assertNotIn(dados["name"],self.request("GET","/auditores",outro[0])[2])
        self.assertEqual(self.post("/auditores",admin,acao="editar",**dict(dados,name="Nome alterado"))[0],303)
        self.assertEqual(self.post("/auditores",admin,acao="inativar",username=dados["username"])[0],303)
        self.assertIn("Nome alterado",self.request("GET","/auditores?status=Inativo",admin[0])[2])
        self.assertEqual(self.request("GET","/",identidade[0])[1]["Location"],"/entrar")
        self.assertEqual(self.post("/auditores",admin,acao="reativar",username=dados["username"])[0],303)
        self.login(dados["username"])

    def test_documentacao_ans_comparacao_falha_e_isolamento(self):
        from backend import fonte_ans
        url = "https://www.gov.br/ans/documento"
        from html import escape
        from backend import criterios_dut
        html = "<pre>"+escape(criterios_dut.BASE.read_text(encoding="utf-8"))+"\n61. Seguinte</pre>"
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((36,52),"60. PET-CT ONCOLÓGICO\n1. Cobertura obrigatória fictícia.\n61. Seguinte")
            corpo,_ = fonte_ans.extrair("application/pdf",pdf.tobytes())
            self.assertIn("Cobertura obrigatória",corpo)
            self.assertNotIn("Seguinte",corpo)
        with self.assertRaises(ValueError):
            fonte_ans.destino("https://example.org/documento")
        with patch.object(app.config,"BETA",True), patch.object(fonte_ans,"ARQUIVOS",Path(self.tmp.name)/"versoes"):
            admin=self.login("admin-aurora")
            outro=self.login("admin-horizonte")
            def consultar(conteudo):
                with patch.object(fonte_ans,"baixar",return_value=(url,"text/html",conteudo.encode())):
                    self.assertEqual(self.post("/beta/vigencia",admin,acao="consultar",url=url)[0],303)
            consultar(html)
            with storage.connection() as conn:
                registro=conn.execute("SELECT * FROM dut_documents").fetchone()
                ident=registro["id"]
                self.assertIsNone(registro["validated_by"])
                self.assertEqual(len(registro["source_hash"]),64)
                texto=(fonte_ans.ARQUIVOS/registro["filename"]).read_text(encoding="utf-8")
                self.assertIn("Cobertura obrigatória",texto)
                self.assertNotIn("Seguinte",texto)
                motor = conn.execute("SELECT texto FROM dut_ensaio WHERE tenant='aurora'").fetchone()[0]
            self.assertEqual(self.request("GET",f"/dut/arquivo/{ident}",outro[0])[0],404)
            self.assertEqual(self.post("/beta/vigencia",outro,acao="validar_documento",documento=ident)[0],409)
            self.assertEqual(self.post("/beta/vigencia",admin,acao="validar_documento",documento=ident)[0],303)
            consultar(html)
            consultar(html.replace("de PET-CT","revisada de PET-CT"))
            self.assertEqual(self.post("/beta/vigencia",admin,acao="validar_documento",documento=3)[0],409)
            consultar("<p>Documento incompleto</p>")
            painel=self.request("GET","/beta/vigencia",admin[0])[2]
            for marcador in ("Sem alteração","Aguardando validação","Falha na extração","Cobertura obrigatória revisada"):
                self.assertIn(marcador,painel)
            with storage.connection() as conn:
                self.assertEqual(conn.execute("SELECT id FROM dut_documents WHERE validated_by IS NOT NULL").fetchall()[0][0],ident)
                self.assertEqual(conn.execute("SELECT texto FROM dut_ensaio WHERE tenant='aurora'").fetchone()[0],motor)
                self.assertEqual(conn.execute("SELECT count(*) FROM dut_documents WHERE filename IS NOT NULL").fetchone()[0],3)

    def test_permission_changes_are_logged_without_credentials(self):
        admin = self.login("admin-aurora")
        response = self.post("/usuarios/permissao",admin,username="auditor-aurora",role="admin")
        self.assertEqual(response[0],303)
        with storage.connection() as conn:
            user = conn.execute("SELECT role FROM users WHERE username='auditor-aurora'").fetchone()
            self.assertEqual(user["role"],"admin")
            event = conn.execute("""SELECT * FROM audit_events
                WHERE action='alteracao_permissoes'""").fetchone()
            self.assertEqual((event["tenant_id"],event["actor"],event["object_id"],event["result"]),
                             ("aurora","admin-aurora","auditor-aurora","sucesso"))
            rows = [dict(row) for row in conn.execute("SELECT * FROM audit_events")]
        text = json.dumps(rows)
        for password in self.passwords.values():
            self.assertNotIn(password,text)
        self.assertEqual(self.request("POST","/auditoria",admin[0],{"csrf":admin[1]})[0],404)
        self.assertEqual(self.post("/sair",admin)[0],303)
        with storage.connection() as conn:
            self.assertEqual(conn.execute("""SELECT count(*) FROM audit_events WHERE
                tenant_id='aurora' AND actor='admin-aurora' AND action='logout'""").fetchone()[0],1)


if __name__ == "__main__":
    unittest.main()
