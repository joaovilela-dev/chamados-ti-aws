"""GET /chamados/{id} - detalhe de um chamado."""
from common import resposta, tabela


def handler(event, context):
    chamado_id = (event.get("pathParameters") or {}).get("id")
    if not chamado_id:
        return resposta(400, {"erro": "ID ausente."})

    item = tabela().get_item(Key={"id": chamado_id}).get("Item")
    if item is None:
        return resposta(404, {"erro": "Chamado nao encontrado."})
    return resposta(200, item)
