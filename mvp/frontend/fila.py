from backend import consultas
from datetime import datetime
from html import escape
from backend.datas import FUSO, data_guia, sla_guia, calcular_sla
from backend.homologacao import PAGE_SIZE, resultados
from frontend.telas import badge_sla, texto_dias_restantes, badge_pendencia_docs


def painel(conn, tenant, codigo, estado, guia, status_guia, pagina, filtro):
    rows = resultados(conn,tenant)
    historico = {r[1]: r for r in rows}
    casos = consultas.fila_de_casos(conn, tenant, codigo, estado, guia, status_guia, pagina)
    concluidos=[r for r in rows if r[4]]
    concordantes=sum(r[2]==r[4] for r in concluidos)
    resumo=f"{len(concluidos)}/{len(rows)} com parecer · {concordantes} classificações concordantes · {sum(bool(r[7]) for r in rows)} primeiras saídas revisadas"
    total_solicitacoes = len(rows)
    concluidas = sum(bool(r[7]) for r in rows)
    revisao_medica = sum(bool(r[4] and not r[7]) for r in rows)
    em_analise = max(0, total_solicitacoes - concluidas - revisao_medica)

    header_html = (
        '<div class="dashboard-header mb-4">'
        '<p class="page-subtitle">Acompanhe as solicitações e prazos regulatórios.</p>'
        '<div class="kpi-grid">'
        f'<div class="kpi-card"><span class="kpi-num">{total_solicitacoes:02d}</span><span class="kpi-label">Solicitações</span></div>'
        f'<div class="kpi-card"><span class="kpi-num">{em_analise:02d}</span><span class="kpi-label">Em análise</span></div>'
        f'<div class="kpi-card kpi-yellow"><span class="kpi-num">{revisao_medica:02d}</span><span class="kpi-label">Revisão médica</span></div>'
        f'<div class="kpi-card"><span class="kpi-num">{concluidas:02d}</span><span class="kpi-label">Concluídas</span></div>'
        '</div>'
        '</div>'
    )

    hoje = datetime.now(FUSO).date()
    linhas = []
    for caso in casos[:PAGE_SIZE]:
        r = historico[caso["id"]]
        c = dict(caso)
        proto = c.get("data_protocolo_operadora")
        data_resposta = c.get("data_resposta_beneficiario")
        sla = calcular_sla(proto, data_encerramento=data_resposta)
        data_limite_txt = data_guia(sla["data_limite"]) if sla.get("data_limite") else "—"
        linhas.append(f'<tr><td><a href="/caso/{r[1]}">{escape(r[0])}</a></td>'
                      f'<td>{escape(c.get("procedure") or "PET-CT solicitado")}</td>'
                      f'<td>{escape(c["guide_status"])}</td><td>{escape(c["estado"])}</td>'
                      f'<td>{data_guia(c["guide_received_at"])}</td>'
                      f'<td>{sla_guia(c["guide_received_at"], c.get("closed_at") or hoje)}</td>'
                      f'<td>{data_limite_txt}</td>'
                      f'<td>{texto_dias_restantes(sla)}</td>'
                      f'<td>{badge_sla(sla)}</td>'
                      f'<td>{badge_pendencia_docs(c.get("total_docs_obrigatorios", 0), c.get("tem_pedido", 0), c.get("tem_anatomo", 0), case=c)}</td>'
                      f'<td>{escape(c.get("beneficiary_code") or "Não informado")}</td>'
                      f'<td>{escape(r[4] or "Pendente")}</td><td>{r[6]}</td><td>{escape("Revisão — "+c["revisao"] if c.get("revisao") else "Pendente")}</td></tr>')
    links = []
    if pagina > 1:
        links.append(f'<a href="/beta?pagina={pagina-1}">Anterior</a>')
    if len(casos) > PAGE_SIZE:
        links.append(f'<a href="/beta?pagina={pagina+1}">Próxima</a>')
    return (f'{header_html}{filtro}<p class="resumo-fila">{resumo}</p><div class="tablewrap"><table class="cases-table"><thead><tr>'
            '<th>Cenário</th><th>Procedimento</th><th>Status da guia</th><th>Status da análise</th>'
            '<th>Data de entrada da guia</th><th title="Dias úteis após a entrada até o encerramento da guia ou, se pendente, até hoje">SLA</th>'
            '<th>Data limite</th><th>Dias restantes</th><th>Situação SLA</th><th>Pendência documental</th>'
            '<th>Código do beneficiário</th><th>Primeira classificação</th><th>Execuções</th><th>Revisão</th></tr></thead><tbody>'
            + ("".join(linhas) or '<tr><td colspan="14">Nenhum caso para estes filtros.</td></tr>')
            + '</tbody></table></div><nav>' + " ".join(links) + '</nav>')
