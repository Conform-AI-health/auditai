from backend import consultas
import re
from html import escape
from urllib.parse import urlencode

from backend import storage
from backend.administracao import pagina
from backend.datas import data_br


def navegacao(url, query, numero, proxima):
    links = []
    for rotulo, destino in (("Anterior",numero-1),("Próxima",numero+1)):
        if destino < 1 or (destino > numero and not proxima):
            continue
        parametros = {k:v[0] for k,v in query.items()}
        parametros["pagina"] = destino
        links.append(f'<a href="{url}?{escape(urlencode(parametros))}">{rotulo}</a>')
    return '<nav>'+" ".join(links)+'</nav>'


def tabela(colunas, linhas, css="", wrap_css="tablewrap"):
    classe = f' class="{escape(css)}"' if css else ""
    w_classe = f' class="{escape(wrap_css)}"' if wrap_css else ' class="tablewrap"'
    return (f'<div{w_classe}><table{classe}><thead><tr>'+''.join(f'<th>{c}</th>' for c in colunas)
            +'</tr></thead><tbody>'+(''.join('<tr>'+''.join(f'<td>{v}</td>' for v in linha)+'</tr>' for linha in linhas)
            or f'<tr><td colspan="{len(colunas)}">Nenhum registro encontrado.</td></tr>')+'</tbody></table></div>')


def auditores(conn,s,q,form):
    n = pagina(q)
    busca = q.get("busca",[""])[0][:120]
    status = q.get("status",[""])[0]
    rows = consultas.listar_auditores(conn, s["tenant"], busca, status, n)
    body = f'<form><label>Busca por nome, usuário ou CRM<input name="busca" value="{escape(busca)}"></label><label>Status<select name="status"><option value="">Todos</option>'
    body += ''.join(f'<option {"selected" if status==v else ""}>{v}</option>' for v in ("Ativo","Inativo"))+'</select></label><button>Filtrar</button></form>'
    def campos(row=None):
        return ''.join(f'<label>{label}<input required name="{key}" value="{escape(str(row[key] or "")) if row else ""}" {"readonly" if row and key=="username" else ""}></label>'
                       for key,label in (("username","Usuário"),("name","Nome completo"),("crm","CRM"),("uf","UF"),("email","E-mail institucional")))
    body += '<details><summary>Cadastrar auditor</summary>'+form("/auditores",s["csrf"],campos()+'<input type="hidden" name="acao" value="criar">',"Cadastrar")+'</details>'
    linhas=[]
    for r in rows[:20]:
        acao = "inativar" if r["estado"]=="Ativo" else "reativar"
        editar = form("/auditores",s["csrf"],campos(r)+'<input type="hidden" name="acao" value="editar">',"Salvar")
        mudar = form("/auditores",s["csrf"],f'<input type="hidden" name="username" value="{escape(r["username"])}"><input type="hidden" name="acao" value="{acao}">',acao.capitalize())
        linhas.append([escape(r["name"] or r["username"]),escape((r["crm"] or "—")+"/"+(r["uf"] or "—")),escape(r["email"] or "—"),
                      "Auditor",escape(s["tenant_name"]),r["estado"],data_br(r["created_at"]),data_br(r["modified"]),
                      "<details><summary>Editar</summary>"+editar+"</details>"+mudar])
    return body+tabela(("Nome","CRM/UF","E-mail","Perfil","Operadora","Status","Cadastro","Alteração","Ações"),linhas)+navegacao("/auditores",q,n,len(rows)>20)


def telemetria(conn,s,q):
    tenant=s["tenant"]
    n=pagina(q)
    guia=q.get("guia",[""])[0]
    if guia and not re.fullmatch(r"[1-9][0-9]{0,12}",guia):
        raise ValueError("Guia inválida.")
    (total, processadas, revisar) = consultas.resumo_processamento(conn, tenant)
    (erros, guias) = consultas.falhas_telemetria(conn, tenant)
    body=f'<p>Guias processadas: {processadas} · Pendentes de análise: {total-processadas} · Aguardando revisão: {revisar} · Guias com falhas: {guias} · Eventos de erro: {erros}</p>'
    medias = consultas.duracao_por_etapa(conn, tenant)
    eventos_norma = consultas.eventos_normativos_recentes(conn, tenant)
    body+="<h2>Eventos regulatórios recentes</h2>"+tabela(("Documento","Etapa","Data","Responsável","Detalhes"),
        [(r[0] or "—",escape(r[1]),data_br(r[2]),escape(r[3]),escape(r[4] or "")) for r in eventos_norma])
    body+=tabela(("Etapa","Tempo médio (ms)"),[(escape(k),int(v)) for k,v in medias])
    eventos = consultas.eventos_telemetria(conn, tenant, guia, n)
    body+=f'<form><label>Linha do tempo por ID da guia<input name="guia" value="{escape(guia)}"></label><button>Consultar</button></form>'
    if guia and storage.case_for(conn,tenant,guia):
        execucoes = consultas.total_execucoes_guia(conn, tenant, guia)
        revisoes = consultas.total_revisoes_ultima_execucao(conn, tenant, guia)
        estado = "Análise pendente" if not execucoes else ("Revisão médica pendente" if not revisoes else "Revisão médica registrada")
        body += f'<h2>Linha do tempo da guia {escape(guia)}</h2><p>{estado} · Execuções: {execucoes} · Reprocessamentos concluídos: {max(0,execucoes-1)}</p>'
    linhas=[(r["id"],f'<a href="/telemetria?guia={r["case_id"]}">{r["case_id"]}</a>',escape(r["stage"]),escape(r["result"]),data_br(r["created"]),
             r["duration_ms"] if r["duration_ms"] is not None else "—",escape(r["actor"]),escape(r["correlation"]),escape(r["version"] or "—"),escape(r["detail"] or "—")) for r in eventos[:50]]
    return body+tabela(("Evento","Guia","Etapa","Status","Data e hora","Duração (ms)","Responsável","Correlação","Versão","Detalhes"),linhas)+navegacao("/telemetria",q,n,len(eventos)>50)


