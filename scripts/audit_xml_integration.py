"""Record per-profile technical integration evidence; never grant human approval."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import time
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'samples/tagged_pdf_xml_poc/src'))

from src.semantic_xml_reader import _attributes, _source_attributes, _children
from src.xml_review_gate import CONTRACT, EXTRACTOR_SHA256, sha256
from src.xml_review_run import extract_review_document, extractor_digest
from tagged_pdf_extractor.infrastructure.xml_writer import decode_data_element

SAMPLES = (
    ('ZC_L02', 'BN68-25100B-00'), ('XU_ENG', 'BN68-24437C-01'),
    ('ZG XN ZT_L05', 'BN68-25448A-00'), ('AFRICA_L05', 'BN68-25031G-00'),
    ('CE_L05', 'BN68-26318A-00'), ('TK_L02', 'BN68-26343A-00'),
    ('TK_ARA', 'BN68-26344A-00'), ('MENA_L02', 'BN68-25031L-00'),
    ('SQ MI_HEAR', 'BN68-24437H-00'), ('XT_L02', 'BN68-25031M-00'),
    ('ZW_TPE', 'BN68-24973D-00'), ('PY_ENRU', 'BN68-26639A-00'),
    ('UA_ENG', 'BN68-26754A-00'), ('XD_INS', 'BN68-25031D-00'),
    ('XL_ENG', 'BN68-25031J-00'),
)


def assert_semantic_preservation(folder, document):
    """Every semantic node/text/attribute/page/MCID stays in ordered review data."""
    xml_nodes = []
    def visit(element):
        xml_nodes.append(element)
        if element.tag != 'text':
            for child in _children(element):
                visit(child)
    for child in _children(ET.parse(folder / 'semantic_document.xml').getroot()):
        visit(child)
    nodes = tuple(document.iter_nodes())
    assert len(nodes) == len(xml_nodes), 'semantic/review node count differs'
    for element, node in zip(xml_nodes, nodes, strict=True):
        assert element.tag == node.structure_type
        attrs = {**_attributes(element), **_source_attributes(element)}
        assert attrs.items() <= dict(node.attributes).items(), 'lost semantic attributes'
        if element.tag == 'text':
            assert node.content == (decode_data_element(element),), 'lost or changed text'
        assert node.evidence, 'missing source evidence'
        assert not node.review_roles, 'unexpected business classification'
    return Counter(n.language or 'UNASSIGNED' for n in nodes if n.structure_type == 'text')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--tokens', nargs='*')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    assert extractor_digest() == EXTRACTOR_SHA256
    mapping = ROOT / 'metadata/pdf_profile_mapping/pdf_profile_mapping.json'
    result = {'contract': CONTRACT, 'extractor_sha256': EXTRACTOR_SHA256,
              'mapping_sha256': sha256(mapping.read_bytes()), 'human_approval': 'not_granted', 'profiles': []}
    for token, prefix in SAMPLES:
        if args.tokens and token not in args.tokens:
            continue
        row = {'source_token': token, 'status': 'blocked'}
        start = time.monotonic()
        try:
            pdf, = (ROOT / 'samples/SUG_RAW').rglob(prefix + '*.pdf')
            row.update(pdf_filename=pdf.name, pdf_sha256=sha256(pdf.read_bytes()))
            folder = args.output / token.replace(' ', '_')
            document = extract_review_document(pdf, folder, mapping)
            counts = assert_semantic_preservation(folder, document)
            row.update(status='technical_pass', languages=list(document.context.expected_languages),
                       text_fragments_by_language=dict(counts),
                       review_node_count=sum(1 for _ in document.iter_nodes()),
                       receipt_sha256=sha256((folder / 'review_run.json').read_bytes()))
        except Exception as exc:
            row.update(error_type=type(exc).__name__, reason=str(exc))
        row['seconds'] = round(time.monotonic() - start, 2)
        result['profiles'].append(row)
        (args.output / 'integration_audit.json').write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(row, ensure_ascii=True), flush=True)
    return int(any(r['status'] != 'technical_pass' for r in result['profiles']))


if __name__ == '__main__':
    raise SystemExit(main())
