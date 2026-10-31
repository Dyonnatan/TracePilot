# Arquitetura de código — TracePilot

> Mapa do repositório módulo a módulo: o que cada arquivo representa, que
> decisão de design ele carrega, e o que falta implementar. Serve de guia
> para continuar o código e de base técnica para o pitch. Visão geral em
> [architecture.md](architecture.md).
>
> **Status**: MVP funcional — o fluxo linear completo (logs → métricas →
> traces → diagnóstico → verificação → relatório) roda de ponta a ponta
> contra uma instância real do OpenObserve, usando a OpenRouter como backend
> de LLM (modelo pequeno/barato por padrão, trocável via `.env`).

## `agents/llm/` — interface comum de LLM

| Arquivo | O que é | Decisão de design | Falta implementar |
|---|---|---|---|
| `base.py` | Classe abstrata `LLMProvider` com `generate(prompt, **kwargs)`. | O resto do código (orquestrador, agentes) depende só dessa interface, nunca de uma API específica — permite trocar cloud↔local por `.env`, sem tocar nos agentes. | — (interface fechada, só evolui se surgir necessidade nova, ex. streaming) |
| `cloud_provider.py` | `LLMProvider` via **OpenRouter** (API compatível com a da OpenAI). | OpenRouter dá acesso a um catálogo amplo de modelos (do mais barato ao mais avançado) com uma única chave — trocar de modelo é só mudar `OPENROUTER_MODEL` no `.env`, sem tocar em código. Cliente HTTP inicializado de forma preguiçosa (só na primeira chamada), para que montar o grafo não exija chave configurada. | Retries/backoff, logging estruturado de prompt/saída por chamada (rastreabilidade LLMOps — hoje não há log nenhum das chamadas). |
| `local_provider.py` | `LLMProvider` via **Ollama** — backend padrão do MVP (GPU local, GTX 1650/4GB). | Usa `ollama.Client` (biblioteca oficial). Modelo default `gemma3:4b` (~3,4GB — roda majoritariamente na GPU, ~69%, investigação completa em 40-58s, diagnóstico correto e consistente em repetições). Trocar é só mudar `OLLAMA_MODEL`. Erro de conexão vira `RuntimeError` com instrução de como corrigir (`ollama serve` / `ollama pull`). | Fallback automático para `CloudProvider` se o modelo local não responder (hoje é um erro direto). |
| — *modelos testados e descartados* | `hf.co/BrainboxAI/cyber-analyst-4B` (fine-tune de segurança, 6,3GB) foi testado na mesma falha do `demo_app` e **teve desempenho pior que o `gemma3:4b` genérico**: rodou quase todo em CPU (97%/3% CPU/GPU, por não caber na VRAM), levou 3min10s (vs ~45s) e **relatou "nenhuma evidência encontrada" mesmo com log e trace reais presentes** — o Laya confirmou baixa confiança (28%) nessa conclusão. Causa provável: incompatibilidade de template de chat na conversão GGUF comunitária (`hf.co/...`), não necessariamente o fine-tune em si. | Não virou padrão por esse motivo — mantido aqui como registro pra não repetir o teste. |
| `__init__.py` | `get_provider()` resolve qual provider usar a partir de `LLM_BACKEND`. | Ponto único de resolução — nenhum outro módulo deve ler `LLM_BACKEND` diretamente. | — |
| `decision_provider.py` | `DecisionProvider` via **Laya** (Convai Innovations) — modelo de decisão tipada ("System 1", não-gerativo). Implementado e integrado no `verifier_agent` como checagem **independente e paralela** ao veredito do LLM de texto (não o substitui, já que o LLM também gera as notas explicativas do relatório). | Ver [decision-models.md](decision-models.md) para a comparação Jev/Laya/Kev e a justificativa. Best-effort: se o Laya falhar, a investigação segue sem esse campo (`decision_model_error` no estado). | Calibração do checkpoint atual é instável (aviso do próprio pacote: "ships invalid temperatures... treat confidence as uncalibrated") — tratar o número como indicativo, não definitivo, até avaliar outro checkpoint. Também não usa GPU nesta máquina (driver CUDA 12.4 é mais antigo que o esperado pelo PyTorch instalado, cai pra CPU — ainda rápido por ser só 421M). |

