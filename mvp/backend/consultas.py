"""Consultas de leitura das telas, restritas à operadora da sessão."""
import re
from datetime import date, datetime, timedelta, timezone
from backend import storage
from backend.datas import FUSO
from backend.homologacao import PAGE_SIZE


def eventos_auditoria(conn, session, query):
    tenant = session["tenant"]
    selected = query.get("tenant", [tenant])[0]
    if selected != tenant:
        storage.audit(conn, tenant, session["user"], "consulta_auditoria", "tenant", selected, "negado")
        return None
    sql = "SELECT * FROM audit_events WHERE tenant_id=?"
    params = [tenant]
    filters = [
        ("actor", "user", 80), ("case_id", "case", 12), ("action", "action", 80),
    ]
    for column, key, limit in filters:
        value = query.get(key, [""])[0].strip()[:limit]
        if value:
            if key == "case" and not value.isdigit():
                return None
            sql += f" AND {column}=?"
            params.append(value)
    for key, operator in (("from", ">="), ("to", "<")):
        value = query.get(key, [""])[0]
        if value:
            try:
                dia = date.fromisoformat(value)
                if key == "to":
                    dia += timedelta(days=1)
                normalized = datetime.combine(dia,datetime.min.time(),FUSO).astimezone(timezone.utc).isoformat()
            except (ValueError,OverflowError):
                return None
            sql += f" AND created_at {operator} ?"
            params.append(normalized)
    cursor = query.get("antes", [""])[0]
    if cursor:
        if not re.fullmatch(r"[1-9][0-9]{0,17}", cursor):
            return None
        sql += " AND id < ?"
        params.append(int(cursor))
    return conn.execute(sql + " ORDER BY id DESC LIMIT 51", params).fetchall()


def documentos_da_guia(conn, tenant, cid):
    return conn.execute("""SELECT * FROM documents WHERE tenant_id=? AND case_id=? ORDER BY id""",
                            (tenant, cid)).fetchall()


def execucoes_da_guia(conn, tenant, cid):
    return conn.execute("""SELECT * FROM runs WHERE tenant_id=? AND case_id=? ORDER BY id DESC""",
                            (tenant, cid)).fetchall()


def versao_catalogo(conn, tenant, versao_id):
    return conn.execute("SELECT version FROM catalog_versions WHERE tenant_id=? AND id=?",
                              (tenant, versao_id)).fetchone()


def revisoes_da_execucao(conn, tenant, run_id):
    return conn.execute("""SELECT * FROM reviews WHERE tenant_id=? AND run_id=?
                AND id IN (SELECT max(id) FROM reviews WHERE tenant_id=? AND run_id=? GROUP BY stage)
                ORDER BY id""", (tenant,run_id,tenant,run_id)).fetchall()


def status_regulatorio(conn, tenant, run_id):
    return conn.execute("SELECT status,report FROM regulatory_audits WHERE tenant=? AND run_id=? ORDER BY id DESC LIMIT 1",(tenant,run_id)).fetchone()


