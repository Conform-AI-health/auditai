"""Conectores demonstrativos substituíveis. Nenhuma chamada a SIGO, MV ou Tasy."""

from copy import deepcopy


class SyncFailure(Exception):
    code = "FALHA_SINTETICA_ORIGEM_INDISPONIVEL"


EXAMPLES = {
    "sigo": {
        "id": "numero_guia", "procedure": "procedimento", "question": "pergunta_clinica",
        "updated": "atualizado_em", "documents": "anexos", "doc_id": "id_anexo",
    },
    "mv": {
        "id": "id_solicitacao", "procedure": "nome_exame", "question": "questao_clinica",
        "updated": "data_modificacao", "documents": "arquivos", "doc_id": "referencia_arquivo",
    },
    "tasy": {
        "id": "chave_pedido", "procedure": "procedimento_descricao", "question": "indicacao_registrada",
        "updated": "ultima_atualizacao", "documents": "documentos", "doc_id": "chave_documento",
    },
}


def demo_raw(system, tenant_id):
    """Gera uma guia e um documento exclusivamente fictícios por origem e operadora."""
    if system not in EXAMPLES:
        raise ValueError("Conector não reconhecido")
    m = EXAMPLES[system]
    external = {"sigo": "GUIA-001", "mv": "SOL-042", "tasy": "PED-073"}[system]
    report = system == "tasy"
    raw = {
        m["id"]: external,
        m["procedure"]: "PET-CT oncológico (fictício)",
        m["question"]: system != "mv",
        m["updated"]: "2026-11-20T13:00:00+00:00",
        "area": "Oncologia",
        "resumo_sintetico": f"Exemplo {system.upper()} da operadora {tenant_id}; sem dado de paciente.",
        "codigo_tuss": "40708128", "codigos_tuss_associados": [],
        m["documents"]: [{
            m["doc_id"]: external + "-ANEXO-01", "tipo": "relatorio" if report else "guia",
            "nome": "Relatório sintético" if report else "Guia sintética",
            "atualizado_em": "2026-11-20T13:00:00+00:00",
        }],
    }
    return [raw]


def normalize(system, tenant_id, raw):
    """Traduz nomes de campos mantendo os IDs e a data de origem intactos."""
    m = EXAMPLES[system]
    return {
        "tenant_id": tenant_id,
        "source_system": system.upper(),
        "guide_received_at": raw.get("guide_received_at"),
        "beneficiary_code": raw.get("beneficiary_code"),
        "external_id": str(raw[m["id"]]),
        "procedure": str(raw[m["procedure"]]),
        "tuss_code": str(raw.get("codigo_tuss") or ""),
        "associated_tuss_codes": [str(v) for v in raw.get("codigos_tuss_associados",[])],
        "clinical_question": bool(raw[m["question"]]),
        "source_updated_at": str(raw[m["updated"]]),
        "area": str(raw["area"]),
        "narrative": str(raw["resumo_sintetico"]),
        "documents": [{
            "external_id": str(doc[m["doc_id"]]),
            "kind": str(doc["tipo"]), "name": str(doc["nome"]),
            "source_updated_at": str(doc["atualizado_em"]),
            "content_blob": doc.get("conteudo_blob") or doc.get("content_blob"),
            "content_text": doc.get("conteudo_texto") or doc.get("content_text"),
            "mime_type": doc.get("mime_type"),
            "local_path": doc.get("local_path"),
            "source_sha256": doc.get("source_sha256"),
            "extraction_method": doc.get("extraction_method"),
            "verification_status": doc.get("verification_status", "NAO_CONFERIDO"),
        } for doc in raw[m["documents"]]],
    }


def read_demo(system, tenant_id, fail=False):
    if fail:
        raise SyncFailure("Falha de sincronização simulada. Tente novamente.")
    if system.lower() == "sigo":
        from backend import sigo_simulado
        return sigo_simulado.gerar_lote_sigo_sintetico(tenant_id)
    return [normalize(system, tenant_id, deepcopy(raw)) for raw in demo_raw(system, tenant_id)]
