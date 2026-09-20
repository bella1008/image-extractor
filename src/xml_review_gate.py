"""Validate a fresh extraction receipt and its exact artifact bytes before review."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from src.profile_lookup import ProfileLookupService
from src.profile_repository import PdfProfileRepository
from src.review_document import DocumentContext

LEGACY_CONTRACT = "tagged-pdf-xml/8405120"
LEGACY_EXTRACTOR_SHA256 = "fc64c8bc8e7909b27ed413fc802736b3a48fa5463f6316dba9e43f882ed3aa1e"
CONTRACT = "tagged-pdf-xml/8134892"
EXTRACTOR_SHA256 = "f46c72b75627f030ec7ec78c5cd34e3eede2b2e50edaf3a53407f8db97991477"
SUPPORTED_CONTRACTS = {LEGACY_CONTRACT: LEGACY_EXTRACTOR_SHA256, CONTRACT: EXTRACTOR_SHA256}
ARTIFACT_NAMES = ("raw_structure.xml", "semantic_document.xml", "extraction_report.json", "semantic_document.md")
REQUIRED_GATES = frozenset((
    "is_marked", "has_structure", "has_heading", "has_body", "xml_round_trip",
    "resolved_references", "resolved_references_reported", "no_known_text_loss",
    "no_forbidden_xml_controls", "special_character_counts_preserved",
    "numbered_heading_series_valid", "numbered_heading_series_counts_consistent",
    "numbered_heading_typography_valid", "multilingual_interval_count_valid",
    "multilingual_heading_count_parity", "multilingual_heading_level_parity",
    "multilingual_heading_origin_parity", "multilingual_numbered_label_parity",
))


class BundleValidationError(ValueError):
    """Extraction is unusable for automatic review, not a checklist mismatch."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BundleValidationError(message)


@dataclass(frozen=True)
class CheckedBundle:
    context: DocumentContext
    raw: ET.Element
    semantic: ET.Element
    report: dict
    adapter_raw: ET.Element | None = None


def _parse_xml(data: bytes) -> ET.Element:
    require(b"<!DOCTYPE" not in data.upper() and b"<!ENTITY" not in data.upper(), "XML declarations are unsupported")
    return ET.fromstring(data)


def validate_bundle(folder: Path, receipt: dict, *, pdf_path: Path, mapping_path: Path) -> CheckedBundle:
    """Receipt must come from the fresh-run producer, never from re-hashing old files."""
    try:
        contract = receipt.get("contract")
        require(isinstance(contract, str) and contract in SUPPORTED_CONTRACTS, "missing or unsupported extraction contract")
        require(receipt.get("extractor_sha256") == SUPPORTED_CONTRACTS[contract], "missing or unsupported extractor version hash")
        require(sha256(Path(pdf_path).read_bytes()) == receipt.get("pdf_sha256"), "PDF hash mismatch")
        mapping_bytes = Path(mapping_path).read_bytes()
        require(sha256(mapping_bytes) == receipt.get("mapping_sha256"), "mapping hash mismatch")
        hashes = receipt.get("artifacts", {})
        require(isinstance(hashes, dict) and set(hashes) == set(ARTIFACT_NAMES), "missing artifact hashes")
        payloads = {}
        for name in ARTIFACT_NAMES:
            data = (Path(folder) / name).read_bytes()
            require(sha256(data) == hashes[name], f"artifact hash mismatch: {name}")
            payloads[name] = data
        # Keep the canonical repository implementation, and detect a concurrent edit.
        lookup = ProfileLookupService(PdfProfileRepository(mapping_path)).lookup_for_file(pdf_path)
        require(Path(mapping_path).read_bytes() == mapping_bytes, "mapping changed during read")
        profile, parsed = lookup.profile, lookup.parsed_filename
        context = DocumentContext(parsed.manual_code, parsed.source_token, profile.region,
                                  profile.buyer_codes, profile.doc_type, profile.languages)
        raw = _parse_xml(payloads["raw_structure.xml"])
        semantic = _parse_xml(payloads["semantic_document.xml"])
        report = json.loads(payloads["extraction_report.json"])
        require(raw.tag == "tagged-document" and semantic.tag == "document", "unsupported XML roots")
        require(raw.get("marked") == "true" and report.get("marked") is True, "unmarked PDF")
        require(raw.get("source") == report.get("source_path"), "raw/report source mismatch")
        require(Path(str(report.get("source_path", ""))).name == Path(pdf_path).name, "PDF source name mismatch")
        gates = report.get("hard_gates", {})
        require(isinstance(gates, dict) and REQUIRED_GATES <= gates.keys(), "missing required extraction gates")
        require(report.get("status") == "pass" and all(value is True for value in gates.values()), "failed extraction gates")
        diagnostics = report.get("diagnostics")
        require(isinstance(diagnostics, list), "missing extraction diagnostics")
        allowed_severities = {"warning", "info"} if contract == CONTRACT else {"warning"}
        require(all(isinstance(d, dict) and d.get("severity") in allowed_severities for d in diagnostics), "extraction error diagnostic")
        adapter_raw = None
        if contract == CONTRACT:
            from src.xml_source_replay import verify_source_replay
            adapter_raw = verify_source_replay(pdf_path, mapping_path, payloads, receipt)
        _validate_audit(semantic, report["metrics"]["multilingual_heading_audit"], context,
                        source_verified=adapter_raw is not None)
        return CheckedBundle(context, raw, semantic, report, adapter_raw)
    except BundleValidationError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise BundleValidationError(f"invalid extraction bundle: {exc}") from exc


