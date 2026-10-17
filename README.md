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

No Windows (PowerShell), as aspas do `curl` funcionam diferente. Use o `Invoke-RestMethod`:

```powershell
$API = "https://SEU-ID.execute-api.REGIAO.amazonaws.com"
$corpo = @{ titulo="Impressora sem toner"; descricao="Setor financeiro sem impressao"; setor="Financeiro"; solicitante="Maria Teste"; prioridade="alta" } | ConvertTo-Json
$chamado = Invoke-RestMethod -Method Post -Uri "$API/chamados" -ContentType "application/json" -Body $corpo
Invoke-RestMethod "$API/chamados/$($chamado.id)"
Invoke-RestMethod -Method Patch -Uri "$API/chamados/$($chamado.id)/status" -ContentType "application/json" -Body (@{status="em_andamento"} | ConvertTo-Json)
```

Prefira textos sem acento nos exemplos de PowerShell, para evitar problemas de codificação.

## Testar localmente (sem AWS)

Os testes usam o `moto`, que simula DynamoDB, SNS e SQS em memória. Nada é criado na AWS.

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: py -3.12 -m venv .venv e depois .venv\Scripts\activate
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
   o que é prático mas **amplo demais para uso profissional**: em um projeto real, eu restringiria as permissões ao mínimo necessário.
3. Compile e faça o deploy:
   ```bash
   sam build
   sam deploy --guided
   ```
   Respostas sugeridas: nome da stack `chamados-ti`; região de sua escolha; `EmailAlertas` com o seu
   e-mail completo (ou vazio; o SAM não valida o formato, então confira o valor antes de confirmar o deploy); aceitar a criação de roles IAM; salvar a configuração em `samconfig.toml`.
   O SAM avisará que as rotas não têm autenticação: para este estudo responda `y`.
4. Ao final, o terminal mostra `ApiUrl`. Se informou e-mail, **confirme a assinatura** no link que o SNS enviar.
5. Teste as rotas com os exemplos acima e abra um chamado `critica` para receber o alerta por e-mail.
6. Veja os logs: `sam logs -n CriarChamadoFunction --stack-name chamados-ti --tail` ou pelo console (CloudWatch).
7. Confira no console (stack, tabela com itens, logs) que os recursos foram criados e a API responde.
8. **Quando terminar de usar, apague tudo:**
   ```bash
   sam delete --stack-name chamados-ti
   ```
   O Lambda cria os grupos de log no CloudWatch fora da stack, então o `sam delete` não os remove.
   Apague também os grupos `/aws/lambda/chamados-ti-*` (CloudWatch → Logs → Grupos de logs).
   A stack `aws-sam-cli-managed-default`, criada pelo próprio SAM para guardar o código enviado, pode ficar: o custo é desprezível.

## Custos

A conta no plano Free só gasta créditos e fecha ao fim deles ou em 6 meses, sem cobrar o cartão.
Este projeto usa serviços de custo muito baixo em uso de estudo (Lambda, API Gateway, DynamoDB sob demanda,
SNS e CloudWatch). Mesmo assim: configure o alerta de orçamento, não faça upgrade para o plano Paid
e apague a stack quando não precisar mais. Confira os preços atuais na página de cada serviço.

## Validação

Além dos testes automatizados com serviços simulados, a stack foi publicada em uma conta AWS real
(`us-east-2`): as quatro rotas, os códigos 400/404 e o alerta por e-mail de um chamado crítico foram
verificados manualmente e os logs conferidos no CloudWatch. Depois, a stack foi removida.

## Decisões e trade-offs

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
- Os testes automatizados usam serviços simulados (moto); a verificação contra a AWS real foi manual, sem teste de integração automatizado.

## Estrutura

```
template.yaml            # infraestrutura (SAM/CloudFormation)
src/common.py            # validação, resposta HTTP, acesso ao DynamoDB, alerta SNS
src/criar_chamado.py     # POST   /chamados
src/listar_chamados.py   # GET    /chamados
src/buscar_chamado.py    # GET    /chamados/{id}
src/atualizar_status.py  # PATCH  /chamados/{id}/status
tests/                   # testes com moto
LICENSE                  # MIT
```

## Licença

MIT (veja o arquivo `LICENSE`).
