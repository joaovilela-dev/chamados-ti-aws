"""GET /chamados?status=aberto&prioridade=alta - lista chamados com filtros opcionais."""
import logging

from boto3.dynamodb.conditions import Attr

from common import PRIORIDADES, STATUS_VALIDOS, resposta, tabela

logger = logging.getLogger()


def handler(event, context):
    params = event.get("queryStringParameters") or {}
    status = params.get("status")
    prioridade = params.get("prioridade")

    if status and status not in STATUS_VALIDOS:
        return resposta(400, {"erro": f"Status invalido. Use: {', '.join(STATUS_VALIDOS)}."})
    if prioridade and prioridade not in PRIORIDADES:
        return resposta(400, {"erro": f"Prioridade invalida. Use: {', '.join(PRIORIDADES)}."})

    filtro = None
    if status:
        filtro = Attr("status").eq(status)
    if prioridade:
        condicao = Attr("prioridade").eq(prioridade)
        filtro = condicao if filtro is None else filtro & condicao

    # Scan le a tabela inteira e filtra depois. Aceitavel para poucos itens (estudo).
    # Em escala, o correto seria um indice secundario (GSI) por status. Veja o README.
    argumentos = {"FilterExpression": filtro} if filtro is not None else {}
    itens = []
    while True:
        resultado = tabela().scan(**argumentos)
        itens.extend(resultado.get("Items", []))
        if "LastEvaluatedKey" not in resultado:
            break
        argumentos["ExclusiveStartKey"] = resultado["LastEvaluatedKey"]

    itens.sort(key=lambda c: c["criado_em"], reverse=True)
    logger.info("Listagem: %d chamado(s) status=%s prioridade=%s", len(itens), status, prioridade)
    return resposta(200, {"total": len(itens), "chamados": itens})
