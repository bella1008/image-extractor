"""Build a draft manifest, then export JSON only after rereading the created Excel."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from src.checklist_migration import (
    DRAFT_HEADERS, FIELD_MAP, MigrationError, draft_rows, evidence_inventory,
    profile_audit, read_excel_rows, restore_source_rows, sync_differences,
)

SOURCE_COMMIT = "4b001ff9a1a4f8ef91bed75a8ab314f4189d9476"
SOURCE_XLSX_SHA = "d6b0d4a5f3fd57b8eb3b6ea303a444878b9431ba66eed9a15c3692da0c5fa706"
SOURCE_JSON_SHA = "c6c65d8ba2a02d340b14cd9b7ae2a049fd83e461c44aca83edff4fb451784d90"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump_new(path: Path, payload: dict) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def audit_sources(project: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(f"use a fresh output directory: {output}")
    source = project / "metadata/checklist/mvp_checklist_master.xlsx"
    runtime = source.with_suffix(".json")
    mapping = project / "metadata/pdf_profile_mapping/pdf_profile_mapping.json"
    before = [digest(p) for p in (source, runtime, mapping)]
    if before[:2] != [SOURCE_XLSX_SHA, SOURCE_JSON_SHA]:
        raise MigrationError("source differs from the preserved migration baseline")
    rows = read_excel_rows(source)
    differences = sync_differences(rows, json.loads(runtime.read_text(encoding="utf-8")))
    if differences:
        raise MigrationError(f"Excel/JSON drift: {differences[:5]}")
    profiles = json.loads(mapping.read_text(encoding="utf-8"))
    audit = profile_audit(rows, profiles)
    evidence = evidence_inventory(rows, project)
    evidence_by_id = {r["check_id"]: r for r in evidence}
    for row in audit["rows"]:
        row.update(evidence_by_id[row["check_id"]])
    report = {
        "schema_version": "checklist-migration-audit/1", "source_commit": SOURCE_COMMIT,
        "source_xlsx": str(source.resolve()), "source_json": str(runtime.resolve()),
        "source_xlsx_sha256": before[0], "source_json_sha256": before[1], "mapping_sha256": before[2],
        "activation_status": "blocked_pending_contract_review",
        "summary": {"source_rows": len(rows), "common_ids": len({r["common_id"] for r in rows}),
                    "approval_states": dict(Counter(r["status"] for r in rows)), "sync_differences": 0,
                    "source_restriction_affected_rules": len({r["check_id"] for r in audit["scope_differences"]}),
                    "source_restriction_profile_language_pairs": len(audit["scope_differences"]),
                    "overlap_context_groups": len(audit["overlaps"]),
                    "evidence_states": dict(Counter(r["evidence_state"] for r in evidence))},
        "field_map": FIELD_MAP, "draft_headers": DRAFT_HEADERS, "draft_rows": draft_rows(rows), **audit,
    }
    if before != [digest(p) for p in (source, runtime, mapping)]:
        raise MigrationError("source changed during audit")
    output.mkdir(parents=True, exist_ok=False)
    dump_new(output / "migration_audit.json", report)
    return report


def export_draft(workbook: Path, audit_path: Path, destination: Path) -> dict:
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    source = Path(audit["source_xlsx"])
    if digest(source) != audit["source_xlsx_sha256"]:
        raise MigrationError("source Excel changed since audit")
    before = digest(workbook)
    rows = read_excel_rows(workbook, draft=True)
    if restore_source_rows(rows) != read_excel_rows(source):
        raise MigrationError("draft differs from source values or row order")
    if rows != audit["draft_rows"]:
        raise MigrationError("draft differs from audited field mapping")
    if digest(workbook) != before or digest(source) != audit["source_xlsx_sha256"]:
        raise MigrationError("master changed during export")
    # String fields preserve the exact authoring cells. A future approved runtime
    # schema may define selectors; this draft deliberately has no runtime approval.
    payload = {"schema_version": "checklist-v2-draft/1", "activation_status": "blocked_pending_contract_review",
               "source": workbook.name, "master_sha256": before,
               "source_commit": audit["source_commit"], "source_master_sha256": audit["source_xlsx_sha256"],
               "rules": rows}
    dump_new(destination, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    audit = sub.add_parser("audit")
    audit.add_argument("--project", required=True, type=Path)
    audit.add_argument("--output", required=True, type=Path)
    export = sub.add_parser("export")
    export.add_argument("--workbook", required=True, type=Path)
    export.add_argument("--audit", required=True, type=Path)
    export.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.action == "audit":
        result = audit_sources(args.project, args.output)
        print(json.dumps(result["summary"], ensure_ascii=True))
    else:
        result = export_draft(args.workbook, args.audit, args.output)
        print(f"Exported {len(result['rules'])} preserved rows; activation blocked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
