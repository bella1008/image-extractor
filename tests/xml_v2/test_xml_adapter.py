import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from tagged_pdf_extractor.application.evaluate_quality import QualityEvaluator
from tagged_pdf_extractor.domain.models import (
    ContentFragment, HeadingSignatureEntry, LanguageHeadingSignature,
    LanguageIntervalEvidence, MultilingualHeadingAudit, StructureElement, TaggedDocument,
)
from tagged_pdf_extractor.infrastructure.output_bundle import OutputBundleWriter
from tagged_pdf_extractor.domain.readability_formatting import apply_readability_formatting
from src.semantic_xml_reader import read_review_bundle
from src.xml_review_gate import BundleValidationError, EXTRACTOR_SHA256
from src.xml_review_run import extract_review_document


NAMES = ("raw_structure.xml", "semantic_document.xml", "extraction_report.json", "semantic_document.md")
MAPPING = Path(__file__).resolve().parents[2] / "metadata/pdf_profile_mapping/pdf_profile_mapping.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def bundle(tmp_path):
    pdf = tmp_path / "BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf"
    pdf.write_bytes(b"fixture PDF identity; the writer uses a constructed TaggedDocument")
    def fragment(page, mcid, text):
        return ContentFragment(page, mcid, (text,), text_bboxes=((1., 2., 3., 4.),))
    sections = []
    signatures = []
    for page, language, wording in ((0, "ENG", "First. Second."), (1, "C-FRA", "Un. Deux. Trois.")):
        paragraph = StructureElement("P", "paragraph", object_ref=f"{page + 10} 0 R", children=(
            fragment(page, 2, wording + " "),
            StructureElement("Figure", "figure", alternate_text="icon", attributes=(("/BBox", "[1,2,3,4]"),)),
            fragment(page, 3, "after"),
        ))
        cell = StructureElement("TD", "table_cell", attributes=(("/RowSpan", "2"),), children=(
            paragraph, StructureElement("L", "list", children=(
                StructureElement("LI", "list_item", children=(fragment(page, 4, "item"),)),
            )),
        ))
        sections.append(StructureElement("Sect", "section", children=(
            StructureElement("H1", "heading", heading_level=1, children=(fragment(page, 1, "Title"),)),
            StructureElement("Table", "table", children=(StructureElement("TR", "table_row", children=(cell,)),)),
        )))
        interval = LanguageIntervalEvidence(language, page, page, (page,), (page,), "structural_language_section")
        signatures.append(LanguageHeadingSignature(language, interval, (HeadingSignatureEntry(1, "source", None),)))
    audit = MultilingualHeadingAudit(True, True, 2, 2, True, True, True, True, True, tuple(signatures))
    source = TaggedDocument(pdf, True, "en-US", (), tuple(sections), multilingual_heading_audit=audit)
    baseline = "TitleFirst. Second. afteritemTitleUn. Deux. Trois. afteritem"
    report = QualityEvaluator().evaluate(source, baseline, xml_round_trip_ok=True)
    assert report.status == "pass"
    folder = tmp_path / "bundle"
    OutputBundleWriter().write(source, report, folder)
    receipt = {
        "contract": "tagged-pdf-xml/8405120", "extractor_sha256": EXTRACTOR_SHA256,
        "pdf_sha256": digest(pdf), "mapping_sha256": digest(MAPPING),
        "artifacts": {name: digest(folder / name) for name in NAMES},
    }
    return folder, receipt, pdf, source, report


def read(bundle):
    folder, receipt, pdf, *_ = bundle
    return read_review_bundle(folder, receipt, pdf_path=pdf, mapping_path=MAPPING)


def refresh(bundle, name):
    bundle[1]["artifacts"][name] = digest(bundle[0] / name)


