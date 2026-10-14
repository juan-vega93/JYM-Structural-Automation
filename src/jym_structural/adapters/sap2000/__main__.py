"""Run with python -m jym_structural.adapters.sap2000."""

import sys

from .gateway import ComSap2000Gateway, Sap2000Error


def main() -> int:
    try:
        info = ComSap2000Gateway().connect_to_running_instance()
    except Sap2000Error as exc:
        print(f"SAP2000 diagnostic failed: {exc}", file=sys.stderr)
        return 1
    print(info.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
