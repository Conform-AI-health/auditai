from backend import consultas
"""Interfaces de governança e de conferência de evidências da execução."""
from html import escape
import json
import difflib
from urllib.parse import urlsplit

from backend.administracao import pagina
from frontend.administracao import tabela, navegacao
from backend.datas import data_br
from backend import criterios_dut
from backend import regulatoria


def painel(conn,s,q,form):
    n=pagina(q)
    tenant=s["tenant"]
    linhas = consultas.documentos_com_regra(conn, tenant, n)
    ativa = consultas.regra_ativa(conn, tenant)
    motor=(f'{escape(ativa["norm"])} · documento {ativa["doc"]} · vigência {data_br(ativa["effective"])}'
           if ativa else "Aguardando revisão.")
    html=f'<p>Versão ativa no motor: {motor}</p>'
    html+=form("/regulatoria",s["csrf"],f'<input type="hidden" name="acao" value="consultar"><label>URL da fonte oficial da DUT 60<input required name="url" type="url" value="{escape(regulatoria.FONTE)}"></label>',"Consultar e atualizar DUT 60")
    for r in linhas[:10]:
        doc=r["id"]
        html+=f'<section class="card"><h2>Documento {doc} · {escape(r["state"] or r["status"])}</h2><p>Consulta em {data_br(r["consulted"])} · {escape(r["url"])} · responsável {escape(r["actor"])}</p>'
        edicao=urlsplit(r["url"]).path.rstrip("/").rsplit("/",1)[-1]
        html+=f'<p>Edição identificada pelo arquivo da fonte: {escape(edicao)}.</p>'
        if r["source_hash"]:
            html+=f'<p>SHA-256 da fonte {escape(r["source_hash"])} · <a href="/regulatoria/original/{doc}">Baixar fonte original</a></p>'
        if r["spec"]:
            spec=json.loads(r["spec"])
            divergencias=", ".join(spec["diferencas"]) or "Nenhuma diferença na estrutura mapeada."
            html+=f'<p>Extração: {escape(r["status"])} · {escape(divergencias)}</p><p>Revisão: {escape(r["approved_by"] or "Pendente")} · {escape(r["norm"] or "Ato identificado ao finalizar")}</p>'
            html+=f'<a href="/dut/arquivo/{doc}">Markdown</a> · <a href="/regulatoria/criterios/{doc}">Critérios em JSON</a> · <a href="/beta/vigencia?pagina={n}">Comparar versões</a>'
            anterior = consultas.documento_anterior(conn, tenant, doc)
            if anterior:
                ant=criterios_dut.secoes(anterior[0])
                nova=criterios_dut.secoes(r["body"])
                delta="\n".join(difflib.unified_diff([k+" "+criterios_dut.normal(v) for k,v in ant.items()],
                                                     [k+" "+criterios_dut.normal(v) for k,v in nova.items()],lineterm=""))
                html+="<details><summary>Comparação da DUT com a captura anterior</summary><pre>"+escape(delta or "Texto dos itens idêntico à captura anterior.")+"</pre></details>"
            gold = consultas.ultimo_gabarito(conn, tenant, doc)
            if gold:
                html+='<details><summary>Comparação com '+escape(gold["reference"])+'</summary><pre>'+escape(json.dumps(json.loads(gold["results"]),ensure_ascii=False,indent=2))+'</pre></details>'
            if r["state"] in ("Extraída", "Aguardando validação", "Homologada"):
                campos = (f'<input type="hidden" name="doc" value="{doc}"><input type="hidden" name="acao" value="finalizar">'
                          '<p>Ao finalizar, esta versão fica ativa para as guias da operadora conforme a vigência da DUT.</p>'
                          '<label><input type="checkbox" required name="revisado" value="1"> Revisado</label>')
                html += form("/regulatoria", s["csrf"], campos, "Finalizar")
        html+='</section>'
    html+=navegacao("/regulatoria",q,n,len(linhas)>10)
    historico = consultas.historico_regulatorio(conn, tenant)
    html+='<h2>Histórico regulatório recente</h2>'+tabela(("Documento","Etapa","Data","Responsável","Detalhes"),
           [(r[0],escape(r[1]),data_br(r[2]),escape(r[3]),escape(r[4] or "")) for r in historico])
    guias = consultas.auditorias_de_guias(conn, tenant)
    return html+'<h2>Auditorias recentes de guias</h2>'+tabela(("Execução","Resultado técnico","Data","Responsável","Achados"),
            [(r[0],escape(r[1]),data_br(r[2]),escape(r[3]),escape(" ".join(json.loads(r[4]).get("achados",[])))) for r in guias])


