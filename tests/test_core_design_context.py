import subprocess
import sys

import pytest
from pydantic import ValidationError

from jym_structural.core import (
    ApplicabilityDecision,
    DesignContext,
    DesignStandard,
    PropertySource,
    applicability_for,
)


def standard(**changes):
    values = {"name": "supplied standard", "edition": "project edition"}
    values.update(changes)
    return DesignStandard(**values)


def decision(**changes):
    values = {"limit_state": "future_lateral_torsional_buckling", "applicable": True}
    values.update(changes)
    return ApplicabilityDecision(**values)


def test_minimal_standard_and_context():
    supplied = standard()
    assert supplied.method is supplied.jurisdiction is supplied.source is None
    context = DesignContext(standard=supplied)
    assert context.standard == supplied
    assert context.applicability == ()
    assert applicability_for(context, "not supplied") is None


@pytest.mark.parametrize("edition", ["2022", "2016", "Rev 4", "project edition"])
def test_complete_standard_arbitrary_labels_and_source(edition):
    source = PropertySource(kind="manual", name="Project design basis", version="Rev B")
    supplied = standard(
        name=" AISC 360 ",
        edition=edition,
        method=" custom method ",
        jurisdiction="project-specific",
        source=source,
    )
    assert supplied.name == " AISC 360 "
    assert supplied.edition == edition
    assert supplied.method == " custom method "
    assert supplied.jurisdiction == "project-specific"
    assert supplied.source == source


@pytest.mark.parametrize("field", ["name", "edition", "method", "jurisdiction"])
@pytest.mark.parametrize("bad", ["", " \t\n", 2022, True])
def test_standard_strings_strict_and_nonblank(field, bad):
    with pytest.raises(ValidationError):
        standard(**{field: bad})


@pytest.mark.parametrize("field", ["name", "edition"])
def test_standard_required_strings(field):
    values = {"name": "standard", "edition": "edition"}
    values.pop(field)
    with pytest.raises(ValidationError):
        DesignStandard(**values)


@pytest.mark.parametrize("applicable", [True, False])
def test_decision_true_false_future_state_reason_and_source(applicable):
    source = PropertySource(kind="imported", name="supplied decision")
    supplied = decision(applicable=applicable, reason=" supplied reason ", source=source)
    assert supplied.applicable is applicable
    assert supplied.limit_state == "future_lateral_torsional_buckling"
    assert supplied.reason == " supplied reason "
    assert supplied.source == source
    assert decision().reason is decision().source is None


@pytest.mark.parametrize("bad", [1, 0, "true", "false", None, 1.0])
def test_applicable_strict_bool(bad):
    with pytest.raises(ValidationError):
        decision(applicable=bad)


def test_decision_requires_applicable():
    with pytest.raises(ValidationError):
        ApplicabilityDecision(limit_state="state")


@pytest.mark.parametrize("field", ["limit_state", "reason"])
@pytest.mark.parametrize("bad", ["", " \t\n", 1, False])
def test_decision_strings_strict_and_nonblank(field, bad):
    with pytest.raises(ValidationError):
        decision(**{field: bad})


def test_context_order_sources_and_nested_snapshots():
    supplied = standard(source=PropertySource(kind="manual"))
    first = decision(limit_state="z", source=PropertySource(kind="imported"))
    second = decision(limit_state="a", applicable=False, source=PropertySource(kind="solver"))
    before = [value.model_dump_json() for value in (supplied, first, second)]
    context = DesignContext(standard=supplied, applicability=(first, second))
    assert [d.limit_state for d in context.applicability] == ["z", "a"]
    assert context.standard is not supplied
    assert context.standard.source is not supplied.source
    assert context.applicability[0] is not first
    assert context.applicability[0].source is not first.source
    assert before == [value.model_dump_json() for value in (supplied, first, second)]


@pytest.mark.parametrize("applicable", [True, False])
def test_duplicate_same_or_conflicting_decisions_rejected(applicable):
    first = decision()
    second = decision(applicable=applicable)
    for order in ((first, second), (second, first)):
        with pytest.raises(ValidationError, match="Duplicate applicability limit_state"):
            DesignContext(standard=standard(), applicability=order)


def test_exact_duplicate_object_rejected():
    supplied = decision()
    with pytest.raises(ValidationError, match="Duplicate"):
        DesignContext(standard=standard(), applicability=(supplied, supplied))


