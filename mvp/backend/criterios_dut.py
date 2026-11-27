"""Expressões propostas para homologação. Nenhuma expressão executa texto da fonte."""
import re
import unicodedata
from pathlib import Path

BASE = Path(__file__).with_name("DUT60.txt")


def todos(*partes):
    return {"AND": list(partes)}


def algum(*partes):
    return {"OR": list(partes)}


# Cada chave aponta para o parágrafo de onde se origina. A OBS trata da rede.
EXPRESSOES = {
    "1": todos("Câncer pulmonar de células não pequenas", "Comprovação por biópsia"),
    "1.a": "Caracterização de lesões", "1.b": "Estadiamento do comprometimento mediastinal e à distância",
    "1.c": "Detecção de recorrências",
    "2": "Linfoma", "2.a": "Estadiamento primário", "2.b": "Avaliação da resposta terapêutica",
    "2.c": todos("Monitoramento da recidiva", "Linfoma Hodgkin ou não-Hodgkin"),
    "3": "Câncer colo-retal", "3.a": todos("Câncer recidivado", "Potencialmente ressecável"),
    "3.b": todos("CEA elevado", "Ausência de lesão em imagem convencional"),
    "3.c": todos("Recidiva", "Achados radiológicos inconclusivos, com ou sem aumento do CEA"),
    "4": "Nódulo pulmonar solitário", "4.a": algum("RM inconclusiva", "TC inconclusiva"),
    "4.b": "Nódulo maior que 1 cm", "4.c": "Nódulo não espiculado", "4.d": "Nódulo sem calcificações",
    "5": todos("Diagnóstico de câncer de mama metastático", "Achados equívocos em imagem convencional"),
    "6": "Câncer de cabeça e pescoço",
    "6.a": todos("Imagem em órgão suspeita de metástase", "Outros exames de imagem insuficientemente esclarecedores"),
    "6.b": todos("Biópsia por agulha de lesão ou linfonodo cervical", algum("Carcinoma de células escamosas",
                  "Adenocarcinoma", "Carcinoma epitelial anaplásico"), "Tumor primário desconhecido",
                  "Outro exame de imagem insuficientemente esclarecedor"),
    "7": "Melanoma",
    "7.a": todos("Estadiamento", algum("Espessura tumoral maior ou igual a 1,5 mm",
                 "Linfonodo sentinela positivo", "Linfonodo clinicamente positivo"),
                 "Sem evidência de metástases", "Exames convencionais insuficientemente esclarecedores"),
    "7.b": todos("Recidiva detectada por outro método diagnóstico", "Candidato a metastectomia",
                 {"NOT": "Lesão de SNC"}, {"NOT": "Lesão menor que 3 mm de espessura"}),
    "8": todos("Câncer de esôfago localmente avançado", "Detecção de metástase à distância",
               "TC de tórax e avaliação abdominal insuficientemente esclarecedoras",
               algum("USG abdominal realizada", "TC abdominal realizada")),
    "9": todos("PET-CT com análogo de somatostatina", "Tumor neuroendócrino potencialmente expressor de receptores de somatostatina"),
    "9.a": "Localização do tumor primário", "9.b": "Detecção de metástases",
    "9.c": algum("Detecção de doença residual","Detecção de doença recorrente","Detecção de doença progressiva"),
    "9.d": "Determinação da presença de receptores da somatostatina",
    "10": todos("Câncer pulmonar de células pequenas", "Comprovação por biópsia", "Estadiamento do câncer"),
}


def folhas(expr):
    if isinstance(expr,str):
        return [expr]
    op, valores = next(iter(expr.items()))
    return folhas(valores) if op=="NOT" else [f for parte in valores for f in folhas(parte)]


def secoes(texto):
    limpo = re.sub(r"Diretrizes de Utilização \(anexo II – RN nº 465/12021\)\s+\d+\s*", "\n", texto)
    marcadores = list(re.finditer(r"(?m)^[ \t\f]*(?:(\d+|[a-z])\.[ \t]*|(OBS):[ \t]*)",limpo))
    bloco = {}
    item = ""
    for i,m in enumerate(marcadores):
        token = m[1] or m[2]
        if token.isdigit():
            item=token
        chave = item+"."+token if len(token)==1 and token.isalpha() else token
        if chave in bloco:
            raise ValueError("Identificador duplicado na extração: "+chave)
        fim = marcadores[i+1].start() if i+1<len(marcadores) else len(limpo)
        bloco[chave] = limpo[m.end():fim].strip()
    return bloco