def casos_da_operadora(conn, tenant, pagina=1, busca_beneficiario="", card_filtro="", ordem_sla="padrao", current_user=""):
    from backend import storage
    storage.expirar_travas_inativas(conn, tenant)

    where_clauses = ["c.tenant_id = ?"]
    params = [tenant]

    if card_filtro == "concluidas":
        where_clauses.append("coalesce(w.status, '') = 'finalizado'")
    else:
        where_clauses.append("coalesce(w.status, 'ativo') <> 'finalizado'")
        where_clauses.append("c.removido_origem_em IS NULL")

    if busca_beneficiario:
        where_clauses.append("instr(lower(coalesce(c.beneficiary_code, '')), lower(?)) > 0")
        params.append(busca_beneficiario.strip())

    if card_filtro == "aguardando":
        where_clauses.append("c.assumido_por IS NULL AND coalesce(c.divergence_detected, '0') <> '1'")
    elif card_filtro == "em_analise":
        if current_user:
            where_clauses.append("c.assumido_por = ?")
            params.append(current_user)
        else:
            where_clauses.append("c.assumido_por IS NOT NULL")
    elif card_filtro == "pendencias_codificacao":
        where_clauses.append("c.divergence_detected = '1'")
    elif card_filtro == "pendencias_documentais":
        where_clauses.append("""(
            (SELECT count(DISTINCT d.kind) FROM documents d
             WHERE d.case_id=c.id AND d.tenant_id=c.tenant_id
             AND d.kind IN ('pedido_medico','anatomopatologico')) < 2
            OR c.enc_complementacao_em IS NOT NULL
        )""")
    elif card_filtro == "concluidas" and current_user:
        where_clauses.append("""(
            w.actor = ? OR (
                w.actor IS NULL AND ? = (
                    SELECT v.actor FROM reviews v JOIN runs r ON r.id = v.run_id
                    WHERE r.tenant_id = w.tenant AND r.case_id = w.case_id AND v.stage = 'conclusao'
                    ORDER BY v.id DESC LIMIT 1
                )
            )
        )""")
        params.extend([current_user, current_user])

    where_sql = " AND ".join(where_clauses)

    if ordem_sla == "sla_desc":
        order_sql = "ORDER BY (c.data_protocolo_operadora IS NULL) ASC, c.data_protocolo_operadora DESC, c.id DESC"
    elif ordem_sla == "sla_asc":
        order_sql = "ORDER BY (c.data_protocolo_operadora IS NULL) ASC, c.data_protocolo_operadora ASC, c.id ASC"
    else:
        order_sql = "ORDER BY (c.data_protocolo_operadora IS NULL) ASC, c.data_protocolo_operadora ASC, c.id ASC"

    sql = f"""SELECT c.*,
            CASE WHEN r.id IS NULL THEN 'Pendente'
                 WHEN (SELECT status FROM regulatory_audits a
                       WHERE a.tenant=r.tenant_id AND a.run_id=r.id
                       ORDER BY a.id DESC LIMIT 1)
                      IN ('DIVERGENCIA_IDENTIFICADA','REGRA_NAO_VALIDADA')
                    THEN 'Revisão técnica necessária'
                 WHEN json_type(r.original_output,'$.parecer')='object'
                    THEN json_extract(r.original_output,'$.suggestion')
                 ELSE 'Pendente' END AS sugestao,
            v.position,v.created_at AS encaminhado_em,v.actor AS medico_responsavel,
            (SELECT count(DISTINCT d.kind) FROM documents d
             WHERE d.case_id=c.id AND d.tenant_id=c.tenant_id
             AND d.kind IN ('pedido_medico','anatomopatologico')) AS total_docs_obrigatorios,
            (SELECT count(*) FROM documents d
             WHERE d.case_id=c.id AND d.tenant_id=c.tenant_id
             AND d.kind='pedido_medico') AS tem_pedido,
            (SELECT count(*) FROM documents d
             WHERE d.case_id=c.id AND d.tenant_id=c.tenant_id
             AND d.kind='anatomopatologico') AS tem_anatomo
            FROM cases c
            LEFT JOIN runs r ON r.id=(SELECT max(a.id) FROM runs a
                WHERE a.tenant_id=c.tenant_id AND a.case_id=c.id)
            LEFT JOIN reviews v ON v.id=(SELECT max(x.id) FROM reviews x
                WHERE x.tenant_id=c.tenant_id AND x.run_id=r.id AND x.stage='conclusao')
            LEFT JOIN case_workflow w ON w.tenant=c.tenant_id AND w.case_id=c.id
            WHERE {where_sql}
            {order_sql}
            LIMIT 21 OFFSET ?"""

    params.append((pagina - 1) * 20)
    return conn.execute(sql, params).fetchall()


