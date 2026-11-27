"""Correlação oficial TUSS × Rol e triagem sem decisão automática de cobertura."""
import json
import re
import unicodedata
from backend import storage

SOURCE_URL=("https://www.gov.br/ans/pt-br/acesso-a-informacao/participacao-da-sociedade/"
"atualizacao-do-rol-de-procedimentos/correlacaotuss-202409-rol-2021_tuss202609_rn679-2026_rn680-2026-2.xlsx")
SOURCE_VERSION="Rol RN 465/2021 e alterações · TUSS 22.202609 · RN 679/2026 e RN 680/2026"
SOURCE_HASH="2eb6fedf919c4d5fa2bb4b13d8bd41a90c5c87a72fc3a1added155cc13c8acc1"
PUBLISHED_AT="2026-10-15"
LEGAL_SOURCE="STF ADI 7265, Plenário, 18/09/2025; Lei 9.656/1998, art. 10, §§ 12 e 13"
ROWS=(
("40708128","PET dedicado oncológico","PET-CT ONCOLÓGICO (COM DIRETRIZ DE UTILIZAÇÃO)","SIM","60","dut60_direta","procedimento_principal"),
("41001222","TC para PET dedicado oncológico","PET-CT ONCOLÓGICO (COM DIRETRIZ DE UTILIZAÇÃO)","SIM","60","dut60_correlacionada","componente_correlacionado"),
("40708144","Revisão de PET-CT por procedimento","PET-CT ONCOLÓGICO (COM DIRETRIZ DE UTILIZAÇÃO)","SIM","60","conferencia_petct","revisao_acessoria"),
("40708152","Laudo evolutivo de PET-CT por procedimento","PET-CT ONCOLÓGICO (COM DIRETRIZ DE UTILIZAÇÃO)","SIM","60","conferencia_petct","laudo_acessorio"),
("41001311","PET-CT neurológico","---","NÃO",None,"avaliacao_fora_rol","sem_correlacao_na_fonte"),
("41001303","PET-CT infecção","---","NÃO",None,"avaliacao_fora_rol","sem_correlacao_na_fonte"),
("41001290","PET-CT cardiológico","---","NÃO",None,"avaliacao_fora_rol","sem_correlacao_na_fonte"))
LEGAL_ITEMS=(("prescricao","Prescrição por profissional assistente habilitado"),("situacao_ans","Situação perante a ANS"),
             ("alternativa_rol","Alternativa terapêutica adequada prevista no Rol"),("evidencia","Evidências de eficácia e segurança"),
             ("anvisa","Registro sanitário na Anvisa, quando aplicável"))
LEGAL_STATES=("atendido","nao_atendido","nao_verificado","nao_aplicavel")

def preparar(conn):
    for tenant,_ in storage.TENANTS:
        if conn.execute("SELECT 1 FROM tuss_rol_versions WHERE tenant=?",(tenant,)).fetchone(): continue
        stamp=storage.now()
        cur=conn.execute("""INSERT INTO tuss_rol_versions(tenant,source_url,source_version,source_hash,published_at,
        valid_from,validation_status,validated_by,validated_at,created_at) VALUES(?,?,?,?,?,?,'Homologada',?,?,?)""",
        (tenant,SOURCE_URL,SOURCE_VERSION,SOURCE_HASH,PUBLISHED_AT,PUBLISHED_AT,"implantacao-fonte-oficial-ans",stamp,stamp))
        for row in ROWS:
            conn.execute("""INSERT INTO tuss_rol_mappings(version_id,tuss_code,tuss_description,rol_procedure,
            rol_correlation_status,dut_number,routing_category,relationship_type,source_url,source_version,valid_from,
            validation_status,validated_by,validated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,'Homologada',?,?)""",
            (cur.lastrowid,*row,SOURCE_URL,SOURCE_VERSION,PUBLISHED_AT,"implantacao-fonte-oficial-ans",stamp))
        conn.execute("INSERT INTO tuss_rol_events(tenant,version_id,actor,stage,created,detail) VALUES(?,?,?,?,?,?)",
        (tenant,cur.lastrowid,"implantacao-fonte-oficial-ans","Homologada",stamp,SOURCE_HASH))

def _normal(v): return "".join(c for c in unicodedata.normalize("NFKD",str(v or "").lower()) if not unicodedata.combining(c))

def versao_aplicavel(conn,tenant,dia):
    dia=(dia or "")[:10]
    return conn.execute("""SELECT * FROM tuss_rol_versions WHERE tenant=? AND validation_status='Homologada'
    AND valid_from<=? AND (valid_until IS NULL OR valid_until>=?) ORDER BY valid_from DESC,id DESC LIMIT 1""",(tenant,dia,dia)).fetchone()

