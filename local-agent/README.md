# tracepilot-local-agent

Agente leve (Rust) instalado na máquina monitorada: coleta CPU, memória e
disco e exporta via OTLP pro `otel-collector` do TracePilot — a mesma
stack de telemetria que o `demo_app` já usa.

Binário de release: ~2MB, sem dependência externa em runtime (não precisa
de Python/JVM instalado na máquina monitorada).

> Isto é só a parte de **recursos do sistema**. Integridade de arquivos,
> login e execução de comando ficam fora de propósito deste binário — ver
> [docs/local-agent-architecture.md](../docs/local-agent-architecture.md)
> pra por quê e o que usar nesse caso (Wazuh).

## Rodar

```bash
cargo build --release

# aponta pro otel-collector já rodando (ver docker-compose.yml na raiz)
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
export OTEL_SERVICE_NAME=tracepilot-local-agent   # ajuste por máquina
export AGENT_INTERVAL_SECS=10                      # opcional, default 10s

./target/release/tracepilot-agent
```

Métricas exportadas: `system.cpu.usage_percent`,
`system.memory.used_bytes`, `system.memory.total_bytes`,
`system.disk.used_bytes`/`system.disk.total_bytes` (por ponto de
montagem).

## Variáveis de ambiente

| Variável | Default | Descrição |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | Endpoint OTLP/gRPC do collector. |
| `OTEL_SERVICE_NAME` | `tracepilot-local-agent` | Nome do serviço nas métricas — troque por máquina/host se rodar em várias. |
| `AGENT_INTERVAL_SECS` | `10` | Intervalo de coleta/exportação, em segundos. |
| `RUST_LOG` | — | Nível de log (`info`, `debug`) via `tracing-subscriber`. |

## Status

Protótipo validado localmente (Linux) — métricas confirmadas chegando no
OpenObserve via o pipeline existente. Ainda não testado em Windows/macOS,
nem empacotado como instalador (MSI/pkg/deb) — próximos passos.