def normal(texto):
    return " ".join(unicodedata.normalize("NFC",texto).split())


def estruturar(texto, url, versao):
    base = secoes(BASE.read_text(encoding="utf-8"))
    recebido = secoes(texto)
    erros = [k for k in dict.fromkeys([*base,*recebido])
             if k not in base or k not in recebido or normal(recebido[k])!=normal(base[k])]
    if list(recebido)!=list(base):
        erros.append("ordem ou hierarquia")
    criterios = {}
    for k,expr in EXPRESSOES.items():
        criterios[k] = {"id":"60."+k,"referencia_literal":recebido.get(k,""),"condicoes":expr,
                        "informacoes_clinicas":folhas(expr),
                        "evidencia":"Trecho documental confirmado pelo auditor para cada condição."}
    grupos = {}
    for n in map(str,range(1,11)):
        filhos=[k for k in criterios if k.startswith(n+".")]
        grupos[n]=todos(n,(todos if n=="4" else algum)(*filhos)) if filhos else n
    return {"fonte":url,"versao_documental":versao,"criterios":criterios,"grupos":grupos,
            "observacao_rede":recebido.get("OBS",""),"diferencas":erros}


def avaliar(expr, fatos):
    if isinstance(expr,str):
        return fatos.get(expr)
    op, membros = next(iter(expr.items()))
    if op=="NOT":
        v=avaliar(membros,fatos)
        return None if v is None else not v
    valores=[avaliar(m,fatos) for m in membros]
    decisivo = op=="OR"
    if decisivo in valores:
        return decisivo
    return None if None in valores else not decisivo


def testar_logica(spec):
    """Vetores sintéticos de regressão independentes do texto da IA."""
    casos = [
        ("2",{"2":True,"2.b":True},True),
        ("2",{"2":False,"2.a":True},False),
        ("2",{"2":True},None),
        ("4",{"4":True,"4.a":True,"4.b":True,"4.c":True,"4.d":True},True),
        ("4",{"4":True,"4.a":True,"4.b":False,"4.c":True,"4.d":True},False),
        ("4",{"4":True,"4.a":True,"4.b":True,"4.c":True},None),
        ("9",{"9":True,"9.d":True},True),
    ]
    for item, fatos, esperado in casos:
        if avaliar(spec["grupos"][item],fatos) is not esperado:
            raise ValueError(f"Falha no vetor de regressão do item 60.{item}.")
    return len(casos)


# ==============================================================================
# ARQUITETURA AUDITIA: DOIS EIXOS INDEPENDENTES DE AVALIAÇÃO
# (Decisões de arquitetura do AuditIA para auditoria clínica e regulatória de PET-CT)
# ==============================================================================

# Eixo A — Conformidade Regulatória com a DUT 60
ESTADO_ATENDIDO = "ATENDIDO"
ESTADO_NAO_ATENDIDO = "NÃO ATENDIDO"
ESTADO_NAO_COMPROVADO = "NÃO COMPROVADO"
ESTADO_NAO_APLICAVEL = "NÃO APLICÁVEL"

CONCLUSAO_ATENDIDO = "CRITÉRIOS REGULATÓRIOS ATENDIDOS"
CONCLUSAO_NAO_ATENDIDO = "CRITÉRIOS REGULATÓRIOS NÃO ATENDIDOS"
CONCLUSAO_INSUFICIENTE = "DADOS INSUFICIENTES"
CONCLUSAO_NAO_CONTEMPLADA = "INDICAÇÃO NÃO CONTEMPLADA NA DUT 60"

# Eixo B — Suficiência Documental e Pertinência Clínica
DOC_SUFICIENTE = "SUFICIENTE PARA ANÁLISE"
DOC_COMPLEMENTACAO = "COMPLEMENTAÇÃO RECOMENDADA"
DOC_INSUFICIENTE = "INSUFICIENTE PARA ANÁLISE"
DOC_NAO_DETERMINADA = "NÃO DETERMINADA"

