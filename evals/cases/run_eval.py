"""Evaluación del Triage: baseline (palabras clave) vs LLM, sobre messages.csv.

Uso (desde la carpeta principal del repo):
  uv run python evals/triage/run_eval.py                  # baseline + LLM (usa Groq)
  uv run python evals/triage/run_eval.py --baseline-only  # solo baseline (gratis)
  uv run python evals/triage/run_eval.py --limit 10       # prueba rápida con 10 mensajes

Qué mide:
  - Exactitud de RUTA: ¿el cliente llegó al lugar correcto? (lo que más importa)
  - Exactitud de INTENCIÓN: ¿el clasificador entendió bien?
  - Recall por intención: de los que eran X, ¿cuántos detectó como X?
  - FALLOS CRÍTICOS: emergencias que no fueron a EMERGENCY, y cargos
    (not_me / charge_error) que terminaron "fuera de alcance". Meta: 0.
  - Tasa de botones (CLARIFY_INTENT): preguntar mucho también es malo.
  - Barrido del umbral de confianza: para elegir CONFIDENCE_THRESHOLD con datos.
"""
import argparse
import csv
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "agent" / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

import bank_agent.nodes.triage_agent.router as router  # noqa: E402
from bank_agent.nodes.triage_agent.rules import baseline_understand  # noqa: E402
from bank_agent.nodes.triage_agent.schemas import Intent, Route  # noqa: E402

DATA = Path(__file__).parent / "triage_messages.csv"
RESULTS_DIR = Path(__file__).parent / "results"


# ---------------------------------------------------------------------------
# La respuesta correcta según las etiquetas del CSV
# ---------------------------------------------------------------------------
def expected_route(row) -> Route:
    """Misma prioridad que el router: emergencia > humano > ambiguo > intención."""
    intent = Intent(row["intent"])          # falla si el CSV usa un valor que no existe en Intent
    if intent == Intent.EMERGENCY:
        return Route.EMERGENCY
    if row["wants_human"] == "1":
        return Route.ESCALATION
    if row["ambiguous"] == "1":
        return Route.CLARIFY_INTENT
    if intent in (Intent.NOT_ME, Intent.CHARGE_ERROR):
        return Route.FIND_TRANSACTION
    return Route.OUT_OF_SCOPE


def is_critical_miss(row, route: Route) -> bool:
    """Errores que pueden costarle dinero al cliente."""
    intent = Intent(row["intent"])
    if intent == Intent.EMERGENCY and route != Route.EMERGENCY:
        return True                                   # tarjeta robada sin bloquear
    if intent in (Intent.NOT_ME, Intent.CHARGE_ERROR) and route == Route.OUT_OF_SCOPE:
        return True                                   # reclamo de dinero ignorado
    return False


# ---------------------------------------------------------------------------
# Correr un clasificador sobre todos los mensajes
# ---------------------------------------------------------------------------
def run(name, understand_fn, rows, sleep=0.0):
    results = []
    for i, row in enumerate(rows, 1):
        t0 = time.perf_counter()
        u = understand_fn(row["text"])
        latency = time.perf_counter() - t0
        d = router.decide(row["text"], u)
        results.append({"row": row, "u": u, "route": d.route, "reason": d.reason, "latency": latency})
        print(f"\r  {name}: {i}/{len(rows)}", end="", flush=True)
        if sleep:
            time.sleep(sleep)
    print()
    return results


def summarize(name, results):
    n = len(results)
    route_ok = sum(r["route"] == expected_route(r["row"]) for r in results)

    clear = [r for r in results if r["row"]["ambiguous"] == "0"]
    intent_ok = sum(r["u"].intent.value == r["row"]["intent"] for r in clear)

    recall = {}
    for intent in Intent:
        group = [r for r in clear if r["row"]["intent"] == intent.value]
        if group:
            hits = sum(r["u"].intent == intent for r in group)
            recall[intent.value] = (hits, len(group))

    critical = [r for r in results if is_critical_miss(r["row"], r["route"])]
    clarify = sum(r["route"] == Route.CLARIFY_INTENT for r in results)

    by_group = {}
    for key in ("lang", "source"):
        g = defaultdict(lambda: [0, 0])
        for r in results:
            g[r["row"][key]][0] += r["route"] == expected_route(r["row"])
            g[r["row"][key]][1] += 1
        by_group[key] = dict(g)

    return {
        "name": name, "n": n,
        "route_acc": route_ok / n,
        "intent_acc": intent_ok / len(clear) if clear else 0,
        "recall": recall,
        "critical": critical,
        "clarify_rate": clarify / n,
        "by_group": by_group,
        "avg_latency": sum(r["latency"] for r in results) / n,
        "reasons": Counter(r["reason"] for r in results),
        # El FALLBACK del clasificador tiene confianza 0: si aparece, Groq falló
        "llm_failures": sum(r["u"].confidence == 0.0 for r in results) if name == "llm" else 0,
    }


# ---------------------------------------------------------------------------
# Reporte
# ---------------------------------------------------------------------------
def pct(x):
    return f"{x:.0%}"


