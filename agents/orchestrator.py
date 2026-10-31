"""Grafo de orquestração (padrão Supervisor-Trabalhador) dos agentes do
TracePilot, usando LangGraph.

Fase atual: só a fiação do grafo (nós e arestas). A lógica de decisão de
cada nó vive nos módulos de `agents.specialists`, `agents.diagnosis_agent`
e `agents.verifier_agent` — todos ainda com TODO.
"""
from typing import TypedDict

from langgraph.graph import StateGraph, END

from agents.llm import get_provider
from agents.tools.openobserve_client import OpenObserveClient
from agents.specialists import logs_agent, metrics_agent, traces_agent
from agents import diagnosis_agent, verifier_agent


class IncidentState(TypedDict, total=False):
    error_report: str
    evidence_logs: list
    evidence_metrics: list
    evidence_traces: list
    hypotheses: list
    verified: bool
    report: str


def orchestrator_node(state: IncidentState) -> IncidentState:
    """Decide qual especialista consultar em seguida, com base no que já
    foi coletado. TODO: lógica de decisão (hoje só repassa o estado).
    """
    return state


def build_graph() -> StateGraph:
    llm = get_provider()
    client = OpenObserveClient()

    graph = StateGraph(IncidentState)

    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("logs_agent", lambda s: logs_agent.run(s, llm, client))
    graph.add_node("metrics_agent", lambda s: metrics_agent.run(s, llm, client))
    graph.add_node("traces_agent", lambda s: traces_agent.run(s, llm, client))
    graph.add_node("diagnosis_agent", lambda s: diagnosis_agent.run(s, llm))
    graph.add_node("verifier_agent", lambda s: verifier_agent.run(s, llm))

    graph.set_entry_point("orchestrator")

    # TODO: hoje é um fluxo linear fixo; o objetivo é o orchestrator decidir
    # dinamicamente a próxima etapa (roteamento condicional) com base no
    # estado, inclusive voltando a um especialista se o verifier rejeitar.
    graph.add_edge("orchestrator", "logs_agent")
    graph.add_edge("logs_agent", "metrics_agent")
    graph.add_edge("metrics_agent", "traces_agent")
    graph.add_edge("traces_agent", "diagnosis_agent")
    graph.add_edge("diagnosis_agent", "verifier_agent")
    graph.add_edge("verifier_agent", END)

    return graph.compile()


if __name__ == "__main__":
    # TODO: ler um relato de erro real (ex.: via CLI ou endpoint da API) em
    # vez desse placeholder, uma vez que a lógica dos agentes existir.
    app = build_graph()
    app.invoke({"error_report": "exemplo de relato de erro"})
