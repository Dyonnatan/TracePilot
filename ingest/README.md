# tracepilot-ingest

API de ingestão direta: a aplicação monitorada manda log/span em JSON
simples e o TracePilot traduz para OTLP, entregando no mesmo pipeline que
o coletor instalável usa (otel-collector → OpenObserve → agentes de IA).

É o caminho **sem instalador** — para infra onde não dá pra instalar nada
(PaaS, serverless, política de segurança) e para quem quer mandar só o
essencial em vez de todo o log da máquina. Complementar ao coletor
([`local-agent/`](../local-agent/)), não substituto: comparação em
[docs/ingestion-modes.md](../docs/ingestion-modes.md).

## Rodar

```bash
# precisa do otel-collector de pé (docker compose up -d na raiz)
export TRACEPILOT_INGEST_KEYS=chave-do-cliente-a,chave-do-cliente-b
uvicorn ingest.main:app --host 0.0.0.0 --port 8810
```

## Rotas

| Rota | O que faz |
|---|---|
| `POST /v1/events` | Recebe um lote de logs/spans de um serviço, traduz para OTLP e repassa ao collector. Responde `202` com as contagens aceitas e `warnings` — o que falta no lote pro TracePilot investigar bem. |
| `GET /v1/guide` | Serve o [guia de integração para IA](../docs/ai-integration-guide.md) em markdown, na versão que corresponde a esta instância. |
| `GET /v1/health` | Status da própria API + se o collector OTLP está respondendo + se a autenticação está configurada. |

Exemplo de envio e contrato completo dos campos:
[docs/ai-integration-guide.md](../docs/ai-integration-guide.md).

## Variáveis de ambiente

| Variável | Default | Descrição |
|---|---|---|
| `TRACEPILOT_OTLP_HTTP_ENDPOINT` | `http://localhost:4318` | Endpoint OTLP/HTTP do collector para onde os eventos são repassados. |
| `TRACEPILOT_INGEST_KEYS` | — | Chaves de API aceitas, separadas por vírgula. **Vazio = API aberta** (só para desenvolvimento local). |
| `TRACEPILOT_INGEST_MAX_EVENTS` | `500` | Máximo de eventos por lote (acima disso, `413`). |

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `schema.py` | Contrato público: o JSON que a aplicação manda (deliberadamente mais simples que OTLP). |
| `otlp.py` | Tradução para OTLP/JSON + os `warnings` de qualidade de integração. |
| `main.py` | Rotas, autenticação por chave e repasse ao collector. |

## Status

Validada de ponta a ponta contra a stack real deste repositório: lote
enviado por `POST /v1/events` chega ao OpenObserve com os campos que os
agentes especialistas consultam (conferido por consulta via
`OpenObserveClient`). Pendente para produção: TLS (hoje espera-se proxy
reverso na frente), *rate limit* por chave, e amarrar cada chave ao
`service` que ela pode escrever.
