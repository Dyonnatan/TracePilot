"""Snapshot do estado do host monitorado — CPU, memória, disco, rede e
GPU — para alimentar tanto a etapa "configurando" do onboarding quanto os
indicadores de recursos do dashboard. Um lugar só, pra não duplicar a
lógica de "pergunta pro agente, cai pra detecção local se não vier nada"
em duas telas.

Fonte de verdade preferida: as métricas que o `local-agent` (Rust) exporta
via OTLP e que acabam no OpenObserve (ver `local-agent/src/main.rs` e
`agents/tools/openobserve_client.py`). Quando isso não está disponível —
porque o agente não foi instalado, porque o OpenObserve está fora do ar, ou
porque a consulta não bate no formato real (ver TODO abaixo) — cai para
detecção local via biblioteca padrão do Python, do host onde o *painel*
está rodando (não necessariamente o mesmo host monitorado) e deixa isso
explícito em `source`, nunca inventa um número.

Formato validado contra dado real do `local-agent` no OpenObserve: um
stream por métrica, valor em `value`, `host_name` e `mount_point` como
colunas (ver `OpenObserveClient.query_metrics`).
"""
import os
import platform
import shutil
import subprocess
import threading
import time

from agents.tools.openobserve_client import OpenObserveClient

LOCAL_AGENT_SERVICE = os.getenv("LOCAL_AGENT_SERVICE_NAME", "tracepilot-local-agent")

CPU_METRIC = "system.cpu.usage_percent"
MEM_USED_METRIC = "system.memory.used_bytes"
MEM_TOTAL_METRIC = "system.memory.total_bytes"
DISK_USED_METRIC = "system.disk.used_bytes"
DISK_TOTAL_METRIC = "system.disk.total_bytes"
NET_RX_METRIC = "system.network.rx_bytes"
NET_TX_METRIC = "system.network.tx_bytes"

# Candidatos de nome de campo para o valor numérico de uma hit de métrica —
# ver TODO no topo do arquivo.
_VALUE_KEYS = ("value", "gauge_value", "_value", "sum_value")
_MOUNT_KEYS = ("mount_point", "attributes_mount_point")
_HOST_KEYS = ("host_name", "resource_host_name", "attributes_host_name")


def _leaf(value, source: str, label: str) -> dict:
    return {"value": value, "source": source, "label": label}


def _extract_numeric(hits: list[dict]) -> float | None:
    if not hits:
        return None
    hit = hits[0]
    for key in _VALUE_KEYS:
        if key in hit and isinstance(hit[key], (int, float)):
            return float(hit[key])
    return None


def _extract_text(hits: list[dict], keys: tuple[str, ...]) -> str | None:
    if not hits:
        return None
    hit = hits[0]
    for key in keys:
        value = hit.get(key)
        if isinstance(value, str) and value:
            return value
    return None


AGENT_FRESH_MINUTES = 5


def _query_agent_metrics() -> dict | None:
    """Últimos pontos de cada métrica do agente, só da janela recente
    (`AGENT_FRESH_MINUTES`) — dado velho não conta como "agente
    reportando". Cada métrica é um stream próprio no OpenObserve; uma que
    o agente não exporta (ex.: rede, hoje) não derruba as outras.
    `None` só quando o OpenObserve inteiro está inacessível.
    """
    try:
        client = OpenObserveClient()
    except Exception:
        return None
    start_us = int((time.time() - AGENT_FRESH_MINUTES * 60) * 1_000_000)
    results = {}
    failures = 0
    metrics = (
        CPU_METRIC, MEM_USED_METRIC, MEM_TOTAL_METRIC,
        DISK_USED_METRIC, DISK_TOTAL_METRIC, NET_RX_METRIC, NET_TX_METRIC,
    )
    for metric in metrics:
        try:
            results[metric] = client.query_metrics(
                metric, service=LOCAL_AGENT_SERVICE, start_time=start_us, size=10
            )
        except Exception:
            results[metric] = []
            failures += 1
    return None if failures == len(metrics) else results


def _local_disk_snapshot() -> list[dict]:
    path = "C:\\" if os.name == "nt" else "/"
    try:
        usage = shutil.disk_usage(path)
        return [
            {
                "mount_point": path,
                "used_bytes": _leaf(usage.used, "local", "detectado no host do painel"),
                "total_bytes": _leaf(usage.total, "local", "detectado no host do painel"),
            }
        ]
    except OSError:
        return []


