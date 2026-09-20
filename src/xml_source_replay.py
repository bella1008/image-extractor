"""Verify new semantic transformations without duplicating buyer extraction rules.

The original raw tree and the transformed semantic tree need not have identical
positions or text (RTL/source-backed repairs). A receipt is not a signature:
reproduce all four artifacts from the hash-bound PDF with the pinned producer
before accepting those differences. Legacy receipts keep their strict adapter.
"""
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as ET

from src.xml_review_gate import ARTIFACT_NAMES, EXTRACTOR_SHA256, require, sha256


def verify_source_replay(pdf_path, mapping_path, payloads, receipt):
    from tagged_pdf_extractor.application.extract_document import ExtractDocument
    from tagged_pdf_extractor.application.evaluate_quality import QualityEvaluator
    from tagged_pdf_extractor.infrastructure.json_profile_repository import JsonProfileRepository
    from tagged_pdf_extractor.infrastructure.output_bundle import OutputBundleWriter
    from tagged_pdf_extractor.infrastructure.pymupdf_baseline import PyMuPdfBaselineReader
    from tagged_pdf_extractor.infrastructure.pypdf_reader import TaggedPdfReader
    from tagged_pdf_extractor.infrastructure.xml_writer import XmlDocumentWriter
    from src.xml_review_run import extractor_digest

    pdf_path, mapping_path = Path(pdf_path).resolve(), Path(mapping_path).resolve()
    expected_inputs = (receipt['pdf_sha256'], receipt['mapping_sha256'], EXTRACTOR_SHA256)

    def input_hashes():
        return sha256(pdf_path.read_bytes()), sha256(mapping_path.read_bytes()), extractor_digest()

    require(input_hashes() == expected_inputs, 'source replay input/version mismatch')
    with TemporaryDirectory(prefix='xml-source-replay-') as temporary:
        temp = Path(temporary)
        replay = temp / 'bundle'
        producer = ExtractDocument(TaggedPdfReader(), PyMuPdfBaselineReader(), QualityEvaluator(),
                                   OutputBundleWriter(), JsonProfileRepository(mapping_path))
        document, _, _ = producer.run(pdf_path, replay)
        for name in ARTIFACT_NAMES:
            actual, expected = payloads[name], (replay / name).read_bytes()
            if name == 'raw_structure.xml':
                a, b = ET.fromstring(actual), ET.fromstring(expected)
                # Relocation changes only the recorded source directory.
                a.set('source', str(pdf_path))
                b.set('source', str(pdf_path))
                same = ET.tostring(a) == ET.tostring(b)
            elif name == 'extraction_report.json':
                a, b = json.loads(actual), json.loads(expected)
                a['source_path'] = b['source_path'] = str(pdf_path)
                same = a == b
            else:
                same = actual == expected
            require(same, f'source replay mismatch: {name}')
        # This alignment tree is NOT the source XML. The original raw XML stays
        # untouched. It lets the adapter reuse its strict value/structure checks
        # against the now-proven transformed model, including synthetic groups.
        aligned = temp / 'adapter_alignment.xml'
        XmlDocumentWriter().write_raw(replace(document, raw_children=None), aligned)
        result = ET.fromstring(aligned.read_bytes())
        require(input_hashes() == expected_inputs, 'source replay inputs changed')
        return result
