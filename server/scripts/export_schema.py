"""Export the wire models' JSON Schema to shared/schema/ (plan1.txt T6).

    .venv/bin/python scripts/export_schema.py          # write the files
    .venv/bin/python scripts/export_schema.py --check  # exit 1 if they are stale

Each file is self-contained ($defs). web/scripts/gen-types.mjs merges them into
web/src/types/generated.ts. Three adjustments make the TS output usable:
  - named aliases (PortType, ParamSpec, ServerEvent, ...) become $defs instead of being inlined;
  - property titles are dropped (the generator would turn each one into a named type);
  - a constant field (the `type`/`kind` discriminators) is always required, because the server
    always sends it and TS unions only narrow on required fields.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, TypeAdapter
from pydantic.json_schema import GenerateJsonSchema, models_json_schema

from app.api.catalog import CatalogResponse
from app.models import (
    Distribution,
    Docs,
    Graph,
    IssueCode,
    LeaderboardRow,
    NodeCategory,
    NodeDefinition,
    NodeStats,
    Outcome,
    PackSummary,
    ParamSpec,
    PolicyReport,
    PortType,
    RequestTrace,
    RunConfig,
    RunMetrics,
    RunMode,
    RunStatus,
    RunSummary,
    Severity,
    StoredGraph,
    TicketMeta,
    ValidationReport,
)
from app.models.events import ClientMessage, ServerEvent

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "shared" / "schema"
REF = "#/$defs/{model}"

# Aliases that would otherwise be inlined. Order matters only for readability of the output.
NAMED_ALIASES: dict[str, Any] = {
    "PortType": PortType,
    "NodeCategory": NodeCategory,
    "Severity": Severity,
    "RunMode": RunMode,
    "RunStatus": RunStatus,
    "Outcome": Outcome,
    "ParamSpec": ParamSpec,
    "ServerEvent": ServerEvent,
    "ClientMessage": ClientMessage,
}

# file stem -> (models, aliases exported as their own $defs)
GROUPS: dict[str, tuple[list[type[BaseModel]], list[str]]] = {
    "graph": ([Graph, StoredGraph], []),
    "catalog": ([CatalogResponse, NodeDefinition], ["PortType", "NodeCategory", "ParamSpec"]),
    "validation": ([ValidationReport], ["Severity"]),
    "run": (
        [RunConfig, RunSummary, RequestTrace, RunMetrics, NodeStats, LeaderboardRow, PackSummary],
        ["RunMode", "RunStatus", "Outcome"],
    ),
    "events": ([], ["ServerEvent", "ClientMessage"]),
    # json port payloads, named by Port.jsonSchemaRef (the inspector's schema preview)
    "payloads": ([TicketMeta, Docs, PolicyReport, Distribution], []),
}


class NoPropertyTitles(GenerateJsonSchema):
    def field_title_should_be_set(self, schema: Any) -> bool:
        return False


def _alias_schema(alias: Any) -> dict[str, Any]:
    return TypeAdapter(alias).json_schema(
        by_alias=True, ref_template=REF, schema_generator=NoPropertyTitles
    )


def _walk(node: Any, fn) -> Any:
    """Rebuild node bottom-up, applying fn to every dict."""
    if isinstance(node, dict):
        return fn({k: _walk(v, fn) for k, v in node.items()})
    if isinstance(node, list):
        return [_walk(v, fn) for v in node]
    return node


def _require_constants(obj: dict[str, Any]) -> dict[str, Any]:
    props = obj.get("properties")
    if obj.get("type") != "object" or not isinstance(props, dict):
        return obj
    consts = [k for k, v in props.items() if isinstance(v, dict) and "const" in v]
    if consts:
        required = list(obj.get("required", []))
        obj["required"] = required + [k for k in consts if k not in required]
        for k in consts:
            props[k].pop("default", None)
    return obj


def build_group(stem: str) -> dict[str, Any]:
    models, alias_names = GROUPS[stem]
    defs: dict[str, Any] = {}
    if models:
        _, top = models_json_schema(
            [(m, "validation") for m in models],
            ref_template=REF,
            schema_generator=NoPropertyTitles,
        )
        defs.update(top.get("$defs", {}))

    # Promote aliases: their bodies become $defs, and inline copies become $refs.
    named: dict[str, dict[str, Any]] = {}
    for name, alias in NAMED_ALIASES.items():
        schema = _alias_schema(alias)
        defs.update(schema.pop("$defs", {}))
        named[name] = schema
    inline = {json.dumps(body, sort_keys=True): name for name, body in named.items()}

    def promote(obj: dict[str, Any]) -> dict[str, Any]:
        name = inline.get(json.dumps(obj, sort_keys=True))
        if name is None:
            return obj
        alias_names_used.add(name)
        return {"$ref": REF.format(model=name)}

    alias_names_used: set[str] = set(alias_names)
    defs = {k: _walk(v, promote) for k, v in defs.items()}
    for name in sorted(alias_names_used, key=list(NAMED_ALIASES).index):
        # Walk the children only: the body itself would match its own entry in `inline`.
        body = {k: _walk(v, promote) for k, v in named[name].items()}
        defs[name] = {"title": name, **body}
    defs = {k: _walk(v, _require_constants) for k, v in defs.items()}
    defs = _prune(defs, [m.__name__ for m in models] + alias_names)

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{stem}.schema.json",
        "title": stem,
        "description": "GENERATED by server/scripts/export_schema.py. Do not edit.",
        "$defs": dict(sorted(defs.items())),
    }


def _prune(defs: dict[str, Any], roots: list[str]) -> dict[str, Any]:
    """Keep only the $defs reachable from the group's roots."""
    seen: set[str] = set()
    stack = list(roots)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        refs: list[str] = []
        _walk(defs[name], lambda o: refs.append(o["$ref"]) or o if "$ref" in o else o)
        stack.extend(r.rsplit("/", 1)[-1] for r in refs)
    return {k: v for k, v in defs.items() if k in seen}


def render(stem: str) -> str:
    return json.dumps(build_group(stem), indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if shared/schema is stale")
    args = parser.parse_args()

    stale = []
    for stem in GROUPS:
        path = SCHEMA_DIR / f"{stem}.schema.json"
        text = render(stem)
        if args.check:
            if not path.exists() or path.read_text() != text:
                stale.append(path.name)
        else:
            SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    if stale:
        print(f"stale schema files: {', '.join(stale)}; run scripts/export_schema.py", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
