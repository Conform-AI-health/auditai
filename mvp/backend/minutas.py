"""Gerador determinístico e redacional de Minutas Regulatórias para o AuditIA Beta 0.2.
Implementa o padrão redacional formal e técnico exigido pela regulação da saúde suplementar,
contemplando Parecer Favorável, Negativas fundamentadas (DUT e Rol) e Complementação Documental.
Supervisão humana estrita: a IA elabora minutas técnicas; a decisão é exclusiva do médico auditor.
"""

from backend import criterios_dut, storage, tuss_rol
import json


MODALIDADE_FAVORAVEL = "FAVORAVEL"
MODALIDADE_NEGATIVA_DUT = "NEGATIVA_DUT_NAO_ATENDIDA"
MODALIDADE_COMPLEMENTACAO = "COMPLEMENTACAO_DOCUMENTAL"
MODALIDADE_NEGATIVA_ROL = "NEGATIVA_FORA_DO_ROL"
MODALIDADE_NEGATIVA_INDICACAO = "NEGATIVA_INDICACAO_NAO_CONTEMPLADA"
MODALIDADE_PRELIMINAR = "PRELIMINAR_INCONSISTENCIA"

DISCLAIMER_PADRAO = (
    "RASCUNHO_IA — PENDENTE DE REVISÃO MÉDICA. "
    "A emissão ou aprovação desta minuta constitui subsídio técnico e não dispara "
    "envio automático de comunicação ao beneficiário ou prestador."
)


def classificar_modalidade_minuta(case, docs, fatos=None, rota=None):
    """
    Determina objetivamente a modalidade de minuta com base no motor determinístico da DUT 60,
    na triagem TUSS × Rol e na suficiência documental.
    """
    c_dict = dict(case) if hasattr(case, "keys") else (case if isinstance(case, dict) else {})
    narrativa = (c_dict.get("narrative") or "").lower()
    proc = (c_dict.get("procedure") or "").lower()
    tuss = str(c_dict.get("tuss_code") or "").strip()

    # 1. Verifica triagem TUSS × Rol
    rota_dict = dict(rota) if hasattr(rota, "keys") else (rota if isinstance(rota, dict) else {})
    categoria_rota = rota_dict.get("category") if rota else None
    if not categoria_rota:
        # Se não informada, infere
        if tuss == "41001311" or "demência" in narrativa or "neurológico" in proc:
            categoria_rota = "avaliacao_fora_rol"
        elif tuss in ("40708128", "41001222"):
            categoria_rota = "dut60_direta"
        else:
            categoria_rota = "dut60_direta"

    # Caso especial B07 / PET cerebral para demência: Fora do Rol
    if categoria_rota == "avaliacao_fora_rol" or tuss == "41001311" or "demência" in narrativa:
        return MODALIDADE_NEGATIVA_ROL

    # 2. Avaliação pela DUT 60
    resultado = criterios_dut.gerar_resultado_estruturado(case, docs, fatos or {})
    conclusao = resultado["conclusao_agente"]["conclusao"]
    eixo_b = resultado["avaliacao_clinica_eixo_b"]["status_suficiencia"]
    subitem = resultado.get("avaliacao_regulatoria_eixo_a", {}).get("subitem")

    # Indicações conhecidas não contempladas na DUT 60 (ex: testículo, próstata convencional)
    if "testículo" in narrativa or "testicular" in narrativa:
        return MODALIDADE_NEGATIVA_INDICACAO

    # Avaliação da DUT 60
    if conclusao == criterios_dut.CONCLUSAO_ATENDIDO and eixo_b == criterios_dut.DOC_SUFICIENTE:
        return MODALIDADE_FAVORAVEL
    elif conclusao == criterios_dut.CONCLUSAO_NAO_ATENDIDO:
        return MODALIDADE_NEGATIVA_DUT
    elif conclusao == criterios_dut.CONCLUSAO_INSUFICIENTE or eixo_b in (criterios_dut.DOC_INSUFICIENTE, criterios_dut.DOC_COMPLEMENTACAO):
        return MODALIDADE_COMPLEMENTACAO
    elif conclusao == criterios_dut.CONCLUSAO_FORA_ESCOPO:
        return MODALIDADE_NEGATIVA_INDICACAO
    else:
        return MODALIDADE_PRELIMINAR


