# Sistema de Chamados de TI na AWS (projeto de estudo)

API serverless para abrir e acompanhar chamados de suporte de TI, feita para estudar os serviços
básicos da AWS na prática. **Todos os dados são fictícios**: nunca use dados reais de empresa ou
paciente neste projeto.

## Arquitetura

```
 Cliente (curl / Postman)
          |
          v
 API Gateway (HTTP API, com limite de requisições)
          |
   +------+-------------+----------------+------------------+
   v                    v                v                  v
 criar_chamado   listar_chamados   buscar_chamado   atualizar_status      (4 funções Lambda, Python 3.12)
   |   \                 \               |                 |
   |    \_ SNS (e-mail   +---------------+-----------------+
   |       se CRÍTICO)                   v
   +------------------------------> DynamoDB (tabela "chamados")

 Logs de todas as funções -> CloudWatch (automático)
 Permissões -> IAM (uma role por função, só com o necessário)
 Tudo descrito em template.yaml (AWS SAM) -> sobe e apaga com um comando
```

## Rotas

| Método | Rota                      | O que faz                                        |
|--------|---------------------------|--------------------------------------------------|
| POST   | `/chamados`               | Abre um chamado                                  |
| GET    | `/chamados`               | Lista (filtros opcionais `?status=` `?prioridade=`) |
| GET    | `/chamados/{id}`          | Detalhe de um chamado                            |
| PATCH  | `/chamados/{id}/status`   | Muda o status                                    |

Prioridades: `baixa`, `media` (padrão), `alta`, `critica`.
Status: `aberto` (inicial), `em_andamento`, `resolvido`, `fechado`.

Exemplos (troque `$API` pela URL exibida no deploy):

```bash
curl -X POST "$API/chamados" -H "Content-Type: application/json" -d '{
  "titulo": "Impressora sem toner",
  "descricao": "Setor financeiro sem impressão",
  "setor": "Financeiro",
  "solicitante": "Maria Teste",
  "prioridade": "alta"
}'

curl "$API/chamados?status=aberto&prioridade=alta"
curl "$API/chamados/<id>"
curl -X PATCH "$API/chamados/<id>/status" -H "Content-Type: application/json" -d '{"status":"em_andamento"}'
```

No Windows (PowerShell), prefira o Postman ou o `Invoke-RestMethod`, pois as aspas do curl funcionam diferente.

## Testar localmente (sem AWS)

Os testes usam o `moto`, que simula DynamoDB, SNS e SQS em memória. Nada é criado na AWS.

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pytest -q
```

## Deploy na AWS, passo a passo

**Pré-requisitos:** conta AWS, [AWS CLI v2](https://docs.aws.amazon.com/cli/), [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/) e Python 3.12 (ou Docker, usando `sam build --use-container`).

1. **Crie a conta escolhendo o plano Free** e, antes de qualquer coisa, configure um alerta de
   orçamento (Billing and Cost Management → Budgets) com um valor baixo, como US$ 1 a 5.
2. **Não use a conta raiz.** Crie um usuário IAM (ou use o IAM Identity Center) com MFA e configure
   o CLI com `aws configure`. O SAM precisa de permissões amplas (CloudFormation, IAM, Lambda, API
   Gateway, DynamoDB, SNS, S3). Para estudo, um usuário dedicado costuma receber `AdministratorAccess`,
   o que é prático mas **amplo demais para uso profissional**; esteja pronto para explicar isso.
3. Compile e faça o deploy:
   ```bash
   sam build
   sam deploy --guided
   ```
   Respostas sugeridas: nome da stack `chamados-ti`; região de sua escolha; `EmailAlertas` com o seu
   e-mail (ou vazio); aceitar a criação de roles IAM; salvar a configuração em `samconfig.toml`.
   O SAM avisará que as rotas não têm autenticação: para este estudo responda `y`.
4. Ao final, o terminal mostra `ApiUrl`. Se informou e-mail, **confirme a assinatura** no link que o SNS enviar.
5. Teste as rotas com os exemplos acima e abra um chamado `critica` para receber o alerta por e-mail.
6. Veja os logs: `sam logs -n CriarChamadoFunction --stack-name chamados-ti --tail` ou pelo console (CloudWatch).
7. **Tire prints** do console (stack, tabela com itens, logs) e da API respondendo: serão sua prova na dinâmica.
8. **Quando terminar de usar, apague tudo:** `sam delete --stack-name chamados-ti`

## Custos

A conta no plano Free só gasta créditos e fecha ao fim deles ou em 6 meses, sem cobrar o cartão.
Este projeto usa serviços de custo muito baixo em uso de estudo (Lambda, API Gateway, DynamoDB sob demanda,
SNS e CloudWatch). Mesmo assim: configure o alerta de orçamento, não faça upgrade para o plano Paid
e apague a stack quando não precisar mais. Confira os preços atuais na página de cada serviço.

## Decisões e trade-offs (para explicar na entrevista)

- **Serverless (Lambda):** não há servidor para gerenciar e o custo é por uso. Combina com um
  sistema de chamados, que tem tráfego irregular.
- **DynamoDB em vez de banco relacional:** o acesso principal é por `id`, e não há joins. Em troca,
  consultas flexíveis são mais difíceis. A listagem aqui usa `Scan` com filtro, aceitável com poucos itens.
  Em escala eu criaria um índice secundário (GSI) por `status`.
- **Uma função por rota, cada uma com sua permissão:** é o princípio do menor privilégio. A função
  de leitura não consegue escrever no banco.
- **SAM (infraestrutura como código):** o ambiente é reproduzível, versionado no Git e removível com um comando.
- **Sem dependências externas no Lambda:** só `boto3`, que já vem no ambiente, então não há pacote para
  empacotar. A validação é manual e simples; num projeto maior eu usaria o Pydantic.
- **Falha no SNS não derruba o chamado:** o alerta é secundário; salvar o chamado é o que importa.
- **Limite de requisições no API Gateway:** a URL é pública, então limitei a taxa para reduzir abuso.

## Limitações conhecidas e próximos passos

- **Sem autenticação:** qualquer pessoa com a URL acessa a API. Em produção eu usaria um authorizer
  JWT (por exemplo, Cognito). Por isso este projeto deve ficar no ar só enquanto você o estuda.
- `Scan` não escala (veja acima). Falta paginação na resposta da API.
- Sem pipeline de deploy automático (próximo passo: GitHub Actions).
- Sem alarmes no CloudWatch (próximo passo: alarme de erros nas funções).
- Sem frontend (opcional: página simples em S3).
- Os testes cobrem a lógica com serviços simulados; não há teste de integração contra a AWS real.

## O que dizer (e o que não dizer) depois de concluir

Pode dizer, se você fez o deploy e entende cada parte: *"Construí e publiquei uma API serverless na AWS
(API Gateway, Lambda, DynamoDB, SNS, IAM e CloudWatch) usando AWS SAM."*

Evite dizer: "tenho experiência com AWS em produção", "configurei CI/CD" ou "usei Cognito" se isso não for verdade.
A honestidade protege você: quem entrevista costuma perguntar um nível abaixo do que o candidato afirma.

## Estrutura

```
template.yaml            # infraestrutura (SAM/CloudFormation)
src/common.py            # validação, resposta HTTP, acesso ao DynamoDB, alerta SNS
src/criar_chamado.py     # POST   /chamados
src/listar_chamados.py   # GET    /chamados
src/buscar_chamado.py    # GET    /chamados/{id}
src/atualizar_status.py  # PATCH  /chamados/{id}/status
tests/                   # testes com moto
```

## Licença

MIT
