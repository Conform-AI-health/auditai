"""Persistência local da demonstração. As consultas clínicas sempre incluem tenant_id."""

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from backend import config
ROOT = config.ROOT

from backend.adapters import read_demo, SyncFailure
from backend.engine import DEFAULT_CHECKLIST, DEFAULT_REFERENCE

DB = ROOT / "auditia-governanca-demo.sqlite3"
TENANTS = (("aurora", "Aurora Saúde (fictícia)"), ("horizonte", "Horizonte Assistência (fictícia)"))


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connection():
    with closing(sqlite3.connect(DB)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        with conn:
            yield conn


def digest(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600000)


def set_password(conn, username, password):
    if len(password) < 12:
        raise ValueError("Senha deve ter pelo menos 12 caracteres")
    salt = secrets.token_bytes(16)
    conn.execute("UPDATE users SET salt=?, password_hash=? WHERE username=?",
                 (salt, digest(password, salt), username))


def check_password(user, password):
    return hmac.compare_digest(user["password_hash"], digest(password, user["salt"]))


def initialize(seed_demo_cases=False):
    with connection() as conn:
        conn.executescript("""
          CREATE TABLE IF NOT EXISTS tenants(
            id TEXT PRIMARY KEY, name TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS users(
            username TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
            role TEXT NOT NULL CHECK(role IN ('auditor','admin')),
            salt BLOB NOT NULL, password_hash BLOB NOT NULL, created_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS cases(
            id INTEGER PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
            source_system TEXT NOT NULL, external_id TEXT NOT NULL,
            procedure TEXT NOT NULL, area TEXT NOT NULL, narrative TEXT NOT NULL,
            clinical_question INTEGER NOT NULL, source_updated_at TEXT NOT NULL,
            last_imported_at TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            guide_received_at TEXT, beneficiary_code TEXT, tuss_code TEXT, associated_tuss_codes TEXT,
            data_protocolo_operadora TEXT, data_cadastro_sigo TEXT, data_importacao_auditia TEXT,
            data_resposta_beneficiario TEXT,
            UNIQUE(tenant_id,source_system,external_id));
          CREATE TABLE IF NOT EXISTS documents(
            id INTEGER PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
            case_id INTEGER NOT NULL REFERENCES cases(id), source_system TEXT NOT NULL,
            external_id TEXT NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL,
            source_updated_at TEXT NOT NULL, last_imported_at TEXT NOT NULL,
            mime_type TEXT, local_path TEXT, content_text TEXT,
            source_sha256 TEXT, extraction_method TEXT, verification_status TEXT DEFAULT 'NAO_CONFERIDO',
            UNIQUE(tenant_id,source_system,external_id));
          CREATE TABLE IF NOT EXISTS sync_jobs(
            id INTEGER PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
            connector TEXT NOT NULL, actor TEXT NOT NULL, started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL, status TEXT NOT NULL, error_code TEXT,
            retry_of INTEGER REFERENCES sync_jobs(id), inserted INTEGER NOT NULL,
            duplicates INTEGER NOT NULL, documents_inserted INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS catalog_versions(
            id INTEGER PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
            kind TEXT NOT NULL CHECK(kind IN ('checklist','reference')),
            version INTEGER NOT NULL, status TEXT NOT NULL
            CHECK(status IN ('rascunho','aprovado','desativado')),
            content TEXT NOT NULL, created_at TEXT NOT NULL, approved_at TEXT,
            actor TEXT NOT NULL, UNIQUE(tenant_id,kind,version));
          CREATE TABLE IF NOT EXISTS runs(
            id INTEGER PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
            case_id INTEGER NOT NULL REFERENCES cases(id), actor TEXT NOT NULL,
            created_at TEXT NOT NULL, input_snapshot TEXT NOT NULL,
            checklist_version_id INTEGER NOT NULL REFERENCES catalog_versions(id),
            checklist_snapshot TEXT NOT NULL,
            reference_version_id INTEGER NOT NULL REFERENCES catalog_versions(id),
            reference_snapshot TEXT NOT NULL, original_output TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS reviews(
            id INTEGER PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
            run_id INTEGER NOT NULL REFERENCES runs(id), actor TEXT NOT NULL,
            created_at TEXT NOT NULL, stage TEXT NOT NULL CHECK(stage IN ('correcao','conclusao')),
            position TEXT NOT NULL, note TEXT NOT NULL, corrected_suggestion TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS audit_events(
            id INTEGER PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
            actor TEXT NOT NULL, created_at TEXT NOT NULL, action TEXT NOT NULL,
            object_type TEXT NOT NULL, object_id TEXT NOT NULL, case_id INTEGER,
            result TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS ai_terms_acceptances(
            tenant_id TEXT NOT NULL REFERENCES tenants(id),
            username TEXT NOT NULL REFERENCES users(username),
            term_version TEXT NOT NULL, accepted_at TEXT NOT NULL,
            PRIMARY KEY(tenant_id,username,term_version));
          CREATE INDEX IF NOT EXISTS idx_cases_tenant ON cases(tenant_id,id);
          CREATE INDEX IF NOT EXISTS idx_documents_tenant ON documents(tenant_id,case_id);
          CREATE INDEX IF NOT EXISTS idx_runs_tenant ON runs(tenant_id,case_id);
          CREATE INDEX IF NOT EXISTS idx_reviews_run ON reviews(tenant_id,run_id,id);
          CREATE INDEX IF NOT EXISTS idx_events_tenant ON audit_events(tenant_id,created_at);
          CREATE INDEX IF NOT EXISTS idx_events_page ON audit_events(tenant_id,id);
          CREATE TABLE IF NOT EXISTS auditor_profiles(
            username TEXT PRIMARY KEY REFERENCES users(username),tenant TEXT NOT NULL REFERENCES tenants(id),
            name TEXT NOT NULL,crm TEXT NOT NULL,uf TEXT NOT NULL,email TEXT NOT NULL COLLATE NOCASE,
            modified TEXT NOT NULL, UNIQUE(tenant,uf,crm),UNIQUE(tenant,email));
          CREATE TABLE IF NOT EXISTS auditor_disabled(username TEXT PRIMARY KEY REFERENCES users(username));
          CREATE TABLE IF NOT EXISTS telemetry(
            id INTEGER PRIMARY KEY,tenant TEXT NOT NULL,case_id INTEGER NOT NULL REFERENCES cases(id),
            correlation TEXT NOT NULL,stage TEXT NOT NULL,result TEXT NOT NULL,actor TEXT NOT NULL,
            created TEXT NOT NULL,duration_ms INTEGER,version TEXT,detail TEXT);
          CREATE INDEX IF NOT EXISTS telemetry_case ON telemetry(tenant,case_id,id);
          CREATE INDEX IF NOT EXISTS telemetry_created ON telemetry(created);
          CREATE TABLE IF NOT EXISTS dut_documents(
            id INTEGER PRIMARY KEY,tenant TEXT NOT NULL,consulted TEXT NOT NULL,url TEXT NOT NULL,
            actor TEXT NOT NULL,status TEXT NOT NULL,source_hash TEXT,content_hash TEXT,
            filename TEXT,body TEXT,validated_by TEXT,baseline_id INTEGER REFERENCES dut_documents(id));
          CREATE TABLE IF NOT EXISTS dut_sources(hash TEXT PRIMARY KEY, mime TEXT NOT NULL, original BLOB NOT NULL);
          CREATE TABLE IF NOT EXISTS regulatory_rules(
            id INTEGER PRIMARY KEY,tenant TEXT NOT NULL REFERENCES tenants(id), doc INTEGER UNIQUE NOT NULL REFERENCES dut_documents(id),
            state TEXT NOT NULL, spec TEXT NOT NULL, norm TEXT, effective TEXT, approved_by TEXT, clinical_record TEXT);
          CREATE UNIQUE INDEX IF NOT EXISTS idx_reg_active ON regulatory_rules(tenant) WHERE state='Ativa';
          CREATE TABLE IF NOT EXISTS regulatory_gold(id INTEGER PRIMARY KEY,tenant TEXT NOT NULL,doc INTEGER NOT NULL REFERENCES dut_documents(id),
            actor TEXT NOT NULL,created TEXT NOT NULL,reference TEXT NOT NULL,artifact TEXT NOT NULL,results TEXT NOT NULL,passed INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS regulatory_events(id INTEGER PRIMARY KEY,tenant TEXT NOT NULL,doc INTEGER,
            stage TEXT NOT NULL,actor TEXT NOT NULL,created TEXT NOT NULL,detail TEXT);
          CREATE INDEX IF NOT EXISTS idx_reg_events ON regulatory_events(tenant,id);
          CREATE TABLE IF NOT EXISTS regulatory_audits(id INTEGER PRIMARY KEY,tenant TEXT NOT NULL,
            run_id INTEGER NOT NULL REFERENCES runs(id),actor TEXT NOT NULL,created TEXT NOT NULL,status TEXT NOT NULL,report TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS idx_reg_audits ON regulatory_audits(tenant,run_id,id);
          CREATE TABLE IF NOT EXISTS session_acceptances(
            session_ref TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
            username TEXT NOT NULL REFERENCES users(username), term_version TEXT NOT NULL,
            accepted_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS tuss_rol_versions(id INTEGER PRIMARY KEY,tenant TEXT NOT NULL REFERENCES tenants(id),
            source_url TEXT NOT NULL,source_version TEXT NOT NULL,source_hash TEXT NOT NULL,published_at TEXT NOT NULL,
            valid_from TEXT NOT NULL,valid_until TEXT,validation_status TEXT NOT NULL,validated_by TEXT,validated_at TEXT,created_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS tuss_rol_mappings(id INTEGER PRIMARY KEY,version_id INTEGER NOT NULL REFERENCES tuss_rol_versions(id),
            tuss_code TEXT NOT NULL,tuss_description TEXT NOT NULL,rol_procedure TEXT NOT NULL,rol_correlation_status TEXT NOT NULL,
            dut_number TEXT,routing_category TEXT NOT NULL,relationship_type TEXT NOT NULL,source_url TEXT NOT NULL,
            source_version TEXT NOT NULL,valid_from TEXT NOT NULL,valid_until TEXT,validation_status TEXT NOT NULL,
            validated_by TEXT,validated_at TEXT,UNIQUE(version_id,tuss_code));
          CREATE TABLE IF NOT EXISTS tuss_rol_events(id INTEGER PRIMARY KEY,tenant TEXT NOT NULL,version_id INTEGER NOT NULL,
            actor TEXT NOT NULL,stage TEXT NOT NULL,created TEXT NOT NULL,detail TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS case_routes(id INTEGER PRIMARY KEY,tenant TEXT NOT NULL,case_id INTEGER NOT NULL REFERENCES cases(id),
            version_id INTEGER,tuss_code TEXT NOT NULL,category TEXT NOT NULL,status TEXT NOT NULL,reason TEXT NOT NULL,created TEXT NOT NULL,actor TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS out_of_rol_assessments(id INTEGER PRIMARY KEY,tenant TEXT NOT NULL,case_id INTEGER NOT NULL REFERENCES cases(id),
            actor TEXT NOT NULL,created TEXT NOT NULL,version_id INTEGER NOT NULL,statuses TEXT NOT NULL,justification TEXT NOT NULL,
            result TEXT NOT NULL,draft TEXT NOT NULL,medical_reviewed INTEGER NOT NULL DEFAULT 0);
          CREATE TABLE IF NOT EXISTS decisoes_demo(
            tenant TEXT NOT NULL,case_id INTEGER NOT NULL REFERENCES cases(id),run_id INTEGER NOT NULL REFERENCES runs(id),
            review_id INTEGER NOT NULL REFERENCES reviews(id),actor TEXT NOT NULL,decisao TEXT NOT NULL,motivo TEXT NOT NULL,
            criado TEXT NOT NULL,PRIMARY KEY(tenant,case_id));
          CREATE TABLE IF NOT EXISTS case_workflow(
            tenant TEXT NOT NULL REFERENCES tenants(id),case_id INTEGER NOT NULL REFERENCES cases(id),
            status TEXT NOT NULL CHECK(status IN ('ativo','gerencia','finalizado')),
            run_id INTEGER REFERENCES runs(id),actor TEXT NOT NULL,updated_at TEXT NOT NULL,
            PRIMARY KEY(tenant,case_id));
          CREATE TABLE IF NOT EXISTS document_transcriptions(
            id INTEGER PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
            document_id INTEGER NOT NULL REFERENCES documents(id), version INTEGER NOT NULL,
            content_text TEXT NOT NULL, actor TEXT NOT NULL, source_method TEXT NOT NULL,
            change_summary TEXT, created_at TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 1,
            UNIQUE(tenant_id, document_id, version));
          CREATE INDEX IF NOT EXISTS idx_doc_transcriptions ON document_transcriptions(tenant_id, document_id, version);
          CREATE TABLE IF NOT EXISTS clinical_evidences(
            id INTEGER PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
            case_id INTEGER NOT NULL REFERENCES cases(id), document_id INTEGER REFERENCES documents(id),
            fact_key TEXT NOT NULL, fact_value TEXT NOT NULL, page_number INTEGER,
            snippet TEXT, verification_status TEXT NOT NULL DEFAULT 'NAO_CONFERIDO',
            verified_by TEXT, verified_at TEXT, created_at TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS idx_clinical_evidences ON clinical_evidences(tenant_id, case_id);
          CREATE TABLE IF NOT EXISTS governance_audit_trail(
            id INTEGER PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
            actor TEXT NOT NULL, role TEXT NOT NULL, action TEXT NOT NULL,
            object_type TEXT NOT NULL, object_id TEXT NOT NULL, case_id INTEGER,
            old_value TEXT, new_value TEXT, justification TEXT, source_system TEXT,
            created_at TEXT NOT NULL, metadata TEXT);
          CREATE INDEX IF NOT EXISTS idx_gov_audit_tenant ON governance_audit_trail(tenant_id, created_at);
          CREATE INDEX IF NOT EXISTS idx_gov_audit_case ON governance_audit_trail(tenant_id, case_id);
          CREATE TABLE IF NOT EXISTS regulatory_drafts(
            id INTEGER PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
            case_id INTEGER NOT NULL REFERENCES cases(id), modality TEXT NOT NULL,
            title TEXT NOT NULL, normative_basis TEXT NOT NULL, clinical_summary TEXT NOT NULL,
            criteria_analysis TEXT NOT NULL, conclusion TEXT NOT NULL, reanalysis_conditions TEXT,
            draft_text TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'RASCUNHO_IA',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, actor_created TEXT NOT NULL,
            actor_updated TEXT, decision_justification TEXT, disclaimer TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS idx_reg_drafts ON regulatory_drafts(tenant_id, case_id, id);
          CREATE INDEX IF NOT EXISTS idx_tuss_version ON tuss_rol_versions(tenant,valid_from,id);
          CREATE INDEX IF NOT EXISTS idx_case_routes ON case_routes(tenant,case_id,id);
        """)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(documents)")}
        for name in ("mime_type", "local_path", "content_text"):
            if name not in columns:
                conn.execute(f"ALTER TABLE documents ADD COLUMN {name} TEXT")
        if "content_blob" not in columns:
            conn.execute("ALTER TABLE documents ADD COLUMN content_blob BLOB")
        for name, col_type in (
            ("source_sha256", "TEXT"),
            ("extraction_method", "TEXT"),
            ("verification_status", "TEXT DEFAULT 'NAO_CONFERIDO'"),
            ("verified_at", "TEXT"),
            ("verified_by", "TEXT"),
            ("divergences", "TEXT"),
            ("evidence_snippets", "TEXT"),
        ):
            if name not in columns:
                conn.execute(f"ALTER TABLE documents ADD COLUMN {name} {col_type}")
        if "detail" not in {r[1] for r in conn.execute("PRAGMA table_info(telemetry)")}:
            conn.execute("ALTER TABLE telemetry ADD COLUMN detail TEXT")
        prof_columns = {r[1] for r in conn.execute("PRAGMA table_info(auditor_profiles)")}
        if "tratamento" not in prof_columns:
            conn.execute("ALTER TABLE auditor_profiles ADD COLUMN tratamento TEXT")
        if "baseline_id" not in {r[1] for r in conn.execute("PRAGMA table_info(dut_documents)")}:
            conn.execute("ALTER TABLE dut_documents ADD COLUMN baseline_id INTEGER REFERENCES dut_documents(id)")
        if "correlation" not in {r[1] for r in conn.execute("PRAGMA table_info(runs)")}:
            conn.execute("ALTER TABLE runs ADD COLUMN correlation TEXT")
        expirar_telemetria(conn)
        case_columns = {row[1] for row in conn.execute("PRAGMA table_info(cases)")}
        if "conformity_status" not in {r[1] for r in conn.execute("PRAGMA table_info(reviews)")}:
            conn.execute("ALTER TABLE reviews ADD COLUMN conformity_status TEXT")
        for name in ("guide_received_at", "beneficiary_code", "tuss_code", "associated_tuss_codes",
                     "data_protocolo_operadora", "data_cadastro_sigo", "data_importacao_auditia",
                     "data_resposta_beneficiario", "localizacao_sigo", "fila_origem",
                     "removido_origem_em", "dados_pedido_hash", "divergence_detected", "divergence_detail",
                     "assumido_por", "assumido_em", "trava_expira_em", "responsavel_anterior",
                     "enc_complementacao_em", "enc_complementacao_por", "novos_docs_recebidos"):
            if name not in case_columns:
                conn.execute(f"ALTER TABLE cases ADD COLUMN {name} TEXT")
        if conn.execute("SELECT count(*) FROM tenants").fetchone()[0]:
            from backend import tuss_rol
            tuss_rol.preparar(conn)
            return []
        for tenant_id, name in TENANTS:
            conn.execute("INSERT INTO tenants VALUES(?,?)", (tenant_id, name))
        credentials = []
        for tenant_id in ("aurora", "horizonte"):
            for role in ("auditor", "admin"):
                username = f"{role}-{tenant_id}"
                password = secrets.token_urlsafe(15)
                salt = secrets.token_bytes(16)
                conn.execute("INSERT INTO users VALUES(?,?,?,?,?,?)",
                             (username, tenant_id, role, salt, digest(password, salt), now()))
                credentials.append((username, password))
            for kind, content in (("checklist", DEFAULT_CHECKLIST), ("reference", DEFAULT_REFERENCE)):
                conn.execute("""INSERT INTO catalog_versions
                    (tenant_id,kind,version,status,content,created_at,approved_at,actor)
                    VALUES(?,?,1,'aprovado',?,?,?,'sistema')""",
                    (tenant_id, kind, json.dumps(content, ensure_ascii=False), now(), now()))
            if seed_demo_cases:
                created = now()
                conn.execute("""INSERT INTO cases(tenant_id,source_system,external_id,procedure,area,
                    narrative,clinical_question,source_updated_at,last_imported_at,created_at,updated_at)
                    VALUES(?,'MANUAL',?,'PET-CT oncológico (fictício)','Oncologia',?,1,?,?,?,?)""",
                    (tenant_id, "DEMO-" + tenant_id.upper(),
                     f"Caso sintético inicial da operadora {tenant_id}. Sem dados de paciente.",
                     created, created, created, created))
        from backend import tuss_rol
        tuss_rol.preparar(conn)
        return credentials


def audit(conn, tenant, actor, action, object_type, object_id, result="sucesso", case_id=None):
    conn.execute("""INSERT INTO audit_events
        (tenant_id,actor,created_at,action,object_type,object_id,case_id,result)
        VALUES(?,?,?,?,?,?,?,?)""",
        (tenant, actor, now(), action, object_type, str(object_id), case_id, result))


def expirar_telemetria(conn):
    dias = int(os.environ.get("AUDITIA_TELEMETRIA_DIAS","180"))
    if dias < 1:
        raise ValueError("A retenção de telemetria deve ser positiva.")
    conn.execute("""DELETE FROM telemetry WHERE created < strftime('%Y-%m-%dT%H:%M:%S','now',?)""", (f"-{dias} days",))


def event(conn, tenant, case_id, stage, actor, correlation, result="concluído", duration=None, version=None, detail=None):
    expirar_telemetria(conn)
    conn.execute("""INSERT INTO telemetry(tenant,case_id,correlation,stage,result,actor,created,duration_ms,version,detail)
        VALUES(?,?,?,?,?,?,?,?,?,?)""",(tenant,case_id,correlation,stage,result,actor,now(),duration,version,detail))


def case_for(conn, tenant, case_id):
    return conn.execute("SELECT * FROM cases WHERE tenant_id=? AND id=?", (tenant, case_id)).fetchone()


def document_for(conn, tenant, document_id):
    return conn.execute("SELECT * FROM documents WHERE tenant_id=? AND id=?",
                        (tenant, document_id)).fetchone()


def run_for(conn, tenant, run_id):
    return conn.execute("SELECT * FROM runs WHERE tenant_id=? AND id=?", (tenant, run_id)).fetchone()


def latest_approved(conn, tenant, kind):
    return conn.execute("""SELECT * FROM catalog_versions WHERE tenant_id=? AND kind=?
        AND status='aprovado' ORDER BY version DESC LIMIT 1""", (tenant, kind)).fetchone()


def import_records(conn, tenant, records):
    inserted = duplicates = documents_inserted = 0
    for record in records:
        if record["tenant_id"] != tenant:
            raise ValueError("Operadora da importação divergente")
        source, external = record["source_system"], record["external_id"]
        current = conn.execute("""SELECT * FROM cases
            WHERE tenant_id=? AND source_system=? AND external_id=?""",
            (tenant, source, external)).fetchone()
        stamp = now()
        correlation = secrets.token_hex(10)
        # Validação de origem e filas (REQ-04)
        localizacao = record.get("localizacao_sigo") or record.get("fila") or "AMM"
        if localizacao == "AUD":
            # AUD totalmente fora do escopo; não consultar nem importar
            continue
        
        # Cálculo de hash de integridade dos dados mínimos do pedido médico (REQ-16.2)
        pedido_docs_texto = "".join(sorted([d.get("content_text", "") for d in record.get("documents", []) if d.get("kind") == "pedido_medico"]))
        dados_base = f"{tenant}|{record.get('procedure','')}|{record.get('narrative','')}|{record.get('beneficiary_code','')}|{pedido_docs_texto}"
        pedido_hash = hashlib.sha256(dados_base.encode("utf-8")).hexdigest()

        if current:
            duplicates += 1
            case_id = current["id"]
            
            # REQ-16.2: Reativação se a guia havia sido retirada da fila ativa
            removido_anterior = current["removido_origem_em"]
            reativado = False
            if removido_anterior:
                # Validação cumulativa dos 5 critérios (REQ-16.2):
                # 1. Mesma operadora (tenant_id verificado)
                # 2. Mesmo número da guia (external_id verificado)
                # 3. Mesmo código de beneficiário
                # 4. Pedido médico integralmente correspondente (dados_pedido_hash)
                # 5. Mesma data original de entrada na operadora
                mesmo_benef = (record.get("beneficiary_code") or "") == (current["beneficiary_code"] or "")
                mesma_data = (record.get("data_protocolo_operadora") or "") == (current["data_protocolo_operadora"] or "")
                mesmo_hash = not current["dados_pedido_hash"] or current["dados_pedido_hash"] == pedido_hash
                
                if mesmo_benef and mesma_data and mesmo_hash:
                    conn.execute("UPDATE cases SET removido_origem_em=NULL, localizacao_sigo=?, updated_at=? WHERE id=?",
                                 (localizacao, stamp, case_id))
                    event(conn, tenant, case_id, "Reativação de guia", source, correlation, detail="Reativação confirmada cumulativamente em AMM/AMOP")
                    record_governance_event(conn, tenant, "sistema", "sistema", "reativacao_guia", "case", case_id,
                                            justification="Reativação cumulativa aprovada (REQ-16.2)", source_system=source)
                    reativado = True
                else:
                    # Divergência cadastral na reativação: registrar auditoria sem duplicar
                    conn.execute("UPDATE cases SET divergence_detected=1, divergence_detail='Divergência detectada nos dados da solicitação durante reativação', updated_at=? WHERE id=?", (stamp, case_id))
                    record_governance_event(conn, tenant, "sistema", "sistema", "reativacao_divergente", "case", case_id,
                                            justification="Reativação bloqueada por divergência cadastral (REQ-16.2)", source_system=source)

            if not reativado:
                conn.execute("UPDATE cases SET localizacao_sigo=?, updated_at=? WHERE id=?",
                             (localizacao, stamp, case_id))

            if record["source_updated_at"] > current["source_updated_at"]:
                conn.execute("""UPDATE cases SET procedure=?,area=?,narrative=?,clinical_question=?,tuss_code=?,associated_tuss_codes=?,
                    source_updated_at=?,last_imported_at=?,updated_at=?
                    WHERE tenant_id=? AND id=?""",
                    (record["procedure"], record["area"], record["narrative"],
                     int(record["clinical_question"]),record.get("tuss_code"),json.dumps(record.get("associated_tuss_codes",[])), record["source_updated_at"],
                     stamp, stamp, tenant, case_id))
            else:
                conn.execute("UPDATE cases SET last_imported_at=? WHERE tenant_id=? AND id=?",
                             (stamp, tenant, case_id))
        else:
            # REQ-04: Nova guia só entra pela primeira presença na AMM. Não importar guia inédita exclusivamente na AMOP.
            if localizacao != "AMM" and "AMM" not in localizacao:
                continue

            cur = conn.execute("""INSERT INTO cases
                (tenant_id,source_system,external_id,procedure,area,narrative,clinical_question,tuss_code,associated_tuss_codes,
                 data_protocolo_operadora,data_cadastro_sigo,data_importacao_auditia,
                 localizacao_sigo,fila_origem,dados_pedido_hash,
                 source_updated_at,last_imported_at,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (tenant, source, external, record["procedure"], record["area"],
                 record["narrative"], int(record["clinical_question"]),
                 record.get("tuss_code"),json.dumps(record.get("associated_tuss_codes",[])),
                 record.get("data_protocolo_operadora"), record.get("data_cadastro_sigo"),
                 record.get("data_importacao_auditia") or stamp,
                 localizacao, localizacao, pedido_hash,
                 record["source_updated_at"], stamp, stamp, stamp))
            case_id = cur.lastrowid
            event(conn,tenant,case_id,"Entrada da guia",source,correlation)
            inserted += 1
        conn.execute("""UPDATE cases SET guide_received_at=COALESCE(guide_received_at,?),
            beneficiary_code=COALESCE(beneficiary_code,?),tuss_code=COALESCE(tuss_code,?),
            associated_tuss_codes=COALESCE(associated_tuss_codes,?),
            data_protocolo_operadora=COALESCE(data_protocolo_operadora,?),
            data_cadastro_sigo=COALESCE(data_cadastro_sigo,?),
            data_importacao_auditia=COALESCE(data_importacao_auditia,?)
            WHERE tenant_id=? AND id=?""",
            (record.get("guide_received_at"),record.get("beneficiary_code"),record.get("tuss_code"),
             json.dumps(record.get("associated_tuss_codes",[])),
             record.get("data_protocolo_operadora"), record.get("data_cadastro_sigo"),
             record.get("data_importacao_auditia") or stamp,
             tenant,case_id))
        event(conn,tenant,case_id,"Importação de dados sintéticos",source,correlation)
        for doc in record["documents"]:
            existing = conn.execute("""SELECT * FROM documents
                WHERE tenant_id=? AND source_system=? AND external_id=?""",
                (tenant, source, doc["external_id"])).fetchone()
            blob = doc.get("content_blob")
            sha = doc.get("source_sha256")
            if blob and not sha:
                sha = hashlib.sha256(blob).hexdigest()
            ext_method = doc.get("extraction_method")
            text = doc.get("content_text")
            mime = doc.get("mime_type")
            local = doc.get("local_path")
            if blob and not text:
                try:
                    from backend import leitura
                    paginas = list(leitura.paginas_visuais(doc.get("name", "documento.pdf"), blob))
                    text = "\n\n".join(t for t, _ in paginas)
                    if not ext_method:
                        is_pdf = doc.get("name", "").lower().endswith(".pdf") or (mime == "application/pdf")
                        metodos = [m for _, m in paginas]
                        if is_pdf:
                            ext_method = "PDF_DIGITAL" if metodos and metodos[0] == "texto" else "OCR_DIGITALIZADO"
                        else:
                            ext_method = "OCR_IMAGEM"
                except Exception:
                    pass
            if not ext_method:
                if text and not blob:
                    ext_method = "ORIGINAL_TEXTO"
                elif mime == "application/pdf":
                    ext_method = "PDF_DIGITAL"
                elif mime and mime.startswith("image/"):
                    ext_method = "OCR_IMAGEM"
            verif = doc.get("verification_status", "NAO_CONFERIDO")
            if existing:
                if existing["case_id"] != case_id:
                    raise ValueError("Identificador do documento vinculado a outra guia")
                if doc["source_updated_at"] > existing["source_updated_at"]:
                    conn.execute("""UPDATE documents SET kind=?,name=?,source_updated_at=?,
                        last_imported_at=?,mime_type=COALESCE(?,mime_type),local_path=COALESCE(?,local_path),
                        content_text=COALESCE(?,content_text),content_blob=COALESCE(?,content_blob),
                        source_sha256=COALESCE(?,source_sha256),extraction_method=COALESCE(?,extraction_method),
                        verification_status=COALESCE(?,verification_status)
                        WHERE tenant_id=? AND id=?""",
                        (doc["kind"], doc["name"], doc["source_updated_at"], stamp,
                         mime, local, text, blob, sha, ext_method, verif,
                         tenant, existing["id"]))
                else:
                    conn.execute("UPDATE documents SET last_imported_at=? WHERE tenant_id=? AND id=?",
                                 (stamp, tenant, existing["id"]))
            else:
                conn.execute("""INSERT INTO documents
                    (tenant_id,case_id,source_system,external_id,kind,name,source_updated_at,last_imported_at,
                     mime_type,local_path,content_text,content_blob,source_sha256,extraction_method,verification_status)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (tenant, case_id, source, doc["external_id"], doc["kind"], doc["name"],
                     doc["source_updated_at"], stamp, mime, local, text, blob, sha, ext_method, verif))
                event(conn,tenant,case_id,"Recebimento documental",source,correlation)
                documents_inserted += 1
        from backend import tuss_rol
        tuss_rol.registrar_triagem(conn,tenant,case_for(conn,tenant,case_id),source)
    return inserted, duplicates, documents_inserted


def sync_demo(conn, tenant, actor, connector, fail=False, retry_of=None):
    if connector not in ("sigo", "mv", "tasy"):
        raise ValueError("Conector desconhecido")
    if retry_of is not None:
        job = conn.execute("""SELECT * FROM sync_jobs WHERE tenant_id=? AND id=?
            AND connector=? AND status='falha'""", (tenant, retry_of, connector.upper())).fetchone()
        if not job:
            raise ValueError("Tentativa anterior não elegível")
    status, error, counters = "sucesso", None, (0, 0, 0)
    conn.execute("SAVEPOINT sync_import")
    try:
        records = read_demo(connector, tenant, fail=fail)
        counters = import_records(conn, tenant, records)
        conn.execute("RELEASE SAVEPOINT sync_import")
    except SyncFailure as exc:
        conn.execute("ROLLBACK TO SAVEPOINT sync_import")
        conn.execute("RELEASE SAVEPOINT sync_import")
        status, error = "falha", exc.code
    except (ValueError, KeyError, sqlite3.IntegrityError):
        conn.execute("ROLLBACK TO SAVEPOINT sync_import")
        conn.execute("RELEASE SAVEPOINT sync_import")
        status, error = "falha", "FALHA_MAPEAMENTO_ORIGEM"
    stamp = now()
    cur = conn.execute("""INSERT INTO sync_jobs
        (tenant_id,connector,actor,started_at,finished_at,status,error_code,retry_of,
         inserted,duplicates,documents_inserted)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (tenant, connector.upper(), actor, stamp, stamp, status, error, retry_of, *counters))
    audit(conn, tenant, actor, "sincronizacao", "sync_job", cur.lastrowid, status)
    return cur.lastrowid


def requisitos_documentais(docs, case=None):
    tipos = {doc["kind"] for doc in docs}
    faltantes = []
    if "pedido_medico" not in tipos:
        faltantes.append("pedido médico com indicação clínica e justificativa")

    # A exigência genérica de anatomopatológico foi eliminada da Beta 0.2.
    # No caso inicial de demonstração didática fora da Beta 0.2 (test_workflows):
    if case:
        c_dict = dict(case) if hasattr(case, "keys") else (case if isinstance(case, dict) else {})
        if str(c_dict.get("external_id", "")).startswith("DEMO-") and not getattr(config, "BETA", True):
            if "anatomopatologico" not in tipos:
                faltantes.append("laudo da biópsia com anatomopatológico da neoplasia")
    return faltantes


def record_governance_event(conn, tenant, actor, role, action, object_type, object_id,
                            case_id=None, old_value=None, new_value=None, justification=None,
                            source_system="AUDITIA", metadata=None):
    """Registra eventos imutáveis na Trilha de Auditoria e Governança."""
    stamp = now()
    meta_json = json.dumps(metadata or {}, ensure_ascii=False) if isinstance(metadata, dict) else (metadata or "")
    conn.execute("""INSERT INTO governance_audit_trail
        (tenant_id,actor,role,action,object_type,object_id,case_id,old_value,new_value,
         justification,source_system,created_at,metadata)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (tenant, actor, role, action, object_type, str(object_id), case_id,
         str(old_value) if old_value is not None else None,
         str(new_value) if new_value is not None else None,
         justification, source_system, stamp, meta_json))
    audit(conn, tenant, actor, action, object_type, object_id, "sucesso", case_id=case_id)


def get_governance_trail(conn, tenant, action=None, case_id=None, limit=100, offset=0):
    """Consulta paginada da Trilha de Auditoria para o perfil Administrador."""
    query = "SELECT * FROM governance_audit_trail WHERE tenant_id=?"
    params = [tenant]
    if action:
        query += " AND action=?"
        params.append(action)
    if case_id:
        query += " AND case_id=?"
        params.append(case_id)
    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return conn.execute(query, params).fetchall()


def save_document_transcription(conn, tenant, document_id, content_text, actor, source_method,
                                change_summary=None, role="auditor", case_id=None):
    """
    Versiona uma transcrição documental de forma controlada.
    Preserva as versões anteriores e atualiza a transcrição ativa no documento.
    O documento binário original (content_blob) nunca é sobrescrito.
    """
    doc = conn.execute("SELECT * FROM documents WHERE tenant_id=? AND id=?", (tenant, document_id)).fetchone()
    if not doc:
        raise ValueError("Documento não encontrado nesta operadora.")
    c_id = case_id or doc["case_id"]
    last_v = conn.execute("""SELECT MAX(version) FROM document_transcriptions
        WHERE tenant_id=? AND document_id=?""", (tenant, document_id)).fetchone()[0] or 0
    new_v = last_v + 1
    stamp = now()
    old_text = doc["content_text"] or ""
    conn.execute("""INSERT INTO document_transcriptions
        (tenant_id, document_id, version, content_text, actor, source_method,
         change_summary, created_at, is_active)
        VALUES(?,?,?,?,?,?,?,?,1)""",
        (tenant, document_id, new_v, content_text, actor, source_method, change_summary, stamp))
    conn.execute("UPDATE documents SET content_text=?, last_imported_at=? WHERE tenant_id=? AND id=?",
                 (content_text, stamp, tenant, document_id))
    record_governance_event(
        conn, tenant, actor, role, "correcao_ocr_transcricao", "document", document_id,
        case_id=c_id, old_value=f"v{last_v}: {old_text[:100]}...",
        new_value=f"v{new_v}: {content_text[:100]}...",
        justification=change_summary or f"Correção manual de transcrição versão {new_v}",
        metadata={"version": new_v, "source_method": source_method}
    )
    return new_v


def get_document_transcriptions(conn, tenant, document_id):
    """Recupera o histórico completo de versões da transcrição de um documento."""
    return conn.execute("""SELECT * FROM document_transcriptions
        WHERE tenant_id=? AND document_id=? ORDER BY version DESC""",
        (tenant, document_id)).fetchall()


def set_document_verification(conn, tenant, document_id, actor, status,
                              divergences=None, verified_by_info=None, role="auditor"):
    """
    Registra formalmente a conferência humana pelo médico auditor.
    Status permitidos: 'CONFERIDO', 'NAO_CONFERIDO', 'DIVERGENTE'.
    """
    if status not in ("CONFERIDO", "NAO_CONFERIDO", "DIVERGENTE"):
        raise ValueError("Status de conferência inválido.")
    doc = conn.execute("SELECT * FROM documents WHERE tenant_id=? AND id=?", (tenant, document_id)).fetchone()
    if not doc:
        raise ValueError("Documento não encontrado.")
    stamp = now()
    div_str = json.dumps(divergences, ensure_ascii=False) if isinstance(divergences, (list, dict)) else (divergences or "")
    conn.execute("""UPDATE documents SET
        verification_status=?, verified_at=?, verified_by=?, divergences=?
        WHERE tenant_id=? AND id=?""",
        (status, stamp, verified_by_info or actor, div_str, tenant, document_id))
    record_governance_event(
        conn, tenant, actor, role, "conferencia_documental", "document", document_id,
        case_id=doc["case_id"], old_value=doc["verification_status"], new_value=status,
        justification=f"Conferência humana realizada por {verified_by_info or actor}",
        metadata={"divergences": divergences}
    )


def save_clinical_evidence(conn, tenant, case_id, fact_key, fact_value,
                           document_id=None, page_number=None, snippet=None,
                           status="NAO_CONFERIDO", verified_by=None, actor="SISTEMA"):
    """Vincula dados clínicos estruturados a trechos literais dos documentos (evidências)."""
    stamp = now()
    cur = conn.execute("""INSERT INTO clinical_evidences
        (tenant_id, case_id, document_id, fact_key, fact_value, page_number,
         snippet, verification_status, verified_by, verified_at, created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (tenant, case_id, document_id, str(fact_key), str(fact_value),
         page_number, snippet, status, verified_by, stamp if verified_by else None, stamp))
    return cur.lastrowid


def get_clinical_evidences(conn, tenant, case_id):
    """Recupera os vínculos de evidências documentais de um caso."""
    return conn.execute("""SELECT e.*, d.name as document_name, d.kind as document_kind
        FROM clinical_evidences e
        LEFT JOIN documents d ON d.id = e.document_id AND d.tenant_id = e.tenant_id
        WHERE e.tenant_id=? AND e.case_id=? ORDER BY e.id""",
        (tenant, case_id)).fetchall()


def save_regulatory_draft(conn, tenant, case_id, modality, title, normative_basis,
                          clinical_summary, criteria_analysis, conclusion,
                          reanalysis_conditions, draft_text, actor,
                          status="RASCUNHO_IA", justification=None, role="auditor"):
    """
    Salva ou atualiza uma minuta regulatória.
    Status: 'RASCUNHO_IA', 'EM_EDICAO', 'APROVADO_MEDICO', 'DESCARTADO'.
    """
    stamp = now()
    disclaimer = "RASCUNHO_IA — PENDENTE DE REVISÃO MÉDICA. Não emitir comunicação automática ao beneficiário."
    existing = conn.execute("""SELECT * FROM regulatory_drafts
        WHERE tenant_id=? AND case_id=? AND modality=?""",
        (tenant, case_id, modality)).fetchone()
    if existing:
        draft_id = existing["id"]
        old_status = existing["status"]
        conn.execute("""UPDATE regulatory_drafts SET
            title=?, normative_basis=?, clinical_summary=?, criteria_analysis=?,
            conclusion=?, reanalysis_conditions=?, draft_text=?, status=?,
            updated_at=?, actor_updated=?, decision_justification=?, disclaimer=?
            WHERE tenant_id=? AND id=?""",
            (title, normative_basis, clinical_summary, criteria_analysis,
             conclusion, reanalysis_conditions, draft_text, status,
             stamp, actor, justification or existing["decision_justification"],
             disclaimer, tenant, draft_id))
        action_name = "minuta_aprovada" if status == "APROVADO_MEDICO" else ("minuta_descartada" if status == "DESCARTADO" else "minuta_editada")
        record_governance_event(
            conn, tenant, actor, role, action_name, "regulatory_draft", draft_id,
            case_id=case_id, old_value=old_status, new_value=status,
            justification=justification or f"Atualização de minuta ({modality})",
            metadata={"modality": modality, "title": title}
        )
    else:
        cur = conn.execute("""INSERT INTO regulatory_drafts
            (tenant_id, case_id, modality, title, normative_basis, clinical_summary,
             criteria_analysis, conclusion, reanalysis_conditions, draft_text,
             status, created_at, updated_at, actor_created, actor_updated,
             decision_justification, disclaimer)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (tenant, case_id, modality, title, normative_basis, clinical_summary,
             criteria_analysis, conclusion, reanalysis_conditions, draft_text,
             status, stamp, stamp, actor, actor, justification, disclaimer))
        draft_id = cur.lastrowid
        record_governance_event(
            conn, tenant, actor, role, "minuta_gerada", "regulatory_draft", draft_id,
            case_id=case_id, old_value=None, new_value=status,
            justification=justification or f"Geração de rascunho de minuta ({modality})",
            metadata={"modality": modality, "title": title}
        )
    return draft_id


def get_regulatory_drafts(conn, tenant, case_id):
    """Recupera todas as minutas regulatórias associadas a um caso."""
    return conn.execute("""SELECT * FROM regulatory_drafts
        WHERE tenant_id=? AND case_id=? ORDER BY id DESC""",
        (tenant, case_id)).fetchall()


def obter_saudacao_usuario(conn, tenant, username):
    """
    Retorna o texto de saudação personalizada conforme REQ-20:
    Usa o primeiro nome cadastrado em auditor_profiles e o tratamento (ex: 'Dra.', 'Dr.').
    Se ausente ou neutro, retorna fallback neutro com username/perfil.
    """
    if not username:
        return "Olá!", "Acompanhe as solicitações e os prazos regulatórios."
    prof = conn.execute("""
        SELECT name, tratamento FROM auditor_profiles
        WHERE tenant = ? AND username = ?
    """, (tenant, username)).fetchone()
    if prof and prof["name"]:
        primeiro_nome = prof["name"].strip().split()[0]
        tratamento = (prof["tratamento"] or "").strip()
        if tratamento:
            titulo = f"Olá, {tratamento} {primeiro_nome}!"
        else:
            titulo = f"Olá, {primeiro_nome}!"
        subtitulo = "Bem-vinda ao AuditIA. Acompanhe suas solicitações e os prazos regulatórios." if tratamento == "Dra." else ("Bem-vindo ao AuditIA. Acompanhe suas solicitações e os prazos regulatórios." if tratamento == "Dr." else "Acompanhe suas solicitações e os prazos regulatórios.")
        return titulo, subtitulo

    return f"Olá, {username}!", "Acompanhe as solicitações e os prazos regulatórios."



def _tempo_trava_minutos():
    try:
        return int(os.environ.get("AUDITIA_LOCK_TIMEOUT_MINUTES", "60"))
    except ValueError:
        return 60


def expirar_travas_inativas(conn, tenant=None):
    """
    Libera automaticamente travas cuja expiração (60 min) já tenha sido atingida.
    Preserva histórico e análises anteriores sem apagar rascunhos ou dados.
    """
    stamp = now()
    query = """
        UPDATE cases
        SET responsavel_anterior = COALESCE(assumido_por, responsavel_anterior),
            assumido_por = NULL,
            trava_expira_em = NULL,
            updated_at = ?
        WHERE trava_expira_em IS NOT NULL AND trava_expira_em <= ?
    """
    params = [stamp, stamp]
    if tenant:
        query += " AND tenant_id = ?"
        params.append(tenant)
    conn.execute(query, tuple(params))


def assumir_caso(conn, tenant, case_id, actor, role="auditor", minutos_trava=None):
    """
    Bloqueio atômico transacional no banco de dados (REQ-08).
    Garante que dois auditores tentando assumir simultaneamente a mesma guia não colidam.
    Retorna True se assumido com sucesso, False se bloqueado por outro auditor.
    """
    if role != "auditor":
        return False
    
    expirar_travas_inativas(conn, tenant)
    
    duracao = minutos_trava if minutos_trava is not None else _tempo_trava_minutos()
    stamp_agora = datetime.now(timezone.utc)
    stamp_str = stamp_agora.isoformat(timespec="seconds")
    from datetime import timedelta
    expira_str = (stamp_agora + timedelta(minutes=duracao)).isoformat(timespec="seconds")

    # Atualização atômica condicional: caso livre, ou já pertencente ao mesmo médico, ou com trava vencida
    cur = conn.execute("""
        UPDATE cases
        SET assumido_por = ?,
            assumido_em = ?,
            trava_expira_em = ?,
            updated_at = ?
        WHERE tenant_id = ? AND id = ?
          AND (
            assumido_por IS NULL
            OR assumido_por = ?
            OR trava_expira_em <= ?
          )
    """, (actor, stamp_str, expira_str, stamp_str, tenant, case_id, actor, stamp_str))

    if cur.rowcount == 0:
        return False

    record_governance_event(
        conn, tenant, actor, role, "assuncao_caso", "case", case_id,
        case_id=case_id, new_value=actor,
        justification=f"Assunção atômica do caso pelo auditor médico (trava válida por {duracao} min)",
        metadata={"trava_expira_em": expira_str}
    )
    return True


def renovar_trava_caso(conn, tenant, case_id, actor, minutos_trava=None):
    """
    Renovação automática da trava médica mediante atividade clínica válida (REQ-09.1).
    """
    duracao = minutos_trava if minutos_trava is not None else _tempo_trava_minutos()
    stamp_agora = datetime.now(timezone.utc)
    stamp_str = stamp_agora.isoformat(timespec="seconds")
    from datetime import timedelta
    expira_str = (stamp_agora + timedelta(minutes=duracao)).isoformat(timespec="seconds")

    cur = conn.execute("""
        UPDATE cases
        SET trava_expira_em = ?,
            updated_at = ?
        WHERE tenant_id = ? AND id = ? AND assumido_por = ?
          AND (trava_expira_em IS NULL OR trava_expira_em > ?)
    """, (expira_str, stamp_str, tenant, case_id, actor, stamp_str))

    return cur.rowcount > 0


def devolver_caso_fila(conn, tenant, case_id, actor, role="auditor", motivo=None):
    """
    Devolução voluntária da guia à fila pelo médico responsável (REQ-09).
    Preserva integralmente trabalho anterior, rascunhos, histórico e SLA.
    """
    case = case_for(conn, tenant, case_id)
    if not case:
        return False
    if case["assumido_por"] != actor:
        return False

    stamp = now()
    conn.execute("""
        UPDATE cases
        SET responsavel_anterior = assumido_por,
            assumido_por = NULL,
            trava_expira_em = NULL,
            updated_at = ?
        WHERE tenant_id = ? AND id = ? AND assumido_por = ?
    """, (stamp, tenant, case_id, actor))

    record_governance_event(
        conn, tenant, actor, role, "devolucao_caso", "case", case_id,
        case_id=case_id, old_value=actor, new_value=None,
        justification=motivo or "Devolução voluntária do caso à fila de trabalho",
        metadata={"motivo": motivo}
    )
    return True


def verificar_posse_trava(conn, tenant, case_id, actor):
    """
    Verifica se o auditor possui a trava válida e ativa do caso no momento da operação.
    Rejeita operações se a trava expirou ou se foi assumida por outro auditor.
    """
    expirar_travas_inativas(conn, tenant)
    stamp = now()
    case = conn.execute("""
        SELECT assumido_por, trava_expira_em FROM cases
        WHERE tenant_id = ? AND id = ?
    """, (tenant, case_id)).fetchone()
    if not case:
        return False
    if case["assumido_por"] != actor:
        return False
    if case["trava_expira_em"] and case["trava_expira_em"] <= stamp:
        return False
    return True


def registrar_encaminhamento_complementacao(conn, tenant, case_id, actor, role="auditor"):
    """
    Registra encaminhamento ao operacional para solicitação de complementação documental (REQ-11.1).
    Dispara o timer operacional estimativo de 48 horas.
    Não altera/suspende o SLA da ANS nem gera negativa automática.
    """
    stamp = now()
    conn.execute("""
        UPDATE cases
        SET enc_complementacao_em = ?,
            enc_complementacao_por = ?,
            updated_at = ?
        WHERE tenant_id = ? AND id = ?
    """, (stamp, actor, stamp, tenant, case_id))

    record_governance_event(
        conn, tenant, actor, role, "encaminhamento_complementacao_documental", "case", case_id,
        case_id=case_id, old_value=None, new_value=stamp,
        justification="Encaminhamento ao operacional para solicitação de complementação documental (prazo 48h)"
    )
    return True


def marcar_novos_documentos_recebidos(conn, tenant, case_id):
    """
    Sinaliza recebimento de novos documentos (REQ-11.2) para habilitar ação de Reanalisar.
    """
    stamp = now()
    conn.execute("""
        UPDATE cases
        SET novos_docs_recebidos = '1',
            updated_at = ?
        WHERE tenant_id = ? AND id = ?
    """, (stamp, tenant, case_id))


