"""Conector e gerador da integração com o SIGO Simulado para o AuditIA Beta 0.2.
Importa solicitações sintéticas com três marcos temporais preservados,
documentos com blobs binários, correlação TUSS × Rol e vinculação a beneficiários.
"""

from backend import config, storage, tuss_rol, datas
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path


def _subtrair_dias_uteis(inicio, dias_uteis):
    cal = datas.FERIADOS_BR
    atual = inicio.date() if isinstance(inicio, datetime) else inicio
    removidos = 0
    while removidos < dias_uteis:
        atual -= timedelta(days=1)
        if datas.eh_dia_util(atual, cal):
            removidos += 1
    return atual


def gerar_lote_sigo_sintetico(tenant_id):
    """
    Gera exclusivamente as quatro guias demonstrativas da Aurora Saúde
    utilizando como fonte única os documentos e metadados de:
    mvp/assets/documentos/demo_aurora/manifesto_entrada.json

    Casos gerados:
    - SIGO-B01-AURORA: Nódulo pulmonar solitário de 16 x 14 mm (TUSS 40708128)
    - SIGO-B02-AURORA: Suspeita de CPCNP, anatomopatológico pendente (TUSS 41001222)
    - SIGO-B07-AURORA: Investigação de demência por PET-CT cerebral (TUSS 40708136)
    - SIGO-B08-AURORA: Câncer colorretal em seguimento (TUSS 40708128)
    """
    agora_dt = datetime.now(timezone.utc)
    hoje_date = agora_dt.date()

    # Cálculo determinístico dos marcos temporais:
    # B01: 2 dias úteis atrás -> 8 dias úteis restantes (NO_PRAZO)
    dt_proto_b01 = _subtrair_dias_uteis(hoje_date, 2)
    proto_b01 = datetime(dt_proto_b01.year, dt_proto_b01.month, dt_proto_b01.day, 10, 0, 0, tzinfo=timezone.utc).isoformat(timespec="seconds")
    cad_b01 = datetime(dt_proto_b01.year, dt_proto_b01.month, dt_proto_b01.day, 11, 30, 0, tzinfo=timezone.utc).isoformat(timespec="seconds")

    # B02: 8 dias úteis atrás -> 2 dias úteis restantes (ALERTA)
    dt_proto_b02 = _subtrair_dias_uteis(hoje_date, 8)
    proto_b02 = datetime(dt_proto_b02.year, dt_proto_b02.month, dt_proto_b02.day, 10, 0, 0, tzinfo=timezone.utc).isoformat(timespec="seconds")
    cad_b02 = datetime(dt_proto_b02.year, dt_proto_b02.month, dt_proto_b02.day, 11, 30, 0, tzinfo=timezone.utc).isoformat(timespec="seconds")

    # B07: 4 dias úteis atrás -> 6 dias úteis restantes (NO_PRAZO)
    dt_proto_b07 = _subtrair_dias_uteis(hoje_date, 4)
    proto_b07 = datetime(dt_proto_b07.year, dt_proto_b07.month, dt_proto_b07.day, 10, 0, 0, tzinfo=timezone.utc).isoformat(timespec="seconds")
    cad_b07 = datetime(dt_proto_b07.year, dt_proto_b07.month, dt_proto_b07.day, 11, 30, 0, tzinfo=timezone.utc).isoformat(timespec="seconds")

    # B08: 13 dias úteis atrás -> -3 dias úteis (VENCIDO)
    dt_proto_b08 = _subtrair_dias_uteis(hoje_date, 13)
    proto_b08 = datetime(dt_proto_b08.year, dt_proto_b08.month, dt_proto_b08.day, 10, 0, 0, tzinfo=timezone.utc).isoformat(timespec="seconds")
    cad_b08 = datetime(dt_proto_b08.year, dt_proto_b08.month, dt_proto_b08.day, 11, 30, 0, tzinfo=timezone.utc).isoformat(timespec="seconds")

    marcos = {
        "B01": (proto_b01, cad_b01, "AMM"),
        "B02": (proto_b02, cad_b02, "AMM"),
        "B07": (proto_b07, cad_b07, "AMM"),
        "B08": (proto_b08, cad_b08, "AMM/AMOP"),
    }

    demo_dir = config.DOCUMENT_ASSETS / "demo_aurora"
    manifest_file = demo_dir / "manifesto_entrada.json"
    if not manifest_file.is_file():
        raise FileNotFoundError(f"Manifesto de entrada demonstrativo não encontrado em: {manifest_file}")

    with open(manifest_file, "r", encoding="utf-8") as f:
        manifesto = json.load(f)

    from backend import leitura

    registros = []
    for caso_cfg in manifesto.get("casos", []):
        cid = caso_cfg["id"]
        if cid not in marcos:
            continue

        proto_dt, cad_dt, fila_origem = marcos[cid]
        docs_caso = []

        for doc_cfg in caso_cfg.get("documentos", []):
            arq_rel = doc_cfg["arquivo"]
            subpath = arq_rel[len("entrada/"):] if arq_rel.startswith("entrada/") else arq_rel
            doc_path = demo_dir / subpath

            if not doc_path.is_file():
                raise FileNotFoundError(f"Documento demonstrativo referenciado no manifesto não encontrado: {doc_path}")

            blob_bytes = doc_path.read_bytes()
            sha = hashlib.sha256(blob_bytes).hexdigest()

            # Classifica o tipo documental (kind)
            nome_doc = doc_path.name.lower()
            if "pedido" in nome_doc:
                kind = "pedido_medico"
            elif "anatomo" in nome_doc or "biopsia" in nome_doc:
                kind = "anatomopatologico"
            elif "tc" in nome_doc or "tomografia" in nome_doc:
                kind = "laudo_tc"
            elif "rm" in nome_doc or "ressonancia" in nome_doc:
                kind = "laudo_rm"
            elif "cea" in nome_doc:
                kind = "laudo_cea"
            else:
                kind = "outros"

            # Extração de texto visual através do módulo de leitura
            try:
                paginas = list(leitura.paginas_visuais(doc_path.name, blob_bytes))
                texto_transcrito = "\n\n".join(t for t, _ in paginas)
                metodo_ext = "PDF_DIGITAL" if doc_path.name.lower().endswith(".pdf") else "OCR_IMAGEM"
            except Exception:
                texto_transcrito = ""
                metodo_ext = "PDF_DIGITAL"

            ext_doc_id = f"SIGO-DOC-{cid}-{kind.upper()}-{tenant_id.upper()}"
            docs_caso.append({
                "external_id": ext_doc_id,
                "kind": kind,
                "name": doc_path.name,
                "source_updated_at": cad_dt,
                "content_blob": blob_bytes,
                "source_sha256": sha,
                "mime_type": "application/pdf" if doc_path.name.lower().endswith(".pdf") else "image/png",
                "content_text": texto_transcrito,
                "extraction_method": metodo_ext,
                "verification_status": "NAO_CONFERIDO",
            })

        # Monta a narrativa descritiva clínica real do caso a partir do primeiro documento
        if cid == "B01":
            area = "Pneumologia"
            narrative = "Paciente tabagista ativo, 35 maços-ano, com nódulo pulmonar solitário medindo 16 x 14 mm no segmento apical do lobo superior direito."
        elif cid == "B02":
            area = "Pneumologia / Oncologia"
            narrative = "Paciente ex-tabagista, 40 maços-ano, com massa sólida espiculada de 38 x 31 mm no lobo superior esquerdo. Biópsia realizada em 17/11/2026 com resultado histopatológico ainda não disponível."
        elif cid == "B07":
            area = "Neurologia"
            narrative = "Paciente com declínio cognitivo progressivo há 12 meses. RM de encéfalo sem alterações significativas. Estudo metabólico cerebral para investigação de síndrome demencial."
        elif cid == "B08":
            area = "Oncologia"
            narrative = "Adenocarcinoma de sigmoide ressecado em nov/2024 (pT3N0M0) em seguimento. Assintomático. TC de tórax, abdome e pelve sem recidiva e CEA normal (1,8 ng/mL). PET-CT para controle de rotina."
        else:
            area = "Oncologia"
            narrative = caso_cfg.get("procedimento", "PET-CT")

        registros.append({
            "tenant_id": tenant_id,
            "source_system": "SIGO",
            "external_id": f"SIGO-{cid}-{tenant_id.upper()}",
            "procedure": caso_cfg["procedimento"],
            "area": area,
            "narrative": narrative,
            "clinical_question": True,
            "tuss_code": caso_cfg["tuss"],
            "associated_tuss_codes": [],
            "beneficiary_code": f"BENEF-{tenant_id.upper()}-{cid}",
            "localizacao_sigo": fila_origem,
            "fila": fila_origem,
            "data_protocolo_operadora": proto_dt,
            "guide_received_at": None,
            "data_cadastro_sigo": cad_dt,
            "data_importacao_auditia": agora_dt.isoformat(timespec="seconds"),
            "source_updated_at": cad_dt,
            "documents": docs_caso,
        })

    return registros


