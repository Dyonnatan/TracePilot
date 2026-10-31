# Guia de integração direta — para IA implementar

> **Este documento é feito para ser entregue a uma IA** (Claude Code,
> Copilot, Cursor…) trabalhando dentro do código da aplicação que será
> monitorada. Ele descreve o contrato mínimo que o TracePilot precisa para
> investigar um incidente, e como enviar esses dados sem instalar nada na
> máquina.
>
> Também é servido pela própria instância do TracePilot em
> `GET http://<host-do-tracepilot>:8810/v1/guide` — prefira buscar de lá,
> porque bate com a versão que está rodando.
>
> Quando **dá** para instalar o coletor na máquina, instale
> ([`local-agent/`](../local-agent/)) — este caminho aqui é o complemento
> para quando não dá, ou quando se quer mandar só o essencial. Comparação
> entre os dois modos: [ingestion-modes.md](ingestion-modes.md).

## Objetivo da integração

Ao final, quando a aplicação falhar, o TracePilot deve conseguir
responder: **qual requisição falhou, em que operação, com qual exceção, em
qual linha de código, e o que mais estava acontecendo naquele momento.**

Isso só acontece se os dados enviados vierem **correlacionados** — log e
span da mesma requisição carregando o mesmo `trace_id`. Mandar log solto
sem correlação é o erro mais comum e o que mais degrada o diagnóstico.

## Contrato mínimo

Os agentes do TracePilot filtram exatamente por estes campos (ver
`agents/specialists/` e `agents/tools/openobserve_client.py`). Não é uma
lista de boas práticas genéricas — é o que determina se a investigação
encontra ou não a evidência:

| Campo | Obrigatório | Por que o TracePilot precisa |
|---|---|---|
| `service` (no lote) | **sim** | Toda investigação começa filtrando por serviço. Use um nome estável, igual em todos os envios (ex. `checkout-api`). |
| `trace_id` | **sim** para span; **muito recomendado** para log | É o que liga log ↔ span ↔ requisição. Sem ele o TracePilot vê "houve um erro", não "a requisição X falhou". 32 caracteres hexadecimais. |
| `span_id` | **sim** para span | Identifica a operação dentro do trace. 16 caracteres hexadecimais. |
| `severity` (log) | **sim** para log de erro | `logs_agent` filtra por `ERROR`/`WARNING`/`WARN`. Log de erro mandado como `INFO` **não entra** na investigação. |
| `status: "ERROR"` (span) | **sim** quando a operação falhou | Quando a investigação não parte de um `trace_id` conhecido, `traces_agent` busca justamente os spans com erro. |
| `exception.type` / `.message` / `.stacktrace` | **muito recomendado** | Evidência de maior valor. O `stacktrace` é o que permite ao TracePilot apontar arquivo/linha e gerar um prompt de correção aplicável. |
| `timestamp` (log) / `start_time` + `duration_ms` (span) | recomendado | A investigação é sempre uma janela de tempo. Sem timestamp, o evento recebe a hora da ingestão (impreciso, mas não quebra). |
| `http.route` / `http.status_code` / `http.method` | recomendado | Dá contexto de rota e código de resposta ao diagnóstico. |
| `operation` (span) | **sim** para span | Nome da operação (ex. `POST /checkout`, `calcular_preco_unitario`). É o que aparece como ponto de origem do erro. |
| `attributes` | opcional | Contexto de negócio que ajuda a reproduzir (ex. `{"order_id": "1", "quantity": 0}`). **Nunca** dados sensíveis — ver "Privacidade". |

## Opção A (preferida quando possível): SDK de OpenTelemetry

Se a linguagem da aplicação tem SDK de OpenTelemetry e a infra permite
saída de rede para o TracePilot, **use o SDK** em vez da API JSON abaixo:
a instrumentação automática já preenche `trace_id`, `span_id`,
`operation`, `http.*` e propagação entre serviços — sem código manual de
correlação (que é onde integrações caseiras erram).

