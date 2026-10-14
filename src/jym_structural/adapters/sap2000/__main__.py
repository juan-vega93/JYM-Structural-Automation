"""Run with python -m jym_structural.adapters.sap2000."""

import argparse
import json
import sys

from .gateway import ComSap2000Gateway, Sap2000Error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only SAP2000 diagnostic")
    parser.add_argument("--inventory", action="store_true", help="Read B1.2 frames and sections")
    args = parser.parse_args(argv)
    try:
        gateway = ComSap2000Gateway()
        info = gateway.connect_to_running_instance()
        data = info.model_dump()
        if args.inventory:
            sections = gateway.list_sections()
            members = gateway.list_members()
            data = {
                "model": data,
                "counts": {"sections": len(sections), "members": len(members)},
                "sources": {
                    "section": "FrameObj.GetSection.PropName (current property; not SAuto)",
                    "material": "PropFrame.GetMaterial; join member.section to section.name",
                    "length": "derived Global I-J chord from PointObj.GetCoordCartesian",
                    "length_unit": info.units.split("_")[1] if info.units else None,
                },
                "sections": [section.model_dump() for section in sections],
                "members": [member.model_dump() for member in members],
            }
    except Sap2000Error as exc:
        print(f"SAP2000 diagnostic failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
