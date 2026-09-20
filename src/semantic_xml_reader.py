"""Lossless structural adapter for the pinned POC's semantic XML bundle."""
from __future__ import annotations

import base64
import json
from pathlib import Path
from xml.etree import ElementTree as ET

from tagged_pdf_extractor.domain.text_joining import join_text_parts
from tagged_pdf_extractor.infrastructure.xml_writer import decode_data_element
from src.review_document import ReviewDocument, ReviewNode, SourceEvidence
from src.xml_review_gate import BundleValidationError, require, validate_bundle


def _attributes(element: ET.Element) -> dict[str, str]:
    result = {}
    for name, value in element.attrib.items():
        if name.endswith("-encoding"):
            require(name[:-9] in element.attrib, "orphan XML encoding marker")
            continue
        encoding = element.get(name + "-encoding")
        if encoding is not None:
            require(encoding in ("base64-utf8", "base64-utf8-surrogatepass"), "unsupported XML attribute encoding")
            value = base64.b64decode(value, validate=True).decode(
                "utf-8", errors="surrogatepass" if encoding.endswith("surrogatepass") else "strict")
        result[name] = value
    return result


def _children(element: ET.Element) -> list[ET.Element]:
    return [child for child in element if child.tag not in ("attributes", "role-map", "multilingual-heading-audit")]


def _source_attributes(element: ET.Element) -> dict[str, str]:
    result = {}
    for container in element.findall("attributes"):
        for child in container:
            attrs = _attributes(child)
            require(child.tag == "attribute" and set(attrs) == {"name", "value"}, "invalid source attributes")
            key = "source:" + attrs["name"]
            require(key not in result, "duplicate source attribute")
            result[key] = attrs["value"]
    return result


# Source language tags observed in the current adapter acceptance profiles.
# Unlisted tags remain unassigned; this is not a translation/heading dictionary.
_SOURCE_LANGUAGES = {"en": "ENG", "en-US": "ENG", "en-GB": "ENG", "ko": "KOR", "ko-KR": "KOR"}


