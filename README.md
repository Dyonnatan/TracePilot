# TracePilot

Camada inteligente de investigação de incidentes, baseada em agentes de IA,
integrada a ferramentas abertas de observabilidade (OpenTelemetry +
OpenObserve). Proposta para o **AKCIT Camp**.

## O problema

Quando uma aplicação falha em produção, descobrir a causa raiz costuma levar
mais tempo do que detectar a falha. Times precisam correlacionar
manualmente logs, métricas, traces, mudanças de código recentes e relatos
de usuários — muitas vezes a partir de um relato vago como "não consegui
concluir a operação". Isso consome tempo técnico e prolonga
indisponibilidades, especialmente em times sem profissionais dedicados a
confiabilidade (SRE).

## A solução

Quando ocorre um erro, o TracePilot correlaciona (quando disponíveis e
autorizados) eventos da jornada do usuário, requisições, logs, métricas,
traces e histórico de mudanças. Agentes especializados investigam essas
fontes, formulam e confrontam hipóteses, pedem evidências adicionais e
produzem um diagnóstico rastreável: causa provável, evidências, limitações,
passos de reprodução e correções sugeridas — com opção de abrir uma issue
na ferramenta de desenvolvimento do time.

## Por que agentes de IA

Incidentes não seguem um roteiro fixo: o resultado de uma consulta pode
mudar a hipótese e exigir checar outra fonte. Um agente **orquestrador**
(padrão Supervisor-Trabalhador) coordena **especialistas** em logs,
métricas e traces; um agente de **diagnóstico** consolida hipóteses; e um
**verificador** questiona conclusões sem evidência suficiente. Mais
detalhes em [docs/architecture.md](docs/architecture.md) e nomenclatura/
fundamentação teórica em [docs/glossario-conceitos-ia.md](docs/glossario-conceitos-ia.md).

## Arquitetura (visão rápida)

```
Coletor TracePilot (local-agent)       App instrumentada (demo_app)
  recursos do SO, na máquina              OpenTelemetry (traces/logs)
              │                                      │
              │   API de ingestão direta (ingest/)   │
              │   app manda log/span em JSON ────────┤
              ▼                                      ▼
  OTel Collector  ──────▶  OpenObserve (armazenamento/consulta)
        │
        ▼
  Orquestrador (LangGraph) ─▶ logs_agent ─▶ metrics_agent ─▶ traces_agent
        │
        ▼
  timeline_agent ─▶ diagnosis_agent ─▶ verifier_agent ─▶ best_guess_agent
        │
        ▼
  plain_summary_agent ─▶ report ─▶ relatório
```

Detalhe módulo a módulo em [docs/code-architecture.md](docs/code-architecture.md).

### Fluxo do agente, passo a passo

Hoje o grafo (`agents/orchestrator.py::build_graph()`) é **linear e fixo**
— o roteamento dinâmico (orquestrador decidindo a próxima etapa e podendo
voltar a um especialista se o verificador rejeitar) é item de roadmap. A
ordem real de execução é:

1. **`orchestrator`** — ponto de entrada do grafo; hoje não decide nada
   (TODO: roteamento dinâmico).
2. **`logs_agent`**, **`metrics_agent`**, **`traces_agent`** — especialistas
   que consultam o OpenObserve e resumem a evidência de cada fonte.
3. **`timeline_agent`** — reconstrói, de forma determinística, a linha do
   tempo entre serviços (24h, serviço informado + relacionados) e segue
   cada rastro com erro até o span mais profundo que falhou — roda *antes*
   do diagnóstico porque, rodando depois, o diagnóstico só via o serviço de
   entrada e chutava o intermediário como causa.
4. **`diagnosis_agent`** — consolida as evidências e a linha do tempo em
   hipóteses de causa raiz.
5. **`verifier_agent`** — confronta as hipóteses com a evidência real
   (LLM de texto + checagem independente do `DecisionProvider`/Laya) e
   aceita ou rejeita o diagnóstico.
6. **`best_guess_agent`** — só entra em ação se o verificador não aceitou:
   obriga o LLM a dar um palpite com confiança em %, citando a cadeia de
   erro e a temporalidade, em vez de devolver "inconclusivo".
7. **`plain_summary_agent`** — traduz o resultado técnico para linguagem
   simples (causa, ações sugeridas) para quem não é especialista em
   observabilidade.
8. **`report`** — monta o prompt de correção (`fix_prompt.py`) e o
   relatório final (`report.py`), persistido em `reports/`
   (`report_store.py`).

Mais contexto de design por módulo em
[docs/code-architecture.md](docs/code-architecture.md) e a justificativa
teórica (padrão Supervisor-Trabalhador, por que LangGraph) em
[docs/architecture.md](docs/architecture.md).

## Estrutura do repositório

```
TracePilot/
├── agents/            # orquestrador LangGraph + agentes especialistas + providers de LLM
├── webapp/              # painel web (FastAPI) para monitorar e investigar
├── demo_app/           # ambiente de referência multi-serviço + cenários de falha (demo do pitch)
├── local-agent/         # agente leve em Rust (recursos do SO), instalado na máquina monitorada
├── benchmark/          # notas de avaliação (OpenRCA)
├── reports/             # investigações persistidas (JSON)
├── docs/                 # arquitetura geral, de código e glossário de conceitos
├── docker-compose.yml    # OpenObserve + OTel Collector
├── docker-compose.hostmetrics.yml  # override opt-in: métricas de host e containers
├── otel-collector-config.yaml
└── otel-collector-hostmetrics.yaml
```