def test_checklist_pilot_reads_frozen_excel_json_and_retains_all_rows(bundle, tmp_path):
    from scripts.run_checklist_observation import run_observation, DEFAULT_DRAFT
    folder, receipt, pdf, *_ = bundle
    (folder / "review_run.json").write_text(json.dumps(receipt), encoding="utf-8")
    output = tmp_path / "observation.json"
    result = run_observation(folder, pdf, MAPPING, DEFAULT_DRAFT, output)
    assert result["summary"]["rule_count"] == 547
    assert result["decision_status"] == "not_evaluated"
    assert set(r["status"] for r in result["rows"]) <= {"needs_review", "not_applicable", "excluded"}
    assert json.loads(output.read_text(encoding="utf-8"))["summary"] == result["summary"]
    with pytest.raises(FileExistsError):
        run_observation(folder, pdf, MAPPING, DEFAULT_DRAFT, output)


@pytest.mark.parametrize("changed", ["checklist_v2_draft.json", "checklist_v2_draft.xlsx"])
def test_checklist_pilot_rejects_changed_draft(bundle, tmp_path, changed):
    import shutil
    from scripts.run_checklist_observation import run_observation, DEFAULT_DRAFT
    folder, receipt, pdf, *_ = bundle
    (folder / "review_run.json").write_text(json.dumps(receipt), encoding="utf-8")
    draft = tmp_path / "draft"
    shutil.copytree(DEFAULT_DRAFT, draft)
    path = draft / changed
    path.write_bytes(path.read_bytes() + b" ")
    output = tmp_path / "observation.json"
    with pytest.raises(ValueError):
        run_observation(folder, pdf, MAPPING, draft, output)
    assert not output.exists()


def test_checklist_pilot_rejects_input_change_during_observation(bundle, tmp_path, monkeypatch):
    from src import review_service as command
    folder, receipt, pdf, *_ = bundle
    (folder / "review_run.json").write_text(json.dumps(receipt), encoding="utf-8")
    original = command.observe_checklist
    def changed(document, rules):
        path = folder / "semantic_document.xml"
        path.write_bytes(path.read_bytes() + b" ")
        return original(document, rules)
    monkeypatch.setattr(command, "observe_checklist", changed)
    output = tmp_path / "observation.json"
    with pytest.raises(ValueError):
        command.run_observation(folder, pdf, MAPPING, command.DEFAULT_DRAFT, output)
    assert not output.exists()


def test_review_service_publishes_checked_json_html_and_completion_last(bundle, tmp_path):
    from src.review_service import ReviewRequest, run_review
    folder, receipt, pdf, *_ = bundle
    (folder / 'review_run.json').write_text(json.dumps(receipt), encoding='utf-8')
    output = tmp_path / 'review'
    result = run_review(ReviewRequest(pdf, output, bundle=folder, mapping=MAPPING))
    assert result['status'] == 'ready_for_human_review'
    assert result['decision_status'] == 'not_evaluated'
    assert set(result['artifacts']) == {'observation.json', 'review.html'}
    assert all(digest(output / name) == expected for name, expected in result['artifacts'].items())
    assert json.loads((output / 'review_complete.json').read_text()) == result
    with pytest.raises(FileExistsError):
        run_review(ReviewRequest(pdf, output, bundle=folder, mapping=MAPPING))


@pytest.mark.parametrize('fault', ['changed_input', 'report_failure', 'input_changed_during_report', 'json_changed_during_html_write', 'html_changed_during_html_write', 'input_changed_during_html_write'])
def test_review_service_failure_never_publishes_completion(bundle, tmp_path, monkeypatch, fault):
    from src import review_service as service
    folder, receipt, pdf, *_ = bundle
    (folder / 'review_run.json').write_text(json.dumps(receipt), encoding='utf-8')
    path = folder / 'semantic_document.xml'
    if fault == 'changed_input':
        path.write_bytes(path.read_bytes() + b' ')
    elif fault.endswith('_during_html_write'):
        original = service._write_new
        def changed_write(target, text):
            original(target, text)
            if target.name == 'review.html':
                changed = path if fault.startswith('input') else target if fault.startswith('html') else target.parent / 'observation.json'
                changed.write_bytes(changed.read_bytes() + b' ')
        monkeypatch.setattr(service, '_write_new', changed_write)
    else:
        original = service.render_observation_html
        def broken(report):
            if fault == 'report_failure':
                raise ValueError('report failure fixture')
            path.write_bytes(path.read_bytes() + b' ')
            return original(report)
        monkeypatch.setattr(service, 'render_observation_html', broken)
    output = tmp_path / 'review'
    with pytest.raises(ValueError):
        service.run_review(service.ReviewRequest(pdf, output, bundle=folder, mapping=MAPPING))
    assert not (output / 'review_complete.json').exists()
    failure = json.loads((output / 'review_failed.json').read_text())
    assert failure['status'] == 'failed'
    assert failure['decision_status'] == 'not_evaluated'


