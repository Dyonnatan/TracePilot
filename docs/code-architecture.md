# Arquitetura de código — TracePilot

> Mapa do repositório módulo a módulo: o que cada arquivo representa, que
> decisão de design ele carrega, e o que falta implementar. Serve de guia
> para continuar o código e de base técnica para o pitch. Visão geral em
> [architecture.md](architecture.md).
>
> **Status**: MVP funcional — o fluxo linear completo (logs → métricas →
> traces → diagnóstico → verificação → relatório) roda de ponta a ponta
> contra uma instância real do OpenObserve, com backend de LLM local
> (Ollama) por padrão, e uma interface web (`webapp/`) pra disparar
> investigações e fazer drill-down na evidência.

## `webapp/` — interface web

FastAPI + Jinja2 (sem framework JS), pensada pro dono da aplicação (não
necessariamente alguém com conhecimento de observabilidade) monitorar,
disparar investigações e aprofundar na evidência.

| Rota | O que faz |
|---|---|
| `GET /` | Landing page pública sobre o produto (com botão de login). O hero reaproveita o diagrama do painel com dados **ilustrativos** (`monitoring.example_state()`), nunca dado real. |
| `GET/POST /login`, `POST /logout` | Login por e-mail e senha (`webapp/auth.py`): o primeiro login cria a conta do workspace (hash PBKDF2 no perfil); a sessão é um cookie assinado com HMAC. Primeiro acesso → `/onboarding`; depois → `/dashboard`. |
| `/onboarding/*` | Jornada de primeiro acesso em 7 passos: boas-vindas → questionário (nome, objetivo, como foi feito, onde roda) → instalação do agente → repositório (opcional, GitHub) → checagem de conexão → "configurando" (identificação animada da máquina, recursos, tecnologias) → resumo com checklists, tecnologias e diagrama. Estado em `workspace/profile.json` (`agents/workspace_store.py`). `POST /onboarding/reset` volta a jornada pro início (pra demonstrar de novo). |
| `GET /dashboard` | Painel: status geral em linguagem simples, **mapa interativo** (usuários → site → banco, dentro do servidor, observado pelo TracePilot; cada nó com ícone de alerta), indicadores de CPU/RAM/disco/rede/GPU com tendência e "?" explicativo, alertas ("problema agora" × "pode virar problema") com o que fazer, formulário de investigação e histórico. |
| `GET /dashboard/live` | Só o miolo que muda (HTML parcial) — o `static/app.js` troca a cada 10s enquanto a aba está visível. `GET /api/dashboard` devolve o mesmo estado em JSON. |
| `POST /investigations` | Dispara `run_investigation()` numa thread em background (não bloqueia a requisição) e redireciona pro detalhe. |
| `GET /investigations/{id}` | Detalhe: se `running`, faz polling via JS a cada 3s até terminar; se `done`, mostra primeiro um **card de decisão** (causa em linguagem simples + ações + prompt de correção com botão de copiar) — o resto (hipóteses técnicas, verificação, evidência bruta, relatório completo) fica dentro de um `<details>` fechado por padrão, pra não competir visualmente com o que importa decidir em segundos. |
| `GET /api/investigations/{id}` | JSON usado pelo polling da página de detalhe. |
| `GET /api/health` | Status da app monitorada + streams do OpenObserve, em JSON. |

**`webapp/monitoring.py`** traduz sinais técnicos em estado de tela:
dois limites por recurso (atenção → "pode virar problema"; crítico →
"problema agora"), erros recentes do sistema monitorado (contagem de logs
ERROR nos últimos 15 min no OpenObserve), e textos simples de "o que é
isso?" / "o que fazer". Sem dado → `unknown` (cinza), nunca "tudo bem".
O banco de dados aparece sempre como "sem dados": o TracePilot não se
conecta a ele nesta versão. Quando o agente Rust não reporta,
`resource_snapshot.py` mede CPU/RAM/rede (`/proc`) e GPU (`nvidia-smi`)
do host do **painel**, sempre marcado como `source="local"` na tela.

**Os dois caminhos de dados, com nome de produto na interface**:

- **TracePilot Collector** = `local-agent/`, instalado no servidor (CPU,
  memória, disco). Ativo quando há métricas dele nos últimos 5 min.
