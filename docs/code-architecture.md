# Arquitetura de código — TracePilot

> Mapa do repositório módulo a módulo: o que cada arquivo representa, que
> decisão de design ele carrega, e o que falta implementar. Serve de guia
> para continuar o código e de base técnica para o pitch. Visão geral em
> [architecture.md](architecture.md).

## `agents/llm/` — interface comum de LLM

| Arquivo | O que é | Decisão de design | Falta implementar |
|---|---|---|---|
| `base.py` | Classe abstrata `LLMProvider` com `generate(prompt, **kwargs)`. | O resto do código (orquestrador, agentes) depende só dessa interface, nunca de uma API específica — permite trocar cloud↔local por `.env`, sem tocar nos agentes. | — (interface fechada, só evolui se surgir necessidade nova, ex. streaming) |
| `cloud_provider.py` | Stub de `LLMProvider` via Anthropic (configurável). | Lê `CLOUD_MODEL`/`ANTHROPIC_API_KEY` do `.env`. | Chamada real à API, retries, logging de prompt/saída para rastreabilidade (LLMOps). |
| `local_provider.py` | Stub de `LLMProvider` via Ollama. | Lê `OLLAMA_HOST`/`OLLAMA_MODEL` do `.env`. | Chamada real ao Ollama, fallback para `CloudProvider` se o modelo local não responder. |
| `__init__.py` | `get_provider()` resolve qual provider usar a partir de `LLM_BACKEND`. | Ponto único de resolução — nenhum outro módulo deve ler `LLM_BACKEND` diretamente. | — |

## `agents/tools/openobserve_client.py` — acesso a telemetria

Wrapper sobre a API HTTP do OpenObserve. Decisão de design: expõe **só
métodos de consulta** (`query_logs`, `query_traces`, `query_metrics`) — os
agentes nunca devem ter acesso de escrita/admin ao OpenObserve, por
segurança (limitar o "raio de ação" dos agentes a operações seguras, um dos
gaps citados na proposta). Falta implementar: as consultas reais via API
SQL/stream do OpenObserve.

## `agents/specialists/` — agentes especialistas

`logs_agent.py`, `metrics_agent.py`, `traces_agent.py` seguem a mesma
assinatura: `run(state, llm, client) -> state`. Decisão de design: cada
especialista só enxerga sua fonte de dados (logs ou métricas ou traces) e
devolve evidências ao estado compartilhado — a correlação entre fontes
acontece no `diagnosis_agent`, não em cada especialista individualmente,
para manter o raciocínio de correlação em um único lugar auditável. Falta
implementar: a lógica de consulta + resumo de cada um (hoje só
`NotImplementedError`).

## `agents/diagnosis_agent.py` e `agents/verifier_agent.py`

- `diagnosis_agent.run(state, llm) -> state`: consolida evidências dos
  especialistas em hipóteses com nível de confiança.
- `verifier_agent.run(state, llm) -> state`: confronta as hipóteses com as
  evidências e pode rejeitar um diagnóstico sem suporte suficiente.

Decisão de design: são dois agentes separados (não um só) para que o
verificador tenha um papel adversarial explícito — reduzir alucinação ao
forçar uma segunda "opinião" que só aceita conclusões com evidência. Falta
implementar: os critérios de consolidação e de rejeição.

## `agents/orchestrator.py` — o grafo

Define `IncidentState` (TypedDict) e monta um `StateGraph` do LangGraph
ligando `orchestrator → logs_agent → metrics_agent → traces_agent →
diagnosis_agent → verifier_agent → END`.