def test_interrupted_completion_write_leaves_no_completion_name(bundle, tmp_path, monkeypatch):
    from src import review_service as service
    folder, receipt, pdf, *_ = bundle
    (folder / 'review_run.json').write_text(json.dumps(receipt), encoding='utf-8')
    original = service._write_new
    def interrupted(path, text):
        if path.name.startswith('review_complete'):
            original(path, '{partial')
            raise OSError('disk interruption fixture')
        original(path, text)
    monkeypatch.setattr(service, '_write_new', interrupted)
    output = tmp_path / 'interrupted'
    with pytest.raises(OSError):
        service.run_review(service.ReviewRequest(pdf, output, bundle=folder, mapping=MAPPING))
    assert not (output / 'review_complete.json').exists()
    assert (output / 'review_failed.json').exists()


@pytest.mark.parametrize('fault', [None, 'observation.json', 'review.html', 'review_failed.json', 'missing_receipt'])
def test_completed_observation_reader_rejects_changed_or_failed_output(bundle, tmp_path, fault):
    from src.review_service import ReviewRequest, run_review, read_completed_observation
    folder, receipt, pdf, *_ = bundle
    (folder / 'review_run.json').write_text(json.dumps(receipt), encoding='utf-8')
    output = tmp_path / 'review'
    run_review(ReviewRequest(pdf, output, bundle=folder, mapping=MAPPING))
    if fault is None:
        assert read_completed_observation(output)['summary']['rule_count'] == 547
        return
    if fault == 'missing_receipt':
        (output / 'review_complete.json').unlink()
    else:
        target = output / fault
        target.write_bytes((target.read_bytes() if target.exists() else b'') + b' ')
    with pytest.raises((ValueError, OSError)):
        read_completed_observation(output)


def test_report_view_export_consumes_only_completed_run_and_never_overwrites(bundle, tmp_path):
    from src.review_service import ReviewRequest, run_review
    from scripts.prepare_review_report import prepare_view
    folder, receipt, pdf, *_ = bundle
    (folder / 'review_run.json').write_text(json.dumps(receipt), encoding='utf-8')
    output = tmp_path / 'review'
    run_review(ReviewRequest(pdf, output, bundle=folder, mapping=MAPPING))
    view_path = tmp_path / 'view.json'
    view = prepare_view(output, view_path)
    assert len(view['checklist']) + len(view['excluded']) == 547
    assert json.loads(view_path.read_text())['summary'] == view['summary']
    with pytest.raises(FileExistsError):
        prepare_view(output, view_path)


def test_report_view_refuses_completion_changed_during_mapping(bundle, tmp_path, monkeypatch):
    from src.review_service import ReviewRequest, run_review
    from scripts import prepare_review_report as command
    folder, receipt, pdf, *_ = bundle
    (folder / 'review_run.json').write_text(json.dumps(receipt), encoding='utf-8')
    output = tmp_path / 'review'
    run_review(ReviewRequest(pdf, output, bundle=folder, mapping=MAPPING))
    original = command.build_report_view
    def change(report):
        path = output / 'review_complete.json'
        path.write_bytes(path.read_bytes() + b' ')
        return original(report)
    monkeypatch.setattr(command, 'build_report_view', change)
    view_path = tmp_path / 'view.json'
    with pytest.raises(ValueError):
        command.prepare_view(output, view_path)
    assert not view_path.exists()


