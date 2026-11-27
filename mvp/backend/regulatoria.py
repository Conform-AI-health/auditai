"""Governança documental e auditoria independente, exclusivamente sobre o caso selecionado."""
from datetime import date
import hashlib
import json
import re

from backend import criterios_dut as dut
from backend import storage

FONTE = ("https://www.gov.br/ans/pt-br/acesso-a-informacao/participacao-da-sociedade/"
         "atualizacao-do-rol-de-procedimentos/anexo_ii_dut_2021_rn_465-2021_rn683-2026.pdf")
ESTADO = {True:"comprovado",False:"contradito",None:"não documentado"}
RESULTADO = {True:"Critérios demonstrados",False:"Critério não atendido",None:"Dados insuficientes para concluir"}


def evento(conn,tenant,doc,actor,stage,detail=""):
    conn.execute("INSERT INTO regulatory_events(tenant,doc,actor,stage,created,detail) VALUES(?,?,?,?,?,?)",
                 (tenant,doc,actor,stage,storage.now(),detail))
    storage.audit(conn,tenant,actor,"dut60_"+stage,"dut",doc)


def capturar(conn,tenant,doc,actor,spec):
    conn.execute("INSERT INTO regulatory_rules(tenant,doc,state,spec) VALUES(?,?,?,?)",
                 (tenant,doc,"Extraída",json.dumps(spec,ensure_ascii=False)))
    for etapa in ("Consulta à fonte oficial","Capturada","Extraída","Comparação de versões"):
        evento(conn,tenant,doc,actor,etapa)
    evento(conn,tenant,doc,actor,"Verificação dos critérios",", ".join(spec["diferencas"]) or "Estrutura compatível")


def verificar(conn,tenant,doc):
    from backend import fonte_ans
    r=conn.execute("""SELECT d.*,s.original,s.mime,r.spec FROM dut_documents d
        JOIN regulatory_rules r ON r.doc=d.id AND r.tenant=d.tenant
        JOIN dut_sources s ON s.hash=d.source_hash WHERE d.tenant=? AND d.id=?""",(tenant,doc)).fetchone()
    if not r:
        raise ValueError("Original verificável indisponível. Consulte a fonte novamente.")
    trecho,_=fonte_ans.extrair(r["mime"],r["original"])
    if (hashlib.sha256(r["original"]).hexdigest()!=r["source_hash"] or trecho!=r["body"]
        or hashlib.sha256(trecho.encode()).hexdigest()!=r["content_hash"]):
        raise ValueError("Falha de integridade da fonte ou do texto.")
    spec=dut.estruturar(trecho,r["url"],r["content_hash"])
    if spec!=json.loads(r["spec"]) or spec["diferencas"]:
        raise ValueError("Estrutura divergente. Revise o mapeamento e capture nova versão.")
    dut.testar_logica(spec)
    secoes = [(k, dut.normal(v)) for k, v in dut.secoes(trecho).items()]
    assinatura = hashlib.sha256(json.dumps(secoes, ensure_ascii=False).encode()).hexdigest()
    # RN 596/2024, arts. 2º e 4º: inclusão do item 10 com vigência em 22/01/2024.
    if assinatura != "a14ad5583c295faa48f2841845180d6014246f98b21f4ca3b8764f7780b0b108":
        raise ValueError("A vigência desta redação ainda precisa ser identificada.")
    return "RN ANS nº 465/2021, Anexo II, DUT 60, com alteração pela RN nº 596/2024", "2024-01-22"


