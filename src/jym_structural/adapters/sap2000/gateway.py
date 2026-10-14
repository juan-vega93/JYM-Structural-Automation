from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import PureWindowsPath
from typing import Any

from jym_structural.core.models import ModelInfo


class Sap2000Error(RuntimeError):
    """An attachment or read-only OAPI operation failed."""


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


class ComSap2000Gateway:
    """B1.1 read-only subset of the gateway; no model or analysis commands.

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
