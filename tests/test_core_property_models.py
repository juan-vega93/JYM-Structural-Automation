import json
import math
import subprocess
import sys

import pytest
from pydantic import ValidationError

from jym_structural.core import (
    MaterialProperties,
    MaterialUnits,
    PropertySource,
    Section,
    SectionProperties,
    SectionUnits,
)


@pytest.fixture
def material_data():
    # Synthetic, explicitly supplied test data; not a validated grade/catalog.
    return {
        "name": "steel-fixture",
        "fy": 250,
        "fu": 400,
        "elastic_modulus": 200000,
        "shear_modulus": 77000,
        "units": {"stress": "MPa"},
        "source": {"kind": "manual", "name": "synthetic fixture"},
    }


@pytest.fixture
def section_data():
    # Illustrative I-section, no fillets. No official profile designation/data.
    # Area/inertias/moduli approximate a 300x200x20x10 rectangular I fixture.
    # J and Cw are synthetic positive placeholders, never catalog claims.
    area, ix, iy = 10600, 171713333.33333334, 26688333.333333332
    return {
        "name": "I-300-fixture",
        "area": area,
        "ix": ix,
        "iy": iy,
        "sx": ix / 150,
        "sy": iy / 100,
        "zx": 1289000,
        "zy": 406500,
        "rx": math.sqrt(ix / area),
        "ry": math.sqrt(iy / area),
        "j": 600000,
        "cw": 2e12,
        "d": 300,
        "bf": 200,
        "tf": 20,
        "tw": 10,
        "section_type": "I",
        "material_name": "steel-fixture",
        "units": {"length": "mm"},
        "source": {"kind": "manual", "name": "synthetic fixture"},
    }


def test_valid_material_values_are_not_completed_or_derived(material_data):
    material = MaterialProperties.model_validate(material_data)
    assert material.fy == 250
    assert material.fu == 400
    assert material.elastic_modulus == 200000
    assert material.shear_modulus == 77000
    assert material.poisson_ratio is None
    assert material.units.stress == "MPa"
    assert material.source.kind == "manual"
    material_data["fu"] = material_data["fy"]
    assert MaterialProperties.model_validate(material_data).fu == 250


@pytest.mark.parametrize("field", ["fy", "fu", "elastic_modulus", "shear_modulus"])
@pytest.mark.parametrize("value", [0, -1])
def test_material_requires_positive_supplied_values(material_data, field, value):
    material_data[field] = value
    with pytest.raises(ValidationError):
        MaterialProperties.model_validate(material_data)


def test_material_rejects_fu_below_fy(material_data):
    material_data["fu"] = 249
    with pytest.raises(ValidationError, match="fu must be greater than or equal to fy"):
        MaterialProperties.model_validate(material_data)