def finalizar(conn, tenant, doc, actor, revisado):
    if not revisado:
        raise ValueError("Marque Revisado antes de finalizar.")
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    row = conn.execute("SELECT * FROM regulatory_rules WHERE tenant=? AND doc=?", (tenant, doc)).fetchone()
    if not row:
        raise ValueError("Versão indisponível.")
    if row["state"] == "Ativa":
        return
    if row["state"] not in ("Extraída", "Aguardando validação", "Homologada"):
        raise ValueError("Esta versão já foi encerrada.")

    norma, inicio = verificar(conn, tenant, doc)
    # Preserva a vigência já confirmada nas homologações anteriores.
    inicio = row["effective"] or inicio
    anterior = conn.execute("SELECT doc, effective FROM regulatory_rules WHERE tenant=? AND state='Ativa'",
                            (tenant,)).fetchone()
    if anterior and (anterior["effective"] > inicio or anterior["doc"] >= row["doc"]):
        raise ValueError("A versão ativa é mais recente que a selecionada.")

    if anterior:
        conn.execute("UPDATE regulatory_rules SET state='Substituída' WHERE tenant=? AND doc=?",
                     (tenant, anterior["doc"]))
        evento(conn, tenant, anterior["doc"], actor, "Substituída")
    registro = f"Revisado por {actor} em {storage.now()}"
    conn.execute("""UPDATE regulatory_rules SET state='Ativa', norm=COALESCE(norm, ?), effective=?,
                    approved_by=COALESCE(approved_by, ?), clinical_record=COALESCE(clinical_record, ?)
                    WHERE id=?""", (norma, inicio, actor, registro, row["id"]))
    evento(conn, tenant, doc, actor, "Revisado")
    evento(conn, tenant, doc, actor, "Ativa")


def selecionar(conn,tenant,dia):
    if not dia:
        return None
    alvo=date.fromisoformat(dia[:10]).isoformat()
    r=conn.execute("""SELECT r.*,d.body,d.source_hash,d.content_hash,d.url FROM regulatory_rules r
        JOIN dut_documents d ON d.id=r.doc AND d.tenant=r.tenant WHERE r.tenant=?
        AND r.state IN ('Ativa','Substituída') AND r.effective<=?
        ORDER BY r.effective DESC,r.doc DESC LIMIT 1""",(tenant,alvo)).fetchone()
    if not r:
        return None
    return {"id":r["id"],"documento":r["doc"],"texto":r["body"],"inicio":r["effective"],
            "aprovado_por":r["approved_by"],"fonte":r["norm"]+" · "+r["url"],"hash_fonte":r["source_hash"],
            "hash":r["content_hash"],"estrutura":json.loads(r["spec"]),"registro_clinico":r["clinical_record"]}


def fontes_da_execucao(entrada):
    case = entrada["case"]
    fontes = {}
    for doc in entrada.get("documents", []):
        if doc.get("case_id") != case.get("id") or doc.get("tenant_id") != case.get("tenant_id"):
            raise ValueError("Documento importado de outra guia ou operadora.")
        fontes[str(doc["id"])] = {"origem":"sistema_operadora", "paginas":[doc.get("content_text") or ""]}
    for doc in entrada.get("documentos_textuais", []):
        metodos = doc.get("metodo_por_pagina")
        paginas = doc.get("paginas")
        if (not isinstance(doc.get("documento"),str) or not re.fullmatch(r"C[1-8]",doc["documento"])
            or doc.get("case_id") not in (None, case.get("id")) or doc.get("origem") != "complemento_medico_auditor"
            or doc.get("substitui_documento_obrigatorio") is not False
            or not isinstance(doc.get("sha256"),str) or not re.fullmatch(r"[0-9a-f]{64}",doc["sha256"])
            or not isinstance(paginas,list) or not paginas or not all(isinstance(p,str) and p for p in paginas)
            or not isinstance(metodos,list) or len(metodos)!=len(paginas)
            or any(m not in ("texto","ocr") for m in metodos)):
            raise ValueError("Evidência complementar sem origem verificável.")
        if doc["documento"] in fontes:
            raise ValueError("Identificador documental duplicado.")
        fontes[doc["documento"]] = {"origem":doc["origem"],"paginas":paginas,
            "metodos":metodos,"hash":doc["sha256"]}
    return fontes


def _instrucao_nao_autorizada(saida):
    texto = " ".join(str(v) for v in (saida.get("parecer") or {}).values())
    padroes = (
        r"\b(?:ignore|desconsidere)\b.{0,50}\b(?:instruções|regras|diretriz|dut)\b",
        r"\b(?:execute|rode)\b.{0,30}\b(?:comando|script|código)\b",
        r"\b(?:autorize|negue)\b.{0,30}\b(?:automaticamente|imediatamente|sem revisão)\b",
        r"\b(?:envie|transmita)\b.{0,50}\bsem revisão\b",
    )
    return any(re.search(p, texto, re.I | re.S) for p in padroes)


