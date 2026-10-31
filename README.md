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
detalhes em [docs/architecture.md](docs/architecture.md).

## Arquitetura (visão rápida)

```
App instrumentada (demo_app)
        │  OpenTelemetry (traces/logs/métricas)
        ▼
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
├── demo_app/           # ambiente de referência multi-serviço + cenários de falha (demo do pitch)
├── benchmark/          # notas de avaliação (OpenRCA)
├── reports/             # relatórios de incidente gerados
├── docs/                 # arquitetura geral e de código
├── docker-compose.yml    # OpenObserve + OTel Collector
├── docker-compose.hostmetrics.yml  # override opt-in: métricas de host e containers
├── otel-collector-config.yaml
└── otel-collector-hostmetrics.yaml
```

> Estágio atual: os agentes ainda são **scaffold** (interfaces definidas,
> lógica de investigação não implementada; ver TODOs em
> `docs/code-architecture.md`). O [ambiente de referência](demo_app/README.md)
> já gera incidentes reais e telemetria correlacionada para eles investigarem.

## Como rodar localmente

```bash
# 1. Subir a stack de telemetria (OpenObserve + OTel Collector)
docker compose up -d

# 2. Criar ambiente Python e instalar dependências
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Configurações (chaves de API, backend de LLM, endpoints) ficam em `.env` —
copie `.env.example` para `.env` e preencha.

### Ambiente de referência (demo)

```bash
cd demo_app
make up   # telemetria (com métricas de host) + loja multi-serviço + painel de falhas
```

Loja em <http://localhost:8088>, painel de falhas em <http://localhost:8090>
e OpenObserve em <http://localhost:5080>. Roteiro da demo, cenários e
gabaritos em [demo_app/README.md](demo_app/README.md).

## Roadmap

1. Implementar a lógica de cada agente (coleta + raciocínio) sobre o
   `orchestrator.py`.
2. ~~Construir o [ambiente de referência monitorado](docs/reference-environment.md)
   (Docker, multi-serviço, com cenários de falha controlados).~~ Primeira
   versão em [demo_app/](demo_app/README.md): 4 cenários com
   gabarito.
3. Avaliar com o benchmark aberto **OpenRCA**: LLM simples vs. agente único
   vs. multiagente, medindo acurácia, tempo, custo e fundamentação.
4. Laboratório próprio: correlacionar ação do usuário → falha de backend →
   relatório gerado.
5. Memória vetorial de incidentes passados (ver gaps em
   `docs/architecture.md`).

## Licença

A definir.
