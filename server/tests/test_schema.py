"""shared/schema/ is generated from the Pydantic models (plan1.txt T6)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import export_schema  # noqa: E402

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "shared" / "schema"


@pytest.mark.parametrize("stem", list(export_schema.GROUPS))
def test_committed_schema_matches_export(stem):
    path = SCHEMA_DIR / f"{stem}.schema.json"
    assert path.read_text() == export_schema.render(stem), (
        f"{path.name} is stale: run scripts/export_schema.py, then npm run gen:types in web/"
    )


def _all_defs() -> dict:
    defs: dict = {}
    for stem in export_schema.GROUPS:
        for name, body in export_schema.build_group(stem)["$defs"].items():
            assert defs.setdefault(name, body) == body, f"$defs.{name} differs between files"
    return defs


def _refs(node) -> set[str]:
    if isinstance(node, dict):
        own = {node["$ref"].rsplit("/", 1)[-1]} if "$ref" in node else set()
        return own.union(*(_refs(v) for v in node.values()))
    if isinstance(node, list):
        return set().union(*(_refs(v) for v in node))
    return set()


def test_every_ref_resolves_within_its_file():
    for stem in export_schema.GROUPS:
        defs = export_schema.build_group(stem)["$defs"]
        assert _refs(defs) <= set(defs), stem


def test_named_aliases_are_promoted():
    defs = _all_defs()
    for name in export_schema.NAMED_ALIASES:
        assert name in defs
    assert defs["NodeDefinition"]["properties"]["params"]["items"] == {"$ref": "#/$defs/ParamSpec"}
    assert defs["Port"]["properties"]["type"] == {"$ref": "#/$defs/PortType"}
    assert len(defs["ServerEvent"]["oneOf"]) == len(defs["ServerEvent"]["discriminator"]["mapping"])


def test_discriminators_are_required_and_camel_case():
    defs = _all_defs()
    for name in ("NumberParam", "BoolParam", "RunStarted", "StateSync", "Ping"):
        props, required = defs[name]["properties"], defs[name]["required"]
        key = "kind" if name.endswith("Param") else "type"
        assert "const" in props[key] and key in required
    assert "schemaVersion" in defs["Graph"]["required"]
    assert "sourcePort" in defs["GraphEdge"]["properties"]


def test_property_titles_are_dropped():
    def titled_props(node) -> bool:
        if isinstance(node, dict):
            props = node.get("properties", {})
            if any(isinstance(p, dict) and "title" in p for p in props.values()):
                return True
            return any(titled_props(v) for v in node.values())
        return isinstance(node, list) and any(titled_props(v) for v in node)

    assert not titled_props(_all_defs())


def test_check_mode_passes_on_committed_files(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["export_schema.py", "--check"])
    assert export_schema.main() == 0