def triagem(conn,tenant,case):
    c_dict = dict(case) if hasattr(case, "keys") else (case if isinstance(case, dict) else {})
    code=str(c_dict.get("tuss_code") or "").strip()
    data_guia = c_dict.get("guide_received_at") or c_dict.get("data_protocolo_operadora")
    version=versao_aplicavel(conn,tenant,data_guia)
    if not version: return {"category":"revisao_classificacao","status":"fonte_nao_homologada","code":code,"reason":"Sem versão homologada aplicável à data da guia."}
    
    # REQ-02: Variantes de grafia de PET-CT
    proc = case["procedure"] if "procedure" in case.keys() else ""
    narr = case["narrative"] if "narrative" in case.keys() else ""
    texto_bruto = f"{proc or ''} {narr or ''}"
    texto = _normal(texto_bruto)
    variantes_petct = ("pet-ct", "pet ct", "pet/ct", "pet-tc", "pet tc", "pet scan", "petscan", "tomografia por emissao de positrons")
    eh_variante_pet = any(v in texto for v in variantes_petct)
    
    # Pedido exclusivamente por texto sem código TUSS formal
    if not code and eh_variante_pet:
        # Se texto indica oncologia, sugere candidato 40708128 sem confirmar equivalência automática
        if any(t in texto for t in ("oncol", "neoplas", "cancer", "linfom", "tumor")):
            code = "40708128"
        elif any(t in texto for t in ("neurolog", "cerebral", "demenc")):
            code = "41001311"

    mapping=conn.execute("SELECT * FROM tuss_rol_mappings WHERE version_id=? AND tuss_code=?",(version["id"],code)).fetchone()
    if not mapping:
        # Se for variante textual não mapeada formalmente
        if eh_variante_pet:
            return {"category":"revisao_classificacao","status":"variante_textual_sem_codigo","code":code,"version_id":version["id"],
                    "reason":"Variante textual de PET-CT identificada sem código TUSS oficial correspondente; conferência médica necessária."}
        return {"category":"revisao_classificacao","status":"codigo_desconhecido","code":code,"version_id":version["id"],
                "reason":"Código ausente da correlação homologada; revisar sem excluir a guia."}
    categoria=mapping["routing_category"]
    classes={"oncologica":("oncol","neoplas","cancer","linfom","tumor"),"neurologica":("neurolog","cerebral","demenc"),
             "cardiologica":("cardiol","miocard"),"infeccao":("infecc","inflamac")}
    esperada="neurologica" if code=="41001311" else ("cardiologica" if code=="41001290" else ("infeccao" if code=="41001303" else "oncologica"))
    presentes={nome for nome,termos in classes.items() if any(t in texto for t in termos)}
    
    # REQ-02: Ausência de histórico oncológico isoladamente não comprova divergência cadastral
    divergente=bool(presentes and esperada not in presentes and len(presentes) > 0)
    motivo={"dut60_direta":"Correlação oficial SIM com PET-CT oncológico e DUT 60.",
    "dut60_correlacionada":"Código preservado; conferir procedimento principal e códigos associados.",
    "conferencia_petct":"Procedimento acessório; conferir exame originário, finalidade e códigos associados.",
    "avaliacao_fora_rol":"Correlação oficial NÃO; avaliar outros fundamentos de cobertura antes de qualquer negativa."}[categoria]
    if divergente: motivo+=" Divergência entre código, descrição ou indicação; revisão obrigatória."
    return {"category":categoria,"status":"divergente" if divergente else "triado","code":code,"version_id":version["id"],
            "mapping":dict(mapping),"reason":motivo,"associated_codes":json.loads(case["associated_tuss_codes"] or "[]")}

def registrar_triagem(conn,tenant,case,actor="sistema"):
    r=triagem(conn,tenant,case); atual=(r["category"],r["status"],r["reason"],r.get("version_id"),r["code"])
    ant=conn.execute("SELECT category,status,reason,version_id,tuss_code FROM case_routes WHERE tenant=? AND case_id=? ORDER BY id DESC LIMIT 1",(tenant,case["id"])).fetchone()
    if not ant or tuple(ant)!=atual:
        conn.execute("INSERT INTO case_routes(tenant,case_id,version_id,tuss_code,category,status,reason,created,actor) VALUES(?,?,?,?,?,?,?,?,?)",
        (tenant,case["id"],r.get("version_id"),r["code"],r["category"],r["status"],r["reason"],storage.now(),actor))
    return r

