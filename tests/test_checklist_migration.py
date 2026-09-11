from copy import deepcopy

import pytest

from src.checklist_migration import (
    MigrationError, SOURCE_HEADERS, draft_rows, legacy_rule, sync_differences,
    restore_source_rows, validate_rows, metadata_applies, profile_audit, evidence_inventory,
)


def row(**changes):
    value = dict.fromkeys(SOURCE_HEADERS, "")
    value.update(common_id="REG-001", check_id="REG-001-ZC-ENG", scope="WW",
                 language="ENG", required_text="Original. Second sentence.",
                 section_heading="Notes", block_type="regulatory_note",
                 match_method="presence", expected_result="required_present",
                 status="approved", source_token="ZC_L02", importance="major")
    value.update(changes)
    return value


def test_reversible_mapping_preserves_every_field_and_unicode():
    rows = [row(required_text="  é 中文\n문장 2.  ", note="original note", evidence_file="old.xlsx")]
    draft = draft_rows(rows)
    assert draft[0]["approval_status"] == "approved"
    assert draft[0]["legacy_block_type"] == "regulatory_note"
    assert draft[0]["source_reference_token"] == "ZC_L02"
    assert "status" not in draft[0]
    assert "migration_status" not in draft[0]
    assert restore_source_rows(draft) == rows


def test_manually_authored_rules_may_have_no_source_reference():
    rows = [row(source_token="")]
    assert draft_rows(rows)[0]["source_reference_token"] == ""
    assert metadata_applies(rows[0], dict(source_token="XU_ENG", region="XU", language="ENG", doc_type="A3"))


def test_approval_states_and_order_are_not_changed():
    rows = [row(check_id=f"REG-001-{i}-ENG", status=status) for i, status in enumerate(("review", "approved", "deprecated"))]
    original = deepcopy(rows)
    assert [r["approval_status"] for r in draft_rows(rows)] == ["review", "approved", "deprecated"]
    assert rows == original


@pytest.mark.parametrize("change", [{"check_id": ""}, {"status": "candidate"}, {"match_method": "guess"},
                                   {"expected_result": "optional"}, {"new_field": "lost?"}, {"required_text": 0}])
def test_unrecognized_rules_do_not_silently_migrate(change):
    with pytest.raises(MigrationError):
        validate_rows([row(**change)])


def test_duplicate_ids_are_rejected():
    with pytest.raises(MigrationError, match="duplicate"):
        validate_rows([row(), row()])


def test_v1_sync_uses_actual_exporter_normalization():
    source = row(scope="GLOBAL;ZC;WW", language="ENG; C-FRA", required_text=" text \n")
    expected = {**source, "scope": ["WW", "ZC"], "exclude_scope": [], "language": ["ENG", "C-FRA"], "required_text": "text"}
    assert legacy_rule(source) == expected
    assert sync_differences([source], {"schema_version": 1, "rules": [expected]}) == []


def test_sync_reports_changed_fields_not_just_row_counts():
    source = row()
    runtime = legacy_rule(source)
    runtime["required_text"] = "wrong wording"
    diffs = sync_differences([source], {"schema_version": 1, "rules": [runtime]})
    assert [(d["excel_row"], d["field"]) for d in diffs] == [(2, "required_text")]


def test_sync_detects_order_and_extra_row_drift():
    a, b = row(), row(check_id="REG-002-ZC-ENG", common_id="REG-002")
    assert sync_differences([a, b], {"schema_version": 1, "rules": [legacy_rule(b), legacy_rule(a)]})
    assert sync_differences([a], {"schema_version": 1, "rules": []})


def test_source_token_is_a_reported_hypothesis_not_a_silent_new_filter():
    rule = row()
    context = dict(source_token="XU_ENG", region="XU", language="ENG", doc_type="A3")
    assert metadata_applies(rule, context)
    assert not metadata_applies(rule, context, restrict_source_token=True)
    result = profile_audit([rule], [dict(source_token="XU_ENG", region="XU", languages="ENG", doc_type="A3")])
    assert len(result["scope_differences"]) == 1
    assert result["rows"][0]["migration_status"] == "pending"


@pytest.mark.parametrize("rule_change,context_change", [
    ({"exclude_scope": "XU"}, {}), ({"exclude_scope": "XU_ENG"}, {}),
    ({"doc_type": "A2"}, {}), ({"language": "C-FRA"}, {}), ({"scope": "ZC"}, {}),
])
def test_applicability_exclusion_and_language_boundaries(rule_change, context_change):
    context = dict(source_token="XU_ENG", region="XU", language="ENG", doc_type="A3", **context_change)
    assert not metadata_applies(row(**rule_change), context)


