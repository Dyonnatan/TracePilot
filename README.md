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
  Orquestrador (LangGraph) ─┬─▶ logs_agent
                            ├─▶ metrics_agent
                            ├─▶ traces_agent
                            ▼
                     diagnosis_agent ──▶ verifier_agent ──▶ relatório
```

Detalhe módulo a módulo em [docs/code-architecture.md](docs/code-architecture.md).

## Estrutura do repositório

```
TracePilot/
├── agents/            # orquestrador LangGraph + agentes especialistas + providers de LLM
├── webapp/              # painel web (FastAPI) para monitorar e investigar
├── demo_app/           # app FastAPI instrumentada, com falhas controladas
├── local-agent/         # coletor instalável em Rust (recursos do SO), na máquina monitorada
├── ingest/              # API de ingestão direta: a app manda log/span sem instalar nada
├── benchmark/          # notas de avaliação (OpenRCA)
├── reports/             # investigações persistidas (JSON)
├── docs/                 # arquitetura geral, de código e glossário de conceitos
├── docker-compose.yml    # OpenObserve + OTel Collector
└── otel-collector-config.yaml
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
> Detalhe do que está implementado vs. pendente em `docs/code-architecture.md`.

## Demo completa (um comando)

```bash
scripts/demo.sh up       # telemetria + loja Apex Space + TracePilot Collector + TracePilot API + painel
scripts/demo.sh status   # confere cada serviço
scripts/demo.sh down     # derruba (o OpenObserve continua de pé)
```

Abra <http://localhost:8800>. O login e a jornada vêm pré-preenchidos
(`lucas@apexspace.com.br` / `apex2026`, preset em
`webapp/presets/reference-environment.json`); ao terminar, o painel abre
com um guia em balões (reabre pelo botão **Guia**). A loja roda da branch
`feat/reference-environment` num worktree em `.worktrees/`, sem tocar na
branch atual; falhas para demonstrar em <http://localhost:8090>. Logs e
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

# 3. Rodar a aplicação de teste instrumentada (outro terminal)
cd demo_app && pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8099

# 4. Configurar o .env (backend de LLM local via Ollama, por padrão)
cp .env.example .env
ollama pull gemma3:4b

# 5. Subir o painel web (outro terminal)
uvicorn webapp.main:app --host 127.0.0.1 --port 8800
# abra http://localhost:8800 — gere uma falha no demo_app e dispare a
# investigação direto pelo formulário

# 6. (opcional) Subir a API de ingestão direta, se for integrar uma app
#     que não pode instalar o coletor (ver docs/ingestion-modes.md)
uvicorn ingest.main:app --host 127.0.0.1 --port 8810
# curl http://localhost:8810/v1/health
# curl http://localhost:8810/v1/guide   # guia de integração, em markdown

# (alternativa: CLI, sem o painel)
python3 agents/orchestrator.py "checkout falhando com erro 500" \
  --service tracepilot-demo-app
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

## Roadmap

1. Roteamento dinâmico no orquestrador (padrão Planejador-Executor — hoje
   o fluxo é linear fixo, ver `docs/code-architecture.md`).
2. Construir o [ambiente de referência monitorado](docs/reference-environment.md)
   (Docker, multi-serviço, com cenários de falha controlados) para dar
   material realista às investigações.
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
