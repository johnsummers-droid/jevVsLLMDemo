import json
from pathlib import Path

import pytest

from app.catalog.compat import Compat, port_compat, type_compat
from app.models import PORT_TYPES, IssueCode, Port

FIXTURE = Path(__file__).resolve().parents[2] / "shared" / "fixtures" / "port-compat-cases.json"
CASES = json.loads(FIXTURE.read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c['source']}->{c['target']}")
def test_type_compat_matches_fixture(case: dict[str, str]) -> None:
    assert type_compat(case["source"], case["target"]) == Compat(case["expected"])


def test_fixture_covers_every_type_pair() -> None:
    pairs = {(c["source"], c["target"]) for c in CASES}
    assert pairs == {(s, t) for s in PORT_TYPES for t in PORT_TYPES}
    assert len(CASES) == len(pairs)


@pytest.mark.parametrize(
    ("source", "target", "expected"),
    [
        ("boolean", "text", Compat.BLOCKED),  # the spec's own example
        ("enum", "text", Compat.BLOCKED),
        ("score", "probability", Compat.BLOCKED),
        ("text", "any", Compat.OK),
        ("any", "any", Compat.OK),
        ("any", "text", Compat.WARN),
    ],
)
def test_spec_examples(source: str, target: str, expected: Compat) -> None:
    assert type_compat(source, target) is expected


def _port(type_: str, **kwargs: object) -> Port:
    return Port(id="p", label="p", type=type_, **kwargs)


def test_port_compat_issue_codes() -> None:
    assert port_compat(_port("text"), _port("text")) == (Compat.OK, None)
    assert port_compat(_port("boolean"), _port("text")) == (
        Compat.BLOCKED,
        IssueCode.INCOMPATIBLE_PORTS,
    )
    assert port_compat(_port("any"), _port("json")) == (Compat.WARN, IssueCode.ANY_SOURCE)


def test_enum_values_must_be_subset() -> None:
    target = _port("enum", enum_values=["auto", "human", "fallback"])
    subset = _port("enum", enum_values=["auto", "human"])
    superset = _port("enum", enum_values=["auto", "human", "other"])
    unconstrained = _port("enum")

    assert port_compat(subset, target) == (Compat.OK, None)
    assert port_compat(superset, target) == (Compat.BLOCKED, IssueCode.ENUM_VALUES_MISMATCH)
    assert port_compat(superset, unconstrained) == (Compat.OK, None)
