"""Cálculo determinístico de datas e SLA regulatório no fuso America/Sao_Paulo."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from holidays import country_holidays

FUSO = ZoneInfo("America/Sao_Paulo")
FERIADOS_BR = country_holidays("BR")

# Prazos e naturezas regulatórias distintas
TIPO_PRAZO_RESPOSTA_CONCLUSIVA = "Resposta conclusiva ao beneficiário (RN 623/2024)"
TIPO_PRAZO_GARANTIA_ATENDIMENTO = "Garantia de atendimento (RN 566/2022)"

# Propostas normativas de referência para Procedimentos de Alta Complexidade (PAC / PET-CT)
PRAZO_RESPOSTA_PAC_DIAS_UTEIS = 10
PRAZO_GARANTIA_PAC_DIAS_UTEIS = 21

# Estados determinísticos do SLA
STATUS_PROTOCOLO_AUSENTE = "PROTOCOLO_AUSENTE"
STATUS_VENCIDO = "VENCIDO"
STATUS_ALERTA = "ALERTA"
STATUS_NO_PRAZO = "NO_PRAZO"
STATUS_CONCLUIDO_NO_PRAZO = "CONCLUIDO_NO_PRAZO"
STATUS_CONCLUIDO_FORA_PRAZO = "CONCLUIDO_FORA_PRAZO"


def obter_calendario_feriados(ano_ou_anos=None, feriados_adicionais=None):
    """Retorna calendário de feriados com suporte a feriados adicionais configuráveis."""
    base = country_holidays("BR", years=ano_ou_anos) if ano_ou_anos else country_holidays("BR")
    if feriados_adicionais:
        copia = country_holidays("BR")
        copia.update(base)
        copia.update(feriados_adicionais)
        return copia
    return base


def _data_local(valor):
    """Converte valor de data (string ISO, date ou datetime) para datetime com fuso America/Sao_Paulo ou date."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        if valor.tzinfo is None:
            valor = valor.replace(tzinfo=timezone.utc)
        return valor.astimezone(FUSO)
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        v = valor.strip()
        if not v:
            return None
        try:
            if len(v) == 10:
                return date.fromisoformat(v)
            instante = datetime.fromisoformat(v.replace("Z", "+00:00"))
            if instante.tzinfo is None:
                instante = instante.replace(tzinfo=timezone.utc)
            return instante.astimezone(FUSO)
        except (TypeError, ValueError, OverflowError):
            return None
    return None


def eh_dia_util(dia, feriados=None):
    """Verifica se uma data (date ou datetime) é dia útil (segunda a sexta e não feriado)."""
    if isinstance(dia, datetime):
        dia = dia.astimezone(FUSO).date()
    elif not isinstance(dia, date):
        dia = _data_local(dia)
        if isinstance(dia, datetime):
            dia = dia.date()
    if dia is None:
        return False
    cal = feriados if feriados is not None else FERIADOS_BR
    return dia.weekday() < 5 and dia not in cal


def proximo_dia_util(dia, feriados=None):
    """Retorna o próximo dia útil a partir do dia informado (avança se for não útil)."""
    if isinstance(dia, datetime):
        dia = dia.astimezone(FUSO).date()
    elif not isinstance(dia, date):
        dia = _data_local(dia)
        if isinstance(dia, datetime):
            dia = dia.date()
    if dia is None:
        return None
    cal = feriados if feriados is not None else FERIADOS_BR
    while not eh_dia_util(dia, cal):
        dia += timedelta(days=1)
    return dia


def adicionar_dias_uteis(inicio, dias_uteis, feriados=None):
    """
    Adiciona N dias úteis determinísticos segundo a regra administrativa padrão:
    - Se recebido em dia útil, o dia inicial não é contado; a contagem inicia no próximo dia útil.
    - Se recebido em dia não útil (fim de semana ou feriado), considera-se recebido no 1º dia útil subsequente,
      iniciando-se a contagem de prazo no dia útil seguinte a este.
    - O dia do vencimento é incluído na contagem.
    """
    d = _data_local(inicio)
    if isinstance(d, datetime):
        d = d.date()
    if d is None or dias_uteis < 0:
        return None

    cal = feriados if feriados is not None else FERIADOS_BR
    if not eh_dia_util(d, cal):
        d = proximo_dia_util(d + timedelta(days=1), cal)

    adicionados = 0
    atual = d
    while adicionados < dias_uteis:
        atual += timedelta(days=1)
        if eh_dia_util(atual, cal):
            adicionados += 1
    return atual


