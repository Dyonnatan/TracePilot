from agents.evidence_format import format_logs
from agents.llm import LLMProvider
from agents.tools.openobserve_client import OpenObserveClient

SYSTEM_PROMPT = (
    "Você é um especialista em logs investigando um incidente de produção. "
    "Resuma, em português, apenas o que está nos logs fornecidos abaixo. "
    "Nunca invente informação que não esteja nos dados. Se os logs não "
    "tiverem nada relevante, diga isso explicitamente em vez de especular."
)

PROMPT_TEMPLATE = """Relato do erro investigado: {error_report}

Logs coletados (mais recentes primeiro):
{logs}

Resuma em até 4 frases: o que os logs mostram sobre esse erro (mensagens,
severidade, exceções) e se há evidência suficiente para apontar uma causa."""


def run(state: dict, llm: LLMProvider, client: OpenObserveClient) -> dict:
    logs = client.query_logs(
        query_text=state.get("error_report"),
        service=state.get("service"),
        trace_id=state.get("trace_id"),
        start_time=state.get("start_time"),
        end_time=state.get("end_time"),
        size=20,
    )
    summary = llm.generate(
        prompt=PROMPT_TEMPLATE.format(
            error_report=state.get("error_report", "(não informado)"),
            logs=format_logs(logs),
        ),
        system=SYSTEM_PROMPT,
    )
    return {**state, "evidence_logs": logs, "logs_summary": summary}
