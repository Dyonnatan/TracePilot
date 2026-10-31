from agents.llm import LLMProvider

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

Responda no formato exato:

VEREDITO: SUPORTADO
ou
VEREDITO: INSUFICIENTE

seguido de uma linha "NOTAS:" explicando, em até 3 frases, por que cada
hipótese foi aceita ou rejeitada e, se insuficiente, o que precisaria ser
investigado a mais (qual fonte consultar de novo)."""


def run(state: dict, llm: LLMProvider) -> dict:
    verdict_text = llm.generate(
        prompt=PROMPT_TEMPLATE.format(
            hypotheses=state.get("hypotheses", "(nenhuma hipótese gerada)"),
            logs_summary=state.get("logs_summary", "(não coletado)"),
            metrics_summary=state.get("metrics_summary", "(não coletado)"),
            traces_summary=state.get("traces_summary", "(não coletado)"),
        ),
        system=SYSTEM_PROMPT,
    )
    verified = verdict_text.strip().upper().startswith("VEREDITO: SUPORTADO")
    return {**state, "verified": verified, "verification_notes": verdict_text}
