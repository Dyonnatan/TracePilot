"""Monta o relatório final a partir do estado acumulado pelo grafo.

Decisão de design: a composição do relatório é determinística (sem chamada
de LLM) — todo o conteúdo já foi gerado pelos agentes anteriores
(hipóteses, veredito do verificador, resumos). Isso mantém o custo de
inferência previsível: uma investigação custa no máximo 5 chamadas de LLM
(logs, métricas, traces, diagnóstico, verificação), não 6.
"""


def build_report(state: dict) -> str:
    verified = state.get("verified", False)
    status = "✅ Diagnóstico sustentado por evidência" if verified else "⚠️ Evidência insuficiente — tratar como hipótese, não conclusão"

    parts = [
        "# Relatório de investigação — TracePilot",
        "",
        f"**Status**: {status}",
        "",
        "## Relato do erro",
        state.get("error_report", "(não informado)"),
        "",
        "## Causa provável (hipóteses)",
        state.get("hypotheses", "(nenhuma hipótese gerada)"),
        "",
        "## Evidências por fonte",
        f"- **Logs**: {state.get('logs_summary', '(não coletado)')}",
        f"- **Métricas**: {state.get('metrics_summary', '(não coletado)')}",
        f"- **Traces**: {state.get('traces_summary', '(não coletado)')}",
        "",
        "## Verificação",
        state.get("verification_notes", "(não executada)"),
        "",
        "## Limitações",
        (
            "Este relatório foi gerado automaticamente por um protótipo "
            "(TracePilot MVP). A hipótese acima não substitui investigação "
            "humana em incidentes críticos — trate como ponto de partida."
        ),
    ]
    return "\n".join(parts)
