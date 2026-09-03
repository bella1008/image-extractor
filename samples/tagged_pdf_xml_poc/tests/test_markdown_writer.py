from __future__ import annotations

import re
from pathlib import Path

import pytest

from tagged_pdf_extractor.domain.models import QualityReport
from tagged_pdf_extractor.infrastructure.markdown_writer import MarkdownDocumentWriter


def _report(*heading_entries: dict[str, object]) -> QualityReport:
    return QualityReport(
        status="fail",
        metrics={},
        hard_gates={},
        diagnostics=(),
        heading_hierarchy=heading_entries,
    )


def _write_xml(path: Path, body: str) -> None:
    path.write_text(
        f"<?xml version='1.0' encoding='utf-8'?><document>{body}</document>",
        encoding="utf-8",
    )


def _render(
    tmp_path: Path,
    body: str,
    report: QualityReport | None = None,
) -> str:
    semantic = tmp_path / "semantic_document.xml"
    output = tmp_path / "semantic_document.md"
    _write_xml(semantic, body)
    MarkdownDocumentWriter().write(
        semantic,
        report or _report(),
        output,
        source_name="manual.pdf",
    )
    return output.read_text(encoding="utf-8")


def test_promotes_only_candidates_in_order_using_absolute_child_indexes(
    tmp_path: Path,
) -> None:
    body = """
    <document language="en-US">
      <article>
        <section object-ref="section-ref">
          <attributes><attribute name="BBox" value="secret-box" /></attributes>
          <paragraph><text>Introduction</text></paragraph>
          <figure><text>Decorative figure</text></figure>
          <paragraph object-ref="heading-ref">
            <attributes><attribute name="MCID" value="secret-mcid" /></attributes>
            <text page-index="0" mcid="91"> Cover\n</text>
            <span><text object-ref="92 0 R">Title </text></span>
          </paragraph>
          <paragraph><text>( &gt; Settings &gt; Support / Tips: [Open] &amp; https://example.com/a:b)</text></paragraph>
          <paragraph><text>Deep heading</text></paragraph>
          <paragraph><text>Conclusion</text></paragraph>
        </section>
      </article>
    </document>
    """
    report = _report(
        {
            "structure_path": "/document[0]/article[0]/section[0]/paragraph[0]",
            "source_role": "H1",
            "semantic_role": "paragraph",
            "level": 1,
            "joined_text": "Introduction",
            "title": None,
            "classification": "heading",
        },
        {
            # The preceding paragraph and figure make this absolute index 2.
            "structure_path": "/document[0]/article[0]/section[0]/paragraph[2]",
            "source_role": "Cover_Title",
            "semantic_role": "paragraph",
            "level": None,
            "joined_text": "Cover Title",
            "title": None,
            "classification": "source_role_candidate",
        },
        {
            "structure_path": "/document[0]/article[0]/section[0]/paragraph[4]",
            "source_role": "Heading7_0_1",
            "semantic_role": "paragraph",
            "level": 7,
            "joined_text": "Deep heading",
            "title": None,
            "classification": "source_role_candidate",
        },
    )

    markdown = _render(tmp_path, body, report)

    assert markdown.startswith(
        "# Semantic XML 문서 검토\n\n"
        "- 원본 파일: manual.pdf\n"
        "- 목적: PDF 태그 구조와 추출 텍스트 검토\n"
        "- 주의: 아래 제목은 검증된 표준 PDF 제목이 아니라 PDF 원본 역할 후보입니다.\n"
    )
    assert len(re.findall(r"(?m)^# ", markdown)) == 1
    assert "## Introduction" not in markdown
    assert "## Cover Title" in markdown
    assert "###### Deep heading" in markdown
    assert "( > Settings > Support / Tips: [Open] & https://example.com/a:b)" in markdown
    assert markdown.index("Introduction") < markdown.index("## Cover Title")
    assert markdown.index("## Cover Title") < markdown.index("( > Settings")
    assert markdown.index("( > Settings") < markdown.index("###### Deep heading")
    assert markdown.index("###### Deep heading") < markdown.index("Conclusion")
    for metadata in (
        "language",
        "object-ref",
        "heading-ref",
        "page-index",
        "mcid",
        "secret-mcid",
        "BBox",
        "secret-box",
        "92 0 R",
    ):
        assert metadata not in markdown