# ---- Detecção local (host do painel) ----------------------------------
# Fallback honesto para quando o agente não reporta: lê /proc (Linux) e
# `nvidia-smi` (se existir) do host onde o *painel* roda, sempre marcado
# como `source="local"`. Em demo/hackathon o painel e o sistema monitorado
# costumam estar na mesma máquina, então isso deixa o dashboard vivo sem
# fingir que veio do agente. Fora do Linux, volta `None` (sem número).

_LOCAL_LABEL = "detectado no host do painel"
_prev_cpu: tuple[float, float] | None = None  # (idle, total) da leitura anterior
_prev_net: tuple[float, float, float] | None = None  # (t, rx, tx)
_sample_lock = threading.Lock()


def _read_proc_cpu() -> tuple[float, float] | None:
    try:
        with open("/proc/stat") as f:
            parts = f.readline().split()[1:]
        values = [float(v) for v in parts]
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        return idle, sum(values)
    except (OSError, ValueError, IndexError):
        return None


def _local_cpu_percent() -> float | None:
    """Uso de CPU entre esta leitura e a anterior. Na primeira chamada
    (sem leitura anterior) faz uma amostra curta de 150ms."""
    global _prev_cpu
    with _sample_lock:
        current = _read_proc_cpu()
        if current is None:
            return None
        previous = _prev_cpu
        if previous is None:
            time.sleep(0.15)
            previous, current = current, _read_proc_cpu()
            if current is None:
                return None
        _prev_cpu = current
    d_idle = current[0] - previous[0]
    d_total = current[1] - previous[1]
    if d_total <= 0:
        return None
    return max(0.0, min(100.0, (1 - d_idle / d_total) * 100))


def _local_memory() -> tuple[float, float] | None:
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                key, _, rest = line.partition(":")
                info[key] = float(rest.split()[0]) * 1024
        total = info["MemTotal"]
        available = info.get("MemAvailable", info.get("MemFree", 0))
        return total - available, total
    except (OSError, ValueError, KeyError, IndexError):
        return None


def _local_network_rate() -> tuple[float, float] | None:
    """Bytes/s recebidos e enviados (soma das interfaces, exceto loopback)
    desde a última leitura. Primeira chamada não tem base de comparação →
    volta None (o dashboard mostra "medindo…")."""
    global _prev_net
    try:
        rx = tx = 0.0
        with open("/proc/net/dev") as f:
            for line in f.readlines()[2:]:
                name, _, data = line.partition(":")
                if name.strip() == "lo":
                    continue
                fields = data.split()
                rx += float(fields[0])
                tx += float(fields[8])
    except (OSError, ValueError, IndexError):
        return None
    now = time.time()
    with _sample_lock:
        previous = _prev_net
        _prev_net = (now, rx, tx)
    if previous is None or now - previous[0] <= 0:
        return None
    dt = now - previous[0]
    return max(0.0, (rx - previous[1]) / dt), max(0.0, (tx - previous[2]) / dt)


