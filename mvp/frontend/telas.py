"""Telas HTML renderizadas pelo servidor."""
import json
from html import escape
from urllib.parse import urlencode

from backend import consultas, config, datas, storage, homologacao, tuss_rol, vigencia
from backend.adapters import EXAMPLES
from backend.datas import data_br, data_guia
from backend.config import REVIEW_LIMIT, TERM_VERSION
from frontend import administracao

def h(value):
    return escape(str(value), quote=True)


def logo_auditia(variant="horizontal", size_class="", link=True, href="/"):
    """Componente oficial de logotipo AuditIA (100% classes CSS externas, compatível com CSP)."""
    src_map = {
        "horizontal": "/img/logo_horizontal.png",
        "vertical": "/img/logo_vertical.png",
        "symbol": "/img/logo_symbol.png",
    }
    src = src_map.get(variant, "/img/logo_horizontal.png")
    classes = f"logo-auditia logo-{variant}" + (f" {size_class}" if size_class else "")
    img = f'<img src="{src}" alt="AuditIA" class="{classes}">'
    if link:
        return f'<a href="{h(href)}" class="logo-link">{img}</a>'
    return img


def form(url, csrf, fields, button, css="", disabled=False, btn_title="", btn_class=None):
    title_attr = f' title="{h(btn_title)}"' if btn_title else ""
    b_class = btn_class if btn_class else "btn btn-primary"
    return (f'<form method="post" action="{h(url)}" class="api-form {h(css)}">'
            f'<input type="hidden" name="csrf" value="{h(csrf)}">{fields}'
            f'<button class="{h(b_class)}" type="submit"{title_attr} {"disabled" if disabled else ""}>{h(button)}</button></form>')


