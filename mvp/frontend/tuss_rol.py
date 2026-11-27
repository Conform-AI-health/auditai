"""Painel administrativo da correlação oficial TUSS × Rol."""
from html import escape
from backend import tuss_rol


def h(v): return escape(str(v if v is not None else "—"),quote=True)


def painel(conn,session,form):
    tenant=session["tenant"]
    versions=conn.execute("SELECT * FROM tuss_rol_versions WHERE tenant=? ORDER BY id DESC",(tenant,)).fetchall()
    current=next((v for v in versions if v["validation_status"]=="Homologada"),None)
    body=(f'<p>A correlação auxilia a triagem; não determina cobertura nem autoriza negativa automática.</p>'
          f'<p>Fonte oficial: <a href="{h(tuss_rol.SOURCE_URL)}" target="_blank" rel="noreferrer">ANS — Correlação TUSS × Rol</a>. '
          f'Hash SHA-256 <code>{h(tuss_rol.SOURCE_HASH)}</code>.</p>')
    if current:
        rows=conn.execute("SELECT * FROM tuss_rol_mappings WHERE version_id=? ORDER BY tuss_code",(current["id"],)).fetchall()
        table="".join(f'<tr><td><code>{h(r["tuss_code"])}</code></td><td>{h(r["tuss_description"])}</td>'
            f'<td>{h(r["rol_correlation_status"])}</td><td>{h(r["rol_procedure"])}</td><td>{h(r["dut_number"])}</td>'
            f'<td>{h(r["relationship_type"])}</td><td>{h(r["routing_category"])}</td><td>{h(r["source_version"])}</td>'
            f'<td>{h(r["validation_status"])}</td><td>{h(r["validated_at"])}</td></tr>' for r in rows)
        body+=('<div class="tablewrap"><table><thead><tr><th>Código TUSS</th><th>Procedimento</th><th>Correlação</th>'
               '<th>Procedimento no Rol</th><th>DUT</th><th>Tipo de relação</th><th>Fila</th><th>Versão</th>'
               '<th>Validação</th><th>Atualização</th></tr></thead><tbody>'+table+'</tbody></table></div>')
    body+='<h2>Versões e histórico</h2>'
    for v in versions:
        actions=""
        if v["validation_status"]=="Em revisão":
            fields=f'<input type="hidden" name="acao" value="homologar"><input type="hidden" name="version_id" value="{v["id"]}"><label><input type="checkbox" required name="revisado" value="1"> Revisado contra a fonte oficial</label>'
            actions=form("/tuss-rol",session["csrf"],fields,"Homologar versão")
        body+=f'<section class="card"><h3>Versão {v["id"]} · {h(v["validation_status"])}</h3><p>{h(v["source_version"])}</p><small>Vigência {h(v["valid_from"])} a {h(v["valid_until"]) } · responsável {h(v["validated_by"])}</small>{actions}</section>'
    body+=form("/tuss-rol",session["csrf"],'<input type="hidden" name="acao" value="criar_revisao">',"Criar cópia para revisão e comparação")
    events=conn.execute("SELECT * FROM tuss_rol_events WHERE tenant=? ORDER BY id DESC LIMIT 30",(tenant,)).fetchall()
    body+='<h2>Trilha de mudanças</h2><ul>'+"".join(f'<li>{h(e["created"])} · versão {e["version_id"]} · {h(e["stage"])} · {h(e["actor"])}</li>' for e in events)+'</ul>'
    return body