@pytest.mark.parametrize("field", ["fy", "fu", "elastic_modulus", "shear_modulus", "poisson_ratio"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_material_rejects_nonfinite_values(material_data, field, value):
    material_data[field] = value
    with pytest.raises(ValidationError):
        MaterialProperties.model_validate(material_data)


@pytest.mark.parametrize("value", [0, 0.3, 0.4999])
def test_valid_poisson_is_preserved_without_deriving_g(material_data, value):
    material_data["poisson_ratio"] = value
    material = MaterialProperties.model_validate(material_data)
    assert material.poisson_ratio == value
    assert material.shear_modulus == material_data["shear_modulus"]


@pytest.mark.parametrize("value", [-0.1, 0.5, 1])
def test_invalid_poisson(material_data, value):
    material_data["poisson_ratio"] = value
    with pytest.raises(ValidationError):
        MaterialProperties.model_validate(material_data)


@pytest.mark.parametrize("missing", ["fy", "fu", "elastic_modulus", "shear_modulus", "units"])
def test_missing_material_values_are_never_invented(material_data, missing):
    material_data.pop(missing)
    with pytest.raises(ValidationError):
        MaterialProperties.model_validate(material_data)


def test_valid_section_data_no_axis_mapping_and_lightweight_section_compatible(section_data):
    section = SectionProperties.model_validate(section_data)
    assert section.ix != section.iy
    assert section.sx != section.sy
    assert section.units.inertia == "mm^4"
    assert section.material_name == "steel-fixture"
    assert section.section_type == "I"
    lightweight = Section(name=section.name, material=section.material_name, family="I")
    assert lightweight.model_dump() == {
        "name": "I-300-fixture",
        "material": "steel-fixture",
        "family": "I",
    }


POSITIVE_SECTION_FIELDS = ("area", "ix", "iy", "sx", "sy", "zx", "zy", "rx", "ry", "j")
DIMENSIONS = ("d", "bf", "tf", "tw")


@pytest.mark.parametrize("field", POSITIVE_SECTION_FIELDS + DIMENSIONS)
@pytest.mark.parametrize("value", [0, -1])
def test_section_and_supplied_dimensions_must_be_positive(section_data, field, value):
    section_data[field] = value
    with pytest.raises(ValidationError):
        SectionProperties.model_validate(section_data)


@pytest.mark.parametrize("field", POSITIVE_SECTION_FIELDS + DIMENSIONS + ("cw",))
@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_all_section_numeric_fields_must_be_finite(section_data, field, value):
    section_data[field] = value
    with pytest.raises(ValidationError):
        SectionProperties.model_validate(section_data)


def test_cw_zero_allowed_but_negative_rejected(section_data):
    section_data["cw"] = 0
    assert SectionProperties.model_validate(section_data).cw == 0
    section_data["cw"] = -1
    with pytest.raises(ValidationError):
        SectionProperties.model_validate(section_data)


def test_section_optional_dimensions_type_material_and_provenance(section_data):
    for field in (*DIMENSIONS, "section_type", "material_name", "source"):
        section_data.pop(field)
    section = SectionProperties.model_validate(section_data)
    assert all(getattr(section, field) is None for field in DIMENSIONS)
    assert section.source is section.material_name is section.section_type is None


def test_no_type_specific_dimension_relations_are_assumed(section_data):
    section_data.update(section_type="Custom", d=1, tf=2, bf=1, tw=2)
    assert SectionProperties.model_validate(section_data).tf == 2


@pytest.mark.parametrize("bad", ["", " ", "\t\n"])
def test_names_and_unit_labels_must_be_nonblank(material_data, section_data, bad):
    with pytest.raises(ValidationError):
        MaterialProperties.model_validate({**material_data, "name": bad})
    with pytest.raises(ValidationError):
        SectionProperties.model_validate({**section_data, "name": bad})
    with pytest.raises(ValidationError):
        MaterialUnits(stress=bad)
    with pytest.raises(ValidationError):
        SectionUnits(length=bad)


@pytest.mark.parametrize("length", ["mm", "in", "custom-length"])
def test_units_derived_from_only_length_and_not_supplied_separately(length):
    units = SectionUnits(length=length)
    assert units.area == f"{length}^2"
    assert units.inertia == f"{length}^4"
    assert units.section_modulus == f"{length}^3"
    assert units.warping == f"{length}^6"
    assert units.model_dump() == {"length": length}
    assert SectionUnits.model_validate_json(units.model_dump_json()) == units
    with pytest.raises(ValidationError):
        SectionUnits(length=length, area="inconsistent")


def test_no_conversions_or_closed_unit_list(material_data, section_data):
    material_data["units"] = {"stress": "ksi"}
    section_data["units"] = {"length": "in"}
    material = MaterialProperties.model_validate(material_data)
    section = SectionProperties.model_validate(section_data)
    assert material.fy == material_data["fy"]
    assert section.area == section_data["area"]
    assert MaterialUnits(stress="custom-stress").stress == "custom-stress"


@pytest.mark.parametrize("kind", ["manual", "catalog", "solver", "bim", "imported"])
def test_provider_neutral_provenance(kind):
    source = PropertySource(kind=kind)
    assert source.name is source.version is None
    assert PropertySource.model_validate_json(source.model_dump_json()) == source
    named = PropertySource(kind=kind, name="generic source", version="1.0")
    assert named.version == "1.0"


def test_invalid_provenance_kind():
    with pytest.raises(ValidationError):
        PropertySource(kind="vendor-specific")


def test_frozen_models_json_round_trip_and_copy(material_data, section_data):
    material = MaterialProperties.model_validate(material_data)
    section = SectionProperties.model_validate(section_data)
    objects = [material, section, material.units, section.units, material.source]
    for original in objects:
        assert type(original).model_validate_json(original.model_dump_json()) == original
        copied = original.model_copy(deep=True)
        assert copied == original
        assert copied is not original
        field = next(iter(type(original).model_fields))
        with pytest.raises(ValidationError, match="frozen"):
            setattr(original, field, getattr(original, field))
    assert material.model_copy(deep=True).units is not material.units
    assert section.model_copy(deep=True).source is not section.source
    changed = MaterialProperties.model_validate({**material.model_dump(), "fy": 300})
    assert changed.fy == 300 and material.fy == 250
    with pytest.raises(ValidationError):
        MaterialProperties.model_validate({**material.model_dump(), "fy": 500})


def test_misspelled_or_out_of_scope_data_rejected(material_data):
    with pytest.raises(ValidationError, match="Extra inputs"):
        MaterialProperties.model_validate({**material_data, "density": 7850})
    with pytest.raises(ValidationError):
        MaterialUnits(stress="MPa", density="kg/m^3")


def test_property_models_load_without_any_adapter():
    script = """
import json
import sys
from jym_structural.core import MaterialProperties, MaterialUnits, SectionProperties, SectionUnits, PropertySource
assert SectionUnits(length='mm').area == 'mm^2'
print(json.dumps([m for m in sys.modules if m.startswith('jym_structural.adapters')]))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )
    assert json.loads(completed.stdout) == []
