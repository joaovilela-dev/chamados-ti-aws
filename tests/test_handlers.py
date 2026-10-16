"""Testes locais com moto: simula DynamoDB e SNS em memoria, sem tocar na AWS real."""
import json
import os

import boto3
import pytest
from moto import mock_aws

import common
import atualizar_status
import buscar_chamado
import criar_chamado
import listar_chamados

REGIAO = "us-east-1"


@pytest.fixture(autouse=True)
def ambiente():
    os.environ["AWS_ACCESS_KEY_ID"] = "teste"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "teste"
    os.environ["AWS_DEFAULT_REGION"] = REGIAO
    os.environ["TABELA_CHAMADOS"] = "chamados-teste"
    os.environ.pop("TOPICO_ALERTAS", None)
    common._dynamodb = None  # forca recriar o recurso dentro do mock
    with mock_aws():
        boto3.client("dynamodb").create_table(
            TableName="chamados-teste",
            AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield


def evento(corpo=None, caminho=None, query=None):
    e = {}
    if corpo is not None:
        e["body"] = json.dumps(corpo) if not isinstance(corpo, str) else corpo
    if caminho:
        e["pathParameters"] = caminho
    if query:
        e["queryStringParameters"] = query
    return e


def novo(**extra):
    base = {"titulo": "Impressora sem toner", "descricao": "Setor financeiro sem impressao",
            "setor": "Financeiro", "solicitante": "Maria Teste", "prioridade": "baixa"}
    base.update(extra)
    return base


def criar(**extra):
    r = criar_chamado.handler(evento(novo(**extra)), None)
    assert r["statusCode"] == 201
    return json.loads(r["body"])


def test_criar_chamado_valido():
    chamado = criar()
    assert chamado["status"] == "aberto"
    assert chamado["prioridade"] == "baixa"
    salvo = common.tabela().get_item(Key={"id": chamado["id"]})["Item"]
    assert salvo["titulo"] == "Impressora sem toner"


def test_criar_aplica_prioridade_padrao():
    corpo = novo()
    del corpo["prioridade"]
    r = criar_chamado.handler(evento(corpo), None)
    assert json.loads(r["body"])["prioridade"] == "media"


@pytest.mark.parametrize("corpo", [
    novo(titulo=""),
    novo(prioridade="urgentissima"),
    novo(titulo="x" * 101),
    "isso nao e json",
    "[1, 2, 3]",
])
def test_criar_rejeita_entrada_invalida(corpo):
    r = criar_chamado.handler(evento(corpo), None)
    assert r["statusCode"] == 400
    assert "erro" in json.loads(r["body"])


def test_criar_sem_corpo():
    assert criar_chamado.handler({}, None)["statusCode"] == 400


def test_buscar_existente_e_inexistente():
    chamado = criar()
    ok = buscar_chamado.handler(evento(caminho={"id": chamado["id"]}), None)
    assert ok["statusCode"] == 200
    assert json.loads(ok["body"])["id"] == chamado["id"]
    nao = buscar_chamado.handler(evento(caminho={"id": "nao-existe"}), None)
    assert nao["statusCode"] == 404


def test_atualizar_status():
    chamado = criar()
    r = atualizar_status.handler(
        evento({"status": "em_andamento"}, caminho={"id": chamado["id"]}), None)
    assert r["statusCode"] == 200
    assert json.loads(r["body"])["status"] == "em_andamento"


def test_atualizar_status_invalido_e_inexistente():
    chamado = criar()
    invalido = atualizar_status.handler(
        evento({"status": "voando"}, caminho={"id": chamado["id"]}), None)
    assert invalido["statusCode"] == 400
    inexistente = atualizar_status.handler(
        evento({"status": "fechado"}, caminho={"id": "nao-existe"}), None)
    assert inexistente["statusCode"] == 404
    # garante que NAO criou um item fantasma
    assert "Item" not in common.tabela().get_item(Key={"id": "nao-existe"})


def test_listar_com_filtros():
    a = criar(prioridade="alta")
    criar(prioridade="baixa")
    atualizar_status.handler(evento({"status": "resolvido"}, caminho={"id": a["id"]}), None)

    todos = json.loads(listar_chamados.handler(evento(), None)["body"])
    assert todos["total"] == 2

    so_resolvidos = json.loads(
        listar_chamados.handler(evento(query={"status": "resolvido"}), None)["body"])
    assert so_resolvidos["total"] == 1 and so_resolvidos["chamados"][0]["id"] == a["id"]

    combinado = json.loads(listar_chamados.handler(
        evento(query={"status": "aberto", "prioridade": "alta"}), None)["body"])
    assert combinado["total"] == 0


def test_listar_filtro_invalido():
    r = listar_chamados.handler(evento(query={"status": "xyz"}), None)
    assert r["statusCode"] == 400


def test_chamado_critico_dispara_alerta_sns():
    sns, sqs = boto3.client("sns"), boto3.client("sqs")
    topico = sns.create_topic(Name="alertas")["TopicArn"]
    fila_url = sqs.create_queue(QueueName="fila-teste")["QueueUrl"]
    fila_arn = sqs.get_queue_attributes(QueueUrl=fila_url, AttributeNames=["QueueArn"])[
        "Attributes"]["QueueArn"]
    sns.subscribe(TopicArn=topico, Protocol="sqs", Endpoint=fila_arn)
    os.environ["TOPICO_ALERTAS"] = topico

    chamado = criar(prioridade="critica", titulo="Servidor fora do ar")

    mensagens = sqs.receive_message(QueueUrl=fila_url, MaxNumberOfMessages=10).get("Messages", [])
    assert len(mensagens) == 1
    assert chamado["id"] in mensagens[0]["Body"]


def test_chamado_nao_critico_nao_dispara_alerta():
    sns, sqs = boto3.client("sns"), boto3.client("sqs")
    topico = sns.create_topic(Name="alertas")["TopicArn"]
    fila_url = sqs.create_queue(QueueName="fila-teste")["QueueUrl"]
    fila_arn = sqs.get_queue_attributes(QueueUrl=fila_url, AttributeNames=["QueueArn"])[
        "Attributes"]["QueueArn"]
    sns.subscribe(TopicArn=topico, Protocol="sqs", Endpoint=fila_arn)
    os.environ["TOPICO_ALERTAS"] = topico

    criar(prioridade="alta")
    assert "Messages" not in sqs.receive_message(QueueUrl=fila_url)


def test_falha_no_sns_nao_derruba_criacao():
    os.environ["TOPICO_ALERTAS"] = "arn:aws:sns:us-east-1:123456789012:nao-existe"
    chamado = criar(prioridade="critica")  # deve continuar retornando 201
    assert chamado["status"] == "aberto"
