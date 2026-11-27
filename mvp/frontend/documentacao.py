from backend import consultas
import difflib
from html import escape
from backend import criterios_dut
from backend.datas import data_br
from backend.administracao import pagina
from frontend.administracao import navegacao


def painel(conn,s,form,query):
    numero = pagina(query)
    tenant=s["tenant"]
    base = consultas.documento_validado(conn, tenant)
    original=criterios_dut.BASE.read_text(encoding="utf-8")
    atual=escape(base["filename"]) if base else "DUT60.txt (base da beta)"
    html=f'<h2>Documentação oficial da DUT 60</h2><p>Referência documental atual: {atual}. A homologação documental preserva as regras do motor.</p>'
    html+=form("/beta/vigencia",s["csrf"],'<input type="hidden" name="acao" value="consultar"><label>URL da fonte oficial da DUT 60<input type="url" name="url" required placeholder="https://www.gov.br/ans/..."></label>',"Consultar e atualizar DUT 60")
    documentos = consultas.historico_documental(conn, tenant, numero)
    for r in documentos[:10]:
        html+=f'<details><summary>{data_br(r["consulted"])} · {escape(r["status"])} · {escape(r["validated_by"] or r["actor"])}</summary>'
        if r["filename"]:
            diff="\n".join(difflib.unified_diff((r["baseline"] or original).splitlines(),r["body"].splitlines(),lineterm=""))
            html+=f'<a href="/dut/arquivo/{r["id"]}">{escape(r["filename"])}</a><pre>{escape(diff or "Conteúdo idêntico à referência documental.")}</pre>'
            if not r["validated_by"] and (not base or r["id"]>base["id"]):
                html+=form("/beta/vigencia",s["csrf"],f'<input type="hidden" name="acao" value="validar_documento"><input type="hidden" name="documento" value="{r["id"]}">',"Validar versão documental")
        html+="</details>"
    return html+navegacao("/beta/vigencia",query,numero,len(documentos)>10)