def kpis_dashboard_medico(conn, tenant, actor, periodo="hoje"):
    from backend import storage
    storage.expirar_travas_inativas(conn, tenant)

    # 1. Solicitações (compartilhadas ativas)
    solic = conn.execute("""
        SELECT count(*) FROM cases c
        LEFT JOIN case_workflow w ON w.tenant=c.tenant_id AND w.case_id=c.id
        WHERE c.tenant_id=? AND coalesce(w.status, 'ativo') <> 'finalizado'
          AND c.removido_origem_em IS NULL
    """, (tenant,)).fetchone()[0]

    # 2. Aguardando análise (sem responsável e sem divergência)
    aguardando = conn.execute("""
        SELECT count(*) FROM cases c
        LEFT JOIN case_workflow w ON w.tenant=c.tenant_id AND w.case_id=c.id
        WHERE c.tenant_id=? AND coalesce(w.status, 'ativo') <> 'finalizado'
          AND c.removido_origem_em IS NULL
          AND c.assumido_por IS NULL
          AND coalesce(c.divergence_detected, '0') <> '1'
    """, (tenant,)).fetchone()[0]

    # 3. Em análise (assumido pelo médico autenticado)
    em_analise = conn.execute("""
        SELECT count(*) FROM cases c
        LEFT JOIN case_workflow w ON w.tenant=c.tenant_id AND w.case_id=c.id
        WHERE c.tenant_id=? AND coalesce(w.status, 'ativo') <> 'finalizado'
          AND c.removido_origem_em IS NULL
          AND c.assumido_por = ?
    """, (tenant, actor)).fetchone()[0]

    # 4. Pendências de codificação (divergência cadastral/terminológica sinalizada)
    codificacao = conn.execute("""
        SELECT count(*) FROM cases c
        LEFT JOIN case_workflow w ON w.tenant=c.tenant_id AND w.case_id=c.id
        WHERE c.tenant_id=? AND coalesce(w.status, 'ativo') <> 'finalizado'
          AND c.removido_origem_em IS NULL
          AND c.divergence_detected = '1'
    """, (tenant,)).fetchone()[0]

    # 5. Pendências documentais (documentos insuficientes ou encaminhado 48h)
    documentais = conn.execute("""
        SELECT count(*) FROM cases c
        LEFT JOIN case_workflow w ON w.tenant=c.tenant_id AND w.case_id=c.id
        WHERE c.tenant_id=? AND coalesce(w.status, 'ativo') <> 'finalizado'
          AND c.removido_origem_em IS NULL
          AND (
            (SELECT count(DISTINCT d.kind) FROM documents d
             WHERE d.case_id=c.id AND d.tenant_id=c.tenant_id
             AND d.kind IN ('pedido_medico','anatomopatologico')) < 2
            OR c.enc_complementacao_em IS NOT NULL
          )
    """, (tenant,)).fetchone()[0]

    # 6. Concluídas (produtividade individual no período)
    concluidas = produtividade_individual(conn, tenant, actor, periodo=periodo)

    return {
        "solicitacoes": solic,
        "aguardando": aguardando,
        "em_analise": em_analise,
        "pendencias_codificacao": codificacao,
        "pendencias_documentais": documentais,
        "concluidas": concluidas
    }