def criar_revisao(conn,tenant,actor):
    v=conn.execute("SELECT * FROM tuss_rol_versions WHERE tenant=? AND validation_status='Homologada' ORDER BY id DESC LIMIT 1",(tenant,)).fetchone()
    if not v: raise ValueError("Versão homologada inexistente.")
    cur=conn.execute("""INSERT INTO tuss_rol_versions(tenant,source_url,source_version,source_hash,published_at,valid_from,
    validation_status,created_at) VALUES(?,?,?,?,?,?,'Em revisão',?)""",(tenant,v["source_url"],v["source_version"],v["source_hash"],v["published_at"],v["valid_from"],storage.now()))
    conn.execute("""INSERT INTO tuss_rol_mappings(version_id,tuss_code,tuss_description,rol_procedure,rol_correlation_status,dut_number,
    routing_category,relationship_type,source_url,source_version,valid_from,valid_until,validation_status)
    SELECT ?,tuss_code,tuss_description,rol_procedure,rol_correlation_status,dut_number,routing_category,relationship_type,source_url,
    source_version,valid_from,valid_until,'Em revisão' FROM tuss_rol_mappings WHERE version_id=?""",(cur.lastrowid,v["id"]))
    conn.execute("INSERT INTO tuss_rol_events(tenant,version_id,actor,stage,created,detail) VALUES(?,?,?,?,?,?)",(tenant,cur.lastrowid,actor,"Em revisão",storage.now(),"Cópia sem ativação."))

def homologar(conn,tenant,version_id,actor,revisado):
    if not revisado: raise ValueError("Marque Revisado antes de homologar.")
    v=conn.execute("SELECT * FROM tuss_rol_versions WHERE tenant=? AND id=? AND validation_status='Em revisão'",(tenant,version_id)).fetchone()
    if not v: raise ValueError("Versão em revisão indisponível.")
    stamp=storage.now(); conn.execute("UPDATE tuss_rol_versions SET validation_status='Substituída',valid_until=date(?,'-1 day') WHERE tenant=? AND validation_status='Homologada'",(v["valid_from"],tenant))
    conn.execute("UPDATE tuss_rol_versions SET validation_status='Homologada',validated_by=?,validated_at=? WHERE tenant=? AND id=?",(actor,stamp,tenant,version_id))
    conn.execute("UPDATE tuss_rol_mappings SET validation_status='Homologada',validated_by=?,validated_at=? WHERE version_id=?",(actor,stamp,version_id))
    conn.execute("INSERT INTO tuss_rol_events(tenant,version_id,actor,stage,created,detail) VALUES(?,?,?,?,?,?)",(tenant,version_id,actor,"Homologada",stamp,v["source_hash"]))

def salvar_avaliacao(conn,session,case,data):
    tri=triagem(conn,session["tenant"],case)
    if tri["category"]!="avaliacao_fora_rol": raise ValueError("Caso não encaminhado à avaliação fora do Rol.")
    estados={k:data.get(k,"") for k,_ in LEGAL_ITEMS}
    if any(v not in LEGAL_STATES for v in estados.values()): raise ValueError("Avalie todos os requisitos jurídicos.")
    just=data.get("justificativa","").strip()
    if not 20<=len(just)<=4000: raise ValueError("Informe fundamentação entre 20 e 4000 caracteres.")
    suficientes=all(v!="nao_verificado" for v in estados.values()); impeditivo=any(estados[k]=="nao_atendido" for k in ("prescricao","evidencia")) or estados["anvisa"]=="nao_atendido"
    resultado="Revisão jurídica e documental necessária" if not suficientes else ("Sugestão de negativa — procedimento fora do Rol" if impeditivo else "Avaliar cobertura excepcional; negativa não recomendada automaticamente")
    minuta=data.get("minuta","").strip()
    if resultado.startswith("Sugestão") and not minuta: minuta=f"Minuta preliminar para revisão médica e jurídica. Procedimento: {case['procedure']}. Código TUSS: {case['tuss_code']}. Fonte: {SOURCE_VERSION}. Correlação oficial: NÃO. A ausência de correlação não basta para negar cobertura. Fundamentação: {just}. Possível reavaliação mediante novos documentos ou evidências."
    if len(minuta)>6000: raise ValueError("Minuta deve ter no máximo 6000 caracteres.")
    conn.execute("INSERT INTO out_of_rol_assessments(tenant,case_id,actor,created,version_id,statuses,justification,result,draft,medical_reviewed) VALUES(?,?,?,?,?,?,?,?,?,?)",
    (session["tenant"],case["id"],session["user"],storage.now(),tri["version_id"],json.dumps(estados,ensure_ascii=False),just,resultado,minuta,int(data.get("revisado")=="1")))
    storage.audit(conn,session["tenant"],session["user"],"avaliacao_fora_rol","case",case["id"],resultado,case["id"])