def test_text_unit_inventory_uses_checked_bundle_and_fresh_output(bundle, tmp_path):
    from scripts.audit_review_text_units import audit_text_units
    folder, receipt, pdf, *_ = bundle
    (folder / "review_run.json").write_text(json.dumps(receipt), encoding="utf-8")
    output = tmp_path / "inventory.json"
    result = audit_text_units(folder, pdf, MAPPING, output)
    assert result["decision_status"] == "not_evaluated"
    assert result["context"]["source_token"] == "ZC_L02"
    assert result["summary"]["unit_count"] > 0
    assert any("visual_content_requires_review" in unit["issues"] for unit in result["units"])
    assert json.loads(output.read_text(encoding="utf-8"))["summary"] == result["summary"]
    with pytest.raises(FileExistsError):
        audit_text_units(folder, pdf, MAPPING, output)


@pytest.mark.parametrize("fault", ["missing_receipt", "changed_xml", "changed_during_index"])
def test_text_unit_inventory_rejects_untrusted_or_changed_input(bundle, tmp_path, monkeypatch, fault):
    from scripts import audit_review_text_units as command
    folder, receipt, pdf, *_ = bundle
    if fault != "missing_receipt":
        (folder / "review_run.json").write_text(json.dumps(receipt), encoding="utf-8")
    target = folder / "semantic_document.xml"
    if fault == "changed_xml":
        target.write_bytes(target.read_bytes() + b" ")
    if fault == "changed_during_index":
        original = command.build_text_unit_index
        def change(document):
            target.write_bytes(target.read_bytes() + b" ")
            return original(document)
        monkeypatch.setattr(command, "build_text_unit_index", change)
    output = tmp_path / "inventory.json"
    with pytest.raises((OSError, ValueError)):
        command.audit_text_units(folder, pdf, MAPPING, output)
    assert not output.exists()


def test_exact_hierarchy_text_evidence_and_languages(bundle):
    document = read(bundle)
    assert document.context.source_token == "ZC_L02"
    assert document.context.expected_languages == ("ENG", "C-FRA")
    nodes = list(document.iter_nodes())
    paragraphs = [n for n in nodes if n.structure_type == "paragraph"]
    assert [n.text_content for n in paragraphs] == ["First. Second. after", "Un. Deux. Trois. after"]
    assert [n.language for n in paragraphs] == ["ENG", "C-FRA"]
    assert paragraphs[0].source_role == "P"
    assert [n.structure_type for n in paragraphs[0].content] == ["text", "figure", "text"]
    assert paragraphs[0].content[0].evidence[0].bbox == (1., 2., 3., 4.)
    assert paragraphs[0].content[0].evidence[0].mcid == 2
    cell = next(n for n in nodes if n.structure_type == "table_cell")
    assert dict(cell.attributes)["source:/RowSpan"] == "2"
    assert [n.structure_type for n in cell.content] == ["paragraph", "list"]
    assert all(n.review_roles == () for n in nodes)
    assert len({n.node_id for n in nodes}) == len(nodes)
    assert read(bundle) == document


@pytest.mark.parametrize("name", NAMES)
def test_changed_or_mixed_artifact_rejected(bundle, name):
    with (bundle[0] / name).open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(BundleValidationError, match="hash"):
        read(bundle)


@pytest.mark.parametrize("change", ["missing", "false", "integer", "empty", "status", "error"])
def test_quality_failure_is_not_missing_checklist_text(bundle, change):
    path = bundle[0] / "extraction_report.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    if change == "missing":
        del report["hard_gates"]["has_structure"]
    elif change == "empty":
        report["hard_gates"] = {}
    elif change == "status":
        report["status"] = "fail"
    elif change == "error":
        report["diagnostics"].append({"severity": "error", "code": "test", "message": "failed"})
    else:
        report["hard_gates"]["has_structure"] = False if change == "false" else 1
    path.write_text(json.dumps(report), encoding="utf-8")
    refresh(bundle, path.name)
    with pytest.raises(BundleValidationError):
        read(bundle)