# Subitens com exigência expressa de comprovação por biópsia na DUT 60:
# Apenas 60.1 (CPCNP), 60.10 (CPCP) e 60.6.b (biópsia por agulha de lesão/linfonodo cervical).
SUBITENS_BIOPSIA_EXPRESSA = {"1", "10", "6.b"}


def exige_biopsia_expressa(subitem):
    """Retorna True se o subitem possuir exigência normativa expressa de biópsia na DUT 60."""
    return str(subitem).strip() in SUBITENS_BIOPSIA_EXPRESSA


def avaliar_condicao(valor):
    """Mapeia valor de entrada para o estado da condição no Eixo A."""
    if valor is True or valor in ("sim", "comprovado", ESTADO_ATENDIDO):
        return ESTADO_ATENDIDO
    if valor is False or valor in ("não", "nao", "contradito", ESTADO_NAO_ATENDIDO):
        return ESTADO_NAO_ATENDIDO
    if valor == ESTADO_NAO_APLICAVEL:
        return ESTADO_NAO_APLICAVEL
    return ESTADO_NAO_COMPROVADO


def avaliar_eixo_a(item, fatos):
    """
    Avalia deterministicamente o subitem da DUT 60 sob o Eixo A.
    item: string representando o subitem ("1" a "10").
    fatos: dict { "identificador_ou_texto": valor }
    Retorna estrutura determinística do Eixo A.
    """
    item_str = str(item).strip()
    if not item_str or (item_str not in EXPRESSOES and item_str not in map(str, range(1, 11))):
        return {
            "item": item_str or "Não identificado",
            "conclusao": CONCLUSAO_NAO_CONTEMPLADA,
            "estados_condicoes": {},
            "resultado_booleano": None,
        }

    filhos = [k for k in EXPRESSOES if k.startswith(item_str + ".")]
    chaves = [item_str, *filhos] if filhos else [item_str]
    grupo = todos(item_str, (todos if item_str == "4" else algum)(*filhos)) if filhos else item_str

    fatos_bool = {}
    estados_condicoes = {}
    for k, v in (fatos or {}).items():
        st = avaliar_condicao(v)
        estados_condicoes[k] = st
        if st == ESTADO_ATENDIDO:
            fatos_bool[k] = True
        elif st == ESTADO_NAO_ATENDIDO:
            fatos_bool[k] = False
        else:
            fatos_bool[k] = None

    # Avalia cada subcritério da árvore contra fatos_bool
    sub_resultados = {}
    for k in chaves:
        if k in fatos_bool and fatos_bool[k] is not None:
            sub_resultados[k] = fatos_bool[k]
        elif k in EXPRESSOES:
            sub_resultados[k] = avaliar(EXPRESSOES[k], fatos_bool)
        else:
            sub_resultados[k] = fatos_bool.get(k)

    resultado = avaliar(grupo, sub_resultados)

    if resultado is True:
        conclusao = CONCLUSAO_ATENDIDO
    elif resultado is False:
        conclusao = CONCLUSAO_NAO_ATENDIDO
    else:
        conclusao = CONCLUSAO_INSUFICIENTE

    return {
        "item": item_str,
        "conclusao": conclusao,
        "estados_condicoes": estados_condicoes,
        "resultado_booleano": resultado,
    }


