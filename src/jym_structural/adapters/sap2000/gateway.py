from __future__ import annotations

import math
import sys
from collections.abc import Callable
from pathlib import PureWindowsPath
from typing import Any

from pydantic import ValidationError

from jym_structural.core.models import (
    AnalysisResult,
    FrameForces,
    Member,
    ModelInfo,
    Node,
    Point3D,
    ResultUnits,
    Section,
    StructuralModel,
)

from .contracts import (
    Sap2000AnalysisRunner,
    Sap2000ConnectionGateway,
    Sap2000ModelReader,
    Sap2000ResultsReader,
)


class Sap2000Error(RuntimeError):
    """An attachment or OAPI operation failed."""


_UNITS = dict(
    enumerate(
        (
            "lb_in_F",
            "lb_ft_F",
            "kip_in_F",
            "kip_ft_F",
            "kN_mm_C",
            "kN_m_C",
            "kgf_mm_C",
            "kgf_m_C",
            "N_mm_C",
            "N_m_C",
            "Ton_mm_C",
            "Ton_m_C",
            "kN_cm_C",
            "kgf_cm_C",
            "N_cm_C",
            "Ton_cm_C",
        ),
        start=1,
    )
)

# SAP2000 26.2.0: verified DLL, typelib, installed CHM and real typed comtypes call.
_FRAME_FORCE_OUTPUTS = (
    "NumberResults",
    "Obj",
    "ObjSta",
    "Elm",
    "ElmSta",
    "LoadCase",
    "StepType",
    "StepNum",
    "P",
    "V2",
    "V3",
    "T",
    "M2",
    "M3",
)


def _attach_running_instance() -> Any:
    if sys.platform != "win32":
        raise Sap2000Error("SAP2000 COM attachment requires Windows.")
    try:
        import comtypes.client
    except ImportError as exc:
        raise Sap2000Error("Install the sap2000 optional dependency to use COM.") from exc

    # Creating the helper does not start SAP2000. GetObject only attaches.
    helper = comtypes.client.CreateObject("SAP2000v1.Helper")
    from comtypes.gen import SAP2000v1

    helper = helper.QueryInterface(SAP2000v1.cHelper)
    return helper.GetObject("CSI.SAP2000.API.SapObject")


