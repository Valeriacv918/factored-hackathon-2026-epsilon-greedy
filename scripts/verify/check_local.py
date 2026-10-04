"""Run local source checks without deploying or accessing GCP."""
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
node = shutil.which("node")
if not node:
    raise SystemExit("Node.js is required on PATH for Dataform generation tests.")
subprocess.run([sys.executable, "-m", "unittest", "discover", "-s",
                str(root / "data/ingestion"), "-p", "test_validation.py"],
               cwd=root, check=True)
for test in sorted((root / "data/dataform/tests").glob("*.js")):
    subprocess.run([node, str(test)], cwd=root, check=True)
subprocess.run([sys.executable, str(root / "scripts/verify/sandbox_contract.py"), "--check"],
               cwd=root, check=True)
print("Local checks passed. Cloud compilation/execution remains separate.")