- **TracePilot API** = a aplicação envia logs/erros/rastros sem instalar
  nada: JSON pela `ingest/` (marca `tracepilot_ingest_mode=direct_api`) ou
  OTLP direto no collector. Ativo quando chegaram logs/spans do serviço
  monitorado nos últimos 15 min (`OpenObserveClient.recent_sources()`).
- **Armazenamento** (OpenObserve) aparece à parte: se ele cai, a tela diz
  "Armazenamento indisponível", não "TracePilot fora do ar". A checagem
  tenta duas vezes antes de declarar indisponível.

Landing, instalação, conexão, resumo e o nó TracePilot do mapa usam esses
mesmos três nomes.

**Métricas no OpenObserve**: cada métrica OTLP vira um stream próprio
(`system.cpu.usage_percent` → `system_cpu_usage_percent`), com o valor em
`value`. `query_metrics` deriva o stream do nome; antes consultava
`default` e por isso o painel nunca reconhecia o agente.

**Preset de demonstração** (`webapp/presets.py` + `webapp/presets/*.json`,
escolhido por `TRACEPILOT_PRESET`, padrão `reference-environment`):
pré-preenche login e questionário com os dados do ambiente de referência
(loja Apex Space, branch `feat/reference-environment`: `shop-api` em
`http://localhost:8088`, serviços `shop-api` + `payment-service`), mostra
os comandos `make up` no passo de instalação e aponta `demo_app/` como
cópia local do código — `github_inspector` cai nela quando a API do
GitHub não serve (repo privado sem `GITHUB_TOKEN`). Resposta já salva no
perfil sempre vence o preset. A URL e o serviço monitorados vêm do perfil
(`app_url`, `service_name`, `related_services`), com `DEMO_APP_URL` /
`MONITORED_SERVICE_NAME` só como fallback.

Decisão de design: thread em background (não fila/worker) — MVP de
hackathon, uma investigação por vez é suficiente, evita a complexidade
operacional de um broker. Persistência via `agents/report_store.py`
(arquivos JSON em `reports/`, não banco de dados — mesmo raciocínio).

**Lição aprendida rodando isso nesta máquina**: subir Docker (OpenObserve +
collector) + `demo_app` + Ollama com um modelo de 4B + o Laya, tudo ao
mesmo tempo, travou a máquina uma vez (RAM de 19GB, mas só 512MB de swap).
Depois disso, o processo de subir os serviços passou a ser sequencial, com
checagem de memória (`free -h`) entre cada etapa — vale manter esse
cuidado ao reproduzir localmente em máquinas com pouca RAM/swap.

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

## `agents/plain_summary_agent.py` — resumo em linguagem simples

