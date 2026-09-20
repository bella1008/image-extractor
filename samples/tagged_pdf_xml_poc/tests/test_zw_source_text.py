from dataclasses import replace
from pathlib import Path
import os

import pytest

from tagged_pdf_extractor.domain.models import ContentFragment, PdfProfile
from tagged_pdf_extractor.infrastructure.pypdf_reader import TaggedPdfReader
from .acceptance_support import require_sample

ROOT = Path(__file__).resolve().parents[3]
RELATIVE = 'samples/SUG_RAW/TV_ZW/BN68-24973D-00_SUG_Y26 TV ALL_ZW_TPE_260327.0.pdf'
SOURCE = Path(os.environ.get('TAGGED_PDF_ZW_SAMPLE', ROOT / RELATIVE))
PROFILE = PdfProfile('ZW_TPE', 'A3', ('TPE',), 1)

def fragments(n):
    if isinstance(n, ContentFragment):
        yield n
    else:
        for c in n.children:
            yield from fragments(c)

@pytest.fixture(scope='module')
def observed():
    from tagged_pdf_extractor.infrastructure.zw_source_evidence import add_zw_source_evidence
    require_sample(SOURCE if SOURCE.is_file() else None, 'ZW_TPE')
    return add_zw_source_evidence(TaggedPdfReader().read(SOURCE), PROFILE)

def test_source_stroke_fill_overprint_removed_once_with_trace(observed):
    from tagged_pdf_extractor.domain.zw_source_text import restore_zw_text
    children, audit = restore_zw_text(observed.children, observed.diagnostics)
    by_id = {(f.page_index, f.mcid): f for c in children for f in fragments(c)}
    assert by_id[0,27].text.strip() == '閱讀本'
    assert by_id[0,28].text == ''
    assert by_id[0,29].text.strip() == '簡易使用者指南'
    assert by_id[0,30].text == ''
    assert any(x['removed_mcid'] == 28 and x['retained_mcid'] == 27 for x in audit.context['overprints'])
    raw = {(f.page_index,f.mcid): f.text for c in observed.children for f in fragments(c)}
    assert raw[0,28] == '閱讀本'

def test_no_evidence_no_text_change(observed):
    from tagged_pdf_extractor.domain.zw_source_text import restore_zw_text
    children, audit = restore_zw_text(observed.children, ())
    assert children == observed.children
    assert audit.context['overprints'] == []

def test_numbered_label_overprint_with_whitespace_actualtext(observed):
    from tagged_pdf_extractor.domain.zw_source_text import restore_zw_text
    children, audit = restore_zw_text(observed.children, observed.diagnostics)
    values={(f.page_index,f.mcid):f.text for c in children for f in fragments(c)}
    for stroke,fill,number in [(392,393,'1.'),(400,401,'2.'),(412,413,'3.')]:
        assert values[0,stroke].strip() == number
        assert values[0,fill] == ''

def test_other_profile_is_not_observed(observed):
    from tagged_pdf_extractor.infrastructure.zw_source_evidence import add_zw_source_evidence
    assert add_zw_source_evidence(observed, PdfProfile('TK_ARA','A3',('ARA',),1)) is observed

def test_changed_fragment_does_not_lose_text(observed):
    from tagged_pdf_extractor.domain.zw_source_text import restore_zw_text
    fragment = ContentFragment(0,28,('different source',))
    children, audit = restore_zw_text((fragment,), observed.diagnostics)
    assert children == (fragment,)
    assert audit.context['overprints'] == []

def test_public_extraction_dispatches_zw(tmp_path):
    from tagged_pdf_extractor.cli import _build_use_case
    require_sample(SOURCE if SOURCE.is_file() else None, 'ZW_TPE')
    document, report, artifacts = _build_use_case().run(SOURCE, tmp_path/'zw')
    assert document.language == 'TPE'
    assert document.raw_children is not None
    assert any(d.code == 'zw_source_text' for d in document.diagnostics)
    assert report.hard_gates['resolved_references']
    assert report.hard_gates['special_character_counts_preserved']
    assert '閱讀本閱讀本' not in artifacts.semantic_markdown.read_text(encoding='utf8')

def test_special_count_correction_requires_exact_baseline_and_source(observed):
    from tagged_pdf_extractor.domain.zw_source_text import verified_zw_special_counts
    original=''.join(f.text for c in observed.children for f in fragments(c))
    doc=replace(observed,raw_children=observed.children)
    corrected=verified_zw_special_counts(doc,original,'>→/&:[]()')
    assert corrected['['] == corrected[']'] == 1
    assert corrected['/'] == 56
    assert verified_zw_special_counts(doc,original+'/', '>→/&:[]()') is None
    assert verified_zw_special_counts(replace(doc,source_sha256='unknown'),original,'>→/&:[]()') is None

def test_visible_symbol_loss_still_fails_quality(observed):
    from tagged_pdf_extractor.domain.zw_source_text import restore_zw_text
    from tagged_pdf_extractor.application.evaluate_quality import QualityEvaluator
    original=''.join(f.text for c in observed.children for f in fragments(c))
    children,audit=restore_zw_text(observed.children,observed.diagnostics)
    def lose(n):
        if isinstance(n,ContentFragment):return replace(n,text_parts=tuple(p.replace('[','') for p in n.text_parts))
        return replace(n,children=tuple(lose(c) for c in n.children))
    doc=replace(observed,raw_children=observed.children,children=tuple(lose(c) for c in children),diagnostics=(*observed.diagnostics,audit))
    report=QualityEvaluator().evaluate(doc,original,xml_round_trip_ok=True)
    assert not report.hard_gates['special_character_counts_preserved']