def layout(title, body, session=None, is_landing=False, hide_h1=False, main_class=""):
    nav = ""
    page_title = f'<h1>{h(title)}</h1>' if (title and not hide_h1) else ""
    if session and session.get("user") and session.get("role") != "login":
        if session["role"] == "admin":
            links = [("/", "Casos"), ("/integracoes", "Integrações"),
                     ("/referencias", "Versões"), ("/auditoria", "Auditoria"),
                     ("/usuarios", "Usuários")]
        else:
            links = [("/", "Casos")]
        if config.BETA and session["role"] == "auditor":
            links = [("/beta","CASOS ANÁLISE")]
        if config.BETA and session["role"] == "admin":
            links = [("/","Administração"),("/usuarios","Usuários"),("/auditores","Gestão de Auditores"),("/telemetria","Telemetria da Auditoria"),
                     ("/trilha","Trilha de Auditoria"),
                     ("/auditoria","Auditoria"),("/beta/resultados.csv","Comparação CSV"),
                     ("/beta/vigencia","Vigência simulada"),("/regulatoria","Auditoria Regulatória — DUT 60"),
                     ("/tuss-rol","Correlação TUSS × Rol")]
        nav = "".join(f'<a href="{url}">{label}</a>' for url, label in links)
        nav += form("/sair", session["csrf"], "", "Sair", "inline")
        role_name = "Administrador da operadora" if session["role"] == "admin" else "Médico auditor"
        tenant = f'<span class="tenant">{h(session["tenant_name"])} · {role_name}</span>'
        home_href = "/beta" if (config.BETA and session.get("role") == "auditor") else "/"
    else:
        tenant = ""
        home_href = "/"

    logo_markup = logo_auditia(variant="horizontal", size_class="logo-header", href=home_href)

    if is_landing:
        header_markup = f'<header class="header-landing"><div class="mast">{logo_markup}</div></header>'
    else:
        header_markup = f'<header><div class="mast">{logo_markup}{tenant}</div><nav aria-label="Navegação principal">{nav}</nav></header>'

    footer_logo = logo_auditia(variant="horizontal", size_class="logo-footer", href=home_href)

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>{h(title + " · AuditIA") if title else "AuditIA"}</title>
    <link rel="icon" type="image/png" href="/img/favicon.png">
    <link rel="shortcut icon" href="/favicon.ico">
    <link href="/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="/estilo.css"></head>
    <body>{header_markup}
    <main{f' class="{h(main_class)}"' if main_class else ""}><div id="alertas" class="alert-container position-fixed top-0 end-0 p-3" aria-live="polite" aria-atomic="true"></div>
    {page_title}
    {body}</main>
    <footer>
      <div class="mast">{footer_logo}</div>
      <div class="footer-normative">Resolução CFM nº 2.454/2026 · Diretriz de Utilização nº 60 da ANS · RN nº 623/2024</div>
      <div class="footer-copyright">© 2026 AuditIA — Governança e Apoio Decisório em Saúde Suplementar</div>
    </footer>
    <script src="/bootstrap.bundle.min.js"></script>
    <script src="/app.js" defer></script></body></html>"""


def card(title, body, label=""):
    return f'<section class="card"><small>{h(label)}</small><h2>{h(title)}</h2>{body}</section>'


def document_upload_form(cid, csrf, missing_kinds):
    fields = ""
    if "pedido_medico" in missing_kinds:
        fields += ('<label>Pedido médico com indicação clínica e justificativa'
            '<input type="file" name="pedido_medico" accept=".pdf,.txt,.png,.jpeg,.jpg,.webp,.bmp,.tif,.tiff"></label>')
    if "anatomopatologico" in missing_kinds:
        fields += ('<label>Laudo da biópsia com anatomopatológico da neoplasia'
            '<input type="file" name="anatomopatologico" accept=".pdf,.txt,.png,.jpeg,.jpg,.webp,.bmp,.tif,.tiff"></label>')
    if not fields:
        return ""
    return ('<p>Envie um documento por vez ou ambos juntos. A análise continuará bloqueada enquanto faltar algum.</p>'
            '<form method="post" action="/caso/documentos" class="api-form" enctype="multipart/form-data">'
            f'<input type="hidden" name="csrf" value="{h(csrf)}">'
            f'<input type="hidden" name="case_id" value="{h(cid)}">{fields}'
            '<button type="submit">Adicionar documento(s)</button></form>')


def terms_page(session):
    body = card("Termo de ciência e aceite para uso de IA",
        '<p>Declaro ciência de que o AuditIA utiliza inteligência artificial apenas como apoio à análise. '
        'A recomendação não substitui meu julgamento crítico, minha autonomia profissional ou minha '
        'responsabilidade pela decisão final.</p>'
        '<p>Comprometo-me a conferir documentos, indicação clínica, critérios da DUT, limitações, riscos e '
        'eventuais vieses; preservar a confidencialidade; não inserir dados reais nesta demonstração; e não '
        'delegar ao sistema decisões ou comunicações que exijam mediação humana.</p>'
        '<p>Posso recusar uma sugestão da IA e devo registrar a fundamentação da revisão. Este aceite registra '
        'a versão do termo, o usuário e a data.</p>'
        '<p><a href="https://sistemas.cfm.org.br/normas/visualizar/resolucoes/BR/2026/2454" '
        'target="_blank" rel="noreferrer">Consultar a Resolução CFM nº 2.454/2026</a>.</p>'
        + form("/termo",session["csrf"],
            '<label><input type="checkbox" name="aceite" value="1" required> Li e aceito as condições de uso responsável.</label>',
            "Aceitar e continuar",disabled=True))
    body += f'<p>Versão {h(TERM_VERSION)} · Texto da beta pendente de validação jurídica. O aceite registra ciência do uso da plataforma. O tratamento de dados sensíveis exige base legal própria.</p>'
    body += form("/termo",session["csrf"],'<input type="hidden" name="recusa" value="1">',"Não aceito")
    return layout("Termo de Ciência e Uso da Plataforma AuditIA",body+'<script defer src="/fluxos.js"></script>')


def case_page(conn, case, session):
    tenant, cid = session["tenant"], case["id"]
    docs = consultas.documentos_da_guia(conn, tenant, cid)
    runs = consultas.execucoes_da_guia(conn, tenant, cid)
    kinds = {doc["kind"] for doc in docs}
    c_dict = dict(case) if hasattr(case, "keys") else (case if isinstance(case, dict) else {})
    body = f'<p class="subtitle">ID interno {cid} · original {h(case["external_id"])} · {h(case["source_system"])}</p>'
    actor = session.get("user", "")
    assumido = c_dict.get("assumido_por")
    trava_expira = c_dict.get("trava_expira_em")
    if assumido == actor:
        btn_devolver = form("/caso/devolver", session["csrf"], f'<input type="hidden" name="case_id" value="{cid}">',
                            "↩️ Devolver à fila de trabalho", "inline case-return-action", btn_class="btn btn-secondary")
        body += f'<div class="alert alert-info">🔒 <strong>Você é o médico responsável por esta análise.</strong> Sua trava médica está ativa. {btn_devolver}</div>'
    elif assumido:
        body += f'<div class="alert alert-warning">⚠️ <strong>Guia sob responsabilidade de outro médico auditor ({h(assumido)}).</strong> Modo somente leitura ativado.</div>'
    else:
        btn_assumir = form("/caso/assumir", session["csrf"], f'<input type="hidden" name="case_id" value="{cid}">',
                           "🔒 Assumir análise desta guia", "inline case-assume-action", btn_class="btn btn-primary")
        body += f'<div class="alert alert-secondary">Guia disponível na fila. {btn_assumir}</div>'
    if session.get("revisao_salva") == cid:
        body += '<p role="status">Revisão médica registrada com sucesso.</p>'
    if session.get("analise_erro"):
        body += f'<div class="alert alert-danger" role="alert">⚠️ <strong>Erro no processamento da análise com IA:</strong> {h(session.pop("analise_erro", ""))}</div>'
    cards = []
    cards.append(("Guia e origem", card("Guia e origem",
                 f'<p>{h(case["narrative"])}</p><dl><dt>Procedimento</dt><dd>{h(case["procedure"])}</dd>'
                 f'<dt>Código TUSS original</dt><dd>{h(case["tuss_code"] or "Não informado")}</dd>'
                 f'<dt>Códigos associados</dt><dd>{h(case["associated_tuss_codes"] or "[]")}</dd>'
                 f'<dt>Pergunta clínica</dt><dd>{"Registrada" if case["clinical_question"] else "Não registrada"}</dd>'
                 f'<dt>Data de entrada da guia</dt><dd>{data_guia(case["guide_received_at"])}</dd>'
                 f'<dt>Atualização na origem</dt><dd>{data_br(case["source_updated_at"])}</dd>'
                 f'<dt>Última importação</dt><dd>{data_br(case["last_imported_at"])}</dd></dl>')))
    triagem=tuss_rol.triagem(conn,tenant,case)
    cards.append(("Triagem TUSS × Rol",card("Triagem TUSS × Rol",
        f'<p><strong>{h(triagem["category"])}</strong> · {h(triagem["status"])}</p><p>{h(triagem["reason"])}</p>'
        f'<small>Código original preservado: {h(triagem["code"] or "não informado")} · versão {h(triagem.get("version_id","não aplicável"))}</small>')))
    if triagem["category"]=="avaliacao_fora_rol":
        ultima=conn.execute("SELECT * FROM out_of_rol_assessments WHERE tenant=? AND case_id=? ORDER BY id DESC LIMIT 1",(tenant,cid)).fetchone()
        estados=json.loads(ultima["statuses"]) if ultima else {}
        campos=f'<input type="hidden" name="case_id" value="{cid}">'
        for chave,label in tuss_rol.LEGAL_ITEMS:
            opcoes='<option value="">Selecione</option>'+''.join(f'<option value="{v}" {"selected" if estados.get(chave)==v else ""}>{h(v.replace("_"," ").title())}</option>' for v in tuss_rol.LEGAL_STATES)
            campos+=f'<label>{h(label)}<select required name="{chave}">{opcoes}</select></label>'
        campos+=f'<label>Fundamentação documental e regulatória<textarea required name="justificativa" maxlength="4000">{h(ultima["justification"] if ultima else "")}</textarea></label>'
        campos+=f'<label>Minuta editável, quando aplicável<textarea name="minuta" maxlength="6000">{h(ultima["draft"] if ultima else "")}</textarea></label>'
        campos+='<label><input type="checkbox" name="revisado" value="1"> Revisão médica registrada nesta avaliação</label>'
        resultado=f'<p><strong>{h(ultima["result"])}</strong></p><pre>{h(ultima["draft"])}</pre>' if ultima else ''
        cards.append(("Avaliação fora do Rol",card("Avaliação de procedimento potencialmente fora do Rol",
            '<p><strong>Resultado regulatório:</strong> procedimento não identificado na correlação do Rol aplicável. Isso não prova ausência absoluta de cobertura.</p>'
            f'<p>Referência jurídica de apoio: {h(tuss_rol.LEGAL_SOURCE)}. Requisitos materiais de cobertura e critérios de apreciação judicial não são equivalentes.</p>'
            +resultado+form("/fora-rol",session["csrf"],campos,"Registrar avaliação e preparar recomendação"))))
    rows = "".join(
        f'<li><a href="/documento/{doc["id"]}" target="_blank">{h(doc["name"])}</a> · {h(doc["kind"])} '
        f'· ID original {h(doc["external_id"])} · {h(doc["source_system"])}</li>' for doc in docs
    ) or '<li>Nenhum documento vinculado.</li>'

    paineis_docs = []
    for doc in docs:
        d_dict = dict(doc) if hasattr(doc, "keys") else (doc if isinstance(doc, dict) else {})
        tem_original = bool(d_dict.get("content_blob") is not None or d_dict.get("local_path"))
        sha = d_dict.get("source_sha256") or ""
        sha_curto = f"{sha[:16]}..." if len(sha) > 16 else (sha or "Não calculado")
        metodo = d_dict.get("extraction_method") or "Não registrado"
        status_conf = d_dict.get("verification_status") or "NAO_CONFERIDO"
        status_label = "Não conferido" if status_conf == "NAO_CONFERIDO" else status_conf
        mime = (d_dict.get("mime_type") or "").lower()
        nome = d_dict.get("name") or ""
        did = d_dict.get("id")

        if tem_original:
            if "pdf" in mime or nome.lower().endswith(".pdf"):
                visualizador = (f'<div class="doc-viewer-pdf-box">'
                                f'<p class="doc-viewer-pdf-title">📄 Documento PDF original preservado ({h(nome)})</p>'
                                f'<p class="doc-viewer-pdf-meta">A visualização embutida em frame é restrita pela política de segurança (<code>frame-ancestors \'none\'</code>). Abra o arquivo original autenticado abaixo e confira a transcrição integral ao lado.</p>'
                                f'<a href="/documento/{did}/visualizar" target="_blank" class="btn btn-secondary doc-open-btn">🔍 Visualizar PDF original em nova aba</a>'
                                f'</div>')
            else:
                visualizador = (f'<div class="doc-viewer-img-box">'
                                f'<img src="/documento/{did}/visualizar" alt="Documento Original" class="doc-viewer-img"></div>'
                                f'<div class="doc-open-wrap"><a href="/documento/{did}/visualizar" target="_blank" class="doc-open-link">🔍 Abrir documento original em nova aba</a></div>')
        else:
            visualizador = ('<div class="notice doc-notice-empty">'
                            '<p class="doc-notice-title"><strong>⚠️ Documento original não disponível para visualização gráfica.</strong></p>'
                            '<p class="doc-notice-sub">Apenas a transcrição textual está preservada neste registro.</p></div>')

        texto_transcrito = d_dict.get("content_text")
        if texto_transcrito and texto_transcrito.strip():
            transcricao_html = f'<div class="doc-transcription-box">{h(texto_transcrito)}</div>'
        else:
            transcricao_html = '<div class="doc-transcription-empty">Transcrição textual não disponível para este documento.</div>'

        versoes = storage.get_document_transcriptions(conn, tenant, did)
        divergencias_texto = d_dict.get("divergences") or ""
        conferido_por = d_dict.get("verified_by") or ""
        conferido_em = d_dict.get("verified_at") or ""

        if status_conf == "CONFERIDO":
            badge_conf = f'<span class="badge bg-success">🟢 Conferido ({h(conferido_por)} · {data_br(conferido_em)})</span>'
        elif status_conf == "DIVERGENTE":
            badge_conf = f'<span class="badge bg-danger">🔴 Divergente</span>'
        else:
            badge_conf = '<span class="badge bg-warning">🟡 Não conferido</span>'

        div_html = f'<div class="doc-divergence-alert"><strong>Divergência registrada:</strong> {h(divergencias_texto)}</div>' if divergencias_texto else ''

        controles_conferencia = (
            f'<div class="doc-controls-row">'
            f'<details class="doc-details-box"><summary class="doc-details-summary">🔍 Registrar Conferência Médica</summary>'
            f'<form action="/documento/conferir" method="post" class="doc-details-form">'
            f'<input type="hidden" name="csrf" value="{session["csrf"]}"><input type="hidden" name="document_id" value="{did}"><input type="hidden" name="case_id" value="{cid}">'
            f'<label class="doc-form-label">Status da conferência: '
            f'<select name="status" class="doc-form-select">'
            f'<option value="CONFERIDO" {"selected" if status_conf=="CONFERIDO" else ""}>Conferido — Fiel ao original</option>'
            f'<option value="DIVERGENTE" {"selected" if status_conf=="DIVERGENTE" else ""}>Divergente — Identificada divergência</option>'
            f'<option value="NAO_CONFERIDO" {"selected" if status_conf=="NAO_CONFERIDO" else ""}>Pendente (Não conferido)</option>'
            f'</select></label>'
            f'<label class="doc-form-label-mt">Apontamento de divergências (diagnóstico, medidas, unidades, negações):'
            f'<textarea name="divergences" class="doc-form-textarea" placeholder="Ex.: A medida informada diverge do laudo de imagem (8mm vs 12mm)...">{h(divergencias_texto)}</textarea></label>'
            f'<button class="btn btn-primary doc-form-btn">Salvar Conferência</button></form></details>'
            f'<details class="doc-details-box"><summary class="doc-details-summary">✏️ Corrigir Transcrição (Gera Nova Versão)</summary>'
            f'<form action="/documento/corrigir-transcricao" method="post" class="doc-details-form">'
            f'<input type="hidden" name="csrf" value="{session["csrf"]}"><input type="hidden" name="document_id" value="{did}"><input type="hidden" name="case_id" value="{cid}">'
            f'<p class="doc-form-hint">O documento original (blob) nunca é sobrescrito. Esta ação cria uma nova versão auditada da transcrição.</p>'
            f'<textarea name="content_text" required class="doc-form-textarea-mono">{h(texto_transcrito or "")}</textarea>'
            f'<label class="doc-form-label-mt">Resumo/Motivo da alteração:'
            f'<input name="change_summary" required placeholder="Ex.: Correção de nódulo 8mm" class="doc-form-input"></label>'
            f'<button class="btn btn-primary doc-form-btn">Salvar Versão</button></form></details>'
            f'</div>'
        )

        versoes_html = ""
        if versoes:
            itens_v = "".join(f'<li><strong>v{v["version"]}</strong> ({data_br(v["created_at"])}) por {h(v["actor"])} [{h(v["source_method"])}]: <em>{h(v["change_summary"] or "Sem notas")}</em></li>' for v in versoes)
            versoes_html = f'<details class="doc-versions-details"><summary class="doc-versions-summary">📜 Histórico de Versões ({len(versoes)} versões registradas)</summary><ul class="doc-versions-list">{itens_v}</ul></details>'

        painel = (
            f'<div class="doc-panel-card">'
            f'<div class="doc-panel-header">'
            f'<h4 class="doc-panel-title">📄 {h(d_dict.get("name","Documento"))} <small class="doc-panel-kind">({h(d_dict.get("kind",""))})</small></h4>'
            f'<span class="doc-panel-id">ID: {h(d_dict.get("external_id",""))}</span>'
            f'</div>'
            f'<div class="doc-meta-bar">'
            f'<span><strong>Método:</strong> <span class="badge bg-secondary">{h(metodo)}</span></span>'
            f'<span><strong>SHA-256:</strong> <code title="{h(sha)}" class="doc-sha-code">{h(sha_curto)}</code></span>'
            f'<span><strong>Conferência:</strong> {badge_conf}</span>'
            f'</div>'
            f'{div_html}'
            f'<div class="doc-compare-grid">'
            f'<div class="doc-compare-col"><h5 class="doc-col-heading">Documento Original Preservado</h5>{visualizador}</div>'
            f'<div class="doc-compare-col"><h5 class="doc-col-heading">Transcrição Fiel Integral</h5>{transcricao_html}</div>'
            f'</div>'
            f'{controles_conferencia}'
            f'{versoes_html}'
            f'</div>'
        )
        paineis_docs.append(painel)

    form_ajuste_proto = (
        f'<details class="proto-adjust-details"><summary class="proto-adjust-summary">🗓️ Ajuste Justificado da Data Original do Protocolo</summary>'
        f'<form action="/caso/protocolo" method="post" class="proto-adjust-form">'
        f'<input type="hidden" name="csrf" value="{session["csrf"]}"><input type="hidden" name="case_id" value="{cid}">'
        f'<p class="doc-form-hint">Alterações da data de protocolo original são registradas de forma imutável na Trilha de Auditoria com justificativa obrigatória.</p>'
        f'<label class="doc-form-label">Nova data original de entrada na operadora: <input name="data_protocolo" value="{h(case["data_protocolo_operadora"] or "")}" required class="doc-form-input"></label>'
        f'<label class="doc-form-label">Justificativa obrigatória da retificação: <textarea name="justificativa" required placeholder="Motivo comprovado da retificação da data..." class="doc-form-textarea"></textarea></label>'
        f'<button class="btn btn-primary doc-form-btn">Registrar Ajuste na Trilha</button></form></details>'
    )

    corpo_docs = f'<ul>{rows}</ul>' + "".join(paineis_docs) + form_ajuste_proto
    cards.append(("Documentos", card("Documentos vinculados ao caso", corpo_docs)))
    faltantes = storage.requisitos_documentais(docs, case=case)
    missing_kinds = {"pedido_medico","anatomopatologico"} - kinds
    c_dict = dict(case) if hasattr(case, "keys") else (case if isinstance(case, dict) else {})
    enc_48h = c_dict.get("enc_complementacao_em")
    prazo_48h_info = datas.calcular_prazo_complementacao_48h(enc_48h) if enc_48h else None

    if faltantes:
        form_enc_48h = ""
        if not enc_48h:
            form_enc_48h = (
                f'<form action="/caso/encaminhar-complementacao" method="post" class="mt-2">'
                f'<input type="hidden" name="csrf" value="{session["csrf"]}">'
                f'<input type="hidden" name="case_id" value="{cid}">'
                f'<button class="btn btn-secondary btn-sm" title="Dispara prazo operacional estimativo de 48h sem alterar o SLA ANS">📤 Encaminhar solicitação de complementação ao operacional (48h)</button>'
                f'</form>'
            )
        else:
            rotulo_48h = prazo_48h_info["rotulo"] if prazo_48h_info else "Encaminhado ao operacional"
            form_enc_48h = f'<p class="text-muted mt-2"><small>⏱️ <strong>Prazo operacional (48h):</strong> {h(rotulo_48h)} (Encaminhado em: {data_br(enc_48h)})</small></p>'

        status_documental = ('<div class="semaforo semaforo-vermelho"><span aria-hidden="true">🔴</span>'
            '<div><strong>Pendência documental fundamental</strong><p>Documentos obrigatórios ausentes: '
            + h("; ".join(faltantes)) + '. A análise pelo Gemini permanece bloqueada para proteger o SLA.</p>'
            + form_enc_48h
            + document_upload_form(cid,session["csrf"],missing_kinds) + '</div></div>')
    else:
        status_documental = ('<div class="semaforo semaforo-verde"><span aria-hidden="true">🟢</span>'
            '<div><strong>Documentação fundamental presente</strong><p>Pedido médico e laudo anatomopatológico vinculados ao caso.</p></div></div>')
    cards.append(("Pendência documental fundamental" if faltantes else "Documentação fundamental",
                  card("Pendência documental fundamental" if faltantes else "Documentação fundamental",
                       status_documental)))

    evidencias = storage.get_clinical_evidences(conn, tenant, cid)
    if evidencias:
        linhas_ev = "".join(
            f'<li><strong>{h(e["fact_key"])}:</strong> {h(e["fact_value"])} '
            f'· Documento: {h(e["document_name"] or "S/N")} (pág. {e["page_number"] or 1}) '
            f'· Trecho literal: <q class="evidence-quote">{h(e["snippet"] or "—")}</q> '
            f'· Status: <span class="badge {"bg-success" if e["verification_status"]=="CONFERIDO" else "bg-warning"}">{h(e["verification_status"])}</span></li>'
            for e in evidencias
        )
        tem_nao_conferida = any(e["verification_status"] != "CONFERIDO" for e in evidencias)
        alerta_ev = '<div class="aviso-alerta">⚠️ <strong>Atenção:</strong> Existem dados clínicos estruturados baseados em evidências ainda não conferidas por médico auditor.</div>' if tem_nao_conferida else ''
        cards.append(("Evidências clínicas", card("Vínculo Clínico-Documental e Evidências", f'<ul class="evidence-list">{linhas_ev}</ul>{alerta_ev}')))

    # Seção MINUTAS REGULATÓRIAS — AUDITIA
    minutas = storage.get_regulatory_drafts(conn, tenant, cid)
    corpo_minuta = ""
    if minutas:
        minuta = minutas[0]
        status_m = minuta["status"]
        if status_m == "APROVADO_MEDICO":
            badge_m = '<span class="badge bg-success">✅ APROVADO PELO MÉDICO AUDITOR</span>'
        elif status_m == "DESCARTADO":
            badge_m = '<span class="badge bg-danger">🗑️ DESCARTADO</span>'
        elif status_m == "EM_EDICAO":
            badge_m = '<span class="badge bg-info">✏️ EM EDIÇÃO PELO AUDITOR</span>'
        else:
            badge_m = '<span class="badge bg-warning">⏳ RASCUNHO_IA — PENDENTE DE REVISÃO MÉDICA</span>'

        corpo_minuta = (
            f'<div class="draft-panel-box">'
            f'<div class="draft-panel-header">'
            f'<h3 class="draft-panel-title">{h(minuta["title"])}</h3>'
            f'<div>{badge_m}</div>'
            f'</div>'
            f'<div class="draft-meta-box">'
            f'<div><strong>Fundamentação normativa:</strong> {h(minuta["normative_basis"])}</div>'
            f'<div><strong>Modalidade regulatória:</strong> <code>{h(minuta["modality"])}</code> · Gerado em: {data_br(minuta["created_at"])} por {h(minuta["actor_created"])}</div>'
            f'</div>'
            f'<div class="draft-governance-warning">'
            f'<strong>Aviso obrigatório de governança:</strong> {h(minuta["disclaimer"])}'
            f'</div>'
            f'<form action="/caso/minuta/acao" method="post">'
            f'<input type="hidden" name="csrf" value="{session["csrf"]}">'
            f'<input type="hidden" name="draft_id" value="{minuta["id"]}">'
            f'<input type="hidden" name="case_id" value="{cid}">'
            f'<label class="draft-form-label">Texto Integral da Minuta Regulatória (Editável pelo médico auditor):</label>'
            f'<textarea name="draft_text" class="draft-text-area">{h(minuta["draft_text"])}</textarea>'
            f'<label class="draft-form-label-mt">Justificativa médica / conduta / observações regulatórias:</label>'
            f'<textarea name="justification" placeholder="Justificativa da conduta médica para registro auditável na Trilha de Governança..." class="draft-justif-area">{h(minuta["decision_justification"] or "")}</textarea>'
            f'<div class="draft-actions-row">'
            f'<button name="acao" value="editar" class="btn btn-secondary">💾 Salvar Alterações no Rascunho</button>'
            f'<button name="acao" value="aprovar" class="btn btn-primary">✅ Aprovar Minuta Técnica</button>'
            f'<button name="acao" value="descartar" class="btn btn-danger-solid">🗑️ Descartar Minuta</button>'
            f'</div>'
            f'</form>'
            f'</div>'
        )

    cards.append(("Minutas regulatórias", card("MINUTAS REGULATÓRIAS — AUDITIA", corpo_minuta or '<p class="text-muted">Nenhuma minuta gerada para este caso. A minuta será gerada automaticamente na análise com IA.</p>')))
    fields = (f'<input type="hidden" name="case_id" value="{cid}">'
              f'<label>Resumo fictício<textarea name="narrative" required maxlength="6000">{h(case["narrative"])}</textarea></label>'
              f'<label><input type="checkbox" name="question" value="1"'
              f' {"checked" if case["clinical_question"] else ""}> Pergunta clínica registrada</label>')
    if not config.BETA:
        cards.append(("Atualizar dados de ensaio",
                      card("Atualizar dados de ensaio", form("/caso/alterar", session["csrf"], fields, "Salvar alteração"))))
    check = storage.latest_approved(conn, tenant, "checklist")
    ref = storage.latest_approved(conn, tenant, "reference")
    if not config.AI_ENABLED:
        cards.append(("Modo de validação", card(
            "Modo de validação",
            "<p>Análises automatizadas estão desabilitadas nesta instância. Os dados e pareceres existentes permanecem disponíveis para consulta.</p>",
        )))
    elif check and ref:
        lbl_ia = "⚡ Reanalisar com IA (Gemini)" if runs else "⚡ Analisar com IA (Gemini)"
        if assumido and assumido != actor:
            corpo_analise_ia = (
                f'<p class="text-muted">🔒 Esta guia está sob responsabilidade de outro médico auditor ({h(assumido)}). '
                f'O acesso de execução clínica é restrito ao médico responsável.</p>'
            )
        else:
            corpo_analise_ia = (
                f'<p>Inicia a análise clínica automatizada com inteligência artificial (Gemini) utilizando a base regulatória oficial (DUT 60) e os documentos anexos.</p>'
                f'<form action="/parecer" method="post" class="ai-analysis-action-box" '
                f'onsubmit="const b=this.querySelector(\'button\'); if(b){{b.disabled=true; b.innerText=\'Processando análise com IA (Gemini)...\';}}">'
                f'<input type="hidden" name="csrf" value="{h(session["csrf"])}">'
                f'<input type="hidden" name="case_id" value="{cid}">'
                f'<button class="btn btn-primary btn-action-primary btn-lg" type="submit" title="Gerar parecer">{lbl_ia} <span class="visually-hidden">Gerar parecer</span></button>'
                f'</form>'
            )
        cards.append(("Apoio decisório", card("Apoio decisório — Análise com IA", corpo_analise_ia)))
    else:
        cards.append(("Execução indisponível", card("Execução indisponível",
                     "<p>Falta checklist ou referência aprovada nesta operadora.</p>")))
    for run in runs:
        output = json.loads(run["original_output"])
        original = json.loads(run["input_snapshot"])
        checklist = json.loads(run["checklist_snapshot"])
        reference = json.loads(run["reference_snapshot"])
        ck = consultas.versao_catalogo(conn, tenant, run['checklist_version_id'])
        rf = consultas.versao_catalogo(conn, tenant, run['reference_version_id'])
        criteria = "".join(
            f'<li><b>{h(c["item"])}</b>: {h(c["state"])}</li>' for c in output["criteria"]
        )
        revs = consultas.revisoes_da_execucao(conn, tenant, run['id'])
        rev_html = "".join(
            f'<blockquote><b>Revisão — {h(r["position"])}</b> · {h(r["conformity_status"] or "Registro anterior")} '
            f'· execução {run["id"]}<p>{h(r["note"])}</p><p>{h(r["corrected_suggestion"])}</p>'
            f'<small>{h(r["actor"])} · {data_br(r["created_at"])}</small></blockquote>' for r in revs)
        fields = (f'<input type="hidden" name="run_id" value="{run["id"]}">'
                  '<label>Status de conformidade<select required name="conformity"><option value="">Selecione</option>'
                  '<option>Conforme</option><option>Não conforme</option></select></label>'
                  '<label>Avaliação da recomendação do AuditIA<select required name="position"><option value="">Selecione</option>'
                  '<option>Concordo</option><option>Discordo</option></select></label>'
                  f'<label>Observação / Conduta do médico auditor<textarea required name="note" maxlength="{REVIEW_LIMIT}"></textarea>'
                  f'<output>0 / {REVIEW_LIMIT}</output></label>')
        tecnico = consultas.status_regulatorio(conn, tenant, run['id'])
        export = (f'<p>Auditoria técnica: {h(tecnico[0])}. <a href="/regulatoria/guia/{run["id"]}">Conferir evidências e critérios</a></p>' if tecnico else "")
        detalhe = ""
        if "parecer" in output:
            detalhe = card("A · Parecer técnico preliminar",
                "".join(f'<h3>{titulo}</h3><p class="pre-wrap-text">{h(output["parecer"][campo])}</p>'
                for campo,titulo in [("sintese","Síntese"),("confronto","Confronto clínico × DUT"),
                ("pendencias","Pendências"),("confiabilidade","Limitações e confiabilidade")])
                + f'<h3>B · Minuta para revisão</h3><pre>{h(output["parecer"]["minuta"])}</pre>'
                + f'<small>Modelo {h(output["modelo"])}</small>')
            if revs and revs[-1]["stage"] == "conclusao":
                rid = f'<input type="hidden" name="run_id" value="{run["id"]}">'
                if not config.BETA:
                    export += form("/gerencia",session["csrf"],rid,"Baixar pacote PDF para discussão gerencial")
                    export += form("/operadora",session["csrf"],rid +
                    '<label>Decisão médica no simulador da operadora<select name="decisao">'
                    '<option value="">Selecione</option><option>Autorizar</option><option>Negar</option></select></label>'
                    '<label>Justificativa da decisão<textarea required name="justificativa" maxlength="2000"></textarea></label>',
                    "Registrar decisão na operadora fictícia")
        execution_card = (f'Execução {run["id"]}', card(
            f'Execução {run["id"]} · {data_br(run["created_at"])}',
            f'<p id="analise-{run["id"]}"><b>Checklist v{ck["version"]}, referência v{rf["version"]}</b>'
            f' · execução por {h(run["actor"])}</p>'
            f'<p>{h(output["suggestion"])}</p><ul>{criteria}</ul>'
            f'<p>{h(output["scope"])}</p>'
            f'<p><a href="{h(reference["source_url"])}" target="_blank" rel="noreferrer">'
            'Consultar referência no portal da ANS</a> (aplicabilidade a conferir)</p>'
            f'<h3 id="historico-{run["id"]}">Histórico das revisões</h3><div id="revisada-{run["id"]}">{rev_html}</div><h3 id="revisao-{run["id"]}">Revisão médica da análise</h3>{form("/revisar",session["csrf"],fields,"Registrar revisão médica")}{export}',
            "HISTÓRICO PRESERVADO"))
        if detalhe:
            cards.append((f'Parecer da execução {run["id"]}',
                          f'<div id="parecer-{run["id"]}" class="case-section">'
                          f'<h2>Parecer da execução {run["id"]}</h2>{detalhe}</div>'))
        cards.append(execution_card)
    left_titles = {"Guia e origem", "Documentos", "Pendência documental fundamental", "Documentação fundamental", "Evidências clínicas"}
    left_html = "".join(f'<div class="case-section">{sec}</div>' for title, sec in cards if title in left_titles)
    right_html = "".join(f'<div class="case-section">{sec}</div>' for title, sec in cards if title not in left_titles)
    content = f'<div class="case-grid-layout"><div class="case-column case-col-left">{left_html}</div><div class="case-column case-col-right">{right_html}</div></div>'
    return layout(f'Caso {cid}', body+content
                  +'<script defer src="/fluxos.js"></script>', session)


def badge_sla(sla):
    status = sla.get("status")
    detalhe = h(sla.get("detalhe") or "")
    if status == datas.STATUS_VENCIDO:
        return f'<span class="badge bg-danger" title="{detalhe}">Vencido</span>'
    elif status == datas.STATUS_ALERTA:
        return f'<span class="badge bg-warning text-dark" title="{detalhe}">Alerta</span>'
    elif status == datas.STATUS_NO_PRAZO:
        return f'<span class="badge bg-success" title="{detalhe}">No prazo</span>'
    elif status == datas.STATUS_PROTOCOLO_AUSENTE:
        return f'<span class="badge bg-secondary" title="{detalhe}">Protocolo ausente</span>'
    elif status == datas.STATUS_CONCLUIDO_NO_PRAZO:
        return f'<span class="badge bg-info text-dark" title="{detalhe}">Concluído no prazo</span>'
    elif status == datas.STATUS_CONCLUIDO_FORA_PRAZO:
        return f'<span class="badge bg-secondary" title="{detalhe}">Concluído fora do prazo</span>'
    return f'<span class="badge bg-secondary">{h(sla.get("rotulo_status") or "—")}</span>'


def texto_dias_restantes(sla):
    status = sla.get("status")
    if status == datas.STATUS_PROTOCOLO_AUSENTE:
        return '<span class="text-muted">—</span>'
    if status in (datas.STATUS_CONCLUIDO_NO_PRAZO, datas.STATUS_CONCLUIDO_FORA_PRAZO):
        return '<span class="text-muted">Concluído</span>'
    restantes = sla.get("dias_uteis_restantes")
    if restantes is None:
        return '<span class="text-muted">—</span>'
    if restantes < 0:
        return f'<span class="badge bg-danger">{abs(restantes)} d.u. em atraso</span>'
    if restantes == 0:
        return '<span class="badge bg-warning text-dark">Vence hoje</span>'
    if restantes == 1:
        return '<span class="badge bg-warning text-dark">1 d.u. restante</span>'
    return f'<span>{restantes} d.u. restantes</span>'


def avaliar_documentacao_caso(case):
    """
    Avalia a necessidade documental conforme os critérios da DUT 60 e indicação clínica,
    centralizado nas regras de backend.criterios_dut.
    """
    from backend import criterios_dut
    return criterios_dut.categorizar_documentos_caso(case, None)


def badge_pendencia_docs(total_docs, tem_pedido, tem_anatomo, case=None):
    if case is not None:
        return avaliar_documentacao_caso(case)["badge_html"]
    if total_docs == 2 or (tem_pedido and tem_anatomo):
        return '<span class="badge bg-success">Completa</span>'
    if total_docs == 1 or tem_pedido or tem_anatomo:
        if tem_pedido:
            return '<span class="badge bg-warning text-dark">Falta laudo</span>'
        return '<span class="badge bg-warning text-dark">Falta pedido</span>'
    return '<span class="badge bg-danger">Falta pedido e laudo</span>'


def determinar_acao_primaria(c, current_user=""):
    """
    Determina a ação contextual única:
    - Concluída / Fechada: Visualizar
    - Em análise por outro médico: Visualizar (somente leitura)
    - Novos documentos recebidos: Reanalisar com IA
    - Prazo de complementação 48h vencido: Reavaliar
    - Pendência de codificação / divergência: Regularizar
    - Aguardando revisão de sugestão da IA ou parecer prévio: Revisar
    - Guia elegível para análise automatizada: Analisar com IA
    """
    if c.get("data_resposta_beneficiario") or c.get("closed_at"):
        return "Visualizar"
    assumido = c.get("assumido_por")
    if assumido and assumido != current_user:
        return "Visualizar"

    # Verificação de novos documentos após análise prévia (REQ-11.2 / REQ-18)
    if c.get("novos_docs_recebidos") == "1":
        return "Reanalisar com IA"

    # Aguardando revisão de sugestão da IA ou parecer prévio
    if c.get("position") or (c.get("sugestao") and c.get("sugestao") != "Pendente"):
        return "Revisar"

    # Verificação de prazo de complementação 48h (REQ-11.2)
    enc_48h = c.get("enc_complementacao_em")
    if enc_48h:
        prazo_info = datas.calcular_prazo_complementacao_48h(enc_48h)
        if prazo_info and prazo_info.get("vencido"):
            return "Reavaliar"

    # Pendência de codificação / divergência cadastral confirmada (REQ-05 / REQ-16)
    if c.get("divergence_detected") == "1":
        return "Regularizar"

    # Guia elegível para análise clínica automatizada com IA
    return "Analisar com IA"


def badge_status_analise(c):
    if c.get("data_resposta_beneficiario"):
        return ('<span class="badge-status status-concluida">Concluída</span>',
                "Concluída — Resposta conclusiva ao beneficiário emitida")
    if c.get("divergence_detected") == "1":
        return ('<span class="badge-status status-pendencia-codificacao">Pendência de codificação</span>',
                "Pendência de codificação — Aguardando correção/liberação na operadora")
    enc_48h = c.get("enc_complementacao_em")
    if enc_48h:
        prazo_info = datas.calcular_prazo_complementacao_48h(enc_48h)
        if prazo_info and prazo_info.get("vencido"):
            return ('<span class="badge-status status-prazo-vencido">Prazo de complementação vencido</span>',
                    "Prazo estimativo de 48h vencido — Reavaliação necessária")
        return ('<span class="badge-status status-pendencia-documental">Pendência documental (48h)</span>',
                f"Aguardando documentação complementar (iniciado em: {data_br(enc_48h)})")
    if not c.get("tem_pedido"):
        return ('<span class="badge-status status-pendencia-documental">Pendência documental</span>',
                "Aguardando envio de documentação obrigatória complementar")
    if c.get("novos_docs_recebidos") == "1":
        return ('<span class="badge-status status-novos-documentos">Novos documentos</span>',
                "Novos documentos vinculados — Guia disponível para reanálise")
    if c.get("position"):
        pos = c["position"]
        return (f'<span class="badge-status status-revisada">Revisão — {h(pos)}</span>',
                f"Revisão médica registrada: {h(pos)}")
    if c.get("assumido_por"):
        return ('<span class="badge-status status-em-analise">Em análise</span>',
                f"Em análise clínica pelo médico: {h(c['assumido_por'])}")
    if c.get("sugestao") and c.get("sugestao") != "Pendente":
        return ('<span class="badge-status status-revisao-medica">Revisão médica</span>',
                f"Aguardando revisão médica · Sugestão da IA: {h(c['sugestao'])}")
    return ('<span class="badge-status status-aguardando">Aguardando análise</span>',
            "Aguardando início de análise clínica")



def cases_page(conn, session, query):
    tenant = session["tenant"]
    if session["role"] == "admin":
        n_users = conn.execute("SELECT count(*) FROM users WHERE tenant_id=?", (tenant,)).fetchone()[0]
        n_auditores = conn.execute("SELECT count(*) FROM users WHERE tenant_id=? AND role='auditor'", (tenant,)).fetchone()[0]
        n_casos = conn.execute("SELECT count(*) FROM cases WHERE tenant_id=?", (tenant,)).fetchone()[0]
        n_runs = conn.execute("SELECT count(*) FROM runs WHERE tenant_id=?", (tenant,)).fetchone()[0]

        admin_header = (
            '<div class="dashboard-header mb-4">'
            '<p class="page-subtitle">Gestão operacional, acessos e governança.</p>'
            '<div class="kpi-grid">'
            f'<div class="kpi-card"><span class="kpi-label">Usuários ativos</span><span class="kpi-num">{n_users:02d}</span></div>'
            f'<div class="kpi-card"><span class="kpi-label">Auditores</span><span class="kpi-num">{n_auditores:02d}</span></div>'
            f'<div class="kpi-card"><span class="kpi-label">Casos cadastrados</span><span class="kpi-num">{n_casos:02d}</span></div>'
            f'<div class="kpi-card kpi-yellow"><span class="kpi-label">Execuções de IA</span><span class="kpi-num">{n_runs:02d}</span></div>'
            '</div>'
            '</div>'
        )
        modulos = (
            '<div class="grid">'
            '<a class="card" href="/usuarios"><h2>Usuários e permissões</h2></a>'
            '<a class="card" href="/auditores"><h2>Gestão de Auditores</h2></a>'
            '<a class="card" href="/telemetria"><h2>Telemetria da Auditoria</h2></a>'
            '<a class="card" href="/auditoria"><h2>Auditoria da plataforma</h2></a>'
            '<a class="card" href="/beta/resultados.csv"><h2>Comparação com gabarito (CSV)</h2></a>'
            '<a class="card" href="/regulatoria"><h2>Auditoria Regulatória — DUT 60</h2></a>'
            '<a class="card" href="/tuss-rol"><h2>Correlação TUSS × Rol</h2></a>'
            '<a class="card" href="/beta/vigencia"><h2>Vigência simulada</h2></a>'
            '</div>'
        )
        return layout("Painel administrativo",
                      '<p>Este perfil administra usuários e versões. O acesso clínico não é concedido automaticamente.</p>'
                      + admin_header + modulos, session)
    pagina = administracao.pagina(query)
    current_user = session.get("user", "")

    # Parâmetros de pesquisa e filtragem (REQ-07, REQ-13, REQ-14, REQ-19)
    busca = query.get("busca_beneficiario", [""])[0][:100]
    card_filtro = query.get("card", [""])[0]
    periodo = query.get("periodo", ["hoje"])[0]
    ordem_sla = query.get("ordem_sla", ["padrao"])[0]

    # Obter os 6 KPIs dinâmicos (REQ-07 / REQ-19)
    kpis = consultas.kpis_dashboard_medico(conn, tenant, current_user, periodo=periodo)

    # Obter os casos filtrados e ordenados
    cases = consultas.casos_da_operadora(conn, tenant, pagina, busca_beneficiario=busca,
                                         card_filtro=card_filtro, ordem_sla=ordem_sla,
                                         current_user=current_user)

    # Saudação personalizada (REQ-20)
    titulo_saudacao, subtitulo_saudacao = storage.obter_saudacao_usuario(conn, tenant, current_user)

    rows = []
    import re
    for case in cases[:20]:
        c = dict(case)
        case_id = c["id"]
        proto = c.get("data_protocolo_operadora")
        data_resposta = c.get("data_resposta_beneficiario")
        sla = datas.calcular_sla(proto, data_encerramento=data_resposta)
        data_limite_txt = data_guia(sla["data_limite"]) if sla.get("data_limite") else "—"
        entrada_txt = data_guia(proto) if proto else "Protocolo ausente"
        dias_txt = texto_dias_restantes(sla)
        dias_plain = re.sub(r'<[^>]+>', '', dias_txt).strip()

        action_label = determinar_acao_primaria(c, current_user=current_user)
        assumido = c.get("assumido_por")

        if action_label in ("Analisar com IA", "Reanalisar com IA") and not config.AI_ENABLED:
            btn_primary = f'<a class="btn btn-secondary case-action case-open" href="/caso/{case_id}">Visualizar</a>'
        elif action_label in ("Analisar com IA", "Reanalisar com IA"):
            btn_primary = (
                f'<form method="post" action="/parecer" class="inline case-action-form" '
                f'onsubmit="const b=this.querySelector(\'button\'); if(b){{b.disabled=true; b.innerText=\'Processando...\';}}">'
                f'<input type="hidden" name="csrf" value="{session["csrf"]}">'
                f'<input type="hidden" name="case_id" value="{case_id}">'
                f'<button class="btn btn-primary case-action case-open btn-action-primary" type="submit" '
                f'title="Executar análise clínica automatizada com IA (Gemini)">'
                f'⚡ {action_label}'
                f'</button>'
                f'</form>'
            )
        elif action_label == "Visualizar":
            btn_primary = f'<a class="btn btn-secondary case-action case-open" href="/caso/{case_id}">{action_label}</a>'
        else:
            btn_primary = f'<a class="btn btn-primary case-action case-open btn-action-primary" href="/caso/{case_id}">{action_label}</a>'

        opinion_form = ""
        if config.AI_ENABLED:
            opinion_form = form("/parecer", session["csrf"],
                                f'<input type="hidden" name="case_id" value="{case_id}">',
                                "Gerar parecer", "inline case-action case-opinion")
        management_fields = f'<input type="hidden" name="case_id" value="{case_id}">'
        finish_form = form("/caso/finalizar", session["csrf"], management_fields,
                           "Finalizar caso", "inline case-action case-finish")

        # Mantém compatibilidade com testes e padronização contextual (REQ-16)
        actions = (
            f'<div class="case-actions">'
            f'{btn_primary}'
            f'<details class="case-extra-actions visually-hidden">'
            f'<summary class="case-more-toggle">···</summary>'
            f'<div class="case-more-menu">{opinion_form}{finish_form}</div>'
            f'</details>'
            f'</div>'
        )

        sla_tooltip = f'Situação: {sla.get("rotulo_status") or "—"} · Dias restantes: {dias_plain} · Entrada original: {entrada_txt}'
        status_html, status_tooltip = badge_status_analise(c)

        # REQ-21: Responsável atual / Última análise / travessão
        assumido_por = c.get("assumido_por")
        resp_anterior = c.get("responsavel_anterior") or c.get("medico_responsavel")
        if assumido_por:
            medico_html = f'<div class="col-medico" title="Responsável atual: {h(assumido_por)}"><span class="medico-nome">{h(assumido_por)}</span><small class="text-muted d-block">Responsável atual</small></div>'
        elif resp_anterior and resp_anterior != "Pendente":
            medico_html = f'<div class="col-medico" title="Última análise: {h(resp_anterior)}"><span class="medico-nome">{h(resp_anterior)}</span><small class="text-muted d-block">Última análise</small></div>'
        else:
            medico_html = '<span class="col-medico text-muted" title="Nunca analisada">—</span>'

        # REQ-16 / REQ-17: Localização (AMM, AMOP ou presença simultânea)
        loc = c.get("localizacao_sigo") or c.get("fila_origem") or "AMM"
        loc_badge = f'<span class="badge bg-secondary font-mono loc-badge">{h(loc)}</span>'

        rows.append((
            f'<a href="/caso/{case_id}" class="col-guia font-mono" title="ID interno: {case_id}">{h(c["external_id"])}</a>',
            f'<span class="col-beneficiario font-mono" title="{h(c.get("beneficiary_code") or "Não informado")}">{h(c.get("beneficiary_code") or "Não informado")}</span>',
            f'<span class="col-procedimento" title="{h(c["procedure"])}">{h(c["procedure"])}</span>',
            f'<div class="col-sla" title="{h(sla_tooltip)}">{badge_sla(sla)}</div>',
            f'<span class="col-data-limite font-mono" title="Data limite de resposta conclusiva (Entrada original: {h(entrada_txt)})">{h(data_limite_txt)}</span>',
            status_html,
            f'<div class="col-pendencia">{badge_pendencia_docs(c.get("total_docs_obrigatorios", 0), c.get("tem_pedido", 0), c.get("tem_anatomo", 0), case=c)}</div>',
            medico_html,
            loc_badge,
            actions
        ))

    # Link ordenável de SLA (REQ-13)
    prox_ordem_sla = "sla_desc" if ordem_sla == "sla_asc" else "sla_asc"
    link_sla = f'<a href="/?ordem_sla={prox_ordem_sla}&card={h(card_filtro)}&periodo={h(periodo)}&busca_beneficiario={h(busca)}" title="Alternar ordenação por prazo de SLA">Situação SLA ↕</a>'

    cases_table = administracao.tabela(
        ('<abbr title="Nº guia">Nº da guia</abbr>',
         '<abbr title="Código do beneficiário">Cód. beneficiário</abbr>',
         '<abbr title="Procedimento solicitado">Procedimento</abbr>',
         link_sla,
         '<abbr title="Data-limite de resposta conclusiva a partir da Entrada">Data limite</abbr>',
         '<abbr title="Status da análise médica (Status análise)">Status da análise</abbr>',
         '<abbr title="Pendência de documentos obrigatórios">Pendência documental</abbr>',
         '<abbr title="Médico resp.">Médico resp.</abbr>',
         '<abbr title="Localização na operadora (AMM/AMOP)">Localização</abbr>',
         "Ações"),
        rows, "cases-table", "tablewrap cases-table-wrap")

    # Exibir conector simulado SIGO/Oracle (Aurora Saúde)
    fields_sigo = '<input type="hidden" name="connector" value="sigo">'
    imports = (
        '<div class="actions">'
        + form("/sincronizar", session["csrf"], fields_sigo,
               "Importar solicitações", "inline import-action",
               btn_title="Importar casos fictícios — SIGO")
        + '<span class="visually-hidden">Importação de casos fictícios</span>'
        + '</div>'
    )

    # REQ-15: Data/hora da última sincronização bem-sucedida
    ultimo_sync = conn.execute("""
        SELECT finished_at, status FROM sync_jobs
        WHERE tenant_id=? AND connector='SIGO' AND status='sucesso'
        ORDER BY id DESC LIMIT 1
    """, (tenant,)).fetchone()
    sync_time_txt = data_br(ultimo_sync["finished_at"]) if ultimo_sync else "Nenhuma sincronização realizada"
    sync_info = f'<p class="sync-last-time muted"><small>Última sincronização bem-sucedida: {sync_time_txt}</small></p>'

    imports_card = (
        '<details class="card mb-4 imports-details-card glass-panel">'
        '<summary class="imports-details-summary" title="Integração com a operadora">'
        '⚡ Integração com a operadora — SIGO/Oracle</summary>'
        '<div class="imports-details-body">'
        + sync_info
        + imports +
        '</div></details>'
    )

    # 6 Cards clicáveis com Warm Glass (REQ-07, REQ-22)
    def card_link(tipo, rotulo, valor, highlight=False):
        ativo = " active-card" if card_filtro == tipo else ""
        hl = " glass-panel--highlight" if highlight else ""
        url = f"/?card={tipo}&periodo={h(periodo)}"
        return (f'<a href="{url}" class="kpi-card glass-panel{hl}{ativo}">'
                f'<span class="kpi-label">{rotulo}</span>'
                f'<span class="kpi-num">{valor:02d}</span></a>')

    grid_6_cards = (
        '<div class="kpi-grid kpi-grid-6">'
        + card_link("", "Solicitações", kpis["solicitacoes"])
        + card_link("aguardando", "Aguardando análise", kpis["aguardando"])
        + card_link("em_analise", "Em análise", kpis["em_analise"])
        + card_link("pendencias_codificacao", "Pendências de codificação", kpis["pendencias_codificacao"])
        + card_link("pendencias_documentais", "Pendências documentais", kpis["pendencias_documentais"], highlight=True)
        + card_link("concluidas", "Concluídas", kpis["concluidas"])
        + '</div>'
    )

    # Filtro por período discreto (REQ-19)
    periodo_form = (
        f'<div class="periodo-filter-bar mb-3">'
        f'<form method="get" action="/" class="d-flex align-items-center gap-2">'
        f'<input type="hidden" name="card" value="{h(card_filtro)}">'
        f'<input type="hidden" name="busca_beneficiario" value="{h(busca)}">'
        f'<label class="small text-muted mb-0"><strong>Período de produtividade:</strong></label>'
        f'<select name="periodo" class="form-select form-select-sm auto-submit-select" onchange="this.form.submit()">'
        f'<option value="hoje" {"selected" if periodo=="hoje" else ""}>Hoje (padrão)</option>'
        f'<option value="7dias" {"selected" if periodo=="7dias" else ""}>Últimos 7 dias</option>'
        f'<option value="mes" {"selected" if periodo=="mes" else ""}>Mês atual</option>'
        f'<option value="todos" {"selected" if periodo=="todos" else ""}>Todo o período</option>'
        f'</select>'
        f'<noscript><button type="submit" class="btn btn-sm btn-secondary">Filtrar</button></noscript>'
        f'</form>'
        f'</div>'
    )

    # Campo único de busca por código de beneficiário (REQ-14)
    busca_bar = (
        f'<div class="search-filter-bar mb-3">'
        f'<form method="get" action="/" class="d-flex align-items-center gap-2">'
        f'<input type="hidden" name="card" value="{h(card_filtro)}">'
        f'<input type="hidden" name="periodo" value="{h(periodo)}">'
        f'<input type="text" name="busca_beneficiario" value="{h(busca)}" placeholder="Buscar código do beneficiário..." class="form-control form-control-sm" style="max-width: 320px;">'
        f'<button type="submit" class="btn btn-sm btn-primary">Buscar</button>'
        + (f'<a href="/?card={h(card_filtro)}&periodo={h(periodo)}" class="btn btn-sm btn-secondary">Limpar</a>' if busca else '')
        + f'</form>'
        f'</div>'
    )

    header_dashboard = (
        f'<div class="dashboard-header mb-4">'
        f'<h2 class="page-title">{h(titulo_saudacao)}</h2>'
        f'<p class="page-subtitle">{h(subtitulo_saudacao)}</p>'
        f'{periodo_form}'
        f'{grid_6_cards}'
        f'</div>'
    )

    return layout("Painel de auditoria médica",
                  '<p class="tenant-scope-note">Somente casos da operadora indicada no cabeçalho são consultados nesta sessão.</p>'
                  + header_dashboard
                  + imports_card
                  + busca_bar
                  + cases_table
                  + administracao.navegacao("/", query, pagina, len(cases) > 20),
                  session, main_class="dashboard-main dashboard-warm-glass")


def management_page(conn, session, query):
    n = administracao.pagina(query)
    busca = query.get("guia",[""])[0][:100]
    ordem = query.get("ordem",["recente"])[0]
    rows = consultas.pacotes_gerenciais(conn, session["tenant"], busca, ordem, n)
    content=f'<form><label>Número da guia<input name="guia" value="{h(busca)}"></label><label>Ordenar por encaminhamento<select name="ordem"><option value="recente">Mais recente</option><option value="antigo" {"selected" if ordem=="antigo" else ""}>Mais antigo</option></select></label><button>Filtrar</button></form>'
    linhas=[]
    for r in rows[:20]:
        url=f'/caso/{r["case_id"]}'
        acoes=" ".join(f'<a href="{url}#{alvo}-{r["id"]}">{label}</a>' for alvo,label in
                       (("analise","Visualizar análise"),("revisada","Consultar revisão médica"),("historico","Consultar histórico")))
        acoes+=f' <a href="/pacote/{r["id"]}">Abrir pacote gerencial</a>'
        acoes+=form("/gerencia",session["csrf"],f'<input type="hidden" name="run_id" value="{r["id"]}">',"Gerar PDF")
        linhas.append((h(r["external_id"]),h(r["beneficiary_code"] or "Não informado"),h(r["procedure"]),
                       data_guia(r["guide_received_at"]),h(r["sugestao"]),"Revisão — "+h(r["position"]),
                       data_br(r["created_at"]),h(r["actor"]),acoes))
    content+=administracao.tabela(("Número da guia","Código do beneficiário","Procedimento solicitado","Data de entrada da guia",
                    "Status da análise","Status da revisão médica","Data de encaminhamento","Médico responsável","Ações"),linhas)
    return layout("Pacotes para discussão com a gerência médica",content+administracao.navegacao("/gerencia",query,n,len(rows)>20),session)


def integrations_page(conn, session):
    tenant = session["tenant"]
    jobs = consultas.sincronizacoes(conn, tenant)
    html = '<p>Adaptadores de teste: importam uma guia e os metadados de um documento de um lote local fictício. Nenhum acesso aos produtos citados.</p>'
    for connector, mapping in EXAMPLES.items():
        fields = f'<input type="hidden" name="connector" value="{h(connector)}">'
        actions = form("/sincronizar", session["csrf"], fields, "Importar lote fictício", "inline")
        actions += form("/sincronizar", session["csrf"],
                        fields + '<input type="hidden" name="simulate_failure" value="1">',
                        "Simular falha", "inline")
        html += card(connector.upper(),
                     f'<p>Mapeamento para o formato interno: ID da guia ← {h(mapping["id"])}; '
                     f'procedimento ← {h(mapping["procedure"])}; pergunta clínica ← {h(mapping["question"])}; '
                     f'ID do documento ← {h(mapping["doc_id"])}; atualização ← {h(mapping["updated"])}.</p>'
                     f'<div class="actions">{actions}</div>', "CONECTOR DEMONSTRATIVO")
    rows = ""
    for job in jobs:
        retry = ""
        if job["status"] == "falha":
            fields = (f'<input type="hidden" name="connector" value="{h(job["connector"].lower())}">'
                      f'<input type="hidden" name="retry_job" value="{job["id"]}">')
            retry = form("/sincronizar", session["csrf"], fields, "Reprocessar", "inline")
        rows += (f'<tr><td>{job["id"]}</td><td>{h(job["connector"])}</td>'
                 f'<td>{h(job["status"])}</td><td>{h(job["error_code"] or "—")}</td>'
                 f'<td>{job["inserted"]} / {job["duplicates"]} / {job["documents_inserted"]}</td>'
                 f'<td>{data_br(job["finished_at"])}</td><td>{h(job["retry_of"] or "—")} {retry}</td></tr>')
    html += card("Tentativas de sincronização",
                 '<div class="tablewrap"><table><thead><tr><th>ID</th><th>Origem</th><th>Resultado</th>'
                 '<th>Erro</th><th>Guias novas / repetidas / documentos</th><th>Data (São Paulo)</th>'
                 '<th>Nova tentativa</th></tr></thead><tbody>'
                 + (rows or '<tr><td colspan="7">Nenhuma tentativa ainda.</td></tr>')
                 + '</tbody></table></div>')
    return layout("Integrações", html, session)


def versions_page(conn, session):
    tenant = session["tenant"]
    versions = consultas.versoes_da_operadora(conn, tenant)
    body = '<p>Uma versão aprovada é selecionada na execução. Rascunhos e versões desativadas permanecem no histórico; nenhuma muda uma análise já registrada.</p>'
    for row in versions:
        content = json.loads(row["content"])
        actions = ""
        if session["role"] == "admin":
            fields = f'<input type="hidden" name="version_id" value="{row["id"]}">'
            if row["status"] == "rascunho":
                actions = form("/referencias/aprovar",session["csrf"],fields,"Aprovar","inline")
            if row["status"] == "aprovado":
                actions = form("/referencias/desativar",session["csrf"],fields,"Desativar","inline")
        body += card(f'{row["kind"]} v{row["version"]} · {row["status"]}',
                     f'<p>{h(content["title"])}</p><small>ID {row["id"]} · criado {data_br(row["created_at"])}</small>'
                     f'<details><summary>Ver conteúdo versionado</summary><pre>{h(json.dumps(content, ensure_ascii=False, indent=2))}</pre></details>{actions}')
    if session["role"] == "admin":
        fields = ('<label>Tipo<select name="kind"><option value="checklist">Checklist</option>'
                  '<option value="reference">Referência</option></select></label>'
                  '<label>Título<input name="title" required maxlength="120" value="Conferência documental PET-CT"></label>'
                  '<label><input type="checkbox" name="require_report" value="1"> Exigir metadado de relatório no checklist</label>'
                  '<label>URL de consulta oficial (referência)<input name="source_url" type="url" '
                  'value="https://www.gov.br/ans/pt-br/acesso-a-informacao/participacao-da-sociedade/atualizacao-do-rol-de-procedimentos"></label>')
        body += card("Criar próxima versão em rascunho",
                     form("/referencias/rascunho", session["csrf"], fields, "Criar rascunho"))
    return layout("Checklists e referências", body, session)


def users_page(conn, session):
    tenant = session["tenant"]
    users = consultas.usuarios_da_operadora(conn, tenant)
    flash = session.pop("flash", None)
    body = (f'<p class="notice">Credencial criada para {h(flash[0])}: <code>{h(flash[1])}</code>. '
            'Copie agora; esta senha não será exibida novamente.</p>') if flash else ""
    for user in users:
        other = "admin" if user["role"] == "auditor" else "auditor"
        fields = (f'<input type="hidden" name="username" value="{h(user["username"])}">'
                  f'<input type="hidden" name="role" value="{other}">')
        body += card(user["username"], f'<p>Perfil: {h(user["role"])} · cadastrado {data_br(user["created_at"])}</p>'
                     + form("/usuarios/permissao",session["csrf"],fields,f"Alterar para {other}"))
    fields = ('<label>Nome de acesso<input name="username" required maxlength="40" pattern="[a-z0-9-]+" '
              'placeholder="novo-auditor"></label><label>Perfil<select name="role">'
              '<option value="auditor">Médico auditor</option>'
              '<option value="admin">Administrador da operadora</option></select></label>')
    body += card("Cadastrar usuário da operadora",
                 form("/usuarios/criar", session["csrf"], fields, "Criar usuário"))
    return layout("Usuários e permissões", body, session)


def audit_page(conn, session, query):
    tenant = session["tenant"]
    rows = consultas.eventos_auditoria(conn,session,query)
    if rows is None:
        return None
    controls = (f'<label>Operadora<input name="tenant" value="{h(tenant)}" readonly></label>'
                f'<label>Usuário<input name="user" value="{h(query.get("user",[""])[0])}"></label>'
                f'<label>Caso (ID)<input name="case" inputmode="numeric" value="{h(query.get("case",[""])[0])}"></label>'
                f'<label>Ação<input name="action" value="{h(query.get("action",[""])[0])}"></label>'
                f'<label>De<input type="date" name="from" value="{h(query.get("from",[""])[0])}"></label>'
                f'<label>Até<input type="date" name="to" value="{h(query.get("to",[""])[0])}"></label>'
                '<button>Filtrar</button>')
    body = '<p>Eventos somente de leitura na interface. Os filtros e o resultado ficam limitados à operadora da sessão.</p>'
    body += '<form method="get" action="/auditoria" class="filters">' + controls + '</form>'
    table = "".join(
        f'<tr><td>{r["id"]}</td><td>{data_br(r["created_at"])}</td><td>{h(r["tenant_id"])}</td>'
        f'<td>{h(r["actor"])}</td><td>{h(r["action"])}</td>'
        f'<td>{h(r["object_type"])} #{h(r["object_id"])}</td><td>{h(r["case_id"] or "—")}</td>'
        f'<td>{h(r["result"])}</td></tr>' for r in rows[:50])
    body += '<div class="tablewrap"><table><thead><tr><th>ID</th><th>Data (São Paulo)</th><th>Operadora</th>'
    body += '<th>Usuário</th><th>Ação</th><th>Objeto</th><th>Caso</th><th>Resultado</th></tr></thead><tbody>'
    body += table or '<tr><td colspan="8">Nenhum evento para estes filtros.</td></tr>'
    body += '</tbody></table></div><p class="muted">Banco SQLite local: o operador do computador pode alterar ou apagar os eventos; não é trilha imutável de produção. Um histórico guardado em localStorage também seria alterável; este protótipo não usa localStorage. Nenhum conteúdo clínico integral, senha ou token é registrado nos eventos.</p>'
    if len(rows) > 50:
        next_query = {k:query[k][0] for k in ("tenant","user","case","action","from","to") if k in query}
        next_query["antes"] = rows[49]["id"]
        body += f'<a id="proxima" href="/auditoria?{h(urlencode(next_query))}">Próxima página</a><p id="estado" role="status"></p><script defer src="/fluxos.js"></script>'
    return layout("Auditoria da plataforma", body, session)


def login_page(session):
    login_fields = (
        '<label class="login-field-label">Usuário'
        '<input name="username" required autocomplete="username" placeholder="Digite seu usuário" class="login-field-input"></label>'
        '<label class="login-field-label login-field-label-mt">Senha'
        '<input type="password" name="password" required autocomplete="current-password" placeholder="Digite sua senha" class="login-field-input"></label>'
    )
    login_form = form("/entrar", session["csrf"], login_fields, "Entrar na plataforma", "login-form-aether")

    body = f"""
    <div class="login-page-wrapper">
        <div class="login-page-container">
            <div class="login-logo-box">
                {logo_auditia(variant="vertical", size_class="logo-login", link=True, href="/")}
            </div>
            <div class="card login-card">
                <h1 class="header-3 login-card-title">Entrar no AuditIA</h1>
                <p class="paragraph-2 login-card-subtitle">
                    Acesso seguro à plataforma de apoio à decisão em auditoria médica.
                </p>
                {login_form}
                <div class="login-card-footer">
                    <a href="/" class="nav-link login-back-link">← Voltar à página inicial</a>
                </div>
            </div>
        </div>
    </div>
    """
    return layout("Acesso à Plataforma", body, session=session, is_landing=True, hide_h1=True)


def landing_page(session):
    logo_banner = logo_auditia(variant="horizontal", size_class="logo-roi-banner", link=False)
    body = f"""
    <!-- 2. Hero Principal -->
    <div class="hero-fullbleed">
        <h1 class="header-1 landing-hero-h1">Inteligência em saúde,</h1>
        <h2 class="header-2 landing-hero-h2">feita para auditoria</h2>
        <p class="paragraph-1 landing-hero-lead">
            Evidências, regulação e rastreabilidade para decisões médicas.
        </p>
        <div class="hero-buttons">
            <a href="/login" class="btn-aether"><span class="marker"></span>Acessar plataforma</a>
        </div>
    </div>

    <!-- 3. Seção de Eficiência Operacional -->
    <section id="solucao" class="landing-section">
        <div class="landing-section-header">
            <h2 class="header-3 landing-section-title">Menos tempo em processos. Mais valor em cada decisão.</h2>
            <p class="paragraph-2 landing-section-subtitle">
                Reduza o tempo de análise e aumente a consistência técnica conectando diretrizes clínicas, evidências probatórias e governança contínua.
            </p>
        </div>
        <div class="roi-section">
            <div class="roi-image-container">
                <img src="/img/imagem_mulher.png" alt="AuditIA — Inteligência aplicada à decisão médica" class="roi-image">
                <div class="roi-stat-glass roi-logo-banner-glass">
                    {logo_banner}
                </div>
            </div>
            <div class="roi-items-list">
                <div class="roi-item">
                    <div class="roi-text">
                        <h4>Centralize informações clínicas e regulatórias.</h4>
                    </div>
                    <span class="roi-num">001 — Organizar</span>
                </div>
                <div class="roi-item">
                    <div class="roi-text">
                        <h4>Apoie decisões com mais consistência.</h4>
                    </div>
                    <span class="roi-num">002 — Analisar</span>
                </div>
                <div class="roi-item">
                    <div class="roi-text">
                        <h4>Transforme evidências em decisões rastreáveis.</h4>
                    </div>
                    <span class="roi-num">003 — Fundamentar</span>
                </div>
                <div class="roi-item">
                    <div class="roi-text">
                        <h4>Reduza retrabalho e valorize o tempo médico.</h4>
                    </div>
                    <span class="roi-num">004 — Ganhar eficiência</span>
                </div>
                <div class="roi-cta-wrap">
                    <a href="#beneficios" class="btn-aether"><span class="marker"></span>Conheça a solução</a>
                </div>
            </div>
        </div>
    </section>

    <!-- 4. Quatro Cards de Benefícios -->
    <section id="beneficios" class="landing-section">
        <div class="landing-section-header">
            <h2 class="header-3 landing-section-title">Mais eficiência na auditoria. Mais segurança para sua operadora.</h2>
            <p class="paragraph-2 landing-section-subtitle">
                Arquitetura de apoio decisório concebida para a sustentabilidade assistencial e o rigor técnico.
            </p>
        </div>
        <div class="cards-benefits-grid">
            <div class="benefit-card">
                <span class="caption benefit-card-caption">SEGURANÇA REGULATÓRIA</span>
                <h3 class="header-4 benefit-card-title">Decisões mais consistentes</h3>
                <p class="paragraph-1 benefit-card-text">
                    Padronize análises de acordo com as diretrizes da ANS, apoiando decisões fundamentadas e reduzindo divergências.
                </p>
            </div>
            <div class="benefit-card">
                <span class="caption benefit-card-caption">EFICIÊNCIA OPERACIONAL</span>
                <h3 class="header-4 benefit-card-title">Controle de prazos e riscos</h3>
                <p class="paragraph-1 benefit-card-text">
                    Acompanhe prazos regulatórios e identifique pendências, contribuindo para prevenir atrasos.
                </p>
            </div>
            <div class="benefit-card">
                <span class="caption benefit-card-caption">GOVERNANÇA DA INFORMAÇÃO</span>
                <h3 class="header-4 benefit-card-title">Informações confiáveis e rastreáveis</h3>
                <p class="paragraph-1 benefit-card-text">
                    Organize documentos e evidências, com visibilidade sobre os fundamentos de cada análise.
                </p>
            </div>
            <div class="benefit-card">
                <span class="caption benefit-card-caption">PRODUTIVIDADE MÉDICA</span>
                <h3 class="header-4 benefit-card-title">Inteligência que otimiza processos</h3>
                <p class="paragraph-1 benefit-card-text">
                    Reduza tarefas repetitivas com pareceres assistidos, preservando a autonomia médica.
                </p>
            </div>
        </div>
    </section>

    <!-- 5. História e Propósito do AuditIA -->
    <section class="landing-purpose-section">
        <div class="landing-section-header">
            <h2 class="header-3 landing-section-title">Construído para decisões melhores</h2>
            <p class="paragraph-2 landing-section-subtitle">
                O AuditIA nasceu da prática da auditoria médica e da necessidade de transformar processos complexos em decisões mais claras, consistentes e fundamentadas.
            </p>
        </div>
        <div class="geometric-grid">
            <div class="geometric-card">
                <div class="geometric-symbol">
                    <svg width="44" height="44" viewBox="0 0 44 44" fill="none" stroke="#000000" stroke-width="1.75">
                        <circle cx="22" cy="22" r="18"/>
                        <line x1="22" y1="4" x2="22" y2="40"/>
                        <line x1="22" y1="22" x2="40" y2="22"/>
                    </svg>
                </div>
                <h3 class="header-4 geometric-card-title">Clareza para decidir</h3>
                <p class="paragraph-1 geometric-card-text">
                    Organizamos informações clínicas e regulatórias para apoiar decisões fundamentadas em evidências.
                </p>
            </div>
            <div class="geometric-card">
                <div class="geometric-symbol">
                    <svg width="44" height="44" viewBox="0 0 44 44" fill="none" stroke="#000000" stroke-width="1.75">
                        <circle cx="22" cy="22" r="18"/>
                        <ellipse cx="22" cy="22" rx="9" ry="18"/>
                        <line x1="4" y1="22" x2="40" y2="22"/>
                    </svg>
                </div>
                <h3 class="header-4 geometric-card-title">Regulação conectada à prática</h3>
                <p class="paragraph-1 geometric-card-text">
                    Conectamos normas, documentos e processos à realidade operacional da auditoria médica.
                </p>
            </div>
            <div class="geometric-card">
                <div class="geometric-symbol">
                    <svg width="44" height="44" viewBox="0 0 44 44" fill="none" stroke="#000000" stroke-width="1.75">
                        <circle cx="22" cy="22" r="18"/>
                        <line x1="14" y1="30" x2="30" y2="14"/>
                        <polyline points="20 14 30 14 30 24"/>
                    </svg>
                </div>
                <h3 class="header-4 geometric-card-title">Governança com propósito</h3>
                <p class="paragraph-1 geometric-card-text">
                    Desenvolvemos tecnologia para ampliar a eficiência, preservar a responsabilidade médica e fortalecer a segurança das decisões.
                </p>
            </div>
        </div>
    </section>

    <!-- 6 e 7. Governança, Segurança e Interoperabilidade -->
    <section class="landing-section">
        <div class="grid landing-pillars-grid">
            <div class="card landing-pillar-card">
                <span class="caption landing-pillar-caption">RESPONSABILIDADE CLÍNICA</span>
                <h3 class="header-3 landing-pillar-title">Inteligência artificial responsável. Decisões humanas.</h3>
                <p class="paragraph-1 landing-pillar-text">
                    O AuditIA apoia a decisão médica com transparência, rastreabilidade e fundamentação técnica. A tecnologia organiza informações e reduz tarefas operacionais, enquanto a responsabilidade pela decisão permanece com o médico.
                </p>
                <ul class="landing-pillar-list">
                    <li>Supervisão médica humana indelegável em todas as análises</li>
                    <li>Controle de acesso por perfil e isolamento entre operadoras</li>
                    <li>Trilha local de auditoria e registro das revisões médicas</li>
                    <li>Versionamento de critérios alinhado às diretrizes da ANS</li>
                </ul>
            </div>
            <div class="card landing-pillar-card">
                <span class="caption landing-pillar-caption">INTEGRAÇÃO E FLUXOS</span>
                <h3 class="header-3 landing-pillar-title">Inteligência que se conecta à sua operação.</h3>
                <p class="paragraph-1 landing-pillar-text">
                    Uma plataforma concebida para conectar informações, fluxos e rotinas de auditoria médica com fronteiras explícitas de dados.
                </p>
                <ul class="landing-pillar-list">
                    <li>Conectores simulados para SIGO, MV e TASY em ambiente demonstrativo</li>
                    <li>Importação e normalização de lotes sintéticos de guias e documentos</li>
                    <li>Mapeamento estruturado com correlação TUSS × Rol da ANS</li>
                    <li>Execução local isolada com dados exclusivamente sintéticos</li>
                </ul>
            </div>
        </div>
    </section>

    <!-- 8. Chamada Comercial Final -->
    <section id="contato" class="landing-cta-final">
        <h2 class="header-2 landing-cta-title">Transforme a auditoria médica da sua operadora.</h2>
        <p class="paragraph-1 landing-cta-lead">
            Conecte eficiência operacional, segurança regulatória e inteligência aplicada à decisão médica.
        </p>
        <div class="landing-cta-action-wrap">
            <button type="button" class="btn landing-cta-btn landing-cta-btn-disabled" disabled aria-disabled="true">
                <span class="landing-cta-marker"></span>
                Solicitar demonstração
                <span class="landing-cta-soon">Em breve</span>
            </button>
        </div>
    </section>
    """
    return layout("", body, session=session, is_landing=True)


def resumo_vigencia(path, session, nova, estado):
    body=(f'<p>Exercício fictício. As datas e a segunda redação são simuladas.</p>'
          f'<p>Versão inicial em {data_br(vigencia.BASE)}: {h(vigencia.ANTERIOR)}.</p>'
          f'<p>Alteração em {data_br(vigencia.NOVA)}: {h(vigencia.POSTERIOR)}. {estado}.</p>')
    if not nova or not nova[0]:
        acao = "aprovar" if nova else "propor"
        body += form(path,session["csrf"],f'<input type="hidden" name="acao" value="{acao}">',
                     "Aprovar versão simulada" if nova else "Propor versão simulada")
    return body


def filtros_fila(session, codigo, estado, guia="", status_guia=""):
    options = ''.join(f'<option {"selected" if item==estado else ""}>{h(item)}</option>' for item in homologacao.ESTADOS)
    guia_options = ''.join(f'<option value="{valor}" {"selected" if valor==status_guia else ""}>{rotulo}</option>'
                           for valor,rotulo in (("","Todos"),("Pendente","Pendente"),
                                                ("Autorizada","Autorizada"),("Negada","Negada")))
    fields = (f'<label>Número da guia<input name="guia" maxlength="64" value="{h(guia)}" placeholder="Ex.: B01"></label>'
              f'<label>Código do beneficiário<input name="codigo" maxlength="64" value="{h(codigo)}"></label>'
              f'<label>Status da guia<select name="status_guia">{guia_options}</select></label>'
              f'<label>Status da análise<select name="estado"><option value="">Todos</option>{options}</select></label>')
    pesquisar = form("/beta",session["csrf"],fields,"Pesquisar","case-filter-search")
    limpar = form("/beta",session["csrf"],'<input type="hidden" name="limpar" value="1">',"Limpar filtros","case-filter-clear")
    return f'<div class="filters case-filters">{pesquisar}{limpar}</div>'


def documento_page(doc, did, session):
    d_dict = dict(doc) if hasattr(doc, "keys") else (doc if isinstance(doc, dict) else {})
    sha = d_dict.get("source_sha256") or ""
    metodo = d_dict.get("extraction_method") or "Não registrado"
    status_conf = d_dict.get("verification_status") or "NAO_CONFERIDO"
    status_label = "Não conferido" if status_conf == "NAO_CONFERIDO" else status_conf
    texto = d_dict.get("content_text") or "Nenhuma transcrição disponível."

    body = card("Metadados importados",
                f'<dl><dt>Identificador na origem</dt><dd>{h(d_dict.get("external_id",""))}</dd>'
                f'<dt>Origem</dt><dd>{h(d_dict.get("source_system",""))}</dd>'
                f'<dt>Tipo</dt><dd>{h(d_dict.get("kind",""))}</dd><dt>Nome</dt><dd>{h(d_dict.get("name",""))}</dd>'
                f'<dt>Método de extração</dt><dd>{h(metodo)}</dd>'
                f'<dt>SHA-256</dt><dd><code>{h(sha or "Não calculado")}</code></dd>'
                f'<dt>Status de conferência</dt><dd>{h(status_label)}</dd>'
                f'<dt>Atualização na origem</dt><dd>{data_br(d_dict.get("source_updated_at",""))}</dd>'
                f'<dt>Última sincronização</dt><dd>{data_br(d_dict.get("last_imported_at",""))}</dd></dl>'
                f'<h4>Transcrição integral</h4>'
                f'<div class="doc-transcription-box">{h(texto)}</div>'
                f'<br><a href="/caso/{d_dict.get("case_id","")}">Voltar ao caso</a>')
    return layout(f'Documento {did}',body,session)


def pacote_page(case, run, rev, session):
    body=card(h(case["external_id"]),f'<p>{h(json.loads(run["original_output"])["parecer"]["sintese"])}</p><p>Revisão — {h(rev["position"])} · {h(rev["note"])}</p>'
        +form("/gerencia",session["csrf"],f'<input type="hidden" name="run_id" value="{run["id"]}">',"Gerar PDF"))
    return layout("Pacote gerencial",body,session)


def decisao_page(registro, run, session):
    return layout("Operadora fictícia · decisão registrada",card(h(registro["decisao"]),
        f'<p>{h(registro["motivo"])}</p><p>{h(registro["actor"])} · {h(registro["criado"])}</p>'
        f'<a href="/caso/{run["case_id"]}">Voltar ao caso</a>'),session)


def acesso_recusado():
    return layout("Acesso recusado",'<a href="/entrar">Tentar novamente</a>')


def pendencia_documental(faltantes, cid, session, missing_kinds):
    return layout("Pendência documental fundamental",
        card("🔴 Análise bloqueada",f'<p>Solicite: {h("; ".join(faltantes))}.</p>'
             + document_upload_form(cid,session["csrf"],missing_kinds)
             + f'<a href="/caso/{h(cid)}">Voltar ao caso</a>'),session)


def parecer_pendente(exc, cid, session):
    return layout("Parecer pendente",card("Verifique a entrada ou o modelo",
        f'<p>{h(exc)}</p><a href="/caso/{h(cid)}">Voltar ao caso</a>'),session)


def regra_nao_validada(session):
    return layout("Regra não validada",card("REGRA_NAO_VALIDADA","Em Auditoria Regulatória — DUT 60, o administrador deve marcar Revisado e clicar em Finalizar na versão aplicável à data da guia."),session)


def credencial_inicial(cred):
    return f'<p>Senha inicial de {h(cred[0])}: <code>{h(cred[1])}</code></p>'
