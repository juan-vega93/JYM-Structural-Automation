"""Small shared checks for the supported steel yield calculations."""

from typing import Annotated

from pydantic import Field, FiniteFloat, TypeAdapter

_FACTOR = TypeAdapter(Annotated[FiniteFloat, Field(gt=0, strict=True)])


def validate_positive_factor(factor: float) -> float:
    return _FACTOR.validate_python(factor)


def require_mpa_mm(stress: str, length: str) -> None:
    if (stress, length) != ("MPa", "mm"):
        raise ValueError(
            f"Unsupported unit combination: stress={stress!r}, length={length!r}; "
            "only MPa + mm is supported"
        )