def contar_dias_uteis(inicio, fim, feriados=None):
    """
    Conta os dias úteis decorridos entre 'inicio' e 'fim'.
    Exclui o dia inicial e inclui o dia final se útil.
    Se fim < inicio, retorna valor negativo proporcional.
    """
    d_ini = _data_local(inicio)
    d_fim = _data_local(fim)
    if isinstance(d_ini, datetime):
        d_ini = d_ini.date()
    if isinstance(d_fim, datetime):
        d_fim = d_fim.date()
    if d_ini is None or d_fim is None:
        return None
    if d_ini == d_fim:
        return 0
    cal = feriados if feriados is not None else FERIADOS_BR
    if d_ini < d_fim:
        return cal.get_working_days_count(d_ini + timedelta(days=1), d_fim)
    else:
        return -cal.get_working_days_count(d_fim + timedelta(days=1), d_ini)


def calcular_sla(
    data_protocolo,
    data_referencia=None,
    data_encerramento=None,
    prazo_dias_uteis=PRAZO_RESPOSTA_PAC_DIAS_UTEIS,
    tipo_prazo="resposta_conclusiva",
    feriados=None,
    alerta_dias_uteis=2,
):
    """
    Cálculo determinístico e puro do SLA. Não altera registros em banco.
    Diferencia 'resposta_conclusiva' de 'garantia_atendimento'.
    Trata ausência de data_protocolo como STATUS_PROTOCOLO_AUSENTE.
    """
    tipo_desc = (
        TIPO_PRAZO_RESPOSTA_CONCLUSIVA
        if tipo_prazo == "resposta_conclusiva"
        else TIPO_PRAZO_GARANTIA_ATENDIMENTO
    )
    if not data_protocolo:
        return {
            "status": STATUS_PROTOCOLO_AUSENTE,
            "rotulo_status": "Protocolo ausente",
            "detalhe": "Data de protocolo original não informada; impossível aferir SLA regulatório.",
            "data_protocolo": None,
            "data_limite": None,
            "dias_uteis_decorridos": None,
            "dias_uteis_restantes": None,
            "tipo_prazo": tipo_desc,
            "prazo_dias_uteis": prazo_dias_uteis,
            "em_atraso": False,
        }

    dt_proto = _data_local(data_protocolo)
    if dt_proto is None:
        return {
            "status": STATUS_PROTOCOLO_AUSENTE,
            "rotulo_status": "Protocolo inválido",
            "detalhe": "Formato de data de protocolo não reconhecido.",
            "data_protocolo": None,
            "data_limite": None,
            "dias_uteis_decorridos": None,
            "dias_uteis_restantes": None,
            "tipo_prazo": tipo_desc,
            "prazo_dias_uteis": prazo_dias_uteis,
            "em_atraso": False,
        }

    proto_date = dt_proto.date() if isinstance(dt_proto, datetime) else dt_proto
    cal = feriados if feriados is not None else FERIADOS_BR

    data_limite = adicionar_dias_uteis(proto_date, prazo_dias_uteis, cal)

    if data_encerramento:
        dt_enc = _data_local(data_encerramento)
        ref_date = dt_enc.date() if isinstance(dt_enc, datetime) else dt_enc
        encerrado = True
    else:
        dt_ref = _data_local(data_referencia) if data_referencia else datetime.now(FUSO)
        ref_date = dt_ref.date() if isinstance(dt_ref, datetime) else dt_ref
        encerrado = False

    decorridos = contar_dias_uteis(proto_date, ref_date, cal)
    restantes = contar_dias_uteis(ref_date, data_limite, cal)

    if encerrado:
        no_prazo = ref_date <= data_limite
        status = STATUS_CONCLUIDO_NO_PRAZO if no_prazo else STATUS_CONCLUIDO_FORA_PRAZO
        rotulo = "Concluído no prazo" if no_prazo else "Concluído fora do prazo"
    else:
        if restantes < 0 or ref_date > data_limite:
            status = STATUS_VENCIDO
            rotulo = "Prazo regulatório vencido"
        elif restantes <= alerta_dias_uteis:
            status = STATUS_ALERTA
            rotulo = f"Alerta de vencimento ({restantes} {'dia útil restante' if restantes == 1 else 'dias úteis restantes'})"
        else:
            status = STATUS_NO_PRAZO
            rotulo = f"No prazo ({restantes} dias úteis restantes)"

    return {
        "status": status,
        "rotulo_status": rotulo,
        "detalhe": f"{tipo_desc} · Prazo de {prazo_dias_uteis} dias úteis.",
        "data_protocolo": proto_date,
        "data_limite": data_limite,
        "dias_uteis_decorridos": max(0, decorridos) if decorridos is not None else 0,
        "dias_uteis_restantes": restantes,
        "tipo_prazo": tipo_desc,
        "prazo_dias_uteis": prazo_dias_uteis,
        "em_atraso": restantes < 0,
    }