def test_unapproved_rows_are_retained_but_never_counted_as_active():
    source = row(status="review")
    report = profile_audit([source], [dict(source_token="XU_ENG", region="XU", languages="ENG", doc_type="A3")])
    assert len(report["rows"]) == 1
    assert report["rows"][0]["migration_status"] == "excluded"
    assert report["scope_differences"] == []


def test_evidence_distinguishes_multiple_files_folders_and_descriptions(tmp_path):
    output = tmp_path / "outputs"
    output.mkdir()
    (output / "a.json").write_text("{}")
    (output / "b.json").write_text("{}")
    rows = [row(check_id=str(i), evidence_file=value) for i, value in enumerate((
        "outputs/a.json; outputs/b.json", "outputs/", "confirmed final comparison artifacts", "outputs/missing.json"))]
    assert [r["evidence_state"] for r in evidence_inventory(rows, tmp_path)] == [
        "exists_not_revalidated", "directory_reference", "descriptive_reference", "missing"]


@pytest.mark.parametrize("invalid", ["headers", "formula", "error", "number", "blank"])
def test_excel_reader_rejects_unsafe_rule_cells(monkeypatch, invalid):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from src.checklist_migration import read_excel_rows
    cells = [SimpleNamespace(value=value, data_type="s", coordinate=f"R2C{i}")
             for i, value in enumerate(row().values(), 1)]
    headers = list(SOURCE_HEADERS)
    if invalid == "headers":
        headers.reverse()
    elif invalid in ("formula", "error"):
        cells[0].data_type = "f" if invalid == "formula" else "e"
    elif invalid == "number":
        cells[0].value = 123
    else:
        for cell in cells:
            cell.value = None
    sheet = Mock()
    sheet.iter_rows.return_value = iter([[SimpleNamespace(value=h) for h in headers], cells])
    # Use an explicit tiny workbook rather than authoring a real XLSX in this unit test.
    class FakeWorkbook:
        sheetnames = ["Checklist_Master"]
        close = Mock()

        def __getitem__(self, name):
            return sheet

    book = FakeWorkbook()
    monkeypatch.setattr("openpyxl.load_workbook", lambda *a, **kw: book)
    with pytest.raises(MigrationError):
        read_excel_rows("unused.xlsx")
    book.close.assert_called_once()


@pytest.mark.parametrize("change", [None, "required_text", "approval_status", "source_reference_token"])
def test_export_rereads_excel_and_never_activates_draft(tmp_path, monkeypatch, change):
    import json
    from scripts import audit_checklist_migration as command
    source = tmp_path / "source.xlsx"
    source.write_bytes(b"source fixture")
    workbook = tmp_path / "draft.xlsx"
    workbook.write_bytes(b"draft fixture")
    original = [row()]
    expected = draft_rows(original)
    actual = deepcopy(expected)
    if change:
        actual[0][change] = "changed"
    audit = tmp_path / "audit.json"
    audit.write_text(json.dumps({"source_xlsx": str(source), "source_xlsx_sha256": command.digest(source),
                                 "source_commit": command.SOURCE_COMMIT, "draft_rows": expected}))
    monkeypatch.setattr(command, "read_excel_rows", lambda path, draft=False: actual if draft else original)
    destination = tmp_path / "draft.json"
    if change:
        with pytest.raises(MigrationError):
            command.export_draft(workbook, audit, destination)
        assert not destination.exists()
    else:
        result = command.export_draft(workbook, audit, destination)
        assert result["rules"] == expected
        assert result["activation_status"] == "blocked_pending_contract_review"
        with pytest.raises(FileExistsError):
            command.export_draft(workbook, audit, destination)


def test_saved_draft_excel_round_trip_matches_audit_and_derived_json():
    import json
    from pathlib import Path
    from src.checklist_migration import read_excel_rows
    from scripts.audit_checklist_migration import digest, SOURCE_XLSX_SHA
    folder = Path(__file__).resolve().parents[1] / "metadata/checklist_v2/drafts/20260911"
    audit = json.loads((folder / "migration_audit.json").read_text(encoding="utf-8"))
    payload = json.loads((folder / "checklist_v2_draft.json").read_text(encoding="utf-8"))
    workbook = folder / "checklist_v2_draft.xlsx"
    actual = read_excel_rows(workbook, draft=True)
    assert actual == payload["rules"] == audit["draft_rows"]
    assert len(actual) == 547
    assert payload["master_sha256"] == digest(workbook)
    assert payload["source_master_sha256"] == SOURCE_XLSX_SHA
    assert payload["activation_status"] == "blocked_pending_contract_review"
    assert sum(not row["source_reference_token"] for row in actual) == 10