@pytest.mark.parametrize("key", ["contract", "pdf_sha256", "mapping_sha256"])
def test_version_and_input_identity_required(bundle, key):
    bundle[1][key] = "wrong"
    with pytest.raises(BundleValidationError):
        read(bundle)


def test_no_receipt_no_automatic_review(bundle):
    bundle[1].clear()
    with pytest.raises(BundleValidationError):
        read(bundle)


def test_raw_semantic_text_mismatch_even_with_updated_digest(bundle):
    path = bundle[0] / "semantic_document.xml"
    path.write_text(path.read_text(encoding="utf-8").replace("First.", "Other."), encoding="utf-8")
    refresh(bundle, path.name)
    with pytest.raises(BundleValidationError, match="text"):
        read(bundle)


def test_audit_mismatch_even_with_updated_digest(bundle):
    path = bundle[0] / "semantic_document.xml"
    path.write_text(path.read_text(encoding="utf-8").replace('code="C-FRA"', 'code="DEU"'), encoding="utf-8")
    refresh(bundle, path.name)
    with pytest.raises(BundleValidationError, match="audit"):
        read(bundle)


def test_existing_run_directory_never_overwritten(tmp_path):
    folder = tmp_path / "existing"
    folder.mkdir()
    with pytest.raises(FileExistsError):
        extract_review_document(tmp_path / "missing.pdf", folder, MAPPING)
    assert list(folder.iterdir()) == []


def rewrite_source(bundle, source):
    folder, receipt, _, _, report = bundle
    report = QualityEvaluator().evaluate(source, "TitleFirst. Second. afteritemTitleUn. Deux. Trois. afteritem", xml_round_trip_ok=True)
    OutputBundleWriter().write(source, report, folder, overwrite=True)
    for name in NAMES:
        refresh(bundle, name)


def test_unknown_structure_and_shared_empty_figure_preserved(bundle):
    source = bundle[3]
    # A shared item outside the audited intervals must remain unassigned.
    source = replace(source, children=(*source.children, StructureElement("Custom", "unknown")))
    rewrite_source(bundle, source)
    node = read(bundle).roots[-1]
    assert (node.structure_type, node.source_role, node.language, node.content) == ("unknown", "Custom", None, ())


def test_heading_candidate_does_not_become_a_heading(bundle):
    source = bundle[3]
    section = source.children[0]
    heading = replace(section.children[0], source_role="Heading1", semantic_role="paragraph", heading_level=None)
    source = replace(source, children=(replace(section, children=(heading, *section.children[1:])), source.children[1]))
    rewrite_source(bundle, source)
    node = read(bundle).roots[0].content[0]
    assert node.structure_type == "paragraph"
    assert node.source_role == "Heading1"
    assert json.loads(dict(node.attributes)["review:heading-evidence"])["classification"] == "source_role_candidate"


def test_forbidden_controls_are_preserved_by_writer_but_gate_rejects(bundle):
    source = bundle[3]
    section = source.children[0]
    heading = replace(section.children[0], children=(ContentFragment(0, 1, ("before\x00after",)),))
    source = replace(source, children=(replace(section, children=(heading, *section.children[1:])), source.children[1]))
    rewrite_source(bundle, source)
    assert b'<control code="0000"' in (bundle[0] / "semantic_document.xml").read_bytes()
    with pytest.raises(BundleValidationError, match="failed extraction gates"):
        read(bundle)


def test_language_page_and_path_conflict_rejected(bundle):
    for name, old in (("raw_structure.xml", 'page-index="0"'), ("semantic_document.xml", 'page-index="0"')):
        path = bundle[0] / name
        path.write_text(path.read_text(encoding="utf-8").replace(old, 'page-index="1"', 1), encoding="utf-8")
        refresh(bundle, name)
    with pytest.raises(BundleValidationError, match="page/path"):
        read(bundle)


def test_missing_files_rejected(bundle):
    (bundle[0] / "raw_structure.xml").unlink()
    with pytest.raises(BundleValidationError):
        read(bundle)


