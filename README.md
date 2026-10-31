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
├── demo_app/           # app FastAPI instrumentada, com falhas controladas
├── benchmark/          # notas de avaliação (OpenRCA)
├── reports/             # relatórios de incidente gerados
├── docs/                 # arquitetura geral e de código
├── docker-compose.yml    # OpenObserve + OTel Collector
└── otel-collector-config.yaml
```

> Estágio atual: **scaffold**. Estrutura e interfaces definidas, lógica de
> investigação ainda não implementada (ver TODOs em `docs/code-architecture.md`).

## Como rodar localmente

```bash
# 1. Subir a stack de telemetria (OpenObserve + OTel Collector)
docker compose up -d

# 2. Criar ambiente Python e instalar dependências
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Rodar a aplicação de teste instrumentada
cd demo_app && pip install -r requirements.txt
uvicorn main:app --reload
```

Configurações (chaves de API, backend de LLM, endpoints) ficam em `.env` —
copie `.env.example` para `.env` e preencha.

## Roadmap

1. Implementar a lógica de cada agente (coleta + raciocínio) sobre o
   `orchestrator.py`.
2. Avaliar com o benchmark aberto **OpenRCA**: LLM simples vs. agente único
   vs. multiagente, medindo acurácia, tempo, custo e fundamentação.
3. Laboratório próprio: correlacionar ação do usuário → falha de backend →
   relatório gerado.
4. Memória vetorial de incidentes passados (ver gaps em
   `docs/architecture.md`).

## Licença

A definir.
