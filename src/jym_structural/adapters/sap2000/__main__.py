"""Read-only by default; --run-analysis explicitly executes a CSI command."""

import argparse
import json
import sys

from .gateway import ComSap2000Gateway, Sap2000Error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SAP2000 diagnostic and explicit analysis command")
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--inventory", action="store_true", help="Read B1.2 frames and sections")
    operation.add_argument(
        "--frame-results",
        metavar="MEMBER_ID",
        help="Read one frame for the current output selection",
    )
    operation.add_argument(
        "--run-analysis",
        action="store_true",
        help="COMMAND: run analysis once; SAP2000 may change analysis state and files",
    )
    args = parser.parse_args(argv)
    try:
        gateway = ComSap2000Gateway()
        info = gateway.connect_to_running_instance()
        data = info.model_dump()
        if args.run_analysis:
            gateway.run_analysis()
            data = {"command": "run_analysis", "status": "completed"}
        elif args.frame_results is not None:
            data = gateway.get_member_results(args.frame_results).model_dump()
        elif args.inventory:
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