def trilha_auditoria(conn, s, q):
    tenant = s["tenant"]
    n = pagina(q)
    acao = q.get("acao", [""])[0]
    case_id = q.get("case_id", [""])[0]
    if case_id and not re.fullmatch(r"[1-9][0-9]{0,12}", case_id):
        raise ValueError("Identificador de guia inválido.")

    eventos = storage.get_governance_trail(conn, tenant, action=acao or None, case_id=case_id or None, limit=51, offset=(n-1)*50)

    filtro_html = f'''
    <form method="get" action="/trilha" class="trilha-filter-form">
      <div><label class="trilha-filter-label">Filtrar por Ação</label>
        <select name="acao" class="trilha-filter-input">
          <option value="">Todas as ações</option>
          <option value="conferencia_documental" {"selected" if acao=="conferencia_documental" else ""}>Conferência Documental</option>
          <option value="correcao_ocr_transcricao" {"selected" if acao=="correcao_ocr_transcricao" else ""}>Correção de OCR / Versão</option>
          <option value="ajuste_data_protocolo" {"selected" if acao=="ajuste_data_protocolo" else ""}>Ajuste de Data de Protocolo</option>
          <option value="minuta_gerada" {"selected" if acao=="minuta_gerada" else ""}>Geração de Minuta</option>
          <option value="minuta_editada" {"selected" if acao=="minuta_editada" else ""}>Edição de Minuta</option>
          <option value="minuta_aprovada" {"selected" if acao=="minuta_aprovada" else ""}>Aprovação de Minuta</option>
          <option value="minuta_descartada" {"selected" if acao=="minuta_descartada" else ""}>Descarte de Minuta</option>
          <option value="sincronizacao_sigo" {"selected" if acao=="sincronizacao_sigo" else ""}>Sincronização SIGO</option>
        </select>
      </div>
      <div><label class="trilha-filter-label">ID da Guia / Caso</label>
        <input name="case_id" value="{escape(case_id)}" placeholder="Ex.: 1" class="trilha-filter-input">
      </div>
      <button class="btn btn-primary">Filtrar</button>
      <a href="/trilha" class="btn btn-secondary">Limpar</a>
    </form>
    '''

    linhas = []
    for r in eventos[:50]:
        guia_link = f'<a href="/caso/{r["case_id"]}">Guia {r["case_id"]}</a>' if r["case_id"] else "—"
        linhas.append([
            str(r["id"]),
            data_br(r["created_at"]),
            f'{escape(r["actor"])} <small class="text-secondary-muted">({escape(r["role"])})</small>',
            f'<strong>{escape(r["action"])}</strong>',
            f'{escape(r["object_type"])} #{escape(r["object_id"])}',
            guia_link,
            escape(r["old_value"] or "—"),
            escape(r["new_value"] or "—"),
            escape(r["justification"] or "—"),
            escape(r["source_system"] or "AUDITIA"),
        ])

    cabecalho = ("ID", "Data/Hora", "Responsável", "Ação", "Objeto", "Caso", "Valor Anterior", "Novo Valor", "Justificativa", "Origem")
    tabela_html = tabela(cabecalho, linhas)
    nav_html = navegacao("/trilha", q, n, len(eventos) > 50)

    return f'''
    <section class="card">
      <small>Governança Corporativa e Rastreabilidade</small>
      <h2>Trilha de Auditoria e Governança</h2>
      <p class="trilha-desc">Registro contínuo, imutável e auditável de eventos operacionais, correções de transcrição, ajustes de protocolo e deliberações de minutas regulatórias.</p>
      {filtro_html}
      {tabela_html}
      {nav_html}
    </section>
    '''