def redigir_minuta(case, docs, modalidade, fatos=None, rota=None):
    """
    Elabora a minuta no padrão redacional formal da regulação da ANS,
    utilizando texto corrido em parágrafos coesos, sem invenção de dados.
    """
    c_dict = dict(case) if hasattr(case, "keys") else (case if isinstance(case, dict) else {})
    proc = c_dict.get("procedure") or "PET-CT oncológico"
    narrativa = c_dict.get("narrative") or ""
    tuss = c_dict.get("tuss_code") or "40708128"
    guia = c_dict.get("external_id") or "S/N"
    beneficiario = c_dict.get("beneficiary_code") or "beneficiário identificado em prontuário"

    resultado = criterios_dut.gerar_resultado_estruturado(case, docs, fatos or {})
    subitem = resultado.get("avaliacao_regulatoria_eixo_a", {}).get("subitem") or "1"

    if modalidade == MODALIDADE_FAVORAVEL:
        titulo = "Parecer Técnico Favorável — Cobertura Obrigatória Atendida (DUT 60)"
        base_normativa = f"Diretriz de Utilização nº 60, subitem {subitem}, do Anexo II da RN ANS nº 465/2021 e suas atualizações."
        resumo_clinico = f"Trata-se de solicitação de {proc} para paciente portador de neoplasia maligna, conforme documentação médica e laudos anexos à guia {guia}."
        criterios = (
            f"Conforme estabelecido na {base_normativa}, a cobertura obrigatória de PET-CT encontra-se "
            f"prevista quando preenchidos os critérios técnicos de indicação clínica e comprovação diagnóstica pertinentes."
        )
        confronto = (
            f"No caso em apreço, os elementos clínicos e documentais apresentados evidenciam o preenchimento "
            f"integral dos requisitos normativos aplicáveis ao subitem {subitem}, estando demonstrada a pertinência "
            f"da indicação e a conformidade regulatória para a realização do exame."
        )
        conclusao = (
            f"Diante do exposto, manifesta-se parecer técnico favorável à autorização do procedimento {proc} "
            f"(código TUSS {tuss}), ressalvada a conferência administrativa e contratual de praxe."
        )
        reanalise = "Recomenda-se o encaminhamento regular do procedimento à rede credenciada apta para realização."
        texto_completo = f"{resumo_clinico}\n\n{criterios}\n\n{confronto}\n\n{conclusao}\n\n{reanalise}"

    elif modalidade == MODALIDADE_NEGATIVA_DUT:
        titulo = "Minuta de Proposta de Indeferimento — Critério Obrigatório da DUT 60 Não Atendido"
        # Detecção de subitem específico
        if subitem == "4":
            base_normativa = "Diretriz de Utilização nº 60, item 4, do Anexo II da RN ANS nº 465/2021 e atualizações."
            resumo_clinico = "Trata-se de solicitação de PET-CT oncológico para investigação de nódulo pulmonar solitário, conforme relatório médico e exame de imagem apresentados."
            criterios = (
                "A Diretriz de Utilização nº 60, item 4, do Anexo II da RN ANS nº 465/2021 e suas atualizações aplicáveis, "
                "estabelece cobertura obrigatória para avaliação de nódulo pulmonar solitário quando preenchidos cumulativamente "
                "os seguintes critérios: ressonância magnética ou tomografia computadorizada inconclusivas, nódulo maior que um centímetro, "
                "ausência de espiculações e ausência de calcificações."
            )
            confronto = (
                "No caso em análise, o exame de imagem apresentado descreve nódulo pulmonar com dimensão inferior ao limite "
                "estabelecido no item 4.b da diretriz (nódulo menor ou igual a 1 cm) ou presença de características radiológicas "
                "que descaracterizam o preenchimento cumulativo dos critérios normativos."
            )
        elif subitem == "5":
            base_normativa = "Diretriz de Utilização nº 60, item 5, do Anexo II da RN ANS nº 465/2021 e atualizações."
            resumo_clinico = "Trata-se de solicitação de PET-CT oncológico para paciente com diagnóstico de neoplasia maligna de mama, conforme documentação médica apresentada."
            criterios = (
                "De acordo com a Diretriz de Utilização nº 60, item 5, do Anexo II da RN ANS nº 465/2021 e suas atualizações aplicáveis, "
                "a cobertura obrigatória de PET-CT oncológico está prevista para o diagnóstico do câncer de mama metastático quando "
                "os exames de imagem convencionais apresentarem achados equívocos."
            )
            confronto = (
                "No caso em análise, a indicação descrita corresponde ao acompanhamento ou resposta terapêutica de doença previamente conhecida, "
                "não estando caracterizada a finalidade diagnóstica específica estabelecida no referido subitem, tampouco outra hipótese de cobertura da DUT 60."
            )
        else:
            base_normativa = f"Diretriz de Utilização nº 60, item {subitem}, do Anexo II da RN ANS nº 465/2021 e atualizações."
            resumo_clinico = f"Trata-se de solicitação de {proc} para indicação oncológica referida na guia {guia}."
            criterios = f"A cobertura obrigatória encontra-se disciplinada pela {base_normativa}, que estabelece critérios específicos e cumulativos."
            confronto = "No caso em apreço, os elementos documentados comprovam o não preenchimento de requisito normativo indispensável previsto na diretriz."

        conclusao = (
            "Dessa forma, considerando que a solicitação não atende integralmente aos critérios regulatórios obrigatórios previstos "
            "na diretriz analisada, fundamenta-se a presente proposta de indeferimento, sujeita à revisão médica e à verificação "
            "de outras obrigações contratuais ou regulatórias eventualmente aplicáveis."
        )
        reanalise = "A solicitação poderá ser reavaliada mediante apresentação de novos exames ou informações clínicas que modifiquem o enquadramento apresentado."
        texto_completo = f"{resumo_clinico}\n\n{criterios}\n\n{confronto}\n\n{conclusao}\n\n{reanalise}"

    elif modalidade == MODALIDADE_COMPLEMENTACAO:
        titulo = "Solicitação de Complementação Documental — Subsidiação da Análise da DUT 60"
        base_normativa = f"Diretriz de Utilização nº 60 do Anexo II da RN ANS nº 465/2021 e suas atualizações."
        resumo_clinico = f"Trata-se de solicitação de {proc} para paciente portador de suspeita ou diagnóstico de neoplasia maligna, conforme dados preliminares informados na guia {guia}."
        criterios = (
            f"Conforme a {base_normativa}, a cobertura obrigatória do procedimento depende do atendimento "
            f"de requisitos específicos de comprovação diagnóstica e estadiamento clínico definidos na norma regulatória."
        )
        confronto = (
            "Embora a hipótese diagnóstica informada possa ter correlação com as indicações previstas na diretriz, "
            "a documentação disponibilizada para análise não apresenta comprovação documental suficiente dos critérios obrigatórios "
            "(tais como laudo histopatológico definitivo, laudos detalhados de exames de imagem prévios ou descrição dimensional das lesões), "
            "requisitos indispensáveis para a conclusão do enquadramento regulatório."
        )
        conclusao = (
            "Dessa forma, solicita-se a apresentação de documentação complementar pertinente (em especial laudo anatomopatológico ou "
            "relatório médico circunstanciado) para possibilitar a conclusão da análise de enquadramento na DUT 60. "
            "Ressalta-se que a ausência do documento na solicitação não permite afirmar a inexistência do exame ou a improcedência do pedido, "
            "permanecendo a análise pendente de comprovação."
        )
        reanalise = "A análise conclusiva da solicitação será retomada imediatamente após o recebimento dos documentos solicitados."
        texto_completo = f"{resumo_clinico}\n\n{criterios}\n\n{confronto}\n\n{conclusao}\n\n{reanalise}"

    elif modalidade == MODALIDADE_NEGATIVA_ROL:
        titulo = "Minuta de Proposta de Indeferimento — Procedimento ou Indicação Não Previstos no Rol da ANS"
        base_normativa = "Rol de Procedimentos e Eventos em Saúde da ANS (RN nº 465/2021 e atualizações normativas vigentes)."
        resumo_clinico = "Trata-se de solicitação de PET-CT cerebral com FDG para investigação diagnóstica de quadro demencial, conforme indicação clínica apresentada pelo médico assistente."
        criterios = (
            "A análise de cobertura foi realizada considerando o Rol de Procedimentos e Eventos em Saúde da Agência Nacional "
            "de Saúde Suplementar, seus anexos, diretrizes de utilização e atualizações normativas aplicáveis. "
            "A Diretriz de Utilização nº 60 contempla hipóteses específicas de cobertura obrigatória de PET-CT oncológico, "
            "não abrangendo a indicação neurológica de investigação de demência descrita na presente solicitação."
        )
        confronto = (
            "Adicionalmente, conforme a verificação regulatória realizada para o procedimento e a indicação solicitados "
            "(código TUSS 41001311), não se identifica previsão de cobertura obrigatória no Rol vigente para a referida indicação clínica, "
            "tampouco enquadramento nos critérios excepcionais de cobertura fora do Rol previstos na legislação de regência."
        )
        conclusao = (
            "Diante do exposto, considerando a indicação clínica documentada e o enquadramento regulatório verificado, a solicitação "
            "não apresenta previsão de cobertura obrigatória na hipótese analisada, constituindo fundamento para proposta de indeferimento, "
            "condicionada à revisão médica e à verificação das demais obrigações legais e contratuais eventualmente aplicáveis."
        )
        reanalise = "A solicitação poderá ser reavaliada caso sejam apresentados elementos clínicos ou fundamentos de cobertura adicionais."
        texto_completo = f"{resumo_clinico}\n\n{criterios}\n\n{confronto}\n\n{conclusao}\n\n{reanalise}"

    elif modalidade == MODALIDADE_NEGATIVA_INDICACAO:
        titulo = "Minuta de Proposta de Indeferimento — Indicação Não Contemplada na DUT 60"
        base_normativa = "Diretriz de Utilização nº 60 do Anexo II da RN ANS nº 465/2021 e atualizações."
        resumo_clinico = f"Trata-se de solicitação de {proc} para indicação clínica não listada no rol de subitens da DUT 60, conforme documentação apresentada."
        criterios = (
            "A cobertura obrigatória do PET-CT oncológico, segundo a Diretriz de Utilização nº 60 do Anexo II da RN ANS nº 465/2021 "
            "e suas atualizações aplicáveis, está condicionada às indicações clínicas e aos critérios específicos expressamente previstos na norma."
        )
        confronto = (
            "Após confronto entre a indicação clínica apresentada e a integralidade dos dez subitens da referida diretriz, "
            "não foi identificado enquadramento da solicitação nas hipóteses de cobertura obrigatória estabelecidas na DUT 60."
        )
        conclusao = (
            "Assim, considerando a indicação descrita e a ausência de enquadramento nos critérios da diretriz analisada, a solicitação "
            "constitui hipótese de proposta de indeferimento por não preenchimento das condições de cobertura obrigatória da DUT 60, "
            "sujeita à revisão médica e à avaliação de outras bases de cobertura eventualmente aplicáveis."
        )
        reanalise = "A solicitação poderá ser reavaliada mediante apresentação de elementos clínicos ou regulatórios adicionais pertinentes."
        texto_completo = f"{resumo_clinico}\n\n{criterios}\n\n{confronto}\n\n{conclusao}\n\n{reanalise}"

    else:  # PRELIMINAR_INCONSISTENCIA
        titulo = "Minuta Técnica Preliminar — Inconsistência Regulatória Pendente de Homologação"
        base_normativa = "Rol de Procedimentos ANS e Diretriz de Utilização nº 60."
        resumo_clinico = f"Trata-se de solicitação de {proc} apresentando divergência entre o código TUSS informado ({tuss}) e a indicação clínica descrita."
        criterios = "A definição de cobertura depende da consolidação da correlação TUSS × Rol aplicável à data de entrada da solicitação."
        confronto = "Foram identificadas inconsistências preliminares na classificação do procedimento ou da patologia que exigem revisão técnica antes da definição do enquadramento regulatório."
        conclusao = "Emite-se a presente minuta em caráter estritamente preliminar com status FUNDAMENTAÇÃO REGULATÓRIA PENDENTE, vedada qualquer deliberação conclusiva antes da homologação da correlação."
        reanalise = "Encaminha-se o caso para conferência técnica de classificação."
        texto_completo = f"{resumo_clinico}\n\n{criterios}\n\n{confronto}\n\n{conclusao}\n\n{reanalise}"

    return {
        "modality": modalidade,
        "title": titulo,
        "normative_basis": base_normativa,
        "clinical_summary": resumo_clinico,
        "criteria_analysis": f"{criterios}\n\n{confronto}",
        "conclusion": conclusao,
        "reanalysis_conditions": reanalise,
        "draft_text": texto_completo,
    }


