"""Motor didático puro. Não interpreta a DUT nem decide cobertura."""

from copy import deepcopy


DEFAULT_CHECKLIST = {
    "title": "Conferência documental para ensaio PET-CT",
    "require_question": True,
    "require_report": False,
    "notice": "Checklist sintético; não substitui a leitura da DUT 60 vigente.",
}

DEFAULT_REFERENCE = {
    "title": "DUT 60 — consulta humana à fonte oficial",
    "source_url": "https://www.gov.br/ans/pt-br/acesso-a-informacao/participacao-da-sociedade/atualizacao-do-rol-de-procedimentos",
    "notice": "Referência de consulta. O simulador não conclui cobertura pela DUT.",
}


def analyze(case, documents, checklist, reference):
    """Recebe cópias dos dados confirmados; devolve uma sugestão para revisão."""
    criteria = []
    missing = []
    question = bool(case["clinical_question"])
    report = any(doc["kind"] == "relatorio" for doc in documents)
    if checklist["require_question"]:
        criteria.append({"item": "Pergunta clínica registrada", "state": "presente" if question else "não documentado"})
        if not question:
            missing.append("Pergunta clínica a esclarecer com o solicitante.")
    if checklist["require_report"]:
        criteria.append({"item": "Relatório de referência associado", "state": "presente" if report else "não documentado"})
        if not report:
            missing.append("Relatório de referência não consta nos documentos importados.")
    return {
        "procedure": case["procedure"],
        "scope": "Simulação documental PET-CT; pertinência clínica e cobertura dependem de revisão médica da DUT vigente.",
        "criteria": criteria,
        "missing": missing,
        "suggestion": "Solicitar esclarecimento documental para revisão médica." if missing else "Encaminhar à revisão médica de pertinência e DUT.",
        "reference_title": reference["title"],
        "reference_url": reference["source_url"],
        "review_required": True,
    }


def snapshot(value):
    return deepcopy(value)