Módulo novo, pensado pro usuário final (dono da aplicação, não técnico):
pega as hipóteses técnicas + a verificação e pede ao LLM uma tradução
curta — 1 frase de causa (termos técnicos sempre seguidos de explicação
entre parênteses) + no máximo 2 ações concretas. Parsing por prefixo
(`CAUSA:`/`ACAO:`) com fallback gracioso se o modelo não seguir o formato
(usa o texto bruto como causa em vez de quebrar). O prompt proíbe
explicitamente mencionar nomes internos do sistema ("especialista em
logs", "agente", "TracePilot") — são vazamentos de implementação que não
fazem sentido pra quem só quer saber o que aconteceu e o que fazer.

## `agents/fix_prompt.py` — prompt pronto para a IA corrigir

Módulo novo: monta um prompt detalhado pra colar numa IA de código (Claude
Code, Cursor etc.), **sem chamada de LLM** — usa diretamente os campos já
extraídos do log de erro (`code_file_path`, `code_function_name`,
`code_line_number`, `exception_stacktrace`, todos confirmados reais em
`openobserve_client.py`). Decisão de design: isso é mais confiável que
pedir pro LLM reescrever o stacktrace — dado exato não se parafraseia.

## `agents/report.py` — composição do relatório final

Monta o relatório em Markdown a partir do estado final, **sem nenhuma
chamada de LLM adicional** — todo o conteúdo já foi gerado pelos nós
anteriores. Agora inclui, no topo, o resumo simples (causa + ações) e o
prompt de correção. Decisão de design deliberada: manter o custo de uma
investigação em 6 chamadas de LLM (logs, métricas, traces, diagnóstico,
verificação, resumo simples) — compor o relatório/prompt de correção em si
não soma uma sétima.

## `agents/report_store.py` — persistência de investigações

Módulo novo: salva cada investigação como um JSON em `reports/` (id,
status — `running`/`done`/`error` —, timestamps, e o estado final completo
quando termina). Decisão de design: arquivo simples em vez de banco de
dados — volume baixo, sem concorrência pesada de escrita, típico de MVP.
É o que permite a interface web listar investigações passadas e fazer
drill-down na evidência bruta sem precisar rodar tudo de novo.

## `agents/orchestrator.py` — o grafo

Define `IncidentState` (TypedDict) e monta um `StateGraph` do LangGraph
ligando `orchestrator → logs_agent → metrics_agent → traces_agent →
diagnosis_agent → verifier_agent → report → END`. Expõe
`run_investigation(error_report, service, trace_id, ...)` como função
reutilizável (usada tanto pela CLI quanto pelo `webapp/`) que monta o
estado inicial, roda o grafo e persiste o resultado via `report_store`.
A CLI (`python3 agents/orchestrator.py "relato do erro" [--service ...]
[--trace-id ...] [--json]`) é hoje uma casca fina sobre essa função.

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

## `ingest/` — API de ingestão direta (caminho sem instalador)

Serviço FastAPI separado (`uvicorn ingest.main:app`, porta 8810) que
recebe log/span em JSON simples da aplicação monitorada, traduz para OTLP
e repassa ao `otel-collector`. É o segundo caminho de ingestão do
TracePilot, complementar ao coletor instalável (`local-agent/`) — existe
para infra onde não se pode instalar agente (PaaS, serverless, política de
segurança) e para quem quer mandar só o essencial em vez de todo o log da
máquina. Comparação dos modos em [ingestion-modes.md](ingestion-modes.md).

| Rota | O que faz |
|---|---|
| `POST /v1/events` | Lote de eventos de um serviço → OTLP → collector. Responde `202` com as contagens aceitas e `warnings`. |
| `GET /v1/guide` | Serve [ai-integration-guide.md](ai-integration-guide.md) em markdown — o contrato na versão desta instância. |
| `GET /v1/health` | Status da API, do collector OTLP e se a autenticação está configurada. |

| Arquivo | Conteúdo |
|---|---|
| `schema.py` | Contrato público (Pydantic): o JSON que a aplicação manda. |
| `otlp.py` | Tradução para OTLP/JSON + `integration_warnings()`. |
| `main.py` | Rotas, autenticação por chave, repasse ao collector. |

Decisões de design:

- **Schema mais simples que OTLP, não OTLP cru.** O público deste caminho
  é justamente quem não pode adotar um SDK de OTel; exigir OTLP na mão
  devolveria o integrador ao problema que ele não consegue resolver.
- **Traduz para o pipeline existente, não cria outro.** A evidência que
  entra pela API chega ao OpenObserve com os mesmos nomes de campo que
  `openobserve_client.py` consulta — os agentes não distinguem a origem
  (só o atributo `tracepilot.ingest_mode`, para auditoria).
- **`warnings` na resposta.** `integration_warnings()` aponta o que falta
  no lote para a investigação funcionar (log sem `trace_id`, span sem
  `status=ERROR`, nenhum `exception.stacktrace`). É o que fecha o ciclo da
  integração escrita por IA: manda lote de teste, lê os avisos, corrige —
  sem precisar abrir o OpenObserve para conferir. Avisa, não bloqueia: o
  lote é aceito de todo jeito.
- **Processo separado do `webapp/`.** Plano de dados (tráfego da aplicação
  do cliente, possivelmente exposto) versus plano de controle (painel do
  operador) — um processo só daria ao primeiro a superfície de ataque do
  segundo.
- **Só escrita de telemetria.** Não lê investigação nem consulta
  OpenObserve — mesmo raciocínio do `OpenObserveClient`, que só expõe
  leitura.

Validado de ponta a ponta contra a stack real: lote com um span de erro e
um log correlacionado enviado por `POST /v1/events` chegou ao OpenObserve
com `body`, `severity`, `trace_id`, `span_id`, `service_name`,
`exception_type/message/stacktrace`, `operation_name`, `span_status`,
`http_route`, `http_status_code`, `duration` e `events` — conferido por
consulta via `OpenObserveClient`. Pendente: TLS, *rate limit* por chave e
amarrar cada chave ao `service` que pode escrever.

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
6. Endurecer `ingest/` para produção: TLS/proxy reverso, *rate limit* por
   chave e vínculo chave → `service` autorizado.