def test_report_counts_checked_against_tree(bundle):
    path = bundle[0] / "extraction_report.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["metrics"]["fragment_count"] += 1
    path.write_text(json.dumps(data), encoding="utf-8")
    refresh(bundle, path.name)
    with pytest.raises(BundleValidationError, match="fragment count"):
        read(bundle)


def test_wrong_extractor_version_rejected(bundle):
    bundle[1]["extractor_sha256"] = "b" * 64
    with pytest.raises(BundleValidationError, match="extractor"):
        read(bundle)


def test_common_cover_text_outside_bookmark_pages_is_preserved_unassigned(bundle):
    source = bundle[3]
    common = StructureElement("P", "paragraph", children=(ContentFragment(2, 1, ("Common cover",)),))
    rewrite_source(bundle, replace(source, children=(*source.children, common)))
    node = read(bundle).roots[-1]
    assert node.text_content == "Common cover"
    assert node.language is None
    assert dict(node.content[0].attributes)["review:language-evidence"] == "outside_audited_pages"


def test_text_on_language_page_outside_its_path_is_ambiguous(bundle):
    source = bundle[3]
    misplaced = StructureElement("P", "paragraph", children=(ContentFragment(0, 55, ("Misplaced",)),))
    rewrite_source(bundle, replace(source, children=(*source.children, misplaced)))
    with pytest.raises(BundleValidationError, match="language"):
        read(bundle)


def test_sentence_display_hint_is_preserved_without_splitting_paragraph(bundle):
    original = bundle[3]
    paragraph = StructureElement("P", "paragraph", children=(ContentFragment(0, 50, ("First sentence. Next sentence.",)),))
    section = replace(original.children[0], children=(original.children[0].children[0], paragraph))
    source = apply_readability_formatting(replace(original, children=(section, original.children[1])))
    assert source.sentence_break_hints
    rewrite_source(bundle, source)
    paragraphs = [node for node in read(bundle).iter_nodes() if node.structure_type == "paragraph"]
    assert len(paragraphs) == 2
    assert paragraphs[0].text_content == "First sentence. Next sentence."
    assert dict(paragraphs[0].content[0].attributes)["sentence-break-offsets"] == "16"


@pytest.mark.parametrize("tag,expected", [("en-GB", "ENG"), ("en-US", "ENG")])
def test_single_language_requires_observed_xml_language(tmp_path, tag, expected):
    pdf = tmp_path / "BN68-24437C-01_SUG_Y26 TV ALL_XU_ENG_260129.0.pdf"
    pdf.write_bytes(b"fixture")
    audit = MultilingualHeadingAudit(False, True, 1, 0, None, None, None, None, None)
    source = TaggedDocument(pdf, True, "ko", (), (
        StructureElement("Document", "document", language=tag, children=(
            StructureElement("H1", "heading", heading_level=1, children=(ContentFragment(0, 1, ("Title",)),)),
            StructureElement("P", "paragraph", children=(ContentFragment(0, 2, ("Body",)),)),
        )),
    ), multilingual_heading_audit=audit)
    report = QualityEvaluator().evaluate(source, "TitleBody", xml_round_trip_ok=True)
    folder = tmp_path / "single"
    OutputBundleWriter().write(source, report, folder)
    receipt = {"contract": "tagged-pdf-xml/8405120", "extractor_sha256": EXTRACTOR_SHA256,
               "pdf_sha256": digest(pdf), "mapping_sha256": digest(MAPPING),
               "artifacts": {name: digest(folder / name) for name in NAMES}}
    document = read_review_bundle(folder, receipt, pdf_path=pdf, mapping_path=MAPPING)
    assert {node.language for node in document.iter_nodes()} == {expected}
    # Remove actual structure-language evidence; report's global language is not a fallback.
    for name in ("raw_structure.xml", "semantic_document.xml"):
        path = folder / name
        path.write_text(path.read_text(encoding="utf-8").replace(f' language="{tag}"', ""), encoding="utf-8")
        receipt["artifacts"][name] = digest(path)
    with pytest.raises(BundleValidationError, match="language"):
        read_review_bundle(folder, receipt, pdf_path=pdf, mapping_path=MAPPING)