Aponte o exportador OTLP para o collector do TracePilot:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://<host-do-tracepilot>:4318
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_SERVICE_NAME=checkout-api
```

Referência de uma app já instrumentada neste repositório:
[`demo_app/main.py`](../demo_app/main.py) (traces + logs via OTLP, com
exceção registrada no span).

Nesse caminho, o resto deste guia serve só como checklist do que precisa
estar preenchido.

## Opção B: API de ingestão do TracePilot (JSON)

Use quando não houver SDK de OTel viável — função serverless com limite de
tamanho de pacote, runtime sem instrumentação disponível, ou política que
só libera uma chamada HTTP de saída.

### Endpoint

```
POST http://<host-do-tracepilot>:8810/v1/events
Content-Type: application/json
Authorization: Bearer <TRACEPILOT_INGEST_KEY>
```

Resposta `202`:

```json
{
  "accepted": {"logs": 1, "spans": 1},
  "service": "checkout-api",
  "warnings": []
}
```

**`warnings` é a parte importante para quem está implementando**: ele lista
o que falta no lote para o TracePilot investigar bem (ex. "nenhum log com
`trace_id`"). Uma integração correta manda um lote de teste e só considera
pronto quando `warnings` vem **vazio**.

Outros códigos: `401` chave inválida · `413` lote acima de 500 eventos ·
`422` evento malformado (a mensagem diz qual campo) · `502` o pipeline do
TracePilot falhou — **repita o envio**, não "corrija" o lote.

### Formato do lote

```json
{
  "service": "checkout-api",
  "host": "pod-checkout-7f9c",
  "environment": "producao",
  "events": [
    {
      "kind": "span",
      "trace_id": "d6d950f8e45212001feec99001a535bb",
      "span_id": "a586997c7e2c51d8",
      "parent_span_id": null,
      "operation": "POST /checkout",
      "start_time": "2026-10-31T14:20:03.120Z",
      "duration_ms": 134.5,
      "status": "ERROR",
      "http": {"method": "POST", "route": "/checkout", "status_code": 500},
      "exception": {
        "type": "ZeroDivisionError",
        "message": "division by zero",
        "stacktrace": "File \"app/checkout.py\", line 42, in checkout\n    unit = budget / quantity"
      },
      "attributes": {"order_id": "1", "quantity": 0}
    },
    {
      "kind": "log",
      "trace_id": "d6d950f8e45212001feec99001a535bb",
      "span_id": "a586997c7e2c51d8",
      "timestamp": "2026-10-31T14:20:03.250Z",
      "severity": "ERROR",
      "message": "checkout falhou ao calcular preço unitário order_id=1 quantity=0",
      "exception": {"type": "ZeroDivisionError", "message": "division by zero"}
    }
  ]
}
```

Regras de formato:

- `kind` é `"log"` ou `"span"`. Um lote pode misturar os dois (e deve: o
  span dá a requisição, o log dá o detalhe).
- `trace_id`: 32 hex. `span_id`/`parent_span_id`: 16 hex. Minúsculas,
  sem hífen.
- Timestamps aceitam ISO-8601 (`...Z` ou com offset) **ou** epoch
  numérico — segundos, ms, µs ou ns são todos aceitos (a unidade é
  inferida pela magnitude). Ausente = hora da ingestão.
- `duration_ms` é alternativa a `end_time`; mandar um dos dois.
- Limite de 500 eventos por lote.

### Como obter `trace_id` / `span_id`

Em ordem de preferência:

1. **A aplicação já usa OpenTelemetry** (mesmo que exportando para outro
   lugar): leia o contexto ativo e reaproveite os ids — não gere novos.
2. **A requisição chegou com header `traceparent`** (formato W3C:
   `00-<trace_id 32 hex>-<span_id 16 hex>-01`): extraia o `trace_id` dele
   e gere um `span_id` novo para a sua operação. Isso mantém a correlação
   entre serviços.
3. **Nada disso existe**: gere no início da requisição e carregue pelo
   escopo dela — 16 bytes aleatórios em hex para `trace_id`, 8 bytes para
   `span_id`. **Um por requisição**, não um por log.

```python
import secrets
trace_id = secrets.token_hex(16)  # 32 caracteres
span_id = secrets.token_hex(8)    # 16 caracteres
```

### Exemplo mínimo de envio (Python)

```python
import os
import httpx

TRACEPILOT_URL = os.environ["TRACEPILOT_INGEST_URL"]   # http://host:8810/v1/events
TRACEPILOT_KEY = os.environ["TRACEPILOT_INGEST_KEY"]