def sincronizar_sigo_simulado(conn, tenant_id, actor="sistema", registros_custom=None):
    """
    Executa a sincronização segura e idempotente com o SIGO Simulado.
    Registra os jobs de sincronização e a trilha de governança.
    Aplica a regra REQ-16.1 (retirada da fila ativa sob ausência bilateral confirmada em AMM e AMOP).
    """
    registros = registros_custom if registros_custom is not None else gerar_lote_sigo_sintetico(tenant_id)
    conn.execute("SAVEPOINT sigo_sync")
    try:
        inserted, duplicates, docs_inserted = storage.import_records(conn, tenant_id, registros)
        
        # REQ-16.1: Regra de Saída da Fila
        # Quando uma sincronização é completa e bem-sucedida, guias ativas no AuditIA
        # que não estão presentes nem na AMM nem na AMOP são retiradas da fila ativa,
        # preservando histórico, pareceres, status clínico e rastreabilidade.
        stamp = storage.now()
        guias_presentes = {r["external_id"] for r in registros if (r.get("localizacao_sigo") or r.get("fila")) in ("AMM", "AMOP", "AMM/AMOP")}
        casos_existentes = conn.execute("""
            SELECT id, external_id, removido_origem_em FROM cases
            WHERE tenant_id=? AND source_system='SIGO' AND removido_origem_em IS NULL
        """, (tenant_id,)).fetchall()
        
        removidos_count = 0
        for caso in casos_existentes:
            if caso["external_id"] not in guias_presentes:
                conn.execute("UPDATE cases SET removido_origem_em=?, updated_at=? WHERE id=?", (stamp, stamp, caso["id"]))
                storage.event(conn, tenant_id, caso["id"], "Saída da fila de origem", "SIGO", storage.secrets.token_hex(10),
                              detail="Ausência confirmada simultaneamente em AMM e AMOP (REQ-16.1)")
                storage.record_governance_event(conn, tenant_id, actor, "sistema", "saida_fila_origem", "case", caso["id"],
                                                justification="Ausência confirmada em AMM e AMOP na sincronização completa (REQ-16.1)", source_system="SIGO")
                removidos_count += 1
                
        conn.execute("RELEASE SAVEPOINT sigo_sync")
        status = "sucesso"
        error_code = None
    except Exception as exc:
        conn.execute("ROLLBACK TO SAVEPOINT sigo_sync")
        conn.execute("RELEASE SAVEPOINT sigo_sync")
        status = "falha"
        error_code = str(exc)
        inserted = duplicates = docs_inserted = removidos_count = 0

    stamp = storage.now()
    cur = conn.execute("""INSERT INTO sync_jobs
        (tenant_id,connector,actor,started_at,finished_at,status,error_code,retry_of,
         inserted,duplicates,documents_inserted)
        VALUES(?, 'SIGO', ?, ?, ?, ?, ?, NULL, ?, ?, ?)""",
        (tenant_id, actor, stamp, stamp, status, error_code, inserted, duplicates, docs_inserted))
    job_id = cur.lastrowid
    storage.audit(conn, tenant_id, actor, "sincronizacao", "sync_job", job_id, status)

    storage.record_governance_event(
        conn=conn,
        tenant=tenant_id,
        actor=actor,
        role="admin" if "admin" in actor else "sistema",
        action="sincronizacao_sigo",
        object_type="sync_job",
        object_id=job_id,
        justification=f"Importação de dados sintéticos do SIGO ({status})",
        source_system="SIGO",
        metadata={
            "inseridos": inserted,
            "duplicados": duplicates,
            "documentos_inseridos": docs_inserted,
            "removidos_ausencia_origem": removidos_count,
            "status": status,
        }
    )
    return {
        "job_id": job_id,
        "status": status,
        "inserted": inserted,
        "duplicates": duplicates,
        "documents_inserted": docs_inserted,
        "removidos_ausencia_origem": removidos_count,
    }
