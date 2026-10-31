//! Agente local do TracePilot: coleta métricas de recursos (CPU, memória,
//! disco) e exporta via OTLP para o `otel-collector` já existente no
//! pipeline do projeto — mesma stack que o `demo_app` já usa.
//!
//! Decisão de design: só métricas de recurso aqui. Integridade de
//! arquivos, login e execução de comando ficam para o Wazuh (ver
//! docs/local-agent-architecture.md) — este binário é deliberadamente a
//! parte de baixo risco/baixo impacto, pra rodar em qualquer máquina sem
//! implicação de privacidade.

use std::time::Duration;

use opentelemetry::metrics::MeterProvider as _;
use opentelemetry::KeyValue;
use opentelemetry_otlp::WithExportConfig;
use sysinfo::{Disks, System};

const DEFAULT_OTLP_ENDPOINT: &str = "http://localhost:4317";
const DEFAULT_INTERVAL_SECS: u64 = 10;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    tracing_subscriber::fmt::init();

    let endpoint =
        std::env::var("OTEL_EXPORTER_OTLP_ENDPOINT").unwrap_or_else(|_| DEFAULT_OTLP_ENDPOINT.to_string());
    let service_name =
        std::env::var("OTEL_SERVICE_NAME").unwrap_or_else(|_| "tracepilot-local-agent".to_string());
    let interval_secs: u64 = std::env::var("AGENT_INTERVAL_SECS")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(DEFAULT_INTERVAL_SECS);

    tracing::info!(%endpoint, %service_name, interval_secs, "iniciando tracepilot-local-agent");

    let exporter = opentelemetry_otlp::MetricExporter::builder()
        .with_tonic()
        .with_endpoint(&endpoint)
        .build()?;

    let reader = opentelemetry_sdk::metrics::PeriodicReader::builder(exporter, opentelemetry_sdk::runtime::Tokio)
        .with_interval(Duration::from_secs(interval_secs))
        .build();

    let resource = opentelemetry_sdk::Resource::new(vec![
        KeyValue::new("service.name", service_name.clone()),
        KeyValue::new("host.name", hostname()),
    ]);

    let provider = opentelemetry_sdk::metrics::SdkMeterProvider::builder()
        .with_reader(reader)
        .with_resource(resource)
        .build();

    let meter = provider.meter("tracepilot.local_agent");

    let cpu_gauge = meter
        .f64_gauge("system.cpu.usage_percent")
        .with_description("Uso médio de CPU no momento da coleta, em %")
        .build();
    let mem_used_gauge = meter
        .u64_gauge("system.memory.used_bytes")
        .with_description("Memória RAM em uso, em bytes")
        .build();
    let mem_total_gauge = meter
        .u64_gauge("system.memory.total_bytes")
        .with_description("Memória RAM total, em bytes")
        .build();
    let disk_used_gauge = meter
        .u64_gauge("system.disk.used_bytes")
        .with_description("Espaço em disco em uso, em bytes, por ponto de montagem")
        .build();
    let disk_total_gauge = meter
        .u64_gauge("system.disk.total_bytes")
        .with_description("Espaço em disco total, em bytes, por ponto de montagem")
        .build();

    let mut sys = System::new_all();
    let mut shutdown = Box::pin(tokio::signal::ctrl_c());
    let mut tick = tokio::time::interval(Duration::from_secs(interval_secs));

    loop {
        tokio::select! {
            _ = tick.tick() => {
                // Duas leituras de CPU, espaçadas, são necessárias pro sysinfo
                // calcular uso percentual de verdade (a primeira é baseline).
                sys.refresh_cpu_usage();
                tokio::time::sleep(Duration::from_millis(250)).await;
                sys.refresh_cpu_usage();
                sys.refresh_memory();

                let cpu_usage = sys.global_cpu_usage() as f64;
                cpu_gauge.record(cpu_usage, &[]);
                mem_used_gauge.record(sys.used_memory(), &[]);
                mem_total_gauge.record(sys.total_memory(), &[]);

                let disks = Disks::new_with_refreshed_list();
                for disk in disks.list() {
                    let mount = disk.mount_point().to_string_lossy().to_string();
                    let attrs = [KeyValue::new("mount_point", mount.clone())];
                    let total = disk.total_space();
                    let available = disk.available_space();
                    disk_total_gauge.record(total, &attrs);
                    disk_used_gauge.record(total.saturating_sub(available), &attrs);
                }

                tracing::debug!(cpu_usage, mem_used = sys.used_memory(), "coleta enviada");
            }
            _ = &mut shutdown => {
                tracing::info!("encerrando (ctrl-c)");
                break;
            }
        }
    }

    provider.shutdown()?;
    Ok(())
}

fn hostname() -> String {
    System::host_name().unwrap_or_else(|| "desconhecido".to_string())
}
