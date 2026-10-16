"""Funcoes compartilhadas pelas 4 Lambdas: resposta HTTP, validacao e acesso ao banco."""
import base64
import json
import logging
import os
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

PRIORIDADES = ("baixa", "media", "alta", "critica")
STATUS_VALIDOS = ("aberto", "em_andamento", "resolvido", "fechado")

_dynamodb = None


class ErroValidacao(Exception):
    """Erro de entrada do cliente -> vira HTTP 400."""


def tabela():
    """Cria o recurso DynamoDB uma vez e reaproveita nas proximas chamadas (a Lambda 'esquenta')."""
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb.Table(os.environ["TABELA_CHAMADOS"])


def resposta(status_code, corpo):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": json.dumps(corpo, ensure_ascii=False),
    }


def agora_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ler_corpo(event):
    bruto = event.get("body")
    if not bruto:
        raise ErroValidacao("Corpo da requisicao ausente.")
    if event.get("isBase64Encoded"):
        bruto = base64.b64decode(bruto).decode("utf-8")
    try:
        dados = json.loads(bruto)
    except json.JSONDecodeError:
        raise ErroValidacao("Corpo da requisicao nao e um JSON valido.")
    if not isinstance(dados, dict):
        raise ErroValidacao("O corpo deve ser um objeto JSON.")
    return dados


def texto_obrigatorio(dados, campo, maximo):
    valor = dados.get(campo)
    if not isinstance(valor, str) or not valor.strip():
        raise ErroValidacao(f"O campo '{campo}' e obrigatorio e deve ser texto.")
    valor = valor.strip()
    if len(valor) > maximo:
        raise ErroValidacao(f"O campo '{campo}' aceita no maximo {maximo} caracteres.")
    return valor


def validar_novo_chamado(dados):
    prioridade = dados.get("prioridade", "media")
    if prioridade not in PRIORIDADES:
        raise ErroValidacao(f"Prioridade invalida. Use: {', '.join(PRIORIDADES)}.")
    return {
        "titulo": texto_obrigatorio(dados, "titulo", 100),
        "descricao": texto_obrigatorio(dados, "descricao", 1000),
        "setor": texto_obrigatorio(dados, "setor", 60),
        "solicitante": texto_obrigatorio(dados, "solicitante", 60),
        "prioridade": prioridade,
    }


def publicar_alerta(chamado):
    """Avisa por SNS quando o chamado e critico. Falha no aviso NAO derruba a criacao do chamado."""
    topico = os.environ.get("TOPICO_ALERTAS")
    if not topico:
        return
    try:
        boto3.client("sns").publish(
            TopicArn=topico,
            Subject=f"[CRITICO] {chamado['titulo']}"[:100],
            Message=(
                f"Novo chamado critico\n\nID: {chamado['id']}\nSetor: {chamado['setor']}\n"
                f"Solicitante: {chamado['solicitante']}\n\n{chamado['descricao']}"
            ),
        )
    except Exception:
        logger.exception("Falha ao publicar alerta no SNS (chamado %s)", chamado["id"])