Decisão de design: LangGraph (em vez de CrewAI) porque o fluxo real não é
linear — o `orchestrator_node` deve decidir dinamicamente qual especialista
consultar a seguir, e o `verifier_agent` deve poder mandar de volta para um
especialista se rejeitar o diagnóstico. CrewAI dá uma estrutura pronta de
"time de agentes", mas com menos controle fino sobre esse roteamento
condicional — ver justificativa completa em
[architecture.md](architecture.md#3-por-que-agentes-de-ia).

**Estado atual**: o grafo compilado hoje só tem o fluxo linear fixo acima
(fiação, sem roteamento condicional) — é o próximo passo de implementação,
junto com a lógica de cada nó.

## `demo_app/` — ambiente de referência monitorado

Loja multi-serviço em Python (`shop-api`, `payment-service`, Postgres,
`toxiproxy` entre os serviços, `loadgen`) com seu próprio
`docker-compose.yml`, exportando para o mesmo Collector da raiz pela rede
Docker `tracepilot`. Guia de uso em
[demo_app/README.md](../demo_app/README.md). Decisão de design: as falhas
são **determinísticas** (ativadas por comando, nunca aleatórias) para que
qualquer investigação, manual ou por agente, seja reproduzível e comparável
entre execuções, essencial para o benchmark.

| Peça | Decisão de design |
|---|---|
| `scenarios/*.yaml` | Fonte da verdade dos cenários: ativação, TTL, sinais esperados e causa raiz gabarito, para o benchmark comparar com o diagnóstico dos agentes. A tabela do README é gerada a partir deles. |
| `chaos-control/` | Injeta as falhas (toxiproxy, lock no Postgres, CPU burn) **sem OpenTelemetry**: a injeção não pode aparecer na telemetria, senão entrega o gabarito aos agentes. Falhas têm TTL (padrão 120 s). |
| `shop-api/` | Frontend com `session_id` e relato de problema (`user.report` com `trace_id`): é a entrada (`error_report`) que o orquestrador vai consumir. Deploy versionado (`SHOP_VERSION`) gera `change.event`, o histórico de mudanças legítimo. |
| `payment-service/` | `/internal/*` (canal do chaos-control) excluído de traces e sem access log. |
| `dashboards/` | Dashboard OpenObserve com o caminho de investigação manual — o trabalho que o TracePilot automatiza. |

Falta implementar: novos cenários (dependência externa, saturação de
memória), métricas do Postgres via receiver do Collector e uma versão
poliglota de algum serviço.

## `docker-compose.yml` + `otel-collector-config.yaml`

Sobe `openobserve` (armazenamento/consulta de telemetria) e
`otel-collector` (recebe OTLP do `demo_app` e exporta para
o OpenObserve). A imagem do OpenObserve tem tag fixa porque o dashboard em
`demo_app/dashboards/` depende do formato de import da versão. O
override opt-in `docker-compose.hostmetrics.yml` +
`otel-collector-hostmetrics.yaml` adiciona os receivers `host_metrics` e
`docker_stats`; ele monta o socket do Docker (equivale a root no host) e por
isso não faz parte da stack padrão.
Decisão de design: credenciais do OpenObserve (`ZO_ROOT_USER_EMAIL/PASSWORD`)
estão com um valor padrão fixo no compose — aceitável para ambiente de
desenvolvimento local, mas **deve migrar para `.env`** antes de qualquer
deploy fora da máquina local (gap de segurança a resolver antes de
produção).

## `benchmark/` e `reports/`

`benchmark/README.md` documenta o plano de avaliação com OpenRCA (ainda sem
harness implementado). `reports/` é o destino dos relatórios de incidente
gerados pelo `verifier_agent` ao final do fluxo — hoje só existe a pasta
(`.gitkeep`), o formato do relatório ainda não foi definido.

## Ordem sugerida para sair do scaffold

1. Implementar `cloud_provider.py` (mais rápido para prototipar que o
   local) e testar `get_provider()`.
2. Implementar `openobserve_client.py` contra uma instância local do
   `docker-compose.yml`.
3. Implementar `logs_agent.py` sozinho, validando contra o erro determinístico
   do cenário `coupon_bug` do `demo_app` (`ZeroDivisionError` em
   `/cart/quote` e `/checkout`).
4. Repetir para `metrics_agent.py` e `traces_agent.py`.
5. Implementar `diagnosis_agent.py` e `verifier_agent.py`.
6. Trocar o fluxo linear do `orchestrator.py` por roteamento condicional.
7. Só então começar o harness de avaliação em `benchmark/`.
