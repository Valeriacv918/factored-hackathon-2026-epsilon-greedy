import asyncio
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "export_contracts", Path(__file__).resolve().parents[1] / "scripts" / "export_contracts.py")
export = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(export)


def test_published_contracts_match_server_tools():
    schemas = asyncio.run(export.schemas())
    assert set(schemas) == {"find_transactions", "list_cards", "get_card", "verify_identity"}   # no raw SQL tool
    for name, schema in schemas.items():
        path = export.CONTRACTS / f"{name}.json"
        assert path.read_text(encoding="utf-8") == export.render(schema), \
            f"{path.name} is stale: run scripts/export_contracts.py"
