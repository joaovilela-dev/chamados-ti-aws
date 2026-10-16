"""POST /chamados - abre um chamado."""
import logging
import uuid

from common import (ErroValidacao, agora_iso, ler_corpo, publicar_alerta,
                    resposta, tabela, validar_novo_chamado)

logger = logging.getLogger()


def handler(event, context):
    try:
        dados = validar_novo_chamado(ler_corpo(event))
    except ErroValidacao as erro:
        return resposta(400, {"erro": str(erro)})

    agora = agora_iso()
    chamado = {
        "id": str(uuid.uuid4()),
        **dados,
        "status": "aberto",
        "criado_em": agora,
        "atualizado_em": agora,
    }
    tabela().put_item(Item=chamado)
    logger.info("Chamado criado id=%s prioridade=%s", chamado["id"], chamado["prioridade"])

    if chamado["prioridade"] == "critica":
        publicar_alerta(chamado)

    return resposta(201, chamado)