def _local_gpu() -> dict | None:
    if shutil.which("nvidia-smi") is None:
        return None
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )
        first = out.stdout.strip().splitlines()[0]
        name, util, mem_used, mem_total = [p.strip() for p in first.split(",")]
        return {
            "name": name,
            "percent": float(util),
            "memory_used_bytes": float(mem_used) * 1024**2,
            "memory_total_bytes": float(mem_total) * 1024**2,
        }
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def get_resource_snapshot() -> dict:
    agent_results = _query_agent_metrics()
    agent_ok = agent_results is not None

    cpu_hits = agent_results.get(CPU_METRIC, []) if agent_ok else []
    mem_used_hits = agent_results.get(MEM_USED_METRIC, []) if agent_ok else []
    mem_total_hits = agent_results.get(MEM_TOTAL_METRIC, []) if agent_ok else []
    disk_used_hits = agent_results.get(DISK_USED_METRIC, []) if agent_ok else []
    disk_total_hits = agent_results.get(DISK_TOTAL_METRIC, []) if agent_ok else []
    net_rx_hits = agent_results.get(NET_RX_METRIC, []) if agent_ok else []
    net_tx_hits = agent_results.get(NET_TX_METRIC, []) if agent_ok else []

    host_name = _extract_text(cpu_hits, _HOST_KEYS)
    cpu_percent = _extract_numeric(cpu_hits)
    mem_used = _extract_numeric(mem_used_hits)
    mem_total = _extract_numeric(mem_total_hits)

    disk_mounts = []
    if disk_total_hits:
        by_mount: dict[str, dict] = {}
        for hit in disk_total_hits:
            mount = _extract_text([hit], _MOUNT_KEYS) or "/"
            by_mount.setdefault(mount, {})["total"] = _extract_numeric([hit])
        for hit in disk_used_hits:
            mount = _extract_text([hit], _MOUNT_KEYS) or "/"
            by_mount.setdefault(mount, {})["used"] = _extract_numeric([hit])
        for mount, values in by_mount.items():
            disk_mounts.append(
                {
                    "mount_point": mount,
                    "used_bytes": _leaf(values.get("used"), "agent", "via agente local"),
                    "total_bytes": _leaf(values.get("total"), "agent", "via agente local"),
                }
            )

    net_rx = _extract_numeric(net_rx_hits)
    net_tx = _extract_numeric(net_tx_hits)

    if cpu_percent is not None:
        cpu_leaf = _leaf(cpu_percent, "agent", "via agente local")
    else:
        local_cpu = _local_cpu_percent()
        cpu_leaf = (
            _leaf(local_cpu, "local", _LOCAL_LABEL)
            if local_cpu is not None
            else _leaf(None, "unavailable", "sem dados do agente ainda")
        )

    if mem_used is not None and mem_total is not None:
        mem_used_leaf = _leaf(mem_used, "agent", "via agente local")
        mem_total_leaf = _leaf(mem_total, "agent", "via agente local")
    else:
        local_mem = _local_memory()
        if local_mem is not None:
            mem_used_leaf = _leaf(local_mem[0], "local", _LOCAL_LABEL)
            mem_total_leaf = _leaf(local_mem[1], "local", _LOCAL_LABEL)
        else:
            mem_used_leaf = _leaf(None, "unavailable", "sem dados do agente ainda")
            mem_total_leaf = _leaf(None, "unavailable", "sem dados do agente ainda")

    # O agente exporta contadores acumulados; a taxa (bytes/s) só faz
    # sentido localmente, onde guardamos a leitura anterior.
    local_rate = _local_network_rate()
    if local_rate is not None:
        rate_rx = _leaf(local_rate[0], "local", _LOCAL_LABEL)
        rate_tx = _leaf(local_rate[1], "local", _LOCAL_LABEL)
    else:
        rate_rx = _leaf(None, "unavailable", "medindo…")
        rate_tx = _leaf(None, "unavailable", "medindo…")

    gpu = _local_gpu()
    if gpu is not None:
        gpu_leaf = {
            "value": gpu["percent"],
            "source": "local",
            "label": _LOCAL_LABEL,
            "name": gpu["name"],
            "memory_used_bytes": gpu["memory_used_bytes"],
            "memory_total_bytes": gpu["memory_total_bytes"],
        }
    else:
        gpu_leaf = _leaf(None, "not_collected", "nenhuma GPU NVIDIA detectada")

    disk_source = "agent" if disk_mounts else "unavailable"
    if not disk_mounts:
        disk_mounts = _local_disk_snapshot()
        disk_source = "local" if disk_mounts else "unavailable"

    snapshot = {
        "checked_at": time.time(),
        "host_name": (
            _leaf(host_name, "agent", "via agente local")
            if host_name
            else _leaf(platform.node() or None, "local", "detectado no host do painel")
        ),
        "cpu": {
            "percent": cpu_leaf,
            "core_count": _leaf(os.cpu_count(), "local", "detectado no host do painel"),
        },
        "memory": {
            "used_bytes": mem_used_leaf,
            "total_bytes": mem_total_leaf,
        },
        "disk": {
            "mounts": disk_mounts,
            "source": disk_source,
        },
        "network": {
            "rx_bytes": (
                _leaf(net_rx, "agent", "via agente local")
                if net_rx is not None
                else _leaf(None, "unavailable", "sem dados do agente ainda")
            ),
            "tx_bytes": (
                _leaf(net_tx, "agent", "via agente local")
                if net_tx is not None
                else _leaf(None, "unavailable", "sem dados do agente ainda")
            ),
            "rx_rate": rate_rx,
            "tx_rate": rate_tx,
        },
        "gpu": gpu_leaf,
    }
    return snapshot


def agent_is_reporting(snapshot: dict) -> bool:
    leaves = [
        snapshot["host_name"],
        snapshot["cpu"]["percent"],
        snapshot["memory"]["used_bytes"],
        snapshot["memory"]["total_bytes"],
        snapshot["network"]["rx_bytes"],
        snapshot["network"]["tx_bytes"],
    ]
    if snapshot["disk"]["source"] == "agent":
        return True
    return any(leaf["source"] == "agent" for leaf in leaves)
