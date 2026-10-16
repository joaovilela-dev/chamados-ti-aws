"""PATCH /chamados/{id}/status - muda o status de um chamado."""
import logging

from common import (STATUS_VALIDOS, ErroValidacao, agora_iso, ler_corpo,
                    resposta, tabela)

logger = logging.getLogger()


def handler(event, context):
    chamado_id = (event.get("pathParameters") or {}).get("id")
    if not chamado_id:
        return resposta(400, {"erro": "ID ausente."})

    try:
        novo_status = ler_corpo(event).get("status")
    except ErroValidacao as erro:
        return resposta(400, {"erro": str(erro)})
    if novo_status not in STATUS_VALIDOS:
        return resposta(400, {"erro": f"Status invalido. Use: {', '.join(STATUS_VALIDOS)}."})

    try:
        resultado = tabela().update_item(
            Key={"id": chamado_id},
            # 'status' e palavra reservada no DynamoDB, por isso o apelido #s
            UpdateExpression="SET #s = :status, atualizado_em = :agora",
            ConditionExpression="attribute_exists(id)",  # nao cria item novo se o id nao existir
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":status": novo_status, ":agora": agora_iso()},
            ReturnValues="ALL_NEW",
        )
    except tabela().meta.client.exceptions.ConditionalCheckFailedException:
        return resposta(404, {"erro": "Chamado nao encontrado."})

    logger.info("Status atualizado id=%s novo_status=%s", chamado_id, novo_status)
    return resposta(200, resultado["Attributes"])
