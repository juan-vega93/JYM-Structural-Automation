"""Caller-supplied standard metadata and decisions, without normative interpretation."""

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from .property_models import PropertySource

_NonBlank = Annotated[str, Field(min_length=1, pattern=r"\S")]
_LIMIT_STATE = TypeAdapter(_NonBlank)


class DesignStandard(BaseModel):
    """Exact identity/method labels; neither editions nor jurisdictions are inferred."""

    model_config = ConfigDict(
        frozen=True,
        strict=True,
        extra="forbid",
        revalidate_instances="always",
    )

    name: _NonBlank
    edition: _NonBlank
    method: _NonBlank | None = None
    jurisdiction: _NonBlank | None = None
    source: PropertySource | None = None


class ApplicabilityDecision(BaseModel):
    """An explicit supplied decision, not an applicability calculation."""

    model_config = ConfigDict(
        frozen=True,
        strict=True,
        extra="forbid",
        revalidate_instances="always",
    )

    limit_state: _NonBlank
    applicable: bool
    reason: _NonBlank | None = None
    source: PropertySource | None = None


class DesignContext(BaseModel):
    """Ordered immutable decisions, at most one per exact limit-state string."""

    model_config = ConfigDict(
        frozen=True,
        strict=True,
        extra="forbid",
        revalidate_instances="always",
    )

    standard: DesignStandard
    applicability: tuple[ApplicabilityDecision, ...] = ()

    @model_validator(mode="after")
    def unique_limit_states(self) -> Self:
        seen: set[str] = set()
        for decision in self.applicability:
            if decision.limit_state in seen:
                raise ValueError(f"Duplicate applicability limit_state: {decision.limit_state!r}")
            seen.add(decision.limit_state)
        return self


def applicability_for(context: DesignContext, limit_state: str) -> ApplicabilityDecision | None:
    """Look up an exact supplied decision; absence means unknown, never a default."""
    if not isinstance(context, DesignContext):
        raise TypeError("Expected a DesignContext")
    limit_state = _LIMIT_STATE.validate_python(limit_state, strict=True)
    context = DesignContext.model_validate(context)
    return next((d for d in context.applicability if d.limit_state == limit_state), None)
