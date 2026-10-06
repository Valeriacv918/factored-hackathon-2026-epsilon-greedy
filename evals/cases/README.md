# Triage evaluation set

`triage_messages.csv` holds customer messages labeled with the correct answer. It measures how well
triage classifies; it is **not** for training or for prompt examples. If a message from here is
copied into the prompt, the evaluation is no longer honest. CSV files are git-ignored: get the file
from the team before running.

```bash
uv run --project apps/agent python evals/cases/run_eval.py                  # baseline + LLM (uses Groq)
uv run --project apps/agent python evals/cases/run_eval.py --baseline-only  # keyword baseline only (free)
uv run --project apps/agent python evals/cases/run_eval.py --limit 10       # quick run
uv run --project apps/agent python evals/cases/run_eval.py --rpm 15         # slower, for Groq rate limits
```

It reports route accuracy (what matters most), intent accuracy, recall per intent, **critical
failures** (emergencies not routed to EMERGENCY, charges ending out of scope; target 0), the button
rate (CLARIFY_INTENT) and a confidence-threshold sweep. Results go to `evals/cases/results/`
(git-ignored), which the web stats panel reads.

## Columns

| Column | Values | Meaning |
|---|---|---|
| `id` | `es-001`, `pt-045`... | Unique id |
| `lang` | `es` / `pt` | Message language |
| `text` | text | The message as a customer would write it |
| `intent` | `emergency` / `not_me` / `charge_error` / `other` | Correct intent |
| `wants_human` | `1` / `0` | Asks to talk to a person? |
| `ambiguous` | `1` / `0` | `1` = not even a human could decide without asking → buttons are correct |
| `category` | see below | What makes the message hard |
| `source` | `claude` / `team` | Who wrote it |
| `note` | text | Why it was labeled so (required for doubtful cases) |

## Labeling rules

1. **`emergency`**: the customer **does not have** their card or thinks it is compromised: lost,
   stolen, cloned, kept by an ATM, wallet stolen. Asking to "block the card" also counts. If they also
   mention strange purchases, it is still `emergency` (it has priority).
2. **`not_me`**: there is a charge the customer **did not make or authorize** ("my son used my card
   without permission" → `not_me`).
3. **`charge_error`**: the customer **did** make the purchase but the charge is wrong: double charge,
   different amount, cancelled subscription still charging, refund that never arrived, ATM that did
   not dispense, product that never arrived.
4. **`other`**: none of the above (balance, passwords, opening accounts, hours, greetings).
5. **`ambiguous = 1`** only if it **really** cannot be known; then `intent = other`. Examples:
   "Tengo un problema con mi tarjeta"; "Me sale un cobro que no entiendo" (not understanding ≠ not
   having made it); "Cobrança indevida" (used for both cases in Brazil).
6. **`wants_human = 1`** if they ask for a person, whatever the intent. A message can be `not_me`
   **and** `wants_human = 1`.

## Categories

`clear` · `typo` · `slang` · `short` · `long_story` · `indirect` (no keyword) · `multi_issue` ·
`mixed_lang` · `emoji` · `angry` · `vague` · `injection` (tries to manipulate the agent) · `edge`
(between two intents)

## Adding messages (team)

Append rows with `source = team` and new ids (`es-101`, `pt-101`...). Write as you would on WhatsApp:
fast, with typos, without thinking about the model, and without looking at the classifier prompt.
Most valuable: messages you would hesitate to classify, typical Colombian or Brazilian phrases, and
long messy complaints. If unsure about a label, say so in `note`. Goal: at least 30 team messages
across the 4 intents and both languages.
