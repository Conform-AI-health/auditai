"""Caderno sintético de homologação. Os gabaritos são hipóteses para revisão médica."""
import csv
import hashlib
import io
from backend import config, storage

VERSAO = "0.1.0-beta.3"
SIM = "Critérios demonstrados"
NAO = "Critério não atendido"
PEND = "Dados insuficientes para concluir"
FORA = "Fora do escopo configurado"
# Nenhum texto do gabarito é enviado ao modelo.
CASOS = [
    ("B01","PET-CT para estadiamento primário. Relatório: linfoma confirmado por anatomopatológico.",SIM,"60.2.a"),
    ("B02","PET-CT para estadiamento primário. Guia sem diagnóstico e sem laudo anexo.",PEND,"Diagnóstico ausente"),
    ("B03","PET-CT para nódulo pulmonar solitário de exatamente 10 mm, não espiculado e sem calcificações. TC inconclusiva.",NAO,"60.4.b exige mais de 1 cm"),
    ("B04","PET-CT para nódulo pulmonar solitário de 12 mm, não espiculado e sem calcificações. TC inconclusiva.",SIM,"60.4.a–d"),
    ("B05","PET-CT para nódulo pulmonar solitário de 12 mm. TC inconclusiva. Não há descrição das margens ou das calcificações.",PEND,"60.4.c/d sem documentação"),
    ("B06","PET-CT para estadiamento de câncer pulmonar de células pequenas confirmado por biópsia.",SIM,"60.10"),
    ("B07","PET-CT cerebral com FDG para investigação de demência. Ausência de indicação oncológica.",FORA,"Investigação não oncológica"),
    ("B08","PET-CT com FDG para localizar tumor primário neuroendócrino potencialmente expressor de receptores de somatostatina. A guia confirma FDG.",NAO,"60.9 exige análogo de somatostatina"),
    ("B09","PET-CT com análogo de somatostatina para localizar o primário de tumor neuroendócrino potencialmente expressor de receptores de somatostatina.",SIM,"60.9.a"),
    ("B10","PET-CT para avaliação de resposta terapêutica. Relatório de oncologia confirma linfoma em tratamento.",SIM,"60.2.b"),
]
TUSS_CASOS = {codigo:("41001311" if codigo=="B07" else "40708128") for codigo, *_ in CASOS}

DOCUMENTOS = {
    "B01": ("pedido-medico.png", True), "B02": ("pedido-medico.jpg", False),
    "B03": ("pedido-medico.jpeg", True), "B04": ("pedido-medico.webp", True),
    "B05": ("pedido-medico.png", False), "B06": ("pedido-medico.jpg", True),
    "B07": ("pedido-medico.jpeg", True), "B08": ("pedido-medico.webp", True),
    "B09": ("pedido-medico.png", True), "B10": ("pedido-medico.jpg", True),
}

PEDIDO_TEXTO = ("Pedido médico fictício de PET-CT oncológico. Indicação clínica: estadiamento "
                "de neoplasia confirmada. Justificativa: definição de extensão da doença.")
ANATOMO_TEXTO = ("Laudo anatomopatológico fictício. Material: biópsia. Diagnóstico: neoplasia "
                 "maligna confirmada por exame histopatológico.")

