"""Write each tool's input/output JSON Schema to contracts/mcp/<tool>.json.

Run from apps/mcp-server after changing a tool signature:
    uv run scripts/export_contracts.py
tests/test_contracts.py fails while the files are out of date.
"""
import asyncio
import inspect
import json
from pathlib import Path

from bank_mcp.tools.server import mcp

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts" / "mcp"


def _clean(value):
    """Normalize every description with inspect.cleandoc.

    Python 3.13 strips docstring indentation at compile time and 3.12 does not, so
    without this the files differ by Python version and the test fails for one of them.
    """
    if isinstance(value, dict):
        return {k: inspect.cleandoc(v) if k == "description" and isinstance(v, str) else _clean(v)
                for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


async def schemas() -> dict[str, dict]:
    return {t.name: _clean({"name": t.name, "description": t.description,
                            "input_schema": t.input_schema, "output_schema": t.output_schema})
            for t in await mcp.list_tools()}


def render(schema: dict) -> str:
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    for name, schema in asyncio.run(schemas()).items():
        (CONTRACTS / f"{name}.json").write_text(render(schema), encoding="utf-8")
        print(f"wrote contracts/mcp/{name}.json")