def data_br(valor, apenas_data=False):
    """Formata valor de data no padrão brasileiro DD/MM/AAAA ou DD/MM/AAAA HH:MM."""
    local = _data_local(valor)
    if local is None:
        return "Não informado"
    formato = "%d/%m/%Y %H:%M" if isinstance(local, datetime) and not apenas_data else "%d/%m/%Y"
    return local.strftime(formato)


def data_guia(valor):
    """Formata valor de data da guia no padrão DD/MM/AAAA."""
    return data_br(valor, apenas_data=True)


def calcular_prazo_complementacao_48h(encaminhado_em, horas_prazo=48, data_referencia=None):
    """
    Calcula prazo estimativo operacional de 48 horas (REQ-11.1 e REQ-11.2).
    Inicia exclusivamente quando o médico registra encaminhamento ao operacional.
    Não suspende/reinicia o SLA da ANS nem gera negativa automática.
    Retorna dicionário com status ('NO_PRAZO', 'VENCIDO'), data_limite, horas_restantes e vencido (bool).
    """
    if not encaminhado_em:
        return None
    inicio = _data_local(encaminhado_em)
    if not inicio:
        return None
    if isinstance(inicio, date) and not isinstance(inicio, datetime):
        inicio = datetime.combine(inicio, datetime.min.time(), FUSO)

    limite = inicio + timedelta(hours=horas_prazo)
    ref = _data_local(data_referencia) if data_referencia else datetime.now(FUSO)
    if isinstance(ref, date) and not isinstance(ref, datetime):
        ref = datetime.combine(ref, datetime.min.time(), FUSO)

    diff_segundos = (limite - ref).total_seconds()
    horas_restantes = round(diff_segundos / 3600.0, 1)
    vencido = diff_segundos <= 0

    return {
        "inicio": inicio,
        "limite": limite,
        "horas_restantes": max(0.0, horas_restantes) if not vencido else 0.0,
        "vencido": vencido,
        "rotulo": "Prazo de complementação vencido" if vencido else f"{horas_restantes:.0f}h restantes de complementação",
    }


def sla_guia(entrada, fim):
    """Dias úteis decorridos após a entrada, mantido para compatibilidade."""
    inicio = _data_local(entrada)
    if isinstance(inicio, datetime):
        inicio = inicio.date()
    if isinstance(fim, str):
        fim = _data_local(fim)
    if isinstance(fim, datetime):
        fim = fim.date()
    if inicio is None or fim is None or fim < inicio:
        return "Não informado"
    dias = FERIADOS_BR.get_working_days_count(inicio + timedelta(days=1), fim) if inicio < fim else 0
    return "1 dia útil" if dias == 1 else f"{dias} dias úteis"

