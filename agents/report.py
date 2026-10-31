"""Monta o relatório final a partir do estado acumulado pelo grafo.

Decisão de design: a composição do relatório é determinística (sem chamada
de LLM aqui) — o conteúdo em si já foi gerado pelos agentes anteriores
(hipóteses, veredito do verificador, resumo simples, resumos de evidência).
Isso mantém o custo de inferência previsível: uma investigação completa
custa 6 chamadas de LLM (logs, métricas, traces, diagnóstico, verificação,
resumo em linguagem simples) — a composição do relatório/prompt de
correção em si não soma uma sétima.
"""


def build_report(state: dict) -> str:
    verified = state.get("verified", False)
    status = "✅ Diagnóstico sustentado por evidência" if verified else "⚠️ Evidência insuficiente — tratar como hipótese, não conclusão"

    action_lines = [f"- {a}" for a in (state.get("plain_actions") or [])] or ["(nenhuma ação sugerida)"]

    parts = [
        "# Relatório de investigação — TracePilot",
        "",
        f"**Status**: {status}",
        "",
        "## Em resumo",
        f"**Causa**: {state.get('plain_cause', '(não gerado)')}",
        "",
        "**O que fazer**:",
        *action_lines,
        "",
        "## Relato do erro",
        state.get("error_report", "(não informado)"),
        "",
        "## Causa provável — detalhe técnico (hipóteses)",
        state.get("hypotheses", "(nenhuma hipótese gerada)"),
        "",
        "## Evidências por fonte",
        f"- **Logs**: {state.get('logs_summary', '(não coletado)')}",
        f"- **Métricas**: {state.get('metrics_summary', '(não coletado)')}",
        f"- **Traces**: {state.get('traces_summary', '(não coletado)')}",
        "",
        "## Verificação",
        state.get("verification_notes", "(não executada)"),
        _decision_model_line(state),
        "",
        "## Prompt pronto para a IA corrigir",
        "```",
        state.get("fix_prompt", "(não gerado)"),
        "```",
        "",
        "## Limitações",
        (
            "Este relatório foi gerado automaticamente por um protótipo "
            "(TracePilot MVP). A hipótese acima não substitui investigação "
            "humana em incidentes críticos — trate como ponto de partida."
        ),
    ]
    return "\n".join(parts)


def _decision_model_line(state: dict) -> str:
    confidence = state.get("decision_model_confidence")
    if confidence is not None:
        return f"\n_Checagem independente (modelo de decisão Laya): {confidence:.0%} de confiança de que a hipótese está sustentada pela evidência._"
    error = state.get("decision_model_error")
    if error:
        return f"\n_Checagem independente via modelo de decisão indisponível: {error}_"
    return ""
