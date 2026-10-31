"""Avaliação piloto no OpenRCA (sistema Telecom) — pipeline TracePilot adaptado.

O que é: roda o mesmo desenho do TracePilot (ferramentas determinísticas que
filtram a telemetria -> especialistas por fonte -> diagnóstico -> verificador)
sobre casos do dataset OpenRCA/Telecom e pontua com a MESMA regra estrita do
benchmark: um caso só conta como acerto se todos os elementos pedidos na
pergunta (horário em <=1 min, componente, motivo) estiverem corretos.

Limitações conscientes (declarar ao divulgar):
  - só o sistema Telecom (51 casos), só telemetria de métricas (os traces de
    ~1 GB/dia ficaram de fora); o benchmark original usa também traces;
  - modelo pequeno e local; sem busca de hiperparâmetros;
  - não é a mesma configuração do paper -> comparar com cautela.

Uso:
  python benchmark/openrca_pilot.py --n 15 --out benchmark/results/pilot.jsonl
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from agents.llm.local_provider import LocalProvider  # noqa: E402

DATA = ROOT / "benchmark" / "openrca-data" / "Telecom"
TZ = timezone(timedelta(hours=8))  # o dataset usa UTC+8
REASONS = ["CPU fault", "network delay", "network loss", "db connection limit", "db close"]

_cache: dict[str, dict[str, pd.DataFrame]] = {}


def tok(text: str) -> int:
    return max(1, len(text) // 4)  # estimativa grosseira de tokens


def load_day(date: str) -> dict[str, pd.DataFrame]:
    if date in _cache:
        return _cache[date]
    d = DATA / "telemetry" / date.replace("-", "_") / "metric"
    frames = {}
    for key in ("container", "node", "service", "middleware"):
        df = pd.read_csv(d / f"metric_{key}.csv", usecols=["name", "timestamp", "value", "cmdb_id"])
        df["t"] = df["timestamp"] // 1000
        frames[key] = df
    app = pd.read_csv(d / "metric_app.csv")
    app["t"] = app["startTime"] // 1000
    frames["app"] = app
    _cache.clear()
    _cache[date] = frames
    return frames


def parse_window(instruction: str):
    day = datetime.strptime(re.search(r"([A-Z][a-z]+ \d{1,2}, \d{4})", instruction).group(1), "%B %d, %Y")
    t = re.findall(r"(\d{1,2}):(\d{2})", instruction)
    a = day.replace(hour=int(t[0][0]), minute=int(t[0][1]), tzinfo=TZ)
    b = day.replace(hour=int(t[1][0]), minute=int(t[1][1]), tzinfo=TZ)
    return a, b


def anomalies(df: pd.DataFrame, t0: int, t1: int, group_cols=("cmdb_id", "name")):
    """Ferramenta determinística: pontua desvio da janela contra a linha de base do dia."""
    out = []
    for key, g in df.groupby(list(group_cols)):
        w = g[(g["t"] >= t0) & (g["t"] <= t1)]
        b = g[(g["t"] < t0 - 300) | (g["t"] > t1 + 300)]
        if len(w) < 3 or len(b) < 20:
            continue
        med = float(b["value"].median())
        mad = float((b["value"] - med).abs().median()) * 1.4826
        sig = max(mad, 0.05 * abs(med), 1e-6)
        z = (w["value"] - med) / sig
        score = float(abs(z.median()))
        peak = float(z.abs().max())
        hit = w[z.abs() > 4]
        onset = int(hit["t"].min()) if len(hit) else None
        out.append({"cmdb_id": key[0], "metric": key[1], "base": med, "win": float(w["value"].median()),
                    "score": score, "peak": peak, "onset": onset})
    out.sort(key=lambda r: -(r["score"] + 0.1 * r["peak"]))
    return out


def fmt(rows, k=8):
    lines = []
    for r in rows[:k]:
        on = datetime.fromtimestamp(r["onset"], TZ).strftime("%H:%M:%S") if r["onset"] else "-"
        lines.append(f'{r["cmdb_id"]} {r["metric"]}: base={r["base"]:.3g} janela={r["win"]:.3g} z={r["score"]:.1f} inicio={on}')
    return "\n".join(lines) or "(sem anomalia relevante)"


def app_anomalies(app: pd.DataFrame, t0: int, t1: int):
    out = []
    for name, g in app.groupby("serviceName"):
        w = g[(g["t"] >= t0) & (g["t"] <= t1)]
        b = g[(g["t"] < t0 - 300) | (g["t"] > t1 + 300)]
        if len(w) < 2 or len(b) < 10:
            continue
        for col in ("avg_time", "succee_rate"):
            med = float(b[col].median())
            mad = float((b[col] - med).abs().median()) * 1.4826
            sig = max(mad, 0.05 * abs(med), 1e-6)
            out.append({"cmdb_id": name, "metric": col, "base": med, "win": float(w[col].median()),
                        "score": float(abs((w[col].median() - med) / sig)), "peak": 0.0, "onset": None})
    out.sort(key=lambda r: -r["score"])
    return out


def run_case(llm: LocalProvider, q: dict):
    t_start = time.time()
    a, b = parse_window(q["instruction"])
    t0, t1 = int(a.timestamp()), int(b.timestamp())
    frames = load_day(a.strftime("%Y-%m-%d"))
    naive_rows = sum(int(((f["t"] >= t0) & (f["t"] <= t1)).sum()) for f in frames.values())

    infra = anomalies(frames["container"], t0, t1) + anomalies(frames["node"], t0, t1)
    infra.sort(key=lambda r: -(r["score"] + 0.1 * r["peak"]))
    dbmw = anomalies(frames["service"], t0, t1) + anomalies(frames["middleware"], t0, t1)
    dbmw.sort(key=lambda r: -(r["score"] + 0.1 * r["peak"]))
    appr = app_anomalies(frames["app"], t0, t1)

    tokens = 0
    def ask(prompt, system):
        nonlocal tokens
        out = llm.generate(prompt, system=system, temperature=0.1)
        tokens += tok(prompt) + tok(system) + tok(out)
        return out

    sys_spec = ("Você é um especialista em telemetria. Resuma SOMENTE o que está nos dados abaixo, em até 4 linhas, "
                "apontando quais componentes e métricas fugiram do normal. Não invente.")
    s_infra = ask(f"Anomalias de containers (docker_*) e hosts (os_*):\n{fmt(infra)}", sys_spec)
    s_db = ask(f"Anomalias de bancos (db_*) e middleware (redis_*, etc.):\n{fmt(dbmw)}", sys_spec)
    s_app = ask(f"Anomalias de serviços de aplicação:\n{fmt(appr, 5)}", sys_spec)

    comps = sorted({r["cmdb_id"] for r in infra[:8] + dbmw[:8]})
    sys_diag = ("Você é o agente de diagnóstico. Escolha UMA causa raiz. Responda apenas JSON: "
                '{"component": "...", "reason": "...", "evidence": "..."}. '
                f"reason deve ser exatamente um de: {REASONS}. component deve ser um dos componentes citados.")
    diag = ask(f"Pergunta: {q['instruction']}\n\nInfra: {s_infra}\n\nBancos/middleware: {s_db}\n\nAplicação: {s_app}\n\n"
               f"Componentes candidatos: {comps}", sys_diag)
    sys_ver = ("Você é o verificador. Confronte o diagnóstico com os dados brutos. Se estiver sustentado, repita-o; "
               "se não, corrija. Responda apenas JSON no mesmo formato: "
               '{"component": "...", "reason": "...", "evidence": "..."}.')
    top = fmt(sorted(infra[:6] + dbmw[:6], key=lambda r: -r["score"]), 10)
    ver = ask(f"Diagnóstico proposto: {diag}\n\nDados brutos (maiores desvios):\n{top}\n\nreason deve ser um de {REASONS}.", sys_ver)

    def parse(txt):
        m = re.search(r"\{.*\}", txt, re.S)
        try:
            return json.loads(m.group(0)) if m else {}
        except Exception:
            return {}
    final = parse(ver) or parse(diag)
    comp, reason = str(final.get("component", "")).strip(), str(final.get("reason", "")).strip()
    # guardrail genérico: componente inventado (fora da telemetria) cai no maior desvio medido
    valid = {r["cmdb_id"] for r in infra + dbmw}
    if comp not in valid and (infra or dbmw):
        comp = max(infra[:1] + dbmw[:1], key=lambda r: r["score"])["cmdb_id"]
    # horário: ferramenta determinística (início da anomalia do componente escolhido)
    cand = [r for r in infra + dbmw if r["cmdb_id"] == comp and r["onset"]]
    cand.sort(key=lambda r: -r["score"])
    onset = cand[0]["onset"] if cand else t0
    pred_dt = datetime.fromtimestamp(onset, TZ).replace(second=0)

    need_time = "occurrence time" in q["scoring_points"]
    need_comp = "root cause component" in q["scoring_points"]
    need_reason = "root cause reason" in q["scoring_points"]
    gt_t = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", q["scoring_points"])
    gt_comp = re.search(r"component is (\S+)", q["scoring_points"])
    gt_reason = re.search(r"reason is ([^\n]+)", q["scoring_points"])
    ok_t = (abs((pred_dt - datetime.strptime(gt_t.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)).total_seconds()) <= 60) if (need_time and gt_t) else None
    ok_c = (comp == gt_comp.group(1)) if (need_comp and gt_comp) else None
    ok_r = (reason.lower() == gt_reason.group(1).strip().lower()) if (need_reason and gt_reason) else None
    checks = [x for x in (ok_t, ok_c, ok_r) if x is not None]
    return {
        "task": q["task_index"], "ok": all(checks), "time_ok": ok_t, "comp_ok": ok_c, "reason_ok": ok_r,
        "pred": {"component": comp, "reason": reason, "time": pred_dt.strftime("%Y-%m-%d %H:%M:%S")},
        "truth": q["scoring_points"].replace("\n", " | "),
        "seconds": round(time.time() - t_start, 1), "tokens": tokens, "tokens_naive": naive_rows * 12,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=15)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="benchmark/results/pilot.jsonl")
    args = ap.parse_args()
    queries = list(csv.DictReader(open(DATA / "query.csv")))
    idx = list(range(len(queries)))
    random.Random(args.seed).shuffle(idx)
    idx = sorted(idx[: args.n])
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        done = {json.loads(l)["i"] for l in out.read_text().splitlines() if l.strip()}
    llm = LocalProvider()
    for i in idx:
        if i in done:
            continue
        try:
            res = run_case(llm, queries[i])
        except Exception as exc:  # caso falho conta como erro, nunca como acerto
            res = {"task": queries[i]["task_index"], "ok": False, "error": repr(exc)[:200], "seconds": 0, "tokens": 0, "tokens_naive": 0}
        res["i"] = i
        with out.open("a") as f:
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
        print(i, res["ok"], res.get("pred"), res["seconds"], flush=True)


if __name__ == "__main__":
    main()
