from typing import Annotated, Any, Literal, Self

from pydantic import Field, model_validator

from app.models.base import CamelModel


class _ParamBase(CamelModel):
    key: str
    label: str
    help: str = ""

    def check(self, value: Any) -> Any:
        """Return the value if it is valid for this param, else raise ValueError."""
        raise NotImplementedError

    @model_validator(mode="after")
    def _check_default(self) -> Self:
        self.check(self.default)  # type: ignore[attr-defined]
        return self


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class NumberParam(_ParamBase):
    kind: Literal["number"] = "number"
    default: float
    min: float
    max: float
    step: float = 0.05

    def check(self, value: Any) -> float:
        if not _is_number(value):
            raise ValueError(f"{self.key}: expected a number")
        if not self.min <= value <= self.max:
            raise ValueError(f"{self.key}: {value} is outside [{self.min}, {self.max}]")
        return float(value)


class IntParam(_ParamBase):
    kind: Literal["int"] = "int"
    default: int
    min: int
    max: int

    def check(self, value: Any) -> int:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{self.key}: expected an integer")
        if not self.min <= value <= self.max:
            raise ValueError(f"{self.key}: {value} is outside [{self.min}, {self.max}]")
        return value


class EnumParam(_ParamBase):
    kind: Literal["enum"] = "enum"
    default: str
    options: list[str] = Field(min_length=1)

    def check(self, value: Any) -> str:
        if value not in self.options:
            raise ValueError(f"{self.key}: {value!r} is not one of {self.options}")
        return value


class MultiEnumParam(_ParamBase):
    kind: Literal["multi_enum"] = "multi_enum"
    default: list[str]
    options: list[str] = Field(min_length=1)
    min_selected: int = 1

    def check(self, value: Any) -> list[str]:
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ValueError(f"{self.key}: expected a list of strings")
        if len(set(value)) != len(value):
            raise ValueError(f"{self.key}: duplicate selections")
        unknown = [v for v in value if v not in self.options]
        if unknown:
            raise ValueError(f"{self.key}: unknown options {unknown}")
        if len(value) < self.min_selected:
            raise ValueError(f"{self.key}: select at least {self.min_selected}")
        return value


class StringListParam(_ParamBase):
    kind: Literal["string_list"] = "string_list"
    default: list[str]
    max_items: int = 20
    max_len: int = 60

    def check(self, value: Any) -> list[str]:
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ValueError(f"{self.key}: expected a list of strings")
        if len(value) > self.max_items:
            raise ValueError(f"{self.key}: at most {self.max_items} items")
        if any(len(v) > self.max_len for v in value):
            raise ValueError(f"{self.key}: items must be at most {self.max_len} characters")
        return value


class TextParam(_ParamBase):
    kind: Literal["text"] = "text"
    default: str
    max_len: int = 500

    def check(self, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{self.key}: expected a string")
        if len(value) > self.max_len:
            raise ValueError(f"{self.key}: at most {self.max_len} characters")
        return value


class BoolParam(_ParamBase):
    kind: Literal["bool"] = "bool"
    default: bool

    def check(self, value: Any) -> bool:
        if not isinstance(value, bool):
            raise ValueError(f"{self.key}: expected a boolean")
        return value


ParamSpec = Annotated[
    NumberParam | IntParam | EnumParam | MultiEnumParam | StringListParam | TextParam | BoolParam,
    Field(discriminator="kind"),
]
