from agents.llm import LLMProvider

SYSTEM_PROMPT = (
    "Você consolida evidências de logs, métricas e traces em hipóteses de "
    "causa-raiz de um incidente de produção. Baseie-se SOMENTE nos resumos "
    "fornecidos abaixo — nunca invente uma causa que não esteja sustentada "
    "por eles. Se a evidência for insuficiente para qualquer hipótese "
    "concreta, diga isso explicitamente em vez de forçar uma conclusão."
)

PROMPT_TEMPLATE = """Relato do erro investigado: {error_report}

Resumo do especialista em logs:
{logs_summary}

Resumo do especialista em métricas:
{metrics_summary}

Resumo do especialista em traces:
{traces_summary}

Investigação entre serviços (cadeia do erro e linha do tempo, dados brutos):
{deep_dive_digest}

Num erro 500/502, a causa costuma estar no span MAIS PROFUNDO que falhou
(numa dependência), não no serviço que devolveu o erro ao usuário nem num
intermediário (proxy, balanceador). Prefira essa origem quando ela existir.

Liste de 1 a 3 hipóteses de causa-raiz, da mais para a menos provável.
Para cada uma, no formato:

N. <hipótese> — confiança: <alta/média/baixa> — evidência: <qual resumo acima sustenta>

Se não houver evidência suficiente para nenhuma hipótese, responda apenas:
"SEM EVIDÊNCIA SUFICIENTE: <o que falta investigar>"."""


def run(state: dict, llm: LLMProvider) -> dict:
    hypotheses = llm.generate(
        prompt=PROMPT_TEMPLATE.format(
            error_report=state.get("error_report", "(não informado)"),
            logs_summary=state.get("logs_summary", "(não coletado)"),
            metrics_summary=state.get("metrics_summary", "(não coletado)"),
            traces_summary=state.get("traces_summary", "(não coletado)"),
            deep_dive_digest=state.get("deep_dive_digest", "(não coletado)"),
        ),
        system=SYSTEM_PROMPT,
    )
    return {**state, "hypotheses": hypotheses}