## `agents/tools/openobserve_client.py` — acesso a telemetria

Wrapper sobre a API HTTP do OpenObserve, com `query_logs`/`query_traces`
**implementados e validados contra uma instância local real** (schema de
campo confirmado gerando tráfego de sucesso/falha no `demo_app` e
inspecionando o retorno). `query_metrics` segue a mesma mecânica mas
**ainda não foi validado contra dado real**, porque o `demo_app` hoje só
exporta logs/traces (métricas ficam para quando houver uma fonte real —
ver [reference-environment.md](reference-environment.md)).

Decisão de design: só métodos de leitura/consulta são expostos — os
agentes nunca têm acesso de escrita/admin ao OpenObserve. Autenticação
aceita token (produção) ou usuário/senha (dev local, bate com as
credenciais do `docker-compose.yml`).

## `agents/evidence_format.py` — formatação de evidência para prompt

Módulo novo (não previsto no scaffold original): compartilha entre os três
especialistas a lógica de truncar/formatar registros brutos do OpenObserve
em texto compacto para prompt. Decisão de design: existe separado dos
agentes porque formatar evidência é puramente mecânico (sem chamada de
LLM) e idêntico nos três — evita repetir a mesma lógica de truncamento em
cada `*_agent.py`.

## `agents/specialists/` — agentes especialistas

`logs_agent.py`, `metrics_agent.py`, `traces_agent.py` seguem a mesma
assinatura: `run(state, llm, client) -> state`. Cada um: consulta sua
fonte via `OpenObserveClient`, formata a evidência bruta com
`evidence_format`, e pede ao LLM um resumo **restrito ao que veio na
consulta** (prompt explicitamente proíbe inventar informação). Devolvem a
evidência bruta (`evidence_logs`/`evidence_metrics`/`evidence_traces`) e o
resumo (`*_summary`) ao estado — a correlação entre fontes acontece no
`diagnosis_agent`, não em cada especialista, para manter o raciocínio de
correlação em um único lugar auditável.

`metrics_agent.py` tem uma particularidade: como `query_metrics` ainda não
foi validado (ver acima), qualquer exceção na consulta é tratada como
"sem evidência de métricas" em vez de derrubar a investigação inteira.

## `agents/diagnosis_agent.py` e `agents/verifier_agent.py`

- `diagnosis_agent.run(state, llm) -> state`: consolida os três resumos em
  1-3 hipóteses de causa-raiz, cada uma com confiança (alta/média/baixa) e
  a evidência que a sustenta — ou declara explicitamente que a evidência é
  insuficiente, em vez de forçar uma hipótese.
- `verifier_agent.run(state, llm) -> state`: confronta as hipóteses com os
  resumos de evidência e devolve um veredito binário (`verified: bool`)
  mais notas explicando a decisão. O parsing do veredito é por prefixo de
  string (`"VEREDITO: SUPORTADO"`) em vez de JSON — escolha deliberada para
  ser robusto com modelos pequenos/baratos, que nem sempre respeitam
  formato JSON estrito.

Decisão de design: são dois agentes separados (não um só) para que o
verificador tenha um papel adversarial explícito — reduzir alucinação ao
forçar uma segunda "opinião" que só aceita conclusões com evidência citada.

## `agents/report.py` — composição do relatório final

Módulo novo: monta o relatório em Markdown a partir do estado final, **sem
nenhuma chamada de LLM adicional** — todo o conteúdo (hipóteses, resumos,
veredito) já foi gerado pelos nós anteriores. Decisão de design
deliberada: manter o custo de uma investigação em no máximo 5 chamadas de
LLM (logs, métricas, traces, diagnóstico, verificação), já que o MVP usa
modelos pequenos/baratos via OpenRouter e cada chamada extra tem custo.

## `agents/orchestrator.py` — o grafo

