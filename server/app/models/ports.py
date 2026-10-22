from typing import Literal, Self

from pydantic import model_validator

from app.models.base import CamelModel

PortType = Literal["text", "json", "enum", "score", "boolean", "probability", "image", "any"]
PORT_TYPES: tuple[PortType, ...] = PortType.__args__


class Port(CamelModel):
    id: str  # stable handle id, e.g. "text" or "route.billing"
    label: str
    type: PortType
    required: bool = True  # inputs only
    multi: bool = False  # inputs: accepts several edges; the first live value wins
    branch: bool = False  # outputs: member of the node's exclusive branch group
    enum_values: list[str] | None = None
    score_range: tuple[int, int] | None = None
    json_schema_ref: str | None = None  # e.g. "Distribution", "Docs", "PolicyReport"
    dynamic_from_param: str | None = None  # outputs generated from a param's values

    @model_validator(mode="after")
    def _check_type_specific_fields(self) -> Self:
        if not self.id:
            raise ValueError("port id must not be empty")
        if self.enum_values is not None:
            if self.type != "enum":
                raise ValueError("enum_values is only allowed on enum ports")
            if len(set(self.enum_values)) != len(self.enum_values):
                raise ValueError("enum_values must be unique")
        if self.score_range is not None:
            if self.type != "score":
                raise ValueError("score_range is only allowed on score ports")
            low, high = self.score_range
            if low >= high:
                raise ValueError("score_range must be (low, high) with low < high")
        if self.json_schema_ref is not None and self.type != "json":
            raise ValueError("json_schema_ref is only allowed on json ports")
        if self.branch and self.type != "text":
            raise ValueError("branch ports carry pass-through text and must be typed text")
        return self
