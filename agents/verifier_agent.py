from agents.llm import LLMProvider
from agents.llm.decision_provider import DecisionProvider

SYSTEM_PROMPT = (
    "Você é o verificador final de um diagnóstico de incidente. Seu único "
    "trabalho é checar se as hipóteses abaixo estão realmente sustentadas "
    "pelos resumos de evidência, ou se são especulação não sustentada. "
    "Seja rigoroso: uma hipótese plausível mas sem evidência citada deve "
    "ser rejeitada."
)

PROMPT_TEMPLATE = """Hipóteses propostas pelo diagnóstico:
{hypotheses}

Evidência disponível:
- Logs: {logs_summary}
- Métricas: {metrics_summary}
- Traces: {traces_summary}
- Cadeia do erro entre serviços e linha do tempo:
{deep_dive_digest}

Responda no formato exato:

VEREDITO: SUPORTADO
ou
VEREDITO: INSUFICIENTE

seguido de uma linha "NOTAS:" explicando, em até 3 frases, por que cada
hipótese foi aceita ou rejeitada e, se insuficiente, o que precisaria ser
investigado a mais (qual fonte consultar de novo)."""

DECISION_INSTRUCTIONS = (
    "A hipótese de causa-raiz proposta está diretamente sustentada pelas "
    "evidências de logs, métricas e traces descritas no texto?"
)


def run(state: dict, llm: LLMProvider, decision: DecisionProvider | None = None) -> dict:
    verdict_text = llm.generate(
        prompt=PROMPT_TEMPLATE.format(
            hypotheses=state.get("hypotheses", "(nenhuma hipótese gerada)"),
            logs_summary=state.get("logs_summary", "(não coletado)"),
            metrics_summary=state.get("metrics_summary", "(não coletado)"),
            traces_summary=state.get("traces_summary", "(não coletado)"),
            deep_dive_digest=state.get("deep_dive_digest", "(não coletado)"),
        ),
        system=SYSTEM_PROMPT,
    )
    verified = verdict_text.strip().upper().startswith("VEREDITO: SUPORTADO")

    result = {**state, "verified": verified, "verification_notes": verdict_text}

    # Checagem independente via modelo de decisão (Laya) — não substitui o
    # veredito do LLM acima (que também gera as notas explicativas do
    # relatório), serve de segundo sinal que não depende de o LLM "escrever
    # certo" o veredito. Best-effort: se o Laya não estiver disponível, a
    # investigação segue normalmente sem esse campo.
    if decision is None:
        decision = DecisionProvider()
    try:
        state_text = (
            f"Hipóteses: {state.get('hypotheses', '')}\n\n"
            f"Logs: {state.get('logs_summary', '')}\n"
            f"Métricas: {state.get('metrics_summary', '')}\n"
            f"Traces: {state.get('traces_summary', '')}"
        )
        result["decision_model_confidence"] = decision.yes_no(state_text, DECISION_INSTRUCTIONS)
    except Exception as exc:
        result["decision_model_confidence"] = None
        result["decision_model_error"] = str(exc)

    return result
