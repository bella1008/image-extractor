from dataclasses import replace
from pathlib import Path
import pytest
from tagged_pdf_extractor.domain.africa_book import africa_book_scope, prepare_africa_book
from tagged_pdf_extractor.domain.models import PdfProfile, TaggedDocument, StructureElement, ContentFragment, BookmarkPageBounds

PROFILE = PdfProfile("AFRICA_L05", "BOOK", ("ENG", "FRA", "SPA", "POR", "ARA"), 5)

def source():
    articles = tuple(StructureElement("Art", "article", children=(StructureElement("P", "paragraph", children=(ContentFragment(p, p, (("نص عربي " * 10) if p >= 26 else "Latin source",)),)),)) for p in range(36))
    return TaggedDocument(Path("sample.pdf"), True, None, (), (StructureElement("Document", "document", children=articles),), bookmark_page_bounds=tuple(BookmarkPageBounds(i+1, p, [6,12,18,33,35][i], ["English","Français","Español","Português","العربية"][i]) for i,p in enumerate([1,7,13,19,34])))

@pytest.mark.parametrize("profile", [replace(PROFILE,source_token="AFRICA MENA_L05"),replace(PROFILE,source_token="ZG XN ZT_L05"),replace(PROFILE,doc_type="A2"),replace(PROFILE,languages=("ENG","FRA","SPA","POR","DEU"))])
def test_other_profile_doc_type_or_language_never_enables_rule(profile):
    d = source()
    assert not africa_book_scope(profile)
    assert prepare_africa_book(d, profile) is d

def test_rule_preserves_every_source_node_and_trace_path():
    d=source(); result=prepare_africa_book(d,PROFILE)
    assert result.raw_children is d.children
    assert [a.source_structure_path for a in result.children[0].children] == [(0,p) for p in [*range(26),*range(35,25,-1)]]
    assert result.bookmark_page_bounds[3].end_page_index == 24
    with pytest.raises(ValueError, match="already"):
        prepare_africa_book(result,PROFILE)

def test_missing_bookmark_evidence_is_rejected():
    with pytest.raises(ValueError, match="five"):
        prepare_africa_book(replace(source(),bookmark_page_bounds=()), PROFILE)

def test_different_ltr_section_lengths_are_rejected():
    d=source(); bounds=list(d.bookmark_page_bounds);bounds[1]=replace(bounds[1],start_page_index=8)
    with pytest.raises(ValueError,match="extents"):
        prepare_africa_book(replace(d,bookmark_page_bounds=tuple(bounds)),PROFILE)

def test_noncontiguous_arabic_script_evidence_is_rejected():
    d=source();articles=list(d.children[0].children);articles[28]=replace(articles[28],children=())
    with pytest.raises(ValueError,match="evidence"):
        prepare_africa_book(replace(d,children=(replace(d.children[0],children=tuple(articles)),)),PROFILE)

def test_reader_default_entry_point_remains_available():
    from tagged_pdf_extractor.infrastructure.pypdf_reader import TaggedPdfReader
    from tagged_pdf_extractor.cli import main
    from tagged_pdf_extractor.application.extract_document import ExtractDocument
    assert callable(TaggedPdfReader.read) and callable(ExtractDocument.run) and callable(main)


def test_changed_bookmark_language_order_is_not_silently_relabelled():
    d=source(); bounds=list(d.bookmark_page_bounds)
    bounds[0]=replace(bounds[0],source_title="Français")
    bounds[1]=replace(bounds[1],source_title="English")
    with pytest.raises(ValueError,match="bookmark language order"):
        prepare_africa_book(replace(d,bookmark_page_bounds=tuple(bounds)),PROFILE)


@pytest.mark.parametrize("label",["01","02","03","04"])
def test_markdown_label_uses_only_matching_source_digits(label):
    from xml.etree import ElementTree as E
    from tagged_pdf_extractor.infrastructure.markdown_writer import MarkdownDocumentWriter as W
    element=E.fromstring(f'<heading level="2" promotion-reason="numbered_chapter_structure_sequence_typography" numbered-label="{label}"><label><span><text>0</text></span><span><text>{label[-1]}</text></span></label><list_body><text>Source title</text></list_body></heading>')
    assert W._render_element(element,{}) == [f"## {label} Source title"]
    element.set("numbered-label","09")
    with pytest.raises(ValueError,match="source evidence"):
        W._render_element(element,{})


def test_audit_heading_metadata_is_not_rendered_as_source_heading():
    from xml.etree import ElementTree as E
    from tagged_pdf_extractor.infrastructure.markdown_writer import MarkdownDocumentWriter as W
    assert W._render_element(E.fromstring('<heading position="1" level="2" origin="promoted" numbered-label="01"/>'),{}) == []