def categorizar_documentos_caso(case, docs):
    """
    Classifica deterministicamente os documentos do caso nas 4 categorias da arquitetura:
    - Documentos recebidos
    - Documentos não recebidos
    - Documentos efetivamente necessários conforme o critério aplicável
    - Necessidade documental não determinada
    Retorna também a avaliação clínica do Eixo B e o rótulo/badge para exibição.
    """
    c_dict = dict(case) if hasattr(case, "keys") else (case if isinstance(case, dict) else {})
    docs_list = [dict(d) if hasattr(d, "keys") else (d if isinstance(d, dict) else {}) for d in (docs or [])]

    tipos_recebidos = {d.get("kind") for d in docs_list if d.get("kind")}
    tem_pedido = "pedido_medico" in tipos_recebidos or bool(c_dict.get("tem_pedido"))
    tem_anatomo = "anatomopatologico" in tipos_recebidos or bool(c_dict.get("tem_anatomo"))

    recebidos_nomes = []
    if tem_pedido:
        recebidos_nomes.append("Pedido médico")
    if tem_anatomo:
        recebidos_nomes.append("Laudo anatomopatológico")
    for d in docs_list:
        nome = d.get("name") or d.get("kind") or ""
        if nome and nome not in recebidos_nomes and d.get("kind") not in ("pedido_medico", "anatomopatologico"):
            recebidos_nomes.append(nome)

    proc = (c_dict.get("procedure") or "").lower()
    narr = (c_dict.get("narrative") or "").lower()
    tuss = str(c_dict.get("tuss_code") or "").strip()
    texto = f"{proc} {narr}"

    subitem = None
    criterio_rotulo = "DUT 60 (PET-CT Oncológico)"
    if tuss == "41001311" or "neurol" in texto or "demênc" in texto or "demenc" in texto:
        subitem = "neurologico"
        criterio_rotulo = "Fora do Rol (Avaliação neurológica)"
        necessarios = ["Pedido médico"]
        indeterminado = False
    elif "pequenas células" in texto or "cpcp" in texto:
        subitem = "10"
        criterio_rotulo = "DUT 60.10 (CPCP - Estadiamento)"
        necessarios = ["Pedido médico", "Laudo anatomopatológico"]
        indeterminado = False
    elif "células não pequenas" in texto or "cpcnp" in texto:
        subitem = "1"
        criterio_rotulo = "DUT 60.1 (CPCNP)"
        necessarios = ["Pedido médico", "Laudo anatomopatológico"]
        indeterminado = False
    elif "nódulo pulmonar" in texto or "nodulo pulmonar" in texto or ("solitário" in texto and "pulm" in texto) or ("solitario" in texto and "pulm" in texto):
        subitem = "4"
        criterio_rotulo = "DUT 60.4 (Nódulo pulmonar solitário)"
        necessarios = ["Pedido médico"]
        indeterminado = False
    elif "linfoma" in texto or "hodgkin" in texto:
        subitem = "2"
        criterio_rotulo = "DUT 60.2 (Linfoma)"
        necessarios = ["Pedido médico"]
        indeterminado = False
    elif "colo-retal" in texto or "colorretal" in texto or "colon" in texto or "reto" in texto or "cea" in texto:
        subitem = "3"
        criterio_rotulo = "DUT 60.3 (Câncer colorretal)"
        necessarios = ["Pedido médico"]
        indeterminado = False
    elif "mama" in texto:
        subitem = "5"
        criterio_rotulo = "DUT 60.5 (Câncer de mama metastático)"
        necessarios = ["Pedido médico"]
        indeterminado = False
    elif "cabeça e pescoço" in texto or "cabeca e pescoco" in texto or "linfonodo cervical" in texto:
        subitem = "6"
        criterio_rotulo = "DUT 60.6 (Câncer de cabeça e pescoço)"
        necessarios = ["Pedido médico"]
        indeterminado = False
    elif "melanoma" in texto:
        subitem = "7"
        criterio_rotulo = "DUT 60.7 (Melanoma)"
        necessarios = ["Pedido médico"]
        indeterminado = False
    elif "esôfago" in texto or "esofago" in texto:
        subitem = "8"
        criterio_rotulo = "DUT 60.8 (Câncer de esôfago)"
        necessarios = ["Pedido médico"]
        indeterminado = False
    elif "neuroendócrin" in texto or "neuroendocrin" in texto or "somatostatina" in texto:
        subitem = "9"
        criterio_rotulo = "DUT 60.9 (Tumores neuroendócrinos)"
        necessarios = ["Pedido médico"]
        indeterminado = False
    elif tuss in ("40708128", "41001222", "40708152", "40708144") or "oncol" in texto or "estadiamento" in texto or "pet-ct" in texto:
        subitem = "indeterminado"
        criterio_rotulo = "DUT 60 (Indicação oncológica a definir)"
        necessarios = ["Pedido médico"]
        indeterminado = True
    else:
        necessarios = ["Pedido médico"]
        indeterminado = True

    nao_recebidos = [doc for doc in necessarios if doc not in recebidos_nomes]

    # Avaliação do Eixo B (Suficiência documental e pertinência clínica)
    pendencias_clinicas = []
    if not tem_pedido:
        eixo_b = DOC_INSUFICIENTE
        pendencias_clinicas.append("Pedido médico com indicação clínica e justificativa ausente.")
    elif subitem in ("1", "10") and not tem_anatomo:
        eixo_b = DOC_INSUFICIENTE
        pendencias_clinicas.append("Laudo anatomopatológico da biópsia exigida pelo subitem ausente.")
    elif subitem in ("2", "3", "5", "6", "7", "8", "9") and not tem_anatomo:
        # Nos subitens que não exigem biópsia expressa na DUT, a ausência do laudo
        # não bloqueia e gera apenas recomendação de complementação no Eixo B
        eixo_b = DOC_COMPLEMENTACAO
        pendencias_clinicas.append("Laudo histopatológico recomendado para confirmação do subtipo clínico.")
    elif subitem == "4" and not tem_anatomo:
        # Nódulo pulmonar solitário: biópsia prévia não é exigida
        eixo_b = DOC_SUFICIENTE
    elif indeterminado:
        eixo_b = DOC_NAO_DETERMINADA
        pendencias_clinicas.append("Indicação clínica a ser detalhada na análise médica.")
    else:
        eixo_b = DOC_SUFICIENTE

    # Rótulo e Badge para a interface
    if indeterminado:
        status_rotulo = "A determinar"
        badge_html = f'<span class="badge bg-secondary" title="Critério clínico pendente de definição. Recebidos: {", ".join(recebidos_nomes) or "Nenhum"}">A determinar</span>'
    elif not nao_recebidos:
        status_rotulo = "Completa"
        badge_html = f'<span class="badge bg-success" title="{criterio_rotulo} · Necessários: {", ".join(necessarios)} · Recebidos: {", ".join(recebidos_nomes) or "Nenhum"}">Completa</span>'
    else:
        status_rotulo = f"Pendente ({', '.join(nao_recebidos)})"
        if "Laudo anatomopatológico" in nao_recebidos and tem_pedido:
            faltam_txt = "Falta laudo"
        elif "Pedido médico" in nao_recebidos and tem_anatomo:
            faltam_txt = "Falta pedido"
        else:
            faltam_txt = "Falta pedido e laudo"
        badge_html = f'<span class="badge bg-warning text-dark" title="{criterio_rotulo} · Necessários: {", ".join(necessarios)} · Não recebidos: {", ".join(nao_recebidos)} · Recebidos: {", ".join(recebidos_nomes) or "Nenhum"}">{faltam_txt}</span>'

    return {
        "subitem": subitem,
        "criterio": criterio_rotulo,
        "indeterminado": indeterminado,
        "recebidos": recebidos_nomes,
        "nao_recebidos": nao_recebidos,
        "necessarios": necessarios,
        "status_rotulo": status_rotulo,
        "badge_html": badge_html,
        "eixo_b_status": eixo_b,
        "pendencias_clinicas": pendencias_clinicas,
    }