> O TracePilot é composto por dois sistemas: o **coletor instalável**
> ([`local-agent/`](local-agent/), Rust, baixo impacto — recursos do
> sistema; FIM/auditoria de usuário ficam a cargo do Wazuh, ver
> [docs/local-agent-architecture.md](docs/local-agent-architecture.md))
> instalado na máquina monitorada, e o **servidor TracePilot** (este
> repositório — processamento pesado dos agentes de IA).

> A telemetria entra por **dois caminhos complementares**: o coletor
> instalável (padrão) e a **API de ingestão direta**
> ([`ingest/`](ingest/)), em que a própria aplicação manda log/span em
> JSON — para infra que não permite instalador (PaaS, serverless,
> política de segurança) e para quem quer otimizar o envio mandando só o
> essencial. A integração é feita com um
> [guia pronto para IA](docs/ai-integration-guide.md) aplicar na stack do
> cliente, servido pela própria instância em `GET /v1/guide`. Comparação
> dos dois modos em [docs/ingestion-modes.md](docs/ingestion-modes.md).

> Estágio atual: **MVP funcional com interface web**. O fluxo completo
> (logs → métricas → traces → diagnóstico → verificação → relatório) roda
> de ponta a ponta contra uma instância real do OpenObserve, com um
> painel web pra disparar investigações e fazer drill-down na evidência.
> O [ambiente de referência](demo_app/README.md) gera os incidentes e a
> telemetria correlacionada que os agentes investigam. Detalhe do que está
> implementado vs. pendente em `docs/code-architecture.md`.

## Demo completa (um comando)

```bash
scripts/demo.sh up       # telemetria + loja Apex Space + TracePilot Collector + TracePilot API + painel
scripts/demo.sh status   # confere cada serviço
scripts/demo.sh down     # derruba (o OpenObserve continua de pé)
```

Para mostrar a detecção de ataques: `scripts/simulate-attack.sh`
(robô de varredura, SQL injection, XSS, path traversal e crawler contra a
loja local) e veja o painel em até 10 s.

Abra <http://localhost:8800>. O login e a jornada vêm pré-preenchidos
(`lucas@apexspace.com.br` / `apex2026`, preset em
`webapp/presets/reference-environment.json`); ao terminar, o painel abre
com um guia em balões (reabre pelo botão **Guia**). A loja é o `demo_app/` (ambiente de referência); falhas para demonstrar em <http://localhost:8090>. Logs e
PIDs dos processos locais em `workspace/run/`. Para refazer a jornada do
zero: apague `workspace/profile.json`.

## Como rodar localmente

```bash
# 1. Subir a stack de telemetria (OpenObserve + OTel Collector)
docker compose up -d

# 2. Criar ambiente Python e instalar dependências
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Subir o ambiente de referência (loja + painel de falhas), ver abaixo
(cd demo_app && make up)

# 4. Configurar o .env (backend de LLM local via Ollama, por padrão)
cp .env.example .env
ollama pull gemma3:4b

# 5. Subir o painel web (outro terminal)
uvicorn webapp.main:app --host 127.0.0.1 --port 8800
# abra http://localhost:8800 — ligue um cenário no Chaos Control
# (http://localhost:8090), reproduza na loja e dispare a investigação
# direto pelo formulário

# (alternativa: CLI, sem o painel; --service "" busca em todos os serviços)
python3 agents/orchestrator.py "não consegui finalizar o pedido" \
  --service shop-api
```

> Ao reproduzir localmente em máquinas com pouca RAM: suba os serviços um
> de cada vez (Docker → demo_app → painel) em vez de todos juntos — já
> travou uma máquina com 19GB de RAM e pouco swap ao carregar Docker +
> modelo local + Laya tudo de uma vez.

Backend de LLM local via **Ollama** (`LLM_BACKEND=local` no `.env`,
padrão). Comece com `gemma3:4b` (~3,4GB, roda numa GPU de 4GB como a
GTX 1650) e troque só `OLLAMA_MODEL` pra testar outro. Também dá pra usar
a **OpenRouter** (`LLM_BACKEND=cloud`) se preferir backend em nuvem — ver
[openrouter.ai/models](https://openrouter.ai/models) e `.env.example`.

### Ambiente de referência (demo)

```bash
cd demo_app
make up   # telemetria (com métricas de host) + loja multi-serviço + painel de falhas
```

Loja em <http://localhost:8088>, painel de falhas em <http://localhost:8090>
e OpenObserve em <http://localhost:5080>. Roteiro da demo, cenários e
gabaritos em [demo_app/README.md](demo_app/README.md).

## Roadmap

1. Roteamento dinâmico no orquestrador (padrão Planejador-Executor — hoje
   o fluxo é linear fixo, ver `docs/code-architecture.md`).
2. ~~Construir o [ambiente de referência monitorado](docs/reference-environment.md)
   (Docker, multi-serviço, com cenários de falha controlados).~~ Primeira
   versão em [demo_app/](demo_app/README.md): 11 cenários com gabarito.
3. Avaliar com o benchmark aberto **OpenRCA**: LLM simples vs. agente único
   vs. multiagente, medindo acurácia, tempo, custo e fundamentação.
4. Laboratório próprio: correlacionar ação do usuário → falha de backend →
   relatório gerado.
5. Memória vetorial de incidentes passados (ver gaps em
   `docs/architecture.md`).
6. Coletor instalável: empacotar `local-agent/` como instalador (MSI/pkg/deb) e
   decidir, com atenção à privacidade, se/quando integrar o Wazuh para
   FIM e auditoria de usuário — ver
   [docs/local-agent-architecture.md](docs/local-agent-architecture.md).
7. API de ingestão direta: TLS/proxy reverso, *rate limit* por chave e
   amarrar cada chave de ingestão ao serviço que ela pode escrever (ver
   "Segurança" em [docs/ingestion-modes.md](docs/ingestion-modes.md)).

## Licença

A definir.
