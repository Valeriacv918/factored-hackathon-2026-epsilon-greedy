"""Write each tool's input/output JSON Schema to contracts/mcp/<tool>.json.

Run from apps/mcp-server after changing a tool signature:
    .venv/Scripts/python.exe scripts/export_contracts.py
tests/test_contracts.py fails while the files are out of date.
"""
import asyncio
import json
from pathlib import Path

from bank_mcp.tools.server import mcp

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts" / "mcp"


async def schemas() -> dict[str, dict]:
    return {t.name: {"name": t.name, "description": t.description,
                     "input_schema": t.input_schema, "output_schema": t.output_schema}
            for t in await mcp.list_tools()}


def render(schema: dict) -> str:
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    for name, schema in asyncio.run(schemas()).items():
        (CONTRACTS / f"{name}.json").write_text(render(schema), encoding="utf-8")
        print(f"wrote contracts/mcp/{name}.json")