def gerar_resultado_estruturado(case, docs, fatos_confirmados=None):
    """
    Produz o resultado estruturado em 5 seções conforme a arquitetura de dois eixos:
    A. Identificação da solicitação e norma
    B. Avaliação regulatória (Eixo A)
    C. Avaliação clínico-documental (Eixo B)
    D. Conclusão do agente
    E. Apoio à decisão do médico auditor
    """
    cat = categorizar_documentos_caso(case, docs)
    subitem = cat["subitem"]
    c_dict = dict(case) if hasattr(case, "keys") else (case if isinstance(case, dict) else {})

    # A. Identificação
    secao_a = {
        "procedimento": c_dict.get("procedure") or "PET-CT oncológico",
        "indicacao_clinica": c_dict.get("narrative") or "Não informada",
        "subitem_dut": f"60.{subitem}" if subitem and subitem not in ("neurologico", "indeterminado") else (
            "Fora do escopo da DUT 60 (PET-CT neurológico)" if subitem == "neurologico" else (
                "DUT 60 (Subitem a determinar por dados insuficientes)" if subitem == "indeterminado" else "Indicação não contemplada na DUT 60"
            )
        ),
        "versao_normativa": "RN ANS nº 465/2021, Anexo II, DUT 60 (com alteração pela RN nº 596/2024)",
    }

    # B. Avaliação regulatória (Eixo A)
    if subitem and subitem not in ("neurologico", "indeterminado"):
        res_a = avaliar_eixo_a(subitem, fatos_confirmados or {})
        conclusao_eixo_a = res_a["conclusao"]
        estados_condicoes = res_a["estados_condicoes"]
    elif subitem == "indeterminado":
        conclusao_eixo_a = CONCLUSAO_INSUFICIENTE
        estados_condicoes = {}
    elif subitem == "neurologico":
        conclusao_eixo_a = CONCLUSAO_NAO_CONTEMPLADA
        estados_condicoes = {}
    else:
        conclusao_eixo_a = CONCLUSAO_NAO_CONTEMPLADA
        estados_condicoes = {}

    secao_b = {
        "subitem": subitem,
        "conclusao_regulatoria": conclusao_eixo_a,
        "estados_condicoes": estados_condicoes,
        "exige_biopsia_expressa": exige_biopsia_expressa(subitem) if subitem else False,
        "sintese_enquadramento": f"Avaliação do subitem 60.{subitem} da DUT 60." if subitem and subitem not in ("neurologico", "indeterminado") else (
            "Indicação oncológica a definir por dados insuficientes." if subitem == "indeterminado" else "Procedimento não enquadrado na DUT 60 oncológica."
        ),
    }

    # C. Avaliação clínico-documental (Eixo B)
    secao_c = {
        "documentos_recebidos": cat["recebidos"],
        "documentos_faltantes": cat["nao_recebidos"],
        "necessidade_biopsia": "Obrigatória pela norma da DUT 60" if exige_biopsia_expressa(subitem) else (
            "Dispensada (Nódulo pulmonar solitário)" if subitem == "4" else "Recomendação clínica para confirmação histológica (não vinculante na DUT)"
        ),
        "status_suficiencia": cat["eixo_b_status"],
        "pendencias_clinicas": cat["pendencias_clinicas"],
    }

    # D. Conclusão do agente
    if subitem == "neurologico":
        conclusao_agente = CONCLUSAO_NAO_CONTEMPLADA
    elif subitem == "indeterminado":
        conclusao_agente = CONCLUSAO_INSUFICIENTE
    elif conclusao_eixo_a == CONCLUSAO_ATENDIDO and cat["eixo_b_status"] == DOC_SUFICIENTE:
        conclusao_agente = CONCLUSAO_ATENDIDO
    elif conclusao_eixo_a == CONCLUSAO_NAO_ATENDIDO:
        conclusao_agente = CONCLUSAO_NAO_ATENDIDO
    elif conclusao_eixo_a == CONCLUSAO_NAO_CONTEMPLADA:
        conclusao_agente = CONCLUSAO_NAO_CONTEMPLADA
    else:
        conclusao_agente = CONCLUSAO_INSUFICIENTE

    secao_d = {
        "conclusao": conclusao_agente,
        "negativa_automatica_autorizada": False,
    }

    # E. Apoio à decisão e revisão humana
    if conclusao_agente == CONCLUSAO_ATENDIDO:
        recomendacao = "Critérios da DUT 60 demonstrados e documentação suficiente. Encaminhar para conferência médica final."
    elif conclusao_agente == CONCLUSAO_INSUFICIENTE:
        recomendacao = "Dados insuficientes para concluir enquadramento. Recomenda-se solicitar complementação documental sem emitir negativa."
    elif conclusao_agente == CONCLUSAO_NAO_CONTEMPLADA:
        recomendacao = "Indicação não contemplada na DUT 60 oncológica. Encaminhar para avaliação de pertinência clínica ou via fora do Rol pelo médico auditor."
    else:
        recomendacao = "Critério da DUT 60 não atendido pela documentação anexada. Revisão indelegável do médico auditor."

    secao_e = {
        "recomendacao_fundamentada": recomendacao,
        "pendencias": cat["pendencias_clinicas"],
        "alternativas_assistenciais": ["Avaliação médica fora do Rol com fundamentação técnica"] if subitem == "neurologico" else [],
        "revisao_medica_obrigatoria": True,
    }

    return {
        "identificacao": secao_a,
        "avaliacao_regulatoria_eixo_a": secao_b,
        "avaliacao_clinica_eixo_b": secao_c,
        "conclusao_agente": secao_d,
        "revisao_humana": secao_e,
    }