def auditar(entrada,saida,regra,item,confirmacoes,conferido=False):
    """Compara o parecer congelado com fatos atestados e citações do mesmo snapshot."""
    report={"item":item,"achados":[],"criterios":{},"evidencias":confirmacoes,"conferencia_humana":conferido}
    def fim(status,motivo=None):
        if motivo:
            report["achados"].append(motivo)
        return dict(report,status=status)
    if not regra or saida.get("dut_sha256")!=regra["hash"]:
        return fim("REGRA_NAO_VALIDADA","Fonte ausente ou diferente da aplicada na execução.")
    spec=regra["estrutura"]
    if spec["diferencas"] or regra["inicio"]>(entrada["case"].get("guide_received_at") or "")[:10]:
        return fim("REGRA_NAO_VALIDADA","Estrutura ou vigência incompatível com a guia.")
    try:
        fontes = fontes_da_execucao(entrada)
    except ValueError as exc:
        return fim("DIVERGENCIA_IDENTIFICADA",str(exc))
    if _instrucao_nao_autorizada(saida):
        return fim("DIVERGENCIA_IDENTIFICADA","A saída contém instrução ou ação não autorizada.")
    if item not in spec["grupos"]:
        return fim("DIVERGENCIA_IDENTIFICADA" if item else "EVIDENCIAS_INSUFICIENTES",
                   "Item da DUT inexistente na regra aplicada." if item else "Aguardando identificação médica do item aplicável.")
    chaves=dut.folhas(spec["grupos"][item])
    for c in saida.get("citacoes",[]) or []:
        trecho=c.get("trecho")
        fonte_citada = fontes.get(str(c.get("documento")))
        pagina = next((i for i,p in enumerate(fonte_citada["paginas"],1) if isinstance(trecho,str) and trecho in p),None) if fonte_citada else None
        if (not isinstance(trecho,str) or not trecho.strip() or not fonte_citada or not pagina
            or c.get("criterio") not in chaves
            or c.get("fato") not in spec["criterios"][c["criterio"]]["informacoes_clinicas"]):
            return fim("DIVERGENCIA_IDENTIFICADA","Atribuição de evidência inexistente, de outra guia ou de outro critério.")
        if fonte_citada["origem"] == "complemento_medico_auditor" and (
            c.get("origem") != fonte_citada["origem"] or str(c.get("pagina")) != str(pagina)
            or c.get("hash") != fonte_citada["hash"] or c.get("metodo") != fonte_citada["metodos"][pagina-1]):
            return fim("DIVERGENCIA_IDENTIFICADA","Evidência complementar sem página, hash ou método verificável.")
    valores={}
    for ev in confirmacoes:
        k=ev["criterio"]
        if k not in chaves or ev["fato"] not in spec["criterios"][k]["informacoes_clinicas"]:
            return fim("DIVERGENCIA_IDENTIFICADA","Fato sem associação ao critério.")
        fonte_ev = fontes.get(str(ev["documento"]))
        if (not fonte_ev or not ev["trecho"].strip() or not any(ev["trecho"] in p for p in fonte_ev["paginas"])
            or ev["valor"] not in ("sim","não")):
            return fim("DIVERGENCIA_IDENTIFICADA","Evidência sem correspondência documental nesta guia.")
        chave=(k,ev["fato"])
        valor=ev["valor"]=="sim"
        if chave in valores and valores[chave]!=valor:
            return fim("DIVERGENCIA_IDENTIFICADA","Documentos ou registros contraditórios para o mesmo fato.")
        valores[chave]=valor
    resultados={k:dut.avaliar(spec["criterios"][k]["condicoes"],{f:v for (c,f),v in valores.items() if c==k}) for k in chaves}
    calculado=dut.avaliar(spec["grupos"][item],resultados)
    report["criterios"]={k:ESTADO[v] for k,v in resultados.items()}
    report["resultado_motor"]=RESULTADO[calculado]
    if not confirmacoes:
        return fim("EVIDENCIAS_INSUFICIENTES","Aguardando vínculos confirmados entre critérios e documentos.")
    if saida.get("item_dut")!=item:
        report["achados"].append("Enquadramento do parecer divergente ou ausente.")
    citacoes = saida.get("citacoes",[])
    for c in citacoes:
        if not any(all(c.get(k)==ev[k] for k in ("criterio","fato","documento","trecho","valor")) for ev in confirmacoes):
            report["achados"].append("Citação da IA sem vínculo confirmado para este fato e documento.")
    for ev in confirmacoes:
        if not any(all(c.get(k)==ev[k] for k in ("criterio","fato","documento","trecho","valor")) for c in citacoes):
            report["achados"].append("Evidência confirmada omitida no confronto do parecer.")
    mapa=saida.get("estados_criterios",[])
    if len(mapa)!=len(chaves) or {v["criterio"]:v["estado"] for v in mapa}!=report["criterios"]:
        report["achados"].append("Critério omitido ou condição avaliada de forma diferente.")
    if saida.get("suggestion")!=RESULTADO[calculado]:
        report["achados"].append("Conclusão incompatível com o resultado determinístico do item.")
    if report["achados"]:
        return fim("DIVERGENCIA_IDENTIFICADA")
    if calculado is None or not conferido:
        return fim("EVIDENCIAS_INSUFICIENTES","Verifique informações essenciais, escopo e fundamentação narrativa.")
    return fim("VALIDADO")


