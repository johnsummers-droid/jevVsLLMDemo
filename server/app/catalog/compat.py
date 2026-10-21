"""Port compatibility rules. Mirrored in web/src/lib/compat.ts; both are tested
against shared/fixtures/port-compat-cases.json."""

from enum import StrEnum

from app.models.ports import Port, PortType
from app.models.validation import IssueCode


class Compat(StrEnum):
    OK = "ok"
    WARN = "warn"  # allowed, but flagged on the canvas
    BLOCKED = "blocked"


def type_compat(source: PortType, target: PortType) -> Compat:
    """Type-level check used for instant feedback while connecting."""
    if source == target or target == "any":
        return Compat.OK
    if source == "any":
        return Compat.WARN
    return Compat.BLOCKED


def port_compat(source: Port, target: Port) -> tuple[Compat, IssueCode | None]:
    """Full server-side check: types plus enum value subsets."""
    compat = type_compat(source.type, target.type)
    if compat is Compat.BLOCKED:
        return compat, IssueCode.INCOMPATIBLE_PORTS
    if compat is Compat.WARN:
        return compat, IssueCode.ANY_SOURCE
    if (
        source.type == "enum"
        and target.type == "enum"
        and target.enum_values is not None
        and not set(source.enum_values or []) <= set(target.enum_values)
    ):
        return Compat.BLOCKED, IssueCode.ENUM_VALUES_MISMATCH
    return Compat.OK, None