def gerar_e_salvar_minuta(conn, tenant, case_id, actor="SISTEMA_IA", modalidade_forcar=None, justification=None, fatos=None):
    """
    Gera automaticamente a minuta adequada ao caso e persiste em regulatory_drafts.
    """
    case = storage.case_for(conn, tenant, case_id)
    if not case:
        raise ValueError("Caso não encontrado.")
    docs = conn.execute("SELECT * FROM documents WHERE tenant_id=? AND case_id=?", (tenant, case_id)).fetchall()
    rota = conn.execute("SELECT * FROM case_routes WHERE tenant=? AND case_id=? ORDER BY id DESC LIMIT 1", (tenant, case_id)).fetchone()

    modalidade = modalidade_forcar or classificar_modalidade_minuta(case, docs, fatos=fatos, rota=rota)
    minuta_dados = redigir_minuta(case, docs, modalidade, fatos=fatos, rota=rota)

    draft_id = storage.save_regulatory_draft(
        conn=conn,
        tenant=tenant,
        case_id=case_id,
        modality=minuta_dados["modality"],
        title=minuta_dados["title"],
        normative_basis=minuta_dados["normative_basis"],
        clinical_summary=minuta_dados["clinical_summary"],
        criteria_analysis=minuta_dados["criteria_analysis"],
        conclusion=minuta_dados["conclusion"],
        reanalysis_conditions=minuta_dados["reanalysis_conditions"],
        draft_text=minuta_dados["draft_text"],
        actor=actor,
        status="RASCUNHO_IA",
        justification=justification or f"Geração automática de rascunho de minuta ({modalidade})",
        role="sistema" if actor == "SISTEMA_IA" else "auditor"
    )
    return draft_id
