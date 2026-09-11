"""Run the frozen-draft ZC ENG observation pilot without activating the DB."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from src.checklist_migration import read_excel_rows
from src.checklist_observation import observe_checklist

DEFAULT_DRAFT = Path(__file__).resolve().parents[1] / "metadata/checklist_v2/drafts/20260911"
FROZEN_DRAFT_JSON_SHA256 = "9c0ff6c536517905f9a9d675da67ebbc8eeea23beebe8a9ee82dbce370e62762"


def run_observation(bundle: Path, pdf: Path, mapping: Path, draft: Path, output: Path) -> dict:
    from src.semantic_xml_reader import read_review_bundle
    from src.xml_review_gate import require, validate_bundle

    if output.exists():
        raise FileExistsError(f"use a fresh output file: {output}")
    receipt_path = bundle / "review_run.json"
    json_path, excel_path = draft / "checklist_v2_draft.json", draft / "checklist_v2_draft.xlsx"
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    paths = (receipt_path, json_path, excel_path)
    before = tuple(digest(path) for path in paths)
    require(before[1] == FROZEN_DRAFT_JSON_SHA256, "draft JSON is not the frozen audited version")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    require(payload.get("schema_version") == "checklist-v2-draft/1", "unsupported draft schema")
    require(payload.get("activation_status") == "blocked_pending_contract_review", "draft activation status changed")
    require(payload.get("master_sha256") == before[2], "draft Excel hash differs from exported JSON")
    rows = read_excel_rows(excel_path, draft=True)
    require(rows == payload.get("rules"), "draft Excel and JSON values differ")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    document = read_review_bundle(bundle, receipt, pdf_path=pdf, mapping_path=mapping)
    report = observe_checklist(document, rows)
    require(tuple(digest(path) for path in paths) == before, "input changed during observation")
    validate_bundle(bundle, receipt, pdf_path=pdf, mapping_path=mapping)
    report["inputs"] = {"receipt": str(receipt_path.resolve()), "receipt_sha256": before[0],
                        "draft_json": str(json_path.resolve()), "draft_json_sha256": before[1],
                        "draft_excel": str(excel_path.resolve()), "draft_excel_sha256": before[2],
                        "source_bundle": receipt}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=True, indent=2)
        stream.write("\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Provisional ZC ENG evidence observations; no checklist Pass/Fail")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, default=Path(__file__).resolve().parents[1] / "metadata/pdf_profile_mapping/pdf_profile_mapping.json")
    parser.add_argument("--draft", type=Path, default=DEFAULT_DRAFT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run_observation(args.bundle, args.pdf, args.mapping, args.draft, args.output)
    except (OSError, ValueError, ImportError) as exc:
        parser.exit(1, f"Checklist observation failed: {exc}\n")
    print(json.dumps(report["summary"], ensure_ascii=True))
    print("No rule approved; no business Pass/Fail issued.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
