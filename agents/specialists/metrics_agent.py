from agents.evidence_format import format_metrics
from agents.llm import LLMProvider
from agents.tools.openobserve_client import OpenObserveClient

SYSTEM_PROMPT = (
    "Você é um especialista em métricas investigando um incidente de "
    "produção. Resuma, em português, apenas o que está nas métricas "
    "fornecidas abaixo. Nunca invente informação que não esteja nos dados. "
    "Se não houver métricas relevantes, diga isso explicitamente."
)

PROMPT_TEMPLATE = """Relato do erro investigado: {error_report}

Métricas coletadas:
{metrics}

Resuma em até 4 frases: há sinal de saturação de recurso, latência ou taxa
de erro anômala relacionada a esse incidente? Se não houver dado de
métricas disponível, diga isso em vez de especular."""


def run(state: dict, llm: LLMProvider, client: OpenObserveClient) -> dict:
    metric_name = state.get("metric_name", "duration")
    try:
        metrics = client.query_metrics(
            metric_name=metric_name,
            service=state.get("service"),
            start_time=state.get("start_time"),
            end_time=state.get("end_time"),
            size=20,
        )
    except Exception:
        # query_metrics ainda não foi validado contra dado real (ver TODO em
        # agents/tools/openobserve_client.py) — se a instância de OpenObserve
        # não tiver stream de métricas, tratamos como "sem evidência" em vez
        # de derrubar a investigação inteira.
        metrics = []

    summary = llm.generate(
        prompt=PROMPT_TEMPLATE.format(
            error_report=state.get("error_report", "(não informado)"),
            metrics=format_metrics(metrics),
        ),
        system=SYSTEM_PROMPT,
    )
    return {**state, "evidence_metrics": metrics, "metrics_summary": summary}
