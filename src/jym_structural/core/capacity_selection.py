"""Neutral minimum selection over caller-supplied compatible capacities."""

import json
from collections.abc import Iterable

from .capacity_models import CapacityValue


def governing_capacity(capacities: Iterable[CapacityValue]) -> CapacityValue:
    """Return the original minimum; ties use limit state and canonical source JSON.

    All candidates are revalidated, including non-controlling ones. Identity fields
    must agree exactly, with None distinct from any supplied reference. This does
    not determine applicable mechanisms or invoke capacity calculators.
    Identical duplicates are equivalent in data; either original instance may win.
    """
    identity = None
    winner = None
    best_key = None
    for capacity in capacities:
        if not isinstance(capacity, CapacityValue):
            raise TypeError("Each capacity must be a CapacityValue")
        # Validate data without replacing the caller's instance for the return value.
        validated = CapacityValue.model_validate(capacity.model_dump(round_trip=True))
        current_identity = (
            validated.component,
            validated.unit,
            validated.member_id,
            validated.section_name,
            validated.material_name,
        )
        if identity is None:
            identity = current_identity
        else:
            for field, expected, actual in zip(
                ("component", "unit", "member_id", "section_name", "material_name"),
                identity,
                current_identity,
                strict=True,
            ):
                if expected != actual:
                    raise ValueError(f"Capacity {field} values must match exactly")
        source_key = json.dumps(
            validated.source.model_dump(mode="json") if validated.source is not None else None,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        key = (validated.value, validated.limit_state, source_key)
        if best_key is None or key < best_key:
            winner, best_key = capacity, key
    if winner is None:
        raise ValueError("At least one capacity is required")
    return winner
