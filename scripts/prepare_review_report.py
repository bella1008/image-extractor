"""Export a completed observation's thin display view for format prototyping."""
import argparse
import base64
import hashlib
import json
from pathlib import Path, PureWindowsPath
from xml.etree import ElementTree as ET

from src.review_report_view import build_report_view
from src.review_service import read_completed_observation
from src.xml_review_gate import CONTRACT, EXTRACTOR_SHA256, REQUIRED_GATES, require


def load_archived_source(report: dict) -> tuple[dict, dict, dict]:
    """Read hash-bound source metadata for display, without reopening the PDF.

    This indexes the semantic XML with the adapter's zero-based structure-child
    paths. It does not reconstruct, re-extract or reapprove ReviewDocument data.
    """
    inputs = report.get('inputs', {})
    require(bool(inputs.get('receipt')), 'missing source receipt reference')
    receipt_path = Path(inputs['receipt'])
    receipt_bytes = receipt_path.read_bytes()
    require(hashlib.sha256(receipt_bytes).hexdigest() == inputs.get('receipt_sha256'), 'source receipt hash mismatch')
    receipt = json.loads(receipt_bytes)
    require(receipt == inputs.get('source_bundle'), 'source receipt and observation differ')
    require(receipt.get('contract') == CONTRACT and receipt.get('extractor_sha256') == EXTRACTOR_SHA256,
            'unsupported source extraction contract')
    pdf_hash = receipt.get('pdf_sha256')
    require(isinstance(pdf_hash, str) and len(pdf_hash) == 64 and all(c in '0123456789abcdef' for c in pdf_hash),
            'missing or invalid recorded PDF hash')
    snapshots = {receipt_path: receipt_bytes}
    payloads = {}
    for name in ('semantic_document.xml', 'extraction_report.json'):
        path = receipt_path.parent / name
        data = path.read_bytes()
        require(hashlib.sha256(data).hexdigest() == receipt.get('artifacts', {}).get(name), f'source artifact hash mismatch: {name}')
        snapshots[path] = payloads[name] = data
    extraction = json.loads(payloads['extraction_report.json'])
    gates = extraction.get('hard_gates', {})
    require(extraction.get('status') == 'pass' and REQUIRED_GATES <= gates.keys()
            and all(value is True for value in gates.values()), 'source extraction gates failed')
    source_path = extraction.get('source_path')
    require(isinstance(source_path, str) and bool(source_path.strip()), 'missing recorded PDF source name')
    # Windows names remain readable even when archived and viewed on another OS.
    filename = PureWindowsPath(source_path).name
    require(filename.lower().endswith('.pdf'), 'invalid recorded PDF source name')
    data = payloads['semantic_document.xml']
    require(b'<!DOCTYPE' not in data.upper() and b'<!ENTITY' not in data.upper(), 'unsupported XML declarations')
    root = ET.fromstring(data)
    require(root.tag == 'document', 'unsupported semantic XML root')
    nodes = {}

    def children(element):
        return [child for child in element if child.tag not in ('attributes', 'role-map', 'multilingual-heading-audit')]

    def attribute(element, name):
        value = element.get(name)
        encoding = element.get(name + '-encoding')
        if encoding:
            require(value is not None and encoding in ('base64-utf8', 'base64-utf8-surrogatepass'), 'unsupported source attribute encoding')
            value = base64.b64decode(value, validate=True).decode('utf-8', errors='surrogatepass' if encoding.endswith('surrogatepass') else 'strict')
        return value

    def visit(element, path, xml_path, parent_id=None):
        key = 'xml:' + '/'.join(map(str, path))
        page, mcid, bbox = (attribute(element, name) for name in ('page-index', 'mcid', 'bbox'))
        nodes[key] = {'structure_type': element.tag, 'parent_id': parent_id, 'evidence': [{
            'xml_path': xml_path, 'page_index': int(page) if page is not None else None,
            'mcid': int(mcid) if mcid is not None else None, 'object_ref': attribute(element, 'object-ref'),
            'bbox': list(map(float, bbox.split(','))) if bbox is not None else None}]}
        if element.tag != 'text':
            for i, child in enumerate(children(element)):
                visit(child, (*path, i), f'{xml_path}/{child.tag}[{i}]', key)

    for i, element in enumerate(children(root)):
        visit(element, (i,), f'/{element.tag}[{i}]')
    source = {'availability': 'verified_archive', 'pdf_filename': filename,
              'bundle_path': str(receipt_path.parent.resolve()),
              'semantic_xml_path': str((receipt_path.parent / 'semantic_document.xml').resolve()),
              'pdf_sha256': pdf_hash, 'semantic_xml_sha256': receipt['artifacts']['semantic_document.xml'],
              'receipt_ref': str(receipt_path.resolve()), 'receipt_sha256': inputs['receipt_sha256']}
    return nodes, source, snapshots


def prepare_view(run_dir: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(f'use a fresh view file: {output}')
    completion = run_dir / 'review_complete.json'
    before = completion.read_bytes()
    report = read_completed_observation(run_dir)
    nodes, source, snapshots = load_archived_source(report)
    view = build_report_view(report, document=nodes, source=source)
    for path, data in snapshots.items():
        require(path.read_bytes() == data, f'source changed during view mapping: {path.name}')
    require(read_completed_observation(run_dir) == report, 'observation changed during view mapping')
    if completion.read_bytes() != before:
        raise ValueError('completion changed during view mapping')
    view['source_completion_sha256'] = hashlib.sha256(before).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(view, stream, ensure_ascii=True, indent=2)
        stream.write('\n')
    return view


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run_dir', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare_view(args.run_dir, args.output)


if __name__ == '__main__':
    main()
