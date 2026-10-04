#!/usr/bin/env bash
set -euo pipefail
: "${1:?Usage: bash infra/bigquery/sandbox/run_audit.sh SCENARIO_ID}"
scenario_id="$1"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../.." && pwd)"
evidence="$repo_root/artifacts/sandbox/$(date -u +%Y%m%dT%H%M%SZ)-${RANDOM}"
mkdir -p "$evidence"
echo "EVIDENCE: $evidence"
printf '%s\n' "$scenario_id" > "$evidence/scenario_id.txt"
for step in verify_schema preflight audit_contract audit_references; do
  echo "Checking: $step"
  if bq query --project_id=hackaton-509923 --location=us-central1 \
    --use_legacy_sql=false --maximum_bytes_billed=1000000000 --format=json \
    --parameter="scenario_id:STRING:$scenario_id" \
    < "$script_dir/$step.sql" > "$evidence/$step.json" 2> "$evidence/$step.log"; then
    :
  else
    cat "$evidence/$step.log" >&2
    cat "$evidence/$step.json" >&2
    printf '{"status":"FAILED","failed_step":"%s"}\n' "$step" > "$evidence/summary.json"
    echo "FAILED: $step; evidence: $evidence" >&2
    exit 1
  fi
done
python3 - "$evidence" <<'PY'
import json
import sys
from pathlib import Path
p=Path(sys.argv[1])
failures=[]
for name in ("audit_contract","audit_references"):
    rows=json.loads((p/(name+".json")).read_text())
    if not rows:
        raise SystemExit("Missing audit results: "+name)
    failures.extend(r for r in rows if int(r["violations"])!=0)
summary={"status":"FAILED" if failures else "PASSED","failures":failures}
(p/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
print(str(p), summary["status"])
raise SystemExit(bool(failures))
PY