def read_review_bundle(folder: Path, receipt: dict, *, pdf_path: Path, mapping_path: Path) -> ReviewDocument:
    """Read the same bytes checked against a producer receipt. Never parses Markdown."""
    checked = validate_bundle(folder, receipt, pdf_path=pdf_path, mapping_path=mapping_path)
    audit = checked.report["metrics"]["multilingual_heading_audit"]
    intervals = audit["languages"]
    seen_paths = set()
    heading_entries = {}
    for entry in checked.report["heading_hierarchy"]:
        path = entry["structure_path"]
        require(path not in heading_entries, "duplicate heading evidence")
        heading_entries[path] = entry
    consumed_headings = set()

    def convert(raw, semantic, path, xml_path, inherited_language):
        seen_paths.add(path)
        attrs, raw_attrs = _attributes(semantic), _attributes(raw)
        is_text = raw.tag == "fragment"
        require(raw.tag in ("element", "fragment"), "unsupported raw structure")
        require((semantic.tag == "text") == is_text, "raw/semantic structure mismatch")
        for key in ("page-index", "mcid", "object-ref", "bbox"):
            require(attrs.get(key) == raw_attrs.get(key), f"raw/semantic {key} mismatch at {xml_path}")
        for key in ("language", "actual-text", "alternate-text", "title"):
            require(attrs.get(key) == raw_attrs.get(key), f"raw/semantic {key} mismatch at {xml_path}")
        source_attrs = _source_attributes(semantic)
        require(source_attrs == _source_attributes(raw), "raw/semantic source attributes mismatch")
        attrs.update(source_attrs)
        page = int(attrs["page-index"]) if "page-index" in attrs else None
        language = None
        if intervals:
            matches = []
            for item in intervals:
                interval = item["interval"]
                start, end = tuple(interval["start_path"]), tuple(interval["end_path"])
                if start <= path <= end or path[:len(end)] == end:
                    matches.append(item)
            require(len(matches) <= 1, "ambiguous language path")
            if matches:
                item = matches[0]
                if page is not None:
                    require(item["interval"]["start_page_index"] <= page <= item["interval"]["end_page_index"], "language page/path disagreement")
                language = item["language"]
        else:
            source_language = attrs.get("language")
            if source_language is not None:
                language = source_language if source_language in checked.context.expected_languages else _SOURCE_LANGUAGES.get(source_language)
                require(language is None or language in checked.context.expected_languages, "XML language contradicts profile")
            else:
                language = inherited_language
        if language is not None:
            attrs["review:language-evidence"] = "audited_interval" if intervals else "explicit_xml_language"
        if is_text:
            require(all(child.tag == "part" for child in raw), "unsupported raw fragment")
            text = decode_data_element(semantic)
            expected, _ = join_text_parts(tuple(decode_data_element(part) for part in raw))
            require(text == expected, f"raw/semantic text mismatch at {xml_path}")
            if text.strip() and language is None:
                outside_pages = bool(intervals) and page is not None and all(
                    not item["interval"]["start_page_index"] <= page <= item["interval"]["end_page_index"]
                    for item in intervals)
                require(outside_pages, f"ambiguous text language at {xml_path}")
                attrs["review:language-evidence"] = "outside_audited_pages"
            content = (text,)
        else:
            require(not semantic.text or not semantic.text.strip(), "unexpected text outside XML text element")
            require(all(not child.tail or not child.tail.strip() for child in semantic), "unexpected XML tail text")
            require(semantic.tag == raw_attrs["semantic-role"] or
                    (semantic.tag == "heading" and "promotion-reason" in attrs) or semantic.tag == "unknown",
                    "raw/semantic role mismatch")
            raw_children, semantic_children = _children(raw), _children(semantic)
            require(len(raw_children) == len(semantic_children), "raw/semantic child count mismatch")
            content = tuple(convert(r, s, (*path, i), f"{xml_path}/{s.tag}[{i}]", language)
                            for i, (r, s) in enumerate(zip(raw_children, semantic_children)))
            # A container crossing language boundaries is not a match window.
            child_languages = {child.language for child in content if child.language is not None}
            if (checked.adapter_raw is not None and intervals and "language" not in attrs
                    and language is not None and child_languages and child_languages != {language}):
                # Some BOOK Articles contain the previous language's last page
                # and the next language's front cover. Replay proves this tree;
                # keep their audited children but do not label the whole Article.
                language = None
                attrs["review:language-evidence"] = "mixed_audited_container"
            require(language is None or not child_languages or child_languages == {language}, "container crosses language interval")
        if xml_path in heading_entries:
            entry = heading_entries[xml_path]
            require(entry.get("source_role") == raw_attrs.get("source-role"), "heading source-role mismatch")
            attrs["review:heading-evidence"] = json.dumps(entry, ensure_ascii=True, sort_keys=True)
            consumed_headings.add(xml_path)
        evidence = SourceEvidence(
            xml_path=xml_path, page_index=page,
            mcid=int(attrs["mcid"]) if "mcid" in attrs else None,
            object_ref=attrs.get("object-ref"),
            bbox=tuple(map(float, attrs["bbox"].split(","))) if "bbox" in attrs else None,
        )
        return ReviewNode("xml:" + "/".join(map(str, path)), semantic.tag, content,
                          language=language, source_role=raw_attrs.get("source-role"),
                          attributes=tuple(attrs.items()), evidence=(evidence,))

    try:
        alignment = checked.adapter_raw if checked.adapter_raw is not None else checked.raw
        raw_roots, semantic_roots = _children(alignment), _children(checked.semantic)
        require(len(raw_roots) == len(semantic_roots), "raw/semantic root count mismatch")
        roots = tuple(convert(raw, semantic, (i,), f"/{semantic.tag}[{i}]", None)
                      for i, (raw, semantic) in enumerate(zip(raw_roots, semantic_roots)))
        for item in intervals:
            for key in ("start_path", "end_path"):
                require(tuple(item["interval"][key]) in seen_paths, "language interval path missing")
        require(consumed_headings == set(heading_entries), "unresolved heading evidence")
        document = ReviewDocument(checked.context, roots)
        nodes = tuple(document.iter_nodes())
        metrics = checked.report["metrics"]
        require(sum(n.structure_type == "text" for n in nodes) == metrics["fragment_count"], "report fragment count mismatch")
        require(sum(n.structure_type != "text" for n in nodes) == metrics["element_count"], "report element count mismatch")
        return document
    except BundleValidationError:
        raise
    except (ValueError, TypeError, KeyError, RecursionError) as exc:
        raise BundleValidationError(f"invalid semantic XML: {exc}") from exc
