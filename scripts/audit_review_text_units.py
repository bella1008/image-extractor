"""Inspect source-bounded text from an already completed, checked XML run."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from src.review_text_units import build_text_unit_index


def audit_text_units(bundle: Path, pdf: Path, mapping: Path, output: Path) -> dict:
    from src.semantic_xml_reader import read_review_bundle
    from src.xml_review_gate import require, sha256, validate_bundle

    if output.exists():
        raise FileExistsError(f"use a new output file: {output}")
    receipt_path = bundle / "review_run.json"
    receipt_bytes = receipt_path.read_bytes()
    receipt = json.loads(receipt_bytes)
    document = read_review_bundle(bundle, receipt, pdf_path=pdf, mapping_path=mapping)
    index = build_text_unit_index(document)
    # Re-check at the publication boundary rather than trusting a long-running
    # index build while another terminal might replace its inputs.
    require(receipt_path.read_bytes() == receipt_bytes, "receipt changed during indexing")
    validate_bundle(bundle, receipt, pdf_path=pdf, mapping_path=mapping)
    units = [{**asdict(unit), "text": unit.text, "ready_for_text_match": unit.ready_for_text_match}
             for unit in index.units]
    payload = {
        "schema_version": index.schema_version, "decision_status": index.decision_status,
        "source_receipt": str(receipt_path.resolve()), "source_receipt_sha256": sha256(receipt_bytes),
        "source_bundle": receipt, "context": asdict(document.context),
        "summary": {
            "unit_count": len(units), "text_part_count": sum(len(unit.parts) for unit in index.units),
            "text_preconditions_met": sum(unit.ready_for_text_match for unit in index.units),
            "needs_review": sum(not unit.ready_for_text_match for unit in index.units),
            "by_language": dict(Counter(unit.language or "unassigned_or_mixed" for unit in index.units)),
            "by_structure": dict(Counter(unit.structure_type for unit in index.units)),
            "issues": dict(Counter(issue for unit in index.units for issue in unit.issues)),
        },
        "units": units,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=True, indent=2)
        stream.write("\n")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory XML text boundaries; does not evaluate checklist rules")
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--mapping", type=Path, default=Path(__file__).resolve().parents[1] / "metadata/pdf_profile_mapping/pdf_profile_mapping.json")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = audit_text_units(args.bundle, args.pdf, args.mapping, args.output)
    except (OSError, ValueError, ImportError) as exc:
        parser.exit(1, f"Text inventory failed: {exc}\n")
    print(json.dumps(result["summary"], ensure_ascii=True))
    print("Checklist not evaluated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