def registrar_guia(conn,tenant,run,actor,item="",evidencias=None,conferido=False):
    entrada=json.loads(run["input_snapshot"])
    regra=entrada.get("regra_regulatoria")
    try:
        report=auditar(entrada,json.loads(run["original_output"]),regra,item,evidencias or [],conferido)
        if regra:
            prevista=selecionar(conn,tenant,entrada["case"].get("guide_received_at"))
            if not prevista or prevista["id"]!=regra["id"]:
                report["status"]="REGRA_NAO_VALIDADA"
                report["achados"].append("A regra vinculada difere da versão atualmente homologada para a data da guia.")
    except (KeyError,TypeError,ValueError,AttributeError):
        report={"status":"FALHA_TECNICA","achados":["Estrutura da execução incompatível."]}
    conn.execute("INSERT INTO regulatory_audits(tenant,run_id,actor,created,status,report) VALUES(?,?,?,?,?,?)",
                 (tenant,run["id"],actor,storage.now(),report["status"],json.dumps(report,ensure_ascii=False)))
    storage.event(conn,tenant,run["case_id"],"Auditoria regulatória da guia",actor,run["correlation"] or str(run["id"]),
                  result=report["status"],version=str(regra["id"]) if regra else None)
    storage.audit(conn,tenant,actor,"auditoria_regulatoria","run",run["id"],report["status"],run["case_id"])
    return report


def conferir(conn,s,run,d):
    entrada=json.loads(run["input_snapshot"])
    fontes=fontes_da_execucao(entrada)
    spec=entrada.get("regra_regulatoria",{}).get("estrutura",{})
    item=d.get("item","")
    if item not in spec.get("grupos",{}):
        raise ValueError("Item indisponível nesta execução.")
    anterior=conn.execute("""SELECT report FROM regulatory_audits WHERE tenant=? AND run_id=?
        AND json_extract(report,'$.item')=? ORDER BY id DESC LIMIT 1""",(s["tenant"],run["id"],item)).fetchone()
    evidencias=json.loads(anterior[0]).get("evidencias",[]) if anterior else []
    acao=d.get("acao")
    if acao=="vincular":
        k,_,f=d.get("fato","").partition("|")
        doc=d.get("documento","")
        trecho=d.get("trecho","").strip()
        fonte=fontes.get(doc)
        pagina=next((i for i,p in enumerate(fonte["paginas"],1) if trecho in p),None) if fonte else None
        if (k not in dut.folhas(spec["grupos"][item]) or f not in spec["criterios"][k]["informacoes_clinicas"]
            or d.get("valor") not in ("sim","não") or not 1<=len(trecho)<=2000 or len(evidencias)>=150
            or not fonte or not pagina):
            raise ValueError("Confira a condição e a citação literal no documento desta execução.")
        ev={"criterio":k,"fato":f,"documento":doc,"trecho":trecho,"valor":d["valor"]}
        if fonte["origem"]=="complemento_medico_auditor":
            ev.update(case_id=entrada["case"]["id"],origem=fonte["origem"],pagina=pagina,
                      hash=fonte["hash"],metodo=fonte["metodos"][pagina-1])
        if ev not in evidencias:
            evidencias.append(ev)
    elif acao=="reiniciar":
        evidencias=[]
    elif acao!="conferir" or d.get("confirmado")!="1":
        raise ValueError("Confira a declaração médica.")
    registrar_guia(conn,s["tenant"],run,s["user"],item,evidencias,acao=="conferir")
