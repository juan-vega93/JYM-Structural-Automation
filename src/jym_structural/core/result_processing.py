"""Pure force extremes, envelopes and basic demand/capacity comparison."""

from __future__ import annotations

from typing import Literal

from .models import AnalysisResult
from .result_models import DemandCheck, ExtremeKind, ForceComponent, ForceEnvelope, ForceExtreme

_COMPONENTS = ("p", "v2", "v3", "t", "m2", "m3")


def _candidates(
    result: AnalysisResult,
    component: ForceComponent,
    kind: ExtremeKind,
) -> list[ForceExtreme]:
    if component not in _COMPONENTS:
        raise ValueError(f"Unsupported force component: {component!r}")
    if not isinstance(result, AnalysisResult):
        raise TypeError("Expected an AnalysisResult")
    if not result.forces:
        raise ValueError("AnalysisResult.forces must not be empty")
    if result.units is None:
        raise ValueError("AnalysisResult.units is required for force processing")
    # Validate every row, including those that will not control the result.
    # Never sort or filter the input list, or reuse its mutable nested objects.
    return [
        ForceExtreme(
            member_id=result.member_id,
            component=component,
            kind=kind,
            source=row,
            units=result.units,
        )
        for row in result.forces
    ]


def _provenance(extreme: ForceExtreme) -> tuple:
    source = extreme.source
    return (
        source.load_case,
        (source.step_type is not None, source.step_type or ""),
        source.step_num,
        source.station,
        source.element_id,
        source.element_station,
        source.object_id,
        # Complete serialization breaks residual ties (other force components,
        # missing unrequested values, signed zero) without dropping any row data.
        source.model_dump_json(),
    )


def component_extreme(
    result: AnalysisResult,
    component: ForceComponent,
    *,
    kind: Literal["min", "max"],
) -> ForceExtreme:
    """Find a signed minimum/maximum; equal values use neutral provenance order."""
    if kind not in ("min", "max"):
        raise ValueError(f"Unsupported component extreme kind: {kind!r}")
    candidates = _candidates(result, component, kind)
    return min(
        candidates,
        key=lambda row: (
            row.value if kind == "min" else -row.value,
            _provenance(row),
        ),
    )


def component_envelope(result: AnalysisResult, component: ForceComponent) -> ForceEnvelope:
    """Independent min/max source rows; never a synthetic multi-component row."""
    return ForceEnvelope(
        component=component,
        minimum=component_extreme(result, component, kind="min"),
        maximum=component_extreme(result, component, kind="max"),
    )


def absolute_extreme(result: AnalysisResult, component: ForceComponent) -> ForceExtreme:
    """Largest magnitude, original sign; negative wins a +/- magnitude tie."""
    return min(
        _candidates(result, component, "absolute"),
        key=lambda row: (
            -abs(row.value),
            row.value,
            _provenance(row),
        ),
    )


def demand_ratio(demand: ForceExtreme, capacity: float) -> DemandCheck:
    """abs(demand.value)/capacity; caller supplies capacity in demand.unit."""
    return DemandCheck(demand=demand, capacity=capacity)