def _validate_audit(root: ET.Element, audit: dict, context: DocumentContext, *, source_verified=False) -> None:
    nodes = root.findall("multilingual-heading-audit")
    require(len(nodes) == 1, "missing or duplicate XML language audit")
    node = nodes[0]
    count = len(context.expected_languages)
    multi = count > 1
    require(audit.get("applicable") is multi and audit.get("passed") is True, "failed language audit")
    exception = audit.get("source_count_exception")
    has_exception = exception is not None
    require(not has_exception or (source_verified and multi), "unverified source heading exception")
    status = "passed_with_source_exception" if has_exception else ("passed" if multi else "not_applicable")
    require(audit.get("status") == status, "invalid audit status")
    require(type(audit.get("expected_interval_count")) is int and audit["expected_interval_count"] == count, "audit profile count mismatch")
    require(audit.get("diagnostics") == [] and (has_exception or audit.get("mismatch_positions") == []), "audit has unresolved findings")
    flags = ("interval_count_matches", "total_heading_count_matches", "heading_level_sequence_matches",
             "heading_origin_sequence_matches", "numbered_label_sequence_matches")
    for key in flags:
        # Exact exception payload has already been reproduced from the pinned PDF.
        expected_flag = False if has_exception and key == "total_heading_count_matches" else (True if multi else None)
        require(audit.get(key) is expected_flag, f"failed audit component: {key}")
    names = ("applicable", "status", "passed", "expected_interval_count", "observed_interval_count", *flags)
    expected = {key.replace("_", "-"): str(audit[key]).lower() if isinstance(audit[key], bool) else str(audit[key])
                for key in names if audit[key] is not None}
    require(node.attrib == expected, "XML/report audit mismatch")
    languages = audit.get("languages")
    require(isinstance(languages, list), "missing audit languages")
    require(type(audit.get("observed_interval_count")) is int and audit["observed_interval_count"] == (count if multi else 0), "audit interval count mismatch")
    require(tuple(item["language"] for item in languages) == (context.expected_languages if multi else ()), "audit language order mismatch")
    xml_languages = [child for child in node if child.tag == "language"]
    # Source-backed count exceptions retain the covered mismatch records too.
    # Replay above verifies their exact values; never discard or hide them.
    expected_tags = (["source-count-exception"] if has_exception else []) + ["language"] * len(languages)
    expected_tags += ["mismatch"] * len(audit["mismatch_positions"])
    require([child.tag for child in node] == expected_tags, "XML/report audit child mismatch")
    previous = None
    for ordinal, (xml_language, item) in enumerate(zip(xml_languages, languages), 1):
        interval = item["interval"]
        start, end = interval["start_path"], interval["end_path"]
        require(all(isinstance(p, list) and p and all(type(i) is int and i >= 0 for i in p) for p in (start, end)), "invalid audit paths")
        require(tuple(start) <= tuple(end), "reversed audit paths")
        lo, hi = interval["start_page_index"], interval["end_page_index"]
        require(type(lo) is int and type(hi) is int and 0 <= lo <= hi, "invalid audit pages")
        require(interval["evidence_origin"] == ("bookmark" if context.doc_type == "BOOK" else "structural_language_section"), "invalid audit evidence origin")
        if previous is not None:
            require(previous[0] < tuple(start) and tuple(start)[:len(previous[0])] != previous[0] and previous[1] < lo, "overlapping language audit intervals")
        previous = (tuple(end), hi)
        attrs = {"ordinal": str(ordinal), "code": item["language"], "start-page-index": str(lo), "end-page-index": str(hi),
                 "start-path": "/".join(map(str, start)), "end-path": "/".join(map(str, end)),
                 "evidence-origin": interval["evidence_origin"], "heading-total": str(item["heading_total"])}
        require(item["ordinal"] == ordinal and xml_language.tag == "language" and xml_language.attrib == attrs, "XML/report language audit mismatch")
        entries = list(zip(item["heading_levels"], item["heading_origins"], item["numbered_labels"], strict=True))
        require(len(entries) == item["heading_total"] == len(xml_language), "audit heading count mismatch")
        for position, (child, (level, origin, label)) in enumerate(zip(xml_language, entries)):
            attrs = {"position": str(position), "level": str(level), "origin": origin}
            if label is not None:
                attrs["numbered-label"] = label
            require(child.tag == "heading" and child.attrib == attrs, "XML/report heading audit mismatch")
