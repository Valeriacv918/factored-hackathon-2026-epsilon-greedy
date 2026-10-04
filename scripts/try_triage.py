"""Prueba el clasificador del Triage con el LLM real (Groq) y lo compara con el baseline.

Uso (desde la carpeta principal del repo):
  uv run python scripts/try_triage.py                      # mensajes de ejemplo
  uv run python scripts/try_triage.py "me cobraron doble"  # tu propio mensaje
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "agent" / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from bank_agent.nodes.triage_agent.classifier import LLMClassifier  # noqa: E402
from bank_agent.nodes.triage_agent.rules import baseline_understand  # noqa: E402

EXAMPLES = [
    "buenas, se me perdió el plástico ayer en una fiesta",
    "q es esto de 450 mil en mercadolibre??? yo no compre nada",
    "fiz um pix e saiu duas vezes da conta",
    "quiero hablar con alguien de verdad, no con un robot",
    "tengo un lío con la tarjeta",
]

messages = sys.argv[1:] or EXAMPLES
clf = LLMClassifier()

for text in messages:
    base = baseline_understand(text)
    llm = clf.understand(text)
    print(f"\nMensaje:  {text}")
    print(f"  Baseline: {base.intent.value:<15} conf={base.confidence:.2f}  humano={base.wants_human}")
    print(f"  LLM:      {llm.intent.value:<15} conf={llm.confidence:.2f}  humano={llm.wants_human}")
    datos = {k: v for k, v in llm.slots.model_dump().items() if v is not None}
    if datos:
        print(f"  Datos:    {datos}")

print(f"\nLlamadas al LLM: {clf.calls}")
