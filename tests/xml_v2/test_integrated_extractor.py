"""Real-PDF acceptance of the integrated producer, not a fabricated receipt."""
import json
from pathlib import Path

import pytest

from src.semantic_xml_reader import read_review_bundle
from src.profile_repository import PdfProfileRepository
from src.xml_review_gate import BundleValidationError, CONTRACT, EXTRACTOR_SHA256, sha256
from src.xml_review_run import extract_review_document, extractor_digest

ROOT = Path(__file__).resolve().parents[2]
MAPPING = ROOT / 'metadata/pdf_profile_mapping/pdf_profile_mapping.json'


def test_current_producer_is_pinned():
    assert CONTRACT == 'tagged-pdf-xml/8134892'
    assert extractor_digest() == EXTRACTOR_SHA256


def test_xl_has_confirmed_canonical_profile():
    profile = PdfProfileRepository(MAPPING).get('XL_ENG')

    assert profile.region == 'INDIA'
    assert profile.buyer_codes == ('XL',)
    assert profile.languages == ('ENG',)
    assert profile.doc_type == 'A3'
    assert profile.language_count == 1


def test_xl_real_pdf_reaches_review_document_without_semantic_loss(tmp_path):
    pdf, = (ROOT / 'samples/SUG_RAW').rglob('BN68-25031J-00*_XL_ENG_*.pdf')
    folder = tmp_path / 'xl-bundle'

    document = extract_review_document(pdf, folder, MAPPING)

    assert document.context.source_token == 'XL_ENG'
    assert document.context.region == 'INDIA'
    assert document.context.buyer_codes == ('XL',)
    assert document.context.doc_type == 'A3'
    assert document.context.expected_languages == ('ENG',)
    from scripts.audit_xml_integration import assert_semantic_preservation
    counts = assert_semantic_preservation(folder, document)
    assert counts['ENG'] > 0
    assert (folder / 'semantic_document.md').is_file()
    assert (folder / 'review_document.json').is_file()
    assert (folder / 'review_run.json').is_file()


@pytest.fixture(scope='module')
def zc_bundle(tmp_path_factory):
    pdf, = (ROOT / 'samples/SUG_RAW').rglob('BN68-25100B-00*_ZC_L02_*.pdf')
    folder = tmp_path_factory.mktemp('integrated-zc') / 'bundle'
    document = extract_review_document(pdf, folder, MAPPING)
    receipt = json.loads((folder / 'review_run.json').read_text(encoding='utf-8'))
    return pdf, folder, document, receipt


def test_verified_reparenting_retains_structure_and_evidence(zc_bundle):
    _, _, document, _ = zc_bundle
    nodes = tuple(document.iter_nodes())
    assert {n.language for n in nodes if n.language} == {'ENG', 'C-FRA'}
    assert any(dict(n.attributes).get('source-structure-path') for n in nodes)
    target = next(n for n in nodes if dict(n.attributes).get('object-ref') == '117 0 R')
    assert target.structure_type == 'span' and target.language == 'C-FRA'
    assert any(target in parent.content and parent.structure_type == 'list_body' for parent in nodes)
    assert all(n.evidence for n in nodes)
    assert all(not n.review_roles for n in nodes)


@pytest.mark.parametrize('artifact', ['raw_structure.xml', 'semantic_document.xml',
                                      'semantic_document.md', 'extraction_report.json'])
def test_rehashed_tampering_is_not_source_proof(zc_bundle, tmp_path, artifact):
    import shutil
    pdf, folder, _, receipt = zc_bundle
    target = tmp_path / 'tampered'
    shutil.copytree(folder, target)
    receipt = json.loads(json.dumps(receipt))
    path = target / artifact
    if artifact.endswith('.json'):
        data = json.loads(path.read_text(encoding='utf-8'))
        data['metrics']['element_count'] += 1
        path.write_text(json.dumps(data), encoding='utf-8')
    else:
        text = path.read_text(encoding='utf-8')
        assert 'Samsung' in text
        path.write_text(text.replace('Samsung', 'Tampered', 1), encoding='utf-8')
    receipt['artifacts'][artifact] = sha256(path.read_bytes())
    with pytest.raises(BundleValidationError, match='replay'):
        read_review_bundle(target, receipt, pdf_path=pdf, mapping_path=MAPPING)


@pytest.mark.parametrize('prefix,expected', [
    ('BN68-24437C-01', 'synthetic_group'),
    ('BN68-25031G-00', 'source_heading_exception'),
    ('BN68-26344A-00', 'rtl_source_repair'),
])
def test_new_contract_profile_transformations(tmp_path, prefix, expected):
    pdf, = (ROOT / 'samples/SUG_RAW').rglob(prefix + '*.pdf')
    folder = tmp_path / 'bundle'
    document = extract_review_document(pdf, folder, MAPPING)
    from scripts.audit_xml_integration import assert_semantic_preservation
    assert_semantic_preservation(folder, document)
    report = json.loads((folder / 'extraction_report.json').read_text(encoding='utf-8'))
    if expected == 'synthetic_group':
        assert any(n.source_role == 'ReviewGroup' for n in document.iter_nodes())
    elif expected == 'source_heading_exception':
        audit = report['metrics']['multilingual_heading_audit']
        assert audit['status'] == 'passed_with_source_exception'
        assert audit['source_count_exception']['source_sha256'] == sha256(pdf.read_bytes())
        assert set(document.context.expected_languages) == {'ENG', 'FRA', 'SPA', 'POR', 'ARA'}
        mixed = [n for n in document.iter_nodes()
                 if dict(n.attributes).get('review:language-evidence') == 'mixed_audited_container']
        assert len(mixed) == 3
        assert all(n.language is None and n.structure_type == 'article' for n in mixed)
    else:
        assert document.context.expected_languages == ('ARA',)
        assert any(d['severity'] == 'info' for d in report['diagnostics'])