def conferencia(conn,s,run,item,form):
    entrada=json.loads(run["input_snapshot"])
    regra=entrada.get("regra_regulatoria")
    html=f'<a href="/caso/{run["case_id"]}#analise-{run["id"]}">Consultar parecer e documentos da guia</a>'
    if not regra:
        return html+"<p>Execução sem regra regulatória homologada vinculada.</p>"
    spec=regra["estrutura"]
    base=f'/regulatoria/guia/{run["id"]}'
    html+='<form><label>Item da DUT 60<select name="item">'+''.join(
          f'<option value="{k}" {"selected" if k==item else ""}>60.{k} · {escape(criterios_dut.normal(spec["criterios"][k]["referencia_literal"]))}</option>'
          for k in spec["grupos"])+'</select></label><button>Conferir item</button></form>'
    if item not in spec["grupos"]:
        return html
    docs=entrada["documents"]
    for d in docs:
        html+=f'<details><summary>Documento {d["id"]} · {escape(d["name"])}</summary><p>{escape(d["content_text"] or "Sem texto importado.")}</p></details>'
    complementos=entrada.get("documentos_textuais",[])
    for d in complementos:
        paginas="".join(f'<h4>Página {i} · {escape(d["metodo_por_pagina"][i-1])}</h4><p>{escape(texto)}</p>'
                        for i,texto in enumerate(d["paginas"],1))
        html+=f'<details><summary>Complemento {escape(d["documento"])} · {escape(d["nome"])}</summary>{paginas}</details>'
    hidden=f'<input type="hidden" name="item" value="{escape(item)}">'
    opcoes=[]
    for k in criterios_dut.folhas(spec["grupos"][item]):
        for f in spec["criterios"][k]["informacoes_clinicas"]:
            opcoes.append(f'<option value="{escape(k+"|"+f)}">60.{k} · {escape(f)}</option>')
    campos=hidden+'<input type="hidden" name="acao" value="vincular"><label>Condição<select name="fato">'+"".join(opcoes)+'</select></label>'
    opcoes_docs=[str(d["id"]) for d in docs]+[d["documento"] for d in complementos]
    campos+='<label>Documento<select name="documento">'+''.join(f'<option>{escape(v)}</option>' for v in opcoes_docs)+'</select></label>'
    campos+='<label>Trecho literal<textarea required name="trecho" maxlength="2000"></textarea></label><label>O trecho comprova esta condição?<select required name="valor"><option value="">Selecione</option><option>sim</option><option>não</option></select></label>'
    html+=form(base,s["csrf"],campos,"Vincular evidência confirmada")
    html+=form(base,s["csrf"],hidden+'<input type="hidden" name="acao" value="conferir"><label><input type="checkbox" required name="confirmado" value="1">Conferi o escopo do item, as demais hipóteses aplicáveis, os documentos e a fundamentação narrativa do parecer.</label>',"Executar auditoria com conferência médica")
    html+=form(base,s["csrf"],hidden+'<input type="hidden" name="acao" value="reiniciar">',"Iniciar nova conferência do item")
    rows = consultas.conferencias_da_execucao(conn, s["tenant"], run["id"])
    for r in rows:
        html+=f'<details><summary>{data_br(r["created"])} · {escape(r["actor"])} · {escape(json.loads(r["report"])["status"])}</summary><pre>{escape(json.dumps(json.loads(r["report"]),ensure_ascii=False,indent=2))}</pre></details>'
    return html