def print_report(summaries):
    print("\n" + "=" * 70)
    print("RESULTADOS DEL TRIAGE")
    print("=" * 70)
    names = [s["name"] for s in summaries]
    w = 16
    print(f"{'Métrica':<34}" + "".join(f"{n:>{w}}" for n in names))
    print("-" * (34 + w * len(names)))

    def line(label, values):
        print(f"{label:<34}" + "".join(f"{v:>{w}}" for v in values))

    line("Exactitud de ruta", [pct(s["route_acc"]) for s in summaries])
    line("Exactitud de intención (claros)", [pct(s["intent_acc"]) for s in summaries])
    for intent in Intent:
        vals = []
        for s in summaries:
            h, t = s["recall"].get(intent.value, (0, 0))
            vals.append(f"{h}/{t} ({pct(h / t) if t else '-'})")
        line(f"  Recall {intent.value}", vals)
    line("FALLOS CRÍTICOS (meta: 0)", [str(len(s["critical"])) for s in summaries])
    line("Tasa de botones", [pct(s["clarify_rate"]) for s in summaries])
    for lang in sorted(summaries[0]["by_group"]["lang"]):
        line(f"  Ruta correcta [{lang}]",
             [f"{s['by_group']['lang'][lang][0]}/{s['by_group']['lang'][lang][1]}" for s in summaries])
    for src in sorted(summaries[0]["by_group"]["source"]):
        line(f"  Ruta correcta [source={src}]",
             [f"{s['by_group']['source'][src][0]}/{s['by_group']['source'][src][1]}" for s in summaries])
    line("Latencia promedio (s)", [f"{s['avg_latency']:.2f}" for s in summaries])
    line("Fallos de Groq (fallback)", [str(s["llm_failures"]) if s["name"] == "llm" else "-" for s in summaries])

    for s in summaries:
        if s["llm_failures"]:
            print(f"\n⚠️  {s['llm_failures']} respuestas del LLM fueron FALLBACK (Groq falló o limitó la velocidad).")
            print("    Los resultados del LLM no son confiables. Vuelve a correr con: --sleep 2")

    for s in summaries:
        if s["critical"]:
            print(f"\nFallos críticos de {s['name']}:")
            for r in s["critical"]:
                print(f"  [{r['row']['id']}] esperado {r['row']['intent']} → fue a {r['route'].value}: {r['row']['text'][:60]}")


def threshold_sweep(results):
    """Re-decide la ruta con distintos umbrales, SIN volver a llamar al LLM."""
    print("\nBarrido del umbral de confianza (LLM):")
    print(f"  {'umbral':>7} {'ruta ok':>8} {'botones':>8} {'críticos':>9}")
    original = router.CONFIDENCE_THRESHOLD
    for t in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
        router.CONFIDENCE_THRESHOLD = t
        routes = [router.decide(r["row"]["text"], r["u"]).route for r in results]
        ok = sum(rt == expected_route(r["row"]) for rt, r in zip(routes, results))
        btn = sum(rt == Route.CLARIFY_INTENT for rt in routes)
        crit = sum(is_critical_miss(r["row"], rt) for rt, r in zip(routes, results))
        mark = "  ← actual" if t == original else ""
        print(f"  {t:>7.1f} {pct(ok / len(results)):>8} {pct(btn / len(results)):>8} {crit:>9}{mark}")
    router.CONFIDENCE_THRESHOLD = original


def save_details(all_results):
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"triage_{datetime.now():%Y%m%d_%H%M%S}.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["model", "id", "lang", "source", "text", "gold_intent", "pred_intent",
                    "confidence", "expected_route", "route", "reason", "ok", "critical"])
        for name, results in all_results.items():
            for r in results:
                row, exp = r["row"], expected_route(r["row"])
                w.writerow([name, row["id"], row["lang"], row["source"], row["text"], row["intent"],
                            r["u"].intent.value, f"{r['u'].confidence:.2f}", exp.value, r["route"].value,
                            r["reason"], int(r["route"] == exp), int(is_critical_miss(row, r["route"]))])
    print(f"\nDetalle por mensaje guardado en: {path.relative_to(ROOT)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline-only", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--sleep", type=float, default=0.0, help="pausa entre llamadas (límite de Groq)")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(DATA, encoding="utf-8")))[: args.limit]
    print(f"{len(rows)} mensajes de {DATA.name}")

    all_results = {"baseline": run("baseline", baseline_understand, rows)}
    if not args.baseline_only:
        from bank_agent.nodes.triage_agent.classifier import LLMClassifier
        clf = LLMClassifier()
        all_results["llm"] = run("llm", clf.understand, rows, sleep=args.sleep)
        print(f"Llamadas al LLM: {clf.calls} (reintentos incluidos)")

    print_report([summarize(n, r) for n, r in all_results.items()])
    if "llm" in all_results:
        threshold_sweep(all_results["llm"])
    save_details(all_results)


if __name__ == "__main__":
    main()
