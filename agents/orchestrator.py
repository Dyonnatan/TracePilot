"""Grafo de orquestração (padrão Supervisor-Trabalhador) dos agentes do
TracePilot, usando LangGraph.

Fluxo atual: linear e fixo (orchestrator → logs → metrics → traces →
diagnosis → verifier → report). O roteamento dinâmico (orchestrator
decidindo qual especialista consultar e podendo voltar a um deles se o
verifier rejeitar o diagnóstico) fica para uma próxima iteração — ver
docs/code-architecture.md.
"""
import argparse
import json
import time
from typing import TypedDict

from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

from agents.llm import get_provider
from agents.llm.decision_provider import DecisionProvider
from agents.tools.openobserve_client import OpenObserveClient
from agents.specialists import logs_agent, metrics_agent, traces_agent
from agents import diagnosis_agent, verifier_agent, plain_summary_agent
from agents.report import build_report
from agents.fix_prompt import build_fix_prompt
from agents import report_store

# CLI e webapp importam este módulo antes de ler qualquer variável; o .env
# não sobrescreve o que já estiver exportado no shell.
load_dotenv()

# Padrões apontam para o ambiente de referência (demo_app): o shop-api é a
# porta de entrada dos relatos de usuário. Serviço vazio busca em todos, útil
# quando a evidência está numa dependência (ex.: payment-service).
DEFAULT_SERVICE = "shop-api"
DEFAULT_METRIC = "shop_checkout_requests"


class IncidentState(TypedDict, total=False):
    error_report: str
    service: str
    trace_id: str
    metric_name: str
    start_time: int
    end_time: int
    evidence_logs: list
    evidence_metrics: list
    evidence_traces: list
    logs_summary: str
    metrics_summary: str
    traces_summary: str
    hypotheses: str
    verified: bool
    verification_notes: str
    decision_model_confidence: float | None
    decision_model_error: str
    plain_cause: str
    plain_actions: list
    fix_prompt: str
    report: str


def orchestrator_node(state: IncidentState) -> IncidentState:
    """Ponto de entrada do grafo. TODO: decidir dinamicamente a próxima
    etapa (hoje o roteamento é fixo, ver arestas em build_graph()).
    """
    return state


def report_node(state: IncidentState) -> IncidentState:
    state = {**state, "fix_prompt": build_fix_prompt(state)}
    return {**state, "report": build_report(state)}


def build_graph() -> StateGraph:
    llm = get_provider()
    client = OpenObserveClient()
    decision = DecisionProvider()

    graph = StateGraph(IncidentState)

    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("logs_agent", lambda s: logs_agent.run(s, llm, client))
    graph.add_node("metrics_agent", lambda s: metrics_agent.run(s, llm, client))
    graph.add_node("traces_agent", lambda s: traces_agent.run(s, llm, client))
    graph.add_node("diagnosis_agent", lambda s: diagnosis_agent.run(s, llm))
    graph.add_node("verifier_agent", lambda s: verifier_agent.run(s, llm, decision))
    graph.add_node("plain_summary_agent", lambda s: plain_summary_agent.run(s, llm))
    graph.add_node("report", report_node)

    graph.set_entry_point("orchestrator")

    # TODO: hoje é um fluxo linear fixo; o objetivo é o orchestrator decidir
    # dinamicamente a próxima etapa (roteamento condicional) com base no
    # estado, inclusive voltando a um especialista se o verifier rejeitar.
    graph.add_edge("orchestrator", "logs_agent")
    graph.add_edge("logs_agent", "metrics_agent")
    graph.add_edge("metrics_agent", "traces_agent")
    graph.add_edge("traces_agent", "diagnosis_agent")
    graph.add_edge("diagnosis_agent", "verifier_agent")
    graph.add_edge("verifier_agent", "plain_summary_agent")
    graph.add_edge("plain_summary_agent", "report")
    graph.add_edge("report", END)

    return graph.compile()


def run_investigation(
    error_report: str,
    service: str | None = DEFAULT_SERVICE,
    trace_id: str | None = None,
    metric_name: str = DEFAULT_METRIC,
    window_minutes: int = 60,
    investigation_id: str | None = None,
) -> dict:
    """Roda uma investigação completa e persiste o resultado em `reports/`.

    Função reutilizável por quem for chamar os agentes fora da CLI (ex.: o
    `webapp/`) — mantém a lógica de montar o estado inicial, invocar o
    grafo e salvar o resultado num único lugar, em vez de duplicá-la.
    """
    investigation_id = investigation_id or report_store.new_investigation_id()
    now_us = int(time.time() * 1_000_000)
    start_us = now_us - window_minutes * 60 * 1_000_000

    initial_state: IncidentState = {
        "error_report": error_report,
        "metric_name": metric_name,
        "start_time": start_us,
        "end_time": now_us,
    }
    if service:
        initial_state["service"] = service
    if trace_id:
        initial_state["trace_id"] = trace_id

    report_store.save(
        investigation_id,
        {
            "id": investigation_id,
            "status": "running",
            "created_at": time.time(),
            "error_report": error_report,
            "service": service,
        },
    )

    try:
        final_state = build_graph().invoke(initial_state)
    except Exception as exc:
        record = {
            "id": investigation_id,
            "status": "error",
            "created_at": time.time(),
            "error_report": error_report,
            "service": service,
            "error": str(exc),
        }
        report_store.save(investigation_id, record)
        raise

    record = {
        "id": investigation_id,
        "status": "done",
        "created_at": time.time(),
        **final_state,
    }
    report_store.save(investigation_id, record)
    return record


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Investiga um incidente com os agentes do TracePilot.")
    parser.add_argument("error_report", help="Relato do erro (ex.: mensagem do usuário ou do endpoint).")
    parser.add_argument(
        "--service", default=DEFAULT_SERVICE, help="Nome do serviço a investigar (vazio = todos os serviços)."
    )
    parser.add_argument("--trace-id", default=None, help="trace_id específico, se já conhecido.")
    parser.add_argument(
        "--metric-name", default=DEFAULT_METRIC, help="Métrica a consultar (nome do stream no OpenObserve)."
    )
    parser.add_argument("--window-minutes", type=int, default=60, help="Janela de busca, em minutos, a partir de agora.")
    parser.add_argument("--json", action="store_true", help="Imprime o estado final completo em JSON em vez do relatório formatado.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    record = run_investigation(
        error_report=args.error_report,
        service=args.service,
        trace_id=args.trace_id,
        metric_name=args.metric_name,
        window_minutes=args.window_minutes,
    )

    if args.json:
        print(json.dumps(record, default=str, ensure_ascii=False, indent=2))
    else:
        print(record["report"])


if __name__ == "__main__":
    main()