def pacotes_gerenciais(conn, tenant, busca, ordem, n):
    ordem_sql = "v.created_at ASC,r.id" if ordem=="antigo" else "v.created_at DESC,r.id DESC"
    return conn.execute("""SELECT r.id,r.case_id,c.external_id,c.beneficiary_code,c.procedure,c.guide_received_at,
            CASE WHEN (SELECT status FROM regulatory_audits a WHERE a.tenant=r.tenant_id AND a.run_id=r.id ORDER BY a.id DESC LIMIT 1)
                IN ('DIVERGENCIA_IDENTIFICADA','REGRA_NAO_VALIDADA') THEN 'Revisão técnica necessária'
                ELSE json_extract(r.original_output,'$.suggestion') END AS sugestao,v.position,v.created_at,v.actor
            FROM runs r JOIN cases c ON c.id=r.case_id AND c.tenant_id=r.tenant_id
            JOIN case_workflow w ON w.tenant=r.tenant_id AND w.case_id=r.case_id
                AND w.status='gerencia' AND w.run_id=r.id
            JOIN reviews v ON v.id=(SELECT max(id) FROM reviews WHERE tenant_id=r.tenant_id AND run_id=r.id)
            WHERE r.tenant_id=? AND v.stage='conclusao' AND json_type(r.original_output,'$.parecer')='object'
            AND instr(lower(c.external_id),lower(?))>0 ORDER BY """+ordem_sql+" LIMIT 21 OFFSET ?",
            (tenant,busca,(n-1)*20)).fetchall()


def sincronizacoes(conn, tenant):
    return conn.execute("""SELECT * FROM sync_jobs WHERE tenant_id=?
            ORDER BY id DESC LIMIT 30""", (tenant,)).fetchall()


def versoes_da_operadora(conn, tenant):
    return conn.execute("""SELECT * FROM catalog_versions WHERE tenant_id=?
            ORDER BY kind,version DESC""", (tenant,)).fetchall()


def usuarios_da_operadora(conn, tenant):
    return conn.execute("SELECT username,role,created_at FROM users WHERE tenant_id=? ORDER BY username",
                             (tenant,)).fetchall()


def listar_auditores(conn, tenant, busca, status, n):
    base = """ FROM users u LEFT JOIN auditor_profiles p ON p.username=u.username AND p.tenant=u.tenant_id
        LEFT JOIN auditor_disabled x ON x.username=u.username WHERE u.tenant_id=? AND u.role='auditor'"""
    return conn.execute("""SELECT u.username,u.created_at,p.name,p.crm,p.uf,p.email,p.modified,
            CASE WHEN x.username IS NULL THEN 'Ativo' ELSE 'Inativo' END AS estado"""+base+
            """ AND (instr(lower(coalesce(p.name,'')||' '||u.username||' '||coalesce(crm,'')),lower(?))>0)
            AND (?='' OR estado=?) ORDER BY u.username LIMIT 21 OFFSET ?""",
            (tenant,busca,status,status,(n-1)*20)).fetchall()


def resumo_processamento(conn, tenant):
    return conn.execute("""SELECT count(*),coalesce(sum(processada),0),coalesce(sum(aguarda),0)
            FROM (SELECT EXISTS(SELECT 1 FROM runs r WHERE r.case_id=c.id AND r.tenant_id=c.tenant_id) processada,
            EXISTS(SELECT 1 FROM runs r WHERE r.case_id=c.id AND r.tenant_id=c.tenant_id AND NOT EXISTS(
            SELECT 1 FROM reviews v WHERE v.run_id=r.id AND v.stage='conclusao')) aguarda
            FROM cases c WHERE c.tenant_id=?)""",(tenant,)).fetchone()


def falhas_telemetria(conn, tenant):
    return conn.execute("SELECT count(*),count(DISTINCT case_id) FROM telemetry WHERE tenant=? AND result='erro'",(tenant,)).fetchone()


def duracao_por_etapa(conn, tenant):
    return conn.execute("SELECT stage,round(avg(duration_ms)) FROM telemetry WHERE tenant=? AND duration_ms IS NOT NULL GROUP BY stage",(tenant,)).fetchall()


def eventos_normativos_recentes(conn, tenant):
    return conn.execute("SELECT doc,stage,created,actor,detail FROM regulatory_events WHERE tenant=? ORDER BY id DESC LIMIT 30",(tenant,)).fetchall()


def eventos_telemetria(conn, tenant, guia, n):
    return conn.execute("SELECT * FROM telemetry WHERE tenant=? AND (?='' OR case_id=?) ORDER BY id "+("ASC" if guia else "DESC")+" LIMIT 51 OFFSET ?",(tenant,guia,guia,(n-1)*50)).fetchall()


