"""Monta um prompt pronto para colar numa IA de código (Claude Code,
Cursor etc.) corrigir o problema.

Decisão de design: composição determinística (sem LLM) — os dados mais
valiosos aqui (arquivo, função, linha, stacktrace) já vêm prontos e exatos
no log de erro (ver `code_file_path`/`code_function_name`/
`code_line_number`/`exception_stacktrace` em
`agents/tools/openobserve_client.py`); reescrever isso via LLM só
arriscaria perder precisão sem ganhar nada.
"""

MAX_STACKTRACE_CHARS = 2000


def _find_stacktrace_log(evidence_logs: list) -> dict | None:
    for log in evidence_logs or []:
        if log.get("exception_stacktrace"):
            return log
    return None


def build_fix_prompt(state: dict) -> str:
    error_log = _find_stacktrace_log(state.get("evidence_logs") or [])

    parts = [
        "Investigue e corrija o bug a seguir, identificado automaticamente "
        "pelo TracePilot a partir de logs/traces de produção.",
        "",
        f"Relato original do problema: {state.get('error_report', '(não informado)')}",
        f"Serviço: {state.get('service', '(não informado)')}",
        "",
        "Diagnóstico (causa provável, já verificada contra a evidência):",
        state.get("hypotheses", "(nenhuma hipótese gerada)"),
    ]

    if error_log:
        parts += [
            "",
            f"Exceção: {error_log.get('exception_type', '?')}: {error_log.get('exception_message', '?')}",
        ]
        if error_log.get("code_file_path"):
            parts.append(
                f"Local no código: {error_log['code_file_path']}"
                f", função `{error_log.get('code_function_name', '?')}`"
                f", linha {error_log.get('code_line_number', '?')}"
            )
        if error_log.get("exception_stacktrace"):
            trace = error_log["exception_stacktrace"][:MAX_STACKTRACE_CHARS]
            parts += ["", "Stacktrace completo:", "```", trace, "```"]

    parts += [
        "",
        "O que fazer:",
        "1. Leia o arquivo e a função indicados acima antes de propor a correção.",
        "2. Corrija a causa raiz, não só o sintoma (ex.: não é só evitar o "
        "crash — trate a condição que leva a ele).",
        "3. Adicione (ou atualize) um teste automatizado que cobre o caso "
        "que causou esse erro, para não regredir.",
        "4. Explique em 1-2 frases, em português simples, o que mudou — "
        "essa explicação será lida por alguém que não é de TI.",
    ]
    return "\n".join(parts)
