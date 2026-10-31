from agents.evidence_format import format_traces
from agents.llm import LLMProvider
from agents.tools.openobserve_client import OpenObserveClient

SYSTEM_PROMPT = (
    "Você é um especialista em traces distribuídos investigando um "
    "incidente de produção. Resuma, em português, apenas o que está nos "
    "spans fornecidos abaixo. Nunca invente informação que não esteja nos "
    "dados. Se não houver spans relevantes, diga isso explicitamente."
)

PROMPT_TEMPLATE = """Relato do erro investigado: {error_report}

Spans coletados (mais recentes primeiro):
{traces}

Resuma em até 4 frases: em qual operação/span o erro se originou, qual a
exceção registrada (se houver) e se a cadeia de spans aponta para um ponto
específico do código como causa."""


def run(state: dict, llm: LLMProvider, client: OpenObserveClient) -> dict:
    traces = client.query_traces(
        trace_id=state.get("trace_id"),
        service=state.get("service"),
        only_errors=state.get("trace_id") is None,
        start_time=state.get("start_time"),
        end_time=state.get("end_time"),
        size=20,
    )
    summary = llm.generate(
        prompt=PROMPT_TEMPLATE.format(
            error_report=state.get("error_report", "(não informado)"),
            traces=format_traces(traces),
        ),
        system=SYSTEM_PROMPT,
    )
    return {**state, "evidence_traces": traces, "traces_summary": summary}