def send(events: list[dict]) -> None:
    """Envio não-bloqueante e à prova de falha: observabilidade nunca pode
    derrubar a aplicação que ela observa.
    """
    try:
        httpx.post(
            TRACEPILOT_URL,
            json={"service": "checkout-api", "environment": "producao", "events": events},
            headers={"Authorization": f"Bearer {TRACEPILOT_KEY}"},
            timeout=3,
        )
    except Exception:
        pass  # engole: TracePilot fora do ar não pode virar erro de checkout
```

Em produção, troque a chamada direta por uma fila em memória com
*flush* periódico (ou uma thread/task de background) — ver "Como enviar
bem" abaixo.

## Como enviar bem (o que otimizar)

Este caminho existe, em parte, justamente para **mandar menos e melhor**
que um coletor que tail-eia tudo. O que "bem" significa aqui:

1. **Mande todo erro, amostre o sucesso.** 100% dos eventos com
   `severity: ERROR`/`status: ERROR`; dos casos de sucesso, uma amostra
   (ex. 1–5%) só para servir de linha de base de latência.
2. **Agrupe em lote.** Acumule eventos e envie a cada N segundos ou N
   eventos (o que vier primeiro), não uma requisição HTTP por log.
3. **Nunca bloqueie a requisição do usuário.** Envio em background, com
   timeout curto; falha de envio é descartada em silêncio.
4. **Limite o tamanho.** Trunque `stacktrace` (ex. 8KB) e `message`
   (ex. 4KB) — stacktrace gigante não melhora o diagnóstico.
5. **Não reenvie o que já vai pelo coletor.** Se a máquina também tem o
   coletor do TracePilot instalado lendo o arquivo de log, mandar o mesmo
   log pela API duplica evidência e confunde a investigação.
6. **Use `service` estável e `environment` separado.** Nunca misture
   produção e homologação no mesmo nome de serviço.

## Privacidade: o que não enviar

A evidência vai para o OpenObserve e é lida por agentes de IA. Antes de
incluir qualquer coisa em `message` ou `attributes`:

- **Nunca** envie senha, token, chave de API, cookie de sessão, cartão,
  CPF/documento, e-mail ou endereço de usuário final.
- Prefira identificadores opacos (`user_id`, `order_id`) a dados
  pessoais.
- Se o corpo da requisição é necessário para reproduzir o erro, mande só
  os campos relevantes àquele cálculo (como `quantity` no exemplo), não o
  payload inteiro.

## Checklist de validação (rodar antes de considerar pronto)

```bash
# 1. O TracePilot está acessível e com o pipeline de pé?
curl -s http://<host>:8810/v1/health
#    espera: {"status":"ok","collector":{"up":true,...},"auth":"api_key",...}

# 2. Um lote de teste é aceito sem avisos?
curl -s -X POST http://<host>:8810/v1/events \
  -H 'content-type: application/json' \
  -H "Authorization: Bearer $TRACEPILOT_INGEST_KEY" \
  -d @ingest/exemplo-lote.json
#    espera: "accepted" com as contagens certas e "warnings": []
#    (ingest/exemplo-lote.json está neste repositório, pronto pra usar;
#     os timestamps são omitidos de propósito — assim o lote cai na hora
#     da ingestão e aparece na janela de tempo investigada por padrão)
```

3. Provoque um erro real na aplicação e confirme, no painel do TracePilot
   (`http://<host>:8800`), que o serviço aparece com evidência do erro.
4. Dispare uma investigação pelo painel usando o relato em linguagem
   natural (ex. "checkout falhando com erro 500") e confira se o
   diagnóstico cita a exceção e o ponto do código — se citar, a
   integração está completa; se disser "sem evidência suficiente", volte à
   tabela do contrato mínimo e veja qual campo está faltando.

## Erros comuns (nessa ordem de frequência)

| Sintoma | Causa provável |
|---|---|
| Investigação não encontra nada | `service` enviado diferente do que foi buscado no painel; ou todo o lote está fora da janela de tempo investigada. |
| Encontra o log, mas não liga à requisição | `trace_id` ausente nos logs, ou um `trace_id` novo gerado por log em vez de um por requisição. |
| Encontra o span, mas não o erro | `status` do span não foi marcado como `"ERROR"`, ou o log de erro foi enviado como `INFO`. |
| Diagnóstico genérico, sem apontar código | `exception.stacktrace` não está sendo enviado. |
| `422` no envio | `trace_id`/`span_id` fora do formato hexadecimal (ex. UUID com hífen, ou id de 36 caracteres). |
