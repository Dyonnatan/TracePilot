"""Traduz o diagnóstico técnico (hipóteses + verificação) para linguagem
simples: causa em 1-2 frases e uma lista curta de ações — pensado pra quem
não é de TI (o "dono" da aplicação) decidir o que fazer em segundos, sem
precisar ler o relatório técnico completo.
"""
import re

from agents.llm import LLMProvider

SYSTEM_PROMPT = (
    "Você explica problemas técnicos de TI para pessoas que NÃO são de TI "
    "(donas de um negócio, não programadoras). Seja extremamente direto e "
    "curto. Pode usar um termo técnico quando for o nome exato do "
    "problema, mas sempre seguido de uma explicação breve entre "
    "parênteses, em linguagem do dia a dia — por exemplo 'ZeroDivisionError "
    "(o sistema tentou dividir um número por zero, o que é impossível)'. "
    "Nunca escreva parágrafos longos. Nunca invente causa ou ação que não "
    "esteja apoiada no diagnóstico fornecido. Nunca mencione nomes internos "
    "de sistema como 'especialista em logs/métricas/traces', 'agente' ou "
    "'TracePilot' — fale só da causa real e da ação prática."
)

PROMPT_TEMPLATE = """Diagnóstico técnico já concluído:

Hipóteses: {hypotheses}

Verificação: {verification_notes}

Escreva EXATAMENTE neste formato (sem nada antes ou depois):

CAUSA: <1 frase curta explicando o que aconteceu, para alguém sem conhecimento técnico>
ACAO: <uma única ação concreta e específica — o que a pessoa deve pedir ao desenvolvedor/IA para corrigir>

Só escreva uma segunda linha ACAO se for uma ação realmente diferente e
necessária (ex.: validar uma entrada, além de corrigir o cálculo) — nunca
repita a mesma ideia com palavras diferentes. Máximo 2 linhas ACAO."""

_LINE_RE = re.compile(r"^(CAUSA|ACAO)\s*:\s*(.+)$", re.IGNORECASE)


def _parse(text: str) -> tuple[str, list[str]]:
    cause = ""
    actions: list[str] = []
    for line in text.splitlines():
        match = _LINE_RE.match(line.strip())
        if not match:
            continue
        kind, value = match.group(1).upper(), match.group(2).strip()
        if kind == "CAUSA" and not cause:
            cause = value
        elif kind == "ACAO":
            actions.append(value)
    if not cause and not actions:
        # Modelo não seguiu o formato — degrada graciosamente em vez de
        # mostrar uma seção vazia: usa o texto bruto como causa.
        cause = text.strip()[:400]
    return cause, actions


def run(state: dict, llm: LLMProvider) -> dict:
    raw = llm.generate(
        prompt=PROMPT_TEMPLATE.format(
            hypotheses=state.get("hypotheses", "(nenhuma hipótese gerada)"),
            verification_notes=state.get("verification_notes", "(não executada)"),
        ),
        system=SYSTEM_PROMPT,
    )
    cause, actions = _parse(raw)
    return {**state, "plain_cause": cause, "plain_actions": actions}