def total_execucoes_guia(conn, tenant, guia):
    return conn.execute("SELECT count(*) FROM runs WHERE tenant_id=? AND case_id=?", (tenant,guia)).fetchone()[0]


def total_revisoes_ultima_execucao(conn, tenant, guia):
    return conn.execute("""SELECT count(*) FROM reviews WHERE tenant_id=? AND stage='conclusao'
                AND run_id=(SELECT max(id) FROM runs WHERE tenant_id=? AND case_id=?)""", (tenant,tenant,guia)).fetchone()[0]


def fila_de_casos(conn, tenant, codigo, estado, guia, status_guia, pagina):
    return conn.execute("""WITH fila AS (
            SELECT c.id, c.external_id, c.procedure, c.guide_received_at, c.beneficiary_code,
            c.data_protocolo_operadora, c.data_cadastro_sigo, c.data_importacao_auditia,
            CASE d.decisao WHEN 'Autorizar' THEN 'Autorizada' WHEN 'Negar' THEN 'Negada'
                ELSE 'Pendente' END AS guide_status,
            d.criado AS closed_at,
            (SELECT v.position FROM reviews v JOIN runs a ON a.id=v.run_id WHERE a.case_id=c.id
             AND v.tenant_id=c.tenant_id AND v.stage='conclusao' ORDER BY v.id DESC LIMIT 1) AS revisao,
            CASE WHEN (SELECT count(DISTINCT d.kind) FROM documents d
                WHERE d.case_id=c.id AND d.tenant_id=c.tenant_id
                AND d.kind IN ('pedido_medico','anatomopatologico')) < 2 THEN 'Falta de documentos'
            WHEN EXISTS (SELECT 1 FROM runs r WHERE r.tenant_id=c.tenant_id AND r.case_id=c.id
                AND json_type(r.original_output,'$.parecer')='object') THEN 'Com parecer'
            ELSE 'Pendente' END AS estado,
            (SELECT count(DISTINCT d.kind) FROM documents d
             WHERE d.case_id=c.id AND d.tenant_id=c.tenant_id
             AND d.kind IN ('pedido_medico','anatomopatologico')) AS total_docs_obrigatorios,
            (SELECT count(*) FROM documents d
             WHERE d.case_id=c.id AND d.tenant_id=c.tenant_id
             AND d.kind='pedido_medico') AS tem_pedido,
            (SELECT count(*) FROM documents d
             WHERE d.case_id=c.id AND d.tenant_id=c.tenant_id
             AND d.kind='anatomopatologico') AS tem_anatomo
            FROM cases c LEFT JOIN decisoes_demo d ON d.tenant=c.tenant_id AND d.case_id=c.id
            WHERE c.source_system='BETA' AND c.tenant_id=?
            AND (?='' OR instr(c.beneficiary_code,?)>0)
            AND (?='' OR instr(c.external_id,?)>0))
            SELECT * FROM fila WHERE (?='' OR estado=?) AND (?='' OR guide_status=?)
            ORDER BY (guide_status='Pendente') DESC,
                (data_protocolo_operadora IS NULL) ASC,
                julianday(data_protocolo_operadora) ASC,
                id ASC
            LIMIT ? OFFSET ?""",(tenant,codigo,codigo,guia,guia,estado,estado,status_guia,status_guia,
                                  PAGE_SIZE+1,(pagina-1)*PAGE_SIZE)).fetchall()


def documento_validado(conn, tenant):
    return conn.execute("SELECT * FROM dut_documents WHERE tenant=? AND validated_by IS NOT NULL ORDER BY id DESC LIMIT 1",(tenant,)).fetchone()