def carregar(conn,tenant,agora):
    for codigo,texto,_,_ in CASOS:
        nova = conn.execute("""INSERT INTO cases(tenant_id,source_system,external_id,procedure,area,narrative,
          clinical_question,source_updated_at,last_imported_at,created_at,updated_at)
          VALUES(?,'BETA',?,'PET-CT solicitado','Homologação',?,1,?,?,?,?)
          ON CONFLICT(tenant_id,source_system,external_id) DO NOTHING""",
          (tenant,codigo,texto,agora,agora,agora,agora))
        case_id = conn.execute("SELECT id FROM cases WHERE tenant_id=? AND source_system='BETA' AND external_id=?",
                               (tenant,codigo)).fetchone()[0]
        if nova.rowcount:
            for etapa in ("Entrada da guia","Importação de dados sintéticos"):
                storage.event(conn,tenant,case_id,etapa,"bateria sintética",f"entrada-{case_id}")
        imagem, com_anatomo = DOCUMENTOS[codigo]
        numero = codigo[1:]
        conn.execute("""UPDATE cases SET guide_received_at=COALESCE(guide_received_at,?),
            beneficiary_code=COALESCE(beneficiary_code,?),tuss_code=?,associated_tuss_codes=COALESCE(associated_tuss_codes,'[]'),
            procedure=CASE WHEN ?='B07' THEN 'PET-CT neurológico' ELSE procedure END WHERE tenant_id=? AND id=?""",
            (f"2026-11-{numero}T12:00:00-03:00",f"0000{numero}",TUSS_CASOS[codigo],codigo,tenant,case_id))
        documentos = [("PEDIDO", "pedido_medico", "Pedido médico sintético", imagem,
                       "image/" + ("jpeg" if imagem.endswith((".jpg", ".jpeg")) else imagem.rsplit(".",1)[1]),
                       PEDIDO_TEXTO)]
        if com_anatomo:
            documentos.append(("ANATOMO", "anatomopatologico", "Laudo anatomopatológico sintético",
                               "laudo-anatomopatologico.pdf", "application/pdf", ANATOMO_TEXTO))
        for sufixo,kind,name,path,mime,text in documentos:
            blob = None
            sha = None
            ext_method = "PDF_DIGITAL" if mime == "application/pdf" else "OCR_IMAGEM"
            target = (config.DOCUMENT_ASSETS / path).resolve()
            if target.is_file():
                blob = target.read_bytes()
                sha = hashlib.sha256(blob).hexdigest()
            conn.execute("""INSERT INTO documents
                (tenant_id,case_id,source_system,external_id,kind,name,source_updated_at,last_imported_at,
                 mime_type,local_path,content_text,content_blob,source_sha256,extraction_method,verification_status)
                VALUES(?,?,'BETA',?,?,?,?,?,?,?,?,?,?,?,'NAO_CONFERIDO')
                ON CONFLICT(tenant_id,source_system,external_id) DO UPDATE SET
                  case_id=excluded.case_id,kind=excluded.kind,name=excluded.name,mime_type=excluded.mime_type,
                  local_path=excluded.local_path,content_text=excluded.content_text,
                  content_blob=COALESCE(excluded.content_blob, documents.content_blob),
                  source_sha256=COALESCE(excluded.source_sha256, documents.source_sha256),
                  extraction_method=COALESCE(excluded.extraction_method, documents.extraction_method),
                  verification_status=COALESCE(documents.verification_status, 'NAO_CONFERIDO'),
                  last_imported_at=excluded.last_imported_at""",
                (tenant,case_id,f"{codigo}-{sufixo}",kind,name,agora,agora,mime,path,text,blob,sha,ext_method))
        if nova.rowcount and documentos:
            storage.event(conn,tenant,case_id,"Recebimento documental","bateria sintética",f"entrada-{case_id}")
        from backend import tuss_rol
        tuss_rol.registrar_triagem(conn,tenant,storage.case_for(conn,tenant,case_id),"bateria sintética")

def resultados(conn,tenant):
    """Usa a primeira inferência desta bateria e mantém retestes no histórico."""
    rows=[]
    for codigo,_,esperado,base in CASOS:
        case=conn.execute("SELECT id FROM cases WHERE tenant_id=? AND source_system='BETA' AND external_id=?",(tenant,codigo)).fetchone()
        primeira = conn.execute("""SELECT id, json_extract(original_output,'$.suggestion'),
            json_extract(original_output,'$.modelo'), count(*) OVER ()
            FROM runs WHERE tenant_id=? AND case_id=? AND json_type(original_output,'$.parecer')='object'
            ORDER BY id LIMIT 1""",(tenant,case["id"])).fetchone()
        rid, sugestao, modelo, total = primeira or (None,"","",0)
        rev=conn.execute("SELECT stage,position FROM reviews WHERE tenant_id=? AND run_id=? ORDER BY id DESC LIMIT 1",
                         (tenant,rid)).fetchone()
        rows.append((codigo,case["id"],esperado,base,sugestao,modelo,total,
                     rev["position"] if rev and rev["stage"]=="conclusao" else "",rid or ""))
    return rows

def csv_resultados(rows):
    buf=io.StringIO()
    writer=csv.writer(buf,delimiter=";")
    writer.writerow(("Cenário","Caso","Gabarito proposto","Fundamento esperado","Primeira saída","Modelo","Execuções","Revisão da primeira saída","Execução inicial"))
    writer.writerows(rows)
    return "\ufeff"+buf.getvalue()

PAGE_SIZE = 5
ESTADOS = ("Pendente", "Falta de documentos", "Com parecer")