class ComSap2000Gateway(
    Sap2000ConnectionGateway,
    Sap2000ModelReader,
    Sap2000AnalysisRunner,
    Sap2000ResultsReader,
):
    """Read-only queries and an explicit analysis command boundary.

    Keep the gateway on the COM-initialized thread that created it. Attachment
    is explicit; health checks never start SAP2000 or silently reconnect.
    """

    def __init__(self, *, attach: Callable[[], Any] | None = None) -> None:
        self._attach = attach if attach is not None else _attach_running_instance
        self._application: Any = None

    def connect_to_running_instance(self) -> ModelInfo:
        self._application = None
        try:
            application = self._attach()
            if application is None:
                raise Sap2000Error("No accessible running SAP2000 instance was found.")
            info = self._read_model_info(application)
        except Sap2000Error:
            raise
        except Exception as exc:
            raise Sap2000Error("Could not attach to or read a running SAP2000 instance.") from exc
        self._application = application
        return info

    def health_check(self) -> bool:
        if self._application is None:
            return False
        try:
            self._read_model_info(self._application)
        except Exception:  # noqa: BLE001 - health probes report COM/transport failures as False
            return False
        return True

    def run_analysis(self) -> None:
        """Explicit command; CSI may change analysis state and files on disk.

        Run once with the model's existing case settings. Never retry, reconnect,
        save, change units or lock/unlock the model on the caller's behalf.
        """
        if self._application is None:
            raise Sap2000Error("Connect to a running SAP2000 instance before running analysis.")
        try:
            return_code = self._application.SapModel.Analyze.RunAnalysis()
        except Exception as exc:
            raise Sap2000Error("Analyze.RunAnalysis COM command failed.") from exc
        # Verified SAP2000v1 signature: no inputs, scalar Int32 pRetVal.
        if type(return_code) is not int:
            raise Sap2000Error("Analyze.RunAnalysis returned an unexpected CSI response.")
        if return_code != 0:
            raise Sap2000Error(f"Analyze.RunAnalysis failed with CSI return code {return_code}.")

    def get_member_results(self, member_id: str) -> AnalysisResult:
        """Read one object's element forces for the CURRENT output selection.

        Never selects output, analyzes, saves or converts present units. A zero
        row response is an explicit error, not a request to generate results.
        """
        model = self._model()
        if not isinstance(member_id, str) or not member_id.strip():
            raise Sap2000Error("Results.FrameForce requires a nonempty member ID.")
        operation = f"Results.FrameForce({member_id!r})"
        try:
            before = self._read_model_info(self._application)
            result = self._query(
                operation,
                model.Results.FrameForce,
                _FRAME_FORCE_OUTPUTS,
                Name=member_id,
                ItemTypeElm=0,  # ObjectElm: elements belonging to this object.
            )
            if self._read_model_info(self._application) != before:
                raise Sap2000Error(f"{operation}: model metadata or present units changed.")
        except Sap2000Error:
            raise
        except Exception as exc:
            raise Sap2000Error(f"{operation} COM query failed.") from exc

        count = result["NumberResults"]
        if type(count) is not int or count < 0:
            raise Sap2000Error(f"{operation}: invalid NumberResults {count!r}.")
        arrays = []
        for name in _FRAME_FORCE_OUTPUTS[1:]:
            values = result[name]
            if values is None and count == 0:
                values = ()
            if not isinstance(values, (list, tuple)) or len(values) != count:
                raise Sap2000Error(
                    f"{operation}: {name} length does not match NumberResults {count}."
                )
            arrays.append(values)
        if count == 0:
            raise Sap2000Error(
                f"{operation}: no results for the current output selection; "
                "check existing analysis and selected cases/combinations. Analysis was not run."
            )

        forces = []
        for index, values in enumerate(zip(*arrays, strict=True)):
            row = dict(zip(_FRAME_FORCE_OUTPUTS[1:], values, strict=True))
            if row["Obj"] != member_id:
                raise Sap2000Error(f"{operation}: row {index} returned an unexpected object ID.")
            for name in ("Obj", "Elm", "LoadCase"):
                if not isinstance(row[name], str) or not row[name].strip():
                    raise Sap2000Error(f"{operation}: row {index} has invalid {name}.")
            # Unused StepType is a null BSTR in the verified SAP2000 response.
            if row["StepType"] is not None and not isinstance(row["StepType"], str):
                raise Sap2000Error(f"{operation}: row {index} has invalid StepType.")
            for name in ("ObjSta", "ElmSta", "StepNum", "P", "V2", "V3", "T", "M2", "M3"):
                value = row[name]
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise Sap2000Error(f"{operation}: row {index} has non-finite/invalid {name}.")
            forces.append(
                FrameForces(
                    object_id=row["Obj"],
                    station=row["ObjSta"],
                    element_id=row["Elm"],
                    element_station=row["ElmSta"],
                    load_case=row["LoadCase"],
                    step_type=row["StepType"],
                    step_num=row["StepNum"],
                    p=row["P"],
                    v2=row["V2"],
                    v3=row["V3"],
                    t=row["T"],
                    m2=row["M2"],
                    m3=row["M3"],
                )
            )
        # Include all force components to break same-station ties deterministically;
        # retain repeated rows (e.g. element boundaries), never deduplicate/envelope.
        forces.sort(
            key=lambda row: (
                row.load_case,
                row.step_type or "",
                row.step_num,
                row.station,
                row.element_id,
                row.element_station,
                row.p,
                row.v2,
                row.v3,
                row.t,
                row.m2,
                row.m3,
                row.step_type is not None,
            )
        )
        force_unit, length_unit, _temperature = before.units.split("_")
        return AnalysisResult(
            member_id=member_id,
            forces=forces,
            units=ResultUnits(force=force_unit, length=length_unit),
        )

    def _model(self) -> Any:
        if self._application is None:
            raise Sap2000Error("Connect to a running SAP2000 instance before reading inventory.")
        try:
            return self._application.SapModel
        except Exception as exc:
            raise Sap2000Error("Could not access the connected SAP2000 model.") from exc

    @staticmethod
    def _query(
        operation: str, method: Callable[..., Any], outputs: tuple[str, ...], **inputs: Any
    ) -> dict[str, Any]:
        """Decode typed SAP2000v1 output order verified against the installed typelib.

        COM [in,out] parameters precede pRetVal. Do not infer positions from
        value types (counts, coordinates and CSI status can all be numeric).
        """
        try:
            response = method(**inputs)
        except Exception as exc:
            raise Sap2000Error(f"{operation} COM query failed.") from exc
        if not isinstance(response, (list, tuple)) or len(response) != len(outputs) + 1:
            raise Sap2000Error(f"{operation} returned an unexpected COM response shape.")
        *values, return_code = response
        if type(return_code) is not int or return_code != 0:
            raise Sap2000Error(f"{operation} failed with CSI return code {return_code!r}.")
        return dict(zip(outputs, values, strict=True))

    @classmethod
    def _names(cls, operation: str, method: Callable[..., Any]) -> list[str]:
        result = cls._query(operation, method, ("NumberNames", "MyName"))
        count, names = result["NumberNames"], result["MyName"]
        # An empty SAFEARRAY may be marshalled as None, () or [].
        if count == 0 and names is None:
            names = ()
        if (
            type(count) is not int
            or count < 0
            or not isinstance(names, (list, tuple))
            or len(names) != count
            or any(not isinstance(name, str) or not name.strip() for name in names)
            or len(set(names)) != count
        ):
            raise Sap2000Error(f"{operation} returned invalid names/count.")
        return sorted(names)

    def list_sections(self) -> list[Section]:
        model = self._model()
        sections = []
        for name in self._names("PropFrame.GetNameList", model.PropFrame.GetNameList):
            result = self._query(
                f"PropFrame.GetMaterial({name})",
                model.PropFrame.GetMaterial,
                ("MatProp",),
                Name=name,
            )
            material = result["MatProp"]
            if not isinstance(material, str):
                raise Sap2000Error(f"PropFrame.GetMaterial({name}) returned an invalid material.")
            sections.append(Section(name=name, material=material or None))
        return sections

    def list_members(self) -> list[Member]:
        """Length is the Global I-J chord in present length units, not analysis length.

        Section is CSI PropName (current concrete property), not SAuto (the
        auto-select list). Material is available by joining Section.name.
        """
        members, _nodes = self._read_members_and_nodes(self._model())
        return members

    def _read_members_and_nodes(self, model: Any) -> tuple[list[Member], list[Node]]:
        nodes: dict[str, Node] = {}

        def point_coordinates(name: str) -> tuple[float, float, float]:
            if name not in nodes:
                result = self._query(
                    f"PointObj.GetCoordCartesian({name})",
                    model.PointObj.GetCoordCartesian,
                    ("X", "Y", "Z"),
                    Name=name,
                    CSys="Global",
                )
                try:
                    position = Point3D(x=result["X"], y=result["Y"], z=result["Z"])
                except ValidationError as exc:
                    raise Sap2000Error(
                        f"PointObj.GetCoordCartesian({name}) returned invalid XYZ."
                    ) from exc
                nodes[name] = Node(id=name, position=position)
            position = nodes[name].position
            return position.x, position.y, position.z

        members = []
        for name in self._names("FrameObj.GetNameList", model.FrameObj.GetNameList):
            points = self._query(
                f"FrameObj.GetPoints({name})",
                model.FrameObj.GetPoints,
                ("Point1", "Point2"),
                Name=name,
            )
            start, end = points["Point1"], points["Point2"]
            if any(not isinstance(point, str) or not point.strip() for point in (start, end)):
                raise Sap2000Error(f"FrameObj.GetPoints({name}) returned invalid endpoints.")
            assignment = self._query(
                f"FrameObj.GetSection({name})",
                model.FrameObj.GetSection,
                ("PropName", "SAuto"),
                Name=name,
            )
            section = assignment["PropName"]
            if not isinstance(section, str) or not isinstance(assignment["SAuto"], str):
                raise Sap2000Error(f"FrameObj.GetSection({name}) returned an invalid assignment.")
            length = math.dist(point_coordinates(start), point_coordinates(end))
            if not math.isfinite(length):
                raise Sap2000Error(f"Frame {name} has a non-finite derived length.")
            members.append(
                Member(
                    id=name,
                    name=name,
                    section=None if section in ("", "None") else section,
                    start_node=start,
                    end_node=end,
                    length=length,
                )
            )
        return members, [nodes[name] for name in sorted(nodes)]

    def read_structural_model(self) -> StructuralModel:
        """Build a validated snapshot of frame endpoints in present units.

        Does not enumerate isolated points or convert coordinates/lengths.
        """
        model = self._model()
        try:
            info = self._read_model_info(self._application)
            sections = self.list_sections()
            members, nodes = self._read_members_and_nodes(model)
            if self._read_model_info(self._application) != info:
                raise Sap2000Error(
                    "Model metadata or present units changed while reading geometry."
                )
        except (Sap2000Error, ValidationError):
            raise
        except Exception as exc:
            raise Sap2000Error("Could not read SAP2000 structural geometry.") from exc
        return StructuralModel(
            model_info=info,
            length_unit=info.units.split("_")[1],
            nodes=nodes,
            sections=sections,
            members=members,
        )

    @staticmethod
    def _read_model_info(application: Any) -> ModelInfo:
        model = application.SapModel
        # Typed comtypes returns output parameters followed by the CSI return code.
        version, _version_number, return_code = model.GetVersion()
        if return_code != 0:
            raise Sap2000Error(f"GetVersion failed with CSI return code {return_code}.")
        if not isinstance(version, str) or not version.strip():
            raise Sap2000Error("GetVersion returned an empty or invalid version.")
        # These two OAPI methods return values directly, not CSI status codes.
        path = model.GetModelFilename(True)
        if not isinstance(path, str) or not path.strip():
            raise Sap2000Error("No saved model is loaded; open an existing .sdb model.")
        unit_code = model.GetPresentUnits()
        if unit_code not in _UNITS:
            raise Sap2000Error(f"GetPresentUnits returned unsupported units: {unit_code!r}.")
        return ModelInfo(
            software="SAP2000",
            version=version,
            model_name=PureWindowsPath(path).name,
            model_path=path,
            units=_UNITS[unit_code],
        )