def test_case_and_whitespace_are_distinct_and_preserved():
    labels = ("state", "State", " state ")
    context = DesignContext(
        standard=standard(), applicability=tuple(decision(limit_state=s) for s in labels)
    )
    assert tuple(d.limit_state for d in context.applicability) == labels
    for label in labels:
        assert applicability_for(context, label).limit_state == label
    assert applicability_for(context, "STATE") is None


def test_context_requires_tuple_and_standard():
    with pytest.raises(ValidationError):
        DesignContext(standard=standard(), applicability=[decision()])
    with pytest.raises(ValidationError):
        DesignContext()


@pytest.mark.parametrize("target", ["standard", "decision", "context"])
def test_extra_fields_rejected(target):
    with pytest.raises(ValidationError, match="Extra inputs"):
        if target == "standard":
            standard(code="injected")
        elif target == "decision":
            decision(priority=1)
        else:
            DesignContext(standard=standard(), capacity=1)


@pytest.mark.parametrize("target", ["standard", "decision", "nested_standard", "nested_decision"])
def test_unchecked_invalid_sources_rejected(target):
    source = PropertySource(kind="manual").model_copy(update={"name": ""})
    with pytest.raises(ValidationError):
        if target == "standard":
            standard(source=source)
        elif target == "decision":
            decision(source=source)
        elif target == "nested_standard":
            DesignContext(standard=standard().model_copy(update={"source": source}))
        else:
            DesignContext(
                standard=standard(),
                applicability=(decision().model_copy(update={"source": source}),),
            )


@pytest.mark.parametrize("target", ["standard", "decision"])
def test_unchecked_invalid_nested_models_rejected(target):
    with pytest.raises(ValidationError):
        if target == "standard":
            DesignContext(standard=standard().model_copy(update={"name": ""}))
        else:
            DesignContext(
                standard=standard(),
                applicability=(decision().model_copy(update={"applicable": 1}),),
            )


def test_unchecked_duplicate_context_revalidation():
    supplied = decision()
    invalid = DesignContext(standard=standard()).model_copy(
        update={"applicability": (supplied, supplied)}
    )
    with pytest.raises(ValidationError, match="Duplicate"):
        DesignContext.model_validate(invalid)
    with pytest.raises(ValidationError, match="Duplicate"):
        applicability_for(invalid, "state")


def test_every_new_field_frozen_and_json_deep_copy():
    source = PropertySource(kind="manual", name="source")
    supplied = standard(source=source)
    choice = decision(source=source)
    context = DesignContext(standard=supplied, applicability=(choice,))
    for model in (supplied, choice, context):
        assert type(model).model_validate_json(model.model_dump_json()) == model
        assert model.model_copy(deep=True) == model
        for field in type(model).model_fields:
            with pytest.raises(ValidationError, match="frozen"):
                setattr(model, field, getattr(model, field))
    assert context.model_copy(deep=True).standard is not context.standard


def test_query_returns_supplied_true_false_or_unknown_without_mutation():
    context = DesignContext(
        standard=standard(),
        applicability=(decision(limit_state="a"), decision(limit_state="b", applicable=False)),
    )
    before = context.model_dump_json()
    assert applicability_for(context, "a").applicable is True
    assert applicability_for(context, "b").applicable is False
    assert applicability_for(context, "missing") is None
    assert context.model_dump_json() == before


@pytest.mark.parametrize("bad", ["", " \t\n", 1, None])
def test_query_invalid_label(bad):
    with pytest.raises(ValidationError):
        applicability_for(DesignContext(standard=standard()), bad)


@pytest.mark.parametrize("bad", [None, {}, "context"])
def test_query_wrong_context_type(bad):
    with pytest.raises(TypeError, match="Expected a DesignContext"):
        applicability_for(bad, "state")


def test_cold_core_import_no_design_adapters_or_comtypes():
    script = """
import sys
from jym_structural.core import DesignStandard, ApplicabilityDecision, DesignContext, applicability_for
c = DesignContext(standard=DesignStandard(name='unknown', edition='supplied'))
assert applicability_for(c, 'future') is None
assert not any(n.startswith(('jym_structural.design', 'jym_structural.adapters', 'comtypes'))
               for n in sys.modules)
"""
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)