def historico_documental(conn, tenant, numero):
    return conn.execute("""SELECT d.*,b.body AS baseline FROM dut_documents d LEFT JOIN dut_documents b
            ON b.id=d.baseline_id AND b.tenant=d.tenant WHERE d.tenant=? ORDER BY d.id DESC LIMIT 11 OFFSET ?""",
            (tenant,(numero-1)*10)).fetchall()


def documentos_com_regra(conn, tenant, n):
    return conn.execute("""SELECT d.*,r.state,r.approved_by,r.norm,r.effective,r.spec FROM dut_documents d
            LEFT JOIN regulatory_rules r ON d.id=r.doc WHERE d.tenant=? ORDER BY d.id DESC LIMIT 11 OFFSET ?""",
            (tenant,(n-1)*10)).fetchall()


def regra_ativa(conn, tenant):
    return conn.execute("SELECT norm,effective,doc FROM regulatory_rules WHERE tenant=? AND state='Ativa'",(tenant,)).fetchone()


def documento_anterior(conn, tenant, doc):
    return conn.execute("SELECT body FROM dut_documents WHERE tenant=? AND id<? AND body IS NOT NULL ORDER BY id DESC LIMIT 1",(tenant,doc)).fetchone()


def ultimo_gabarito(conn, tenant, doc):
    return conn.execute("SELECT reference,results FROM regulatory_gold WHERE tenant=? AND doc=? ORDER BY id DESC LIMIT 1",(tenant,doc)).fetchone()


def historico_regulatorio(conn, tenant):
    return conn.execute("SELECT doc,stage,created,actor,detail FROM regulatory_events WHERE tenant=? ORDER BY id DESC LIMIT 50",(tenant,)).fetchall()


def auditorias_de_guias(conn, tenant):
    return conn.execute("SELECT run_id,status,created,actor,report FROM regulatory_audits WHERE tenant=? ORDER BY id DESC LIMIT 50",(tenant,)).fetchall()


def conferencias_da_execucao(conn, tenant, run_id):
    return conn.execute("SELECT report,created,actor FROM regulatory_audits WHERE tenant=? AND run_id=? ORDER BY id DESC LIMIT 30",(tenant,run_id)).fetchall()


def produtividade_individual(conn, tenant, actor, periodo="hoje"):
    """
    Apura a produtividade individual de casos concluídos pelo auditor autenticado.
    Fonte canônica de finalização: case_workflow com status='finalizado'.
    Atribui a conclusão estritamente ao autor da finalização (w.actor), ou, caso ausente/nulo,
    ao autor da revisão conclusiva mais recente daquele caso, evitando qualquer dupla atribuição entre auditores.
    Suporta filtros de período discreto (REQ-19): 'hoje', '7dias', 'mes', 'todos'.
    """
    if not tenant or not actor:
        return 0

    where_extra = ""
    params = [tenant, actor, actor]

    hoje = datetime.now(FUSO).date()
    if periodo == "hoje":
        where_extra = " AND date(w.updated_at) = ?"
        params.append(hoje.isoformat())
    elif periodo == "7dias":
        inicio_7d = hoje - timedelta(days=7)
        where_extra = " AND date(w.updated_at) >= ?"
        params.append(inicio_7d.isoformat())
    elif periodo == "mes":
        inicio_mes = hoje.replace(day=1)
        where_extra = " AND date(w.updated_at) >= ?"
        params.append(inicio_mes.isoformat())

    sql = f"""
        SELECT count(DISTINCT w.case_id)
        FROM case_workflow w
        WHERE w.tenant = ?
          AND w.status = 'finalizado'
          AND (
            w.actor = ?
            OR (
                w.actor IS NULL
                AND ? = (
                    SELECT v.actor FROM reviews v
                    JOIN runs r ON r.id = v.run_id
                    WHERE r.tenant_id = w.tenant AND r.case_id = w.case_id AND v.stage = 'conclusao'
                    ORDER BY v.id DESC LIMIT 1
                )
            )
          )
          {where_extra}
    """
    row = conn.execute(sql, params).fetchone()
    return int(row[0]) if row else 0