def test_renders_nested_lists_and_escapes_only_significant_line_prefixes(
    tmp_path: Path,
) -> None:
    markdown = _render(
        tmp_path,
        """
        <list>
          <list_item><list_body><paragraph><text>First &amp; [safe] / item</text></paragraph></list_body></list_item>
          <list_item><list_body><paragraph><text>Second</text></paragraph>
            <list><list_item><list_body><paragraph><text>Nested</text></paragraph></list_body></list_item></list>
          </list_body></list_item>
        </list>
        <paragraph><text>&gt; source line</text></paragraph>
        """,
    )

    assert "- First & [safe] / item" in markdown
    assert "- Second" in markdown
    assert "  - Nested" in markdown
    assert "\\> source line" in markdown


def test_renders_rectangular_table_and_escapes_cell_pipes(tmp_path: Path) -> None:
    markdown = _render(
        tmp_path,
        """
        <table>
          <table_row><table_header><text>Name</text></table_header><table_header><text>Path | URL</text></table_header></table_row>
          <table_row><table_cell><text>Menu</text></table_cell><table_cell><text>A / B | https://example.com</text></table_cell></table_row>
        </table>
        """,
    )

    assert "| Name | Path \\| URL |" in markdown
    assert "| --- | --- |" in markdown
    assert "| Menu | A / B \\| https://example.com |" in markdown


def test_irregular_or_nested_table_falls_back_to_row_lists_without_text_loss(
    tmp_path: Path,
) -> None:
    markdown = _render(
        tmp_path,
        """
        <table>
          <caption><text>Table caption</text></caption>
          <table_row><table_cell><text>Outer A</text></table_cell><span><text>Row note</text></span><table_cell><text>Outer B</text>
            <table><table_row><table_cell><text>Nested one</text></table_cell></table_row>
            <table_row><table_cell><text>Nested two</text></table_cell><table_cell><text>Nested three</text></table_cell></table_row></table>
          </table_cell></table_row>
          <table_row><table_cell><text>Only one cell</text></table_cell></table_row>
        </table>
        """,
    )

    assert "| ---" not in markdown
    assert "- 행 1:" in markdown
    assert "- 행 2:" in markdown
    for text in (
        "Outer A",
        "Outer B",
        "Nested one",
        "Nested two",
        "Nested three",
        "Only one cell",
        "Table caption",
        "Row note",
    ):
        assert markdown.count(text) == 1


def test_renders_empty_figure_and_control_codes_visibly(tmp_path: Path) -> None:
    markdown = _render(
        tmp_path,
        """
        <figure object-ref="hidden-ref"><attributes><attribute name="BBox" value="hidden" /></attributes></figure>
        <paragraph><text>A<control code="0003" />B<control code="000E" />C</text></paragraph>
        """,
    )

    assert "[그림: 텍스트 없음]" in markdown
    assert "A[CONTROL U+0003]B[CONTROL U+000E]C" in markdown
    assert "hidden-ref" not in markdown
    assert "BBox" not in markdown


def test_unresolved_candidate_path_raises_without_replacing_output(
    tmp_path: Path,
) -> None:
    semantic = tmp_path / "semantic_document.xml"
    output = tmp_path / "semantic_document.md"
    _write_xml(semantic, "<paragraph><text>Body</text></paragraph>")
    output.write_bytes(b"existing\r\noutput")
    report = _report(
        {
            "structure_path": "/paragraph[1]",
            "source_role": "Heading1",
            "semantic_role": "paragraph",
            "level": 1,
            "joined_text": "Missing",
            "title": None,
            "classification": "source_role_candidate",
        }
    )

    with pytest.raises(ValueError, match=r"unresolved heading candidate path /paragraph\[1\]"):
        MarkdownDocumentWriter().write(
            semantic,
            report,
            output,
            source_name="manual.pdf",
        )

    assert output.read_bytes() == b"existing\r\noutput"


def test_writes_utf8_with_lf_line_endings(tmp_path: Path) -> None:
    semantic = tmp_path / "semantic_document.xml"
    output = tmp_path / "semantic_document.md"
    _write_xml(semantic, "<paragraph><text>첫째\r\n둘째</text></paragraph>")

    MarkdownDocumentWriter().write(
        semantic,
        _report(),
        output,
        source_name="한글.pdf",
    )

    data = output.read_bytes()
    assert "한글.pdf".encode() in data
    assert b"\r" not in data
    assert b"\n" in data