Define `IncidentState` (TypedDict) e monta um `StateGraph` do LangGraph
ligando `orchestrator → logs_agent → metrics_agent → traces_agent →
diagnosis_agent → verifier_agent → report → END`. Também expõe uma CLI
(`python3 agents/orchestrator.py "relato do erro" [--service ...]
[--trace-id ...] [--json]`) para rodar uma investigação completa e
imprimir o relatório (ou o estado completo em JSON, com `--json`).

Decisão de design: LangGraph (em vez de CrewAI) porque o fluxo real não é
linear — o `orchestrator_node` deve decidir dinamicamente qual especialista
consultar a seguir, e o `verifier_agent` deve poder mandar de volta para um
especialista se rejeitar o diagnóstico. CrewAI dá uma estrutura pronta de
"time de agentes", mas com menos controle fino sobre esse roteamento
condicional — ver justificativa completa em
[architecture.md](architecture.md#3-por-que-agentes-de-ia).

**Estado atual**: o grafo compilado roda o fluxo linear fixo acima e já
produz um relatório real de ponta a ponta. O roteamento dinâmico (próxima
etapa decidida pelo `orchestrator_node`, e retorno a um especialista se o
`verifier_agent` rejeitar) continua como próximo passo — não é mais
bloqueante para ter um MVP demonstrável, mas é o que falta para a
arquitetura corresponder de fato ao padrão Planejador-Executor descrito em
[glossario-conceitos-ia.md](glossario-conceitos-ia.md).

## `demo_app/` — aplicação de teste instrumentada

FastAPI com `FastAPIInstrumentor` (traces) **e exportação de logs via
OTLP** (adicionado durante a implementação do MVP, para o `logs_agent` ter
dado real — antes só exportava traces). O endpoint `POST /checkout` tem
uma falha controlada **determinística** (`ZeroDivisionError` quando
`quantity == 0`) com log de erro (`exc_info=True`, correlacionado por
`trace_id`/`span_id`) e exceção registrada no span — essa é a falha
"canário" que o MVP já consegue investigar de ponta a ponta.

## `docker-compose.yml` + `otel-collector-config.yaml`

Sobe `openobserve` (armazenamento/consulta de telemetria) e
`otel-collector` (recebe OTLP do `demo_app` e exporta para o OpenObserve).
Decisão de design: credenciais do OpenObserve (`ZO_ROOT_USER_EMAIL/PASSWORD`)
estão com um valor padrão fixo no compose — aceitável para ambiente de
desenvolvimento local (e é o mesmo usuário/senha usado por
`OPENOBSERVE_USER`/`OPENOBSERVE_PASSWORD` no `.env.example`), mas **deve
migrar para `.env`** antes de qualquer deploy fora da máquina local (gap de
segurança a resolver antes de produção).

## `benchmark/` e `reports/`

`benchmark/README.md` documenta o plano de avaliação com OpenRCA (ainda sem
harness implementado — agora que o MVP roda de ponta a ponta, esse é um
próximo passo natural). `reports/` continua reservado para persistir
relatórios gerados (hoje o relatório só é impresso via CLI, ainda não é
salvo em arquivo).

## Como rodar uma investigação

```bash
docker compose up -d                 # sobe OpenObserve + OTel Collector
cd demo_app && uvicorn main:app --reload &   # sobe a app de teste
curl -X POST localhost:8000/checkout -H "Content-Type: application/json" \
  -d '{"order_id":"1","quantity":0,"budget":700}'   # gera a falha

cp .env.example .env   # preencher OPENROUTER_API_KEY
python3 agents/orchestrator.py "checkout falhando com erro 500" \
  --service tracepilot-demo-app
```

## Próximos passos

1. Roteamento dinâmico no `orchestrator_node` (padrão Planejador-Executor).
2. Logging estruturado das chamadas de LLM (rastreabilidade/LLMOps).
3. Validar `query_metrics` contra uma fonte real de métricas.
4. Persistir o relatório em `reports/` (hoje só vai para stdout).
5. Harness de avaliação com OpenRCA em `benchmark/`.
