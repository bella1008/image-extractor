"""Hash-bound XML source metadata, usable from files or a self-contained archive."""
import base64
import hashlib
import json
from pathlib import Path, PureWindowsPath
from xml.etree import ElementTree as ET
from src.item_review_service import _unique_object
from src.xml_review_gate import CONTRACT, EXTRACTOR_SHA256, REQUIRED_GATES, require


def parse_archived_source(report, receipt_bytes, xml_bytes, extraction_bytes):
    """Rebuild node metadata from exact archived bytes without reopening inputs."""
    inputs = report.get('inputs', {})
    require(bool(inputs.get('receipt')), 'missing source receipt reference')
    require(hashlib.sha256(receipt_bytes).hexdigest() == inputs.get('receipt_sha256'), 'source receipt hash mismatch')
    receipt = json.loads(receipt_bytes, object_pairs_hook=_unique_object)
    require(isinstance(receipt, dict) and receipt == inputs.get('source_bundle'), 'source receipt and observation differ')
    require(receipt.get('contract') == CONTRACT and receipt.get('extractor_sha256') == EXTRACTOR_SHA256,
            'unsupported source extraction contract')
    pdf_hash = receipt.get('pdf_sha256')
    require(isinstance(pdf_hash, str) and len(pdf_hash) == 64 and all(c in '0123456789abcdef' for c in pdf_hash),
            'missing or invalid recorded PDF hash')
    payloads = {'semantic_document.xml': xml_bytes, 'extraction_report.json': extraction_bytes}
    for name, data in payloads.items():
        require(hashlib.sha256(data).hexdigest() == receipt.get('artifacts', {}).get(name),
                f'source artifact hash mismatch: {name}')
    extraction = json.loads(payloads['extraction_report.json'], object_pairs_hook=_unique_object)
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
              'bundle_path': str(Path(inputs['receipt']).parent.resolve()),
              'semantic_xml_path': str((Path(inputs['receipt']).parent / 'semantic_document.xml').resolve()),
              'pdf_sha256': pdf_hash, 'semantic_xml_sha256': receipt['artifacts']['semantic_document.xml'],
              'receipt_ref': str(Path(inputs['receipt']).resolve()), 'receipt_sha256': inputs['receipt_sha256']}
    return nodes, source



def load_archived_source(report):
    """Snapshot the three required archive files; preserve the prior public API."""
    receipt_path = Path(report['inputs']['receipt'])
    paths = (receipt_path, receipt_path.parent / 'semantic_document.xml',
             receipt_path.parent / 'extraction_report.json')
    snapshots = {path: path.read_bytes() for path in paths}
    nodes, source = parse_archived_source(report, *(snapshots[path] for path in paths))
    require(all(path.read_bytes() == data for path, data in snapshots.items()), 'source changed during archive read')
    return nodes, source, snapshots
