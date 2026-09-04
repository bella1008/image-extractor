from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

from tagged_pdf_extractor.domain.models import QualityReport
from tagged_pdf_extractor.infrastructure import markdown_writer as markdown_writer_module
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


def test_numeric_level_one_candidate_renders_as_level_two_markdown(
    tmp_path: Path,
) -> None:
    report = _report(
        {
            "structure_path": "/paragraph[0]",
            "source_role": "Heading1",
            "semantic_role": "paragraph",
            "level": 1,
            "joined_text": "Numeric heading",
            "title": None,
            "classification": "source_role_candidate",
        }
    )

    markdown = _render(
        tmp_path,
        "<paragraph><text>Numeric heading</text></paragraph>",
        report,
    )

    assert "\n## Numeric heading\n" in markdown


def test_joins_fragment_punctuation_without_blanket_spaces(tmp_path: Path) -> None:
    markdown = _render(
        tmp_path,
        """
        <paragraph><text>Hello</text><span><text>, world</text></span><text>!</text></paragraph>
        <paragraph><text>( &gt; left directional button &gt; Settings &gt; Support &gt; Tips and User Guides &gt; Open User Guide</text><span><text>)</text></span></paragraph>
        """,
    )

    assert "Hello, world!" in markdown
    assert "Hello , world !" not in markdown
    assert "( > left directional button > Settings > Support > Tips and User Guides > Open User Guide)" in markdown
    assert "Open User Guide )" not in markdown


def test_trailing_fragment_whitespace_moves_after_closing_punctuation(
    tmp_path: Path,
) -> None:
    markdown = _render(
        tmp_path,
        """
        <paragraph><text>A </text><text>.B </text><text>,C </text><text>:D </text><text>;E </text><text>?F </text><text>!G </text><text>)</text></paragraph>
        <paragraph><text>Ordinary </text><text>word spacing</text></paragraph>
        """,
    )

    assert "A. B, C: D; E? F! G)" in markdown
    assert "A .B ,C :D ;E ?F !G )" not in markdown
    assert "Ordinary word spacing" in markdown


def test_candidate_heading_lines_resolve_exact_renderer_punctuation(
    tmp_path: Path,
) -> None:
    semantic = tmp_path / "semantic_document.xml"
    _write_xml(
        semantic,
        "<paragraph><text>Warning </text><text>! Important</text></paragraph>",
    )
    report = _report(
        {
            "structure_path": "/paragraph[0]",
            "source_role": "Heading1",
            "semantic_role": "paragraph",
            "level": 1,
            "joined_text": "Warning ! Important",
            "title": None,
            "classification": "source_role_candidate",
        }
    )

    assert MarkdownDocumentWriter.candidate_heading_lines(
        semantic, report
    ) == Counter({"## Warning! Important": 1})


def test_render_text_matches_written_markdown(tmp_path: Path) -> None:
    semantic = tmp_path / "semantic_document.xml"
    output = tmp_path / "semantic_document.md"
    _write_xml(
        semantic,
        "<list><list_item><list><list_item><paragraph>"
        "<text>Nested heading</text></paragraph></list_item></list></list_item></list>",
    )
    report = _report(
        {
            "structure_path": (
                "/list[0]/list_item[0]/list[0]/list_item[0]/paragraph[0]"
            ),
            "level": 1,
            "classification": "source_role_candidate",
        }
    )
    writer = MarkdownDocumentWriter()

    rendered = writer.render_text(semantic, report, source_name="manual.pdf")
    writer.write(semantic, report, output, source_name="manual.pdf")

    assert rendered == output.read_text(encoding="utf-8")
    assert "    ## Nested heading" in rendered.splitlines()


def test_duplicate_candidate_structure_paths_are_rejected(tmp_path: Path) -> None:
    semantic = tmp_path / "semantic_document.xml"
    _write_xml(semantic, "<paragraph><text>Repeated path</text></paragraph>")
    entry = {
        "structure_path": "/paragraph[0]",
        "source_role": "Heading1",
        "semantic_role": "paragraph",
        "level": 1,
        "joined_text": "Repeated path",
        "title": None,
        "classification": "source_role_candidate",
    }

    with pytest.raises(ValueError, match="duplicate heading candidate path"):
        MarkdownDocumentWriter.candidate_heading_lines(
            semantic, _report(entry, dict(entry))
        )


def test_ancestor_and_descendant_heading_candidate_paths_are_rejected(
    tmp_path: Path,
) -> None:
    semantic = tmp_path / "semantic_document.xml"
    _write_xml(
        semantic,
        "<paragraph><text>Parent</text><paragraph><text>Child</text></paragraph></paragraph>",
    )
    parent = {
        "structure_path": "/paragraph[0]",
        "level": 1,
        "classification": "source_role_candidate",
    }
    child = {
        "structure_path": "/paragraph[0]/paragraph[1]",
        "level": 2,
        "classification": "source_role_candidate",
    }

    with pytest.raises(
        ValueError,
        match=(
            r"overlapping heading candidate paths /paragraph\[0\] and "
            r"/paragraph\[0\]/paragraph\[1\]"
        ),
    ):
        MarkdownDocumentWriter.render_text(
            semantic, _report(parent, child), source_name="manual.pdf"
        )


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


def test_unordered_list_label_is_a_marker_role_not_body_text(tmp_path: Path) -> None:
    semantic = tmp_path / "semantic_document.xml"
    _write_xml(
        semantic,
        "<list><list_item>"
        "<label><text>\u0141</text></label>"
        "<list_body><text>Power safety</text></list_body>"
        "</list_item></list>",
    )
    source_xml = semantic.read_bytes()

    markdown = MarkdownDocumentWriter.render_text(
        semantic, _report(), source_name="manual.pdf"
    )

    assert "- Power safety" in markdown
    assert "\u0141" not in markdown
    assert semantic.read_bytes() == source_xml


def test_nested_unordered_label_uses_indented_structural_bullet(
    tmp_path: Path,
) -> None:
    markdown = _render(
        tmp_path,
        """
        <list><list_item>
          <label><text>\u0141</text></label>
          <list_body><text>Outer item</text>
            <list><list_item>
              <label><text>\u0152</text></label>
              <list_body><text>Nested item</text></list_body>
            </list_item></list>
          </list_body>
        </list_item></list>
        """,
    )

    body = markdown.split("\n\n", 2)[2]
    assert body == "- Outer item\n  - Nested item\n"
    assert "\u0141" not in markdown
    assert "\u0152" not in markdown


@pytest.mark.parametrize(
    "label",
    ["2.", "1.", "1)", "(1)", "A.", "b)", "iv.", "IV)"],
)
def test_meaningful_ordered_list_label_is_preserved_once(
    tmp_path: Path,
    label: str,
) -> None:
    markdown = _render(
        tmp_path,
        "<list><list_item>"
        f"<label><text>{label}</text></label>"
        "<list_body><text>Attach the bracket</text></list_body>"
        "</list_item></list>",
    )

    body = markdown.split("\n\n", 2)[2]
    assert body == f"{label} Attach the bracket\n"
    assert body.count(label) == 1


@pytest.mark.parametrize("label", ["Step", "*", "\u0141", "\u0152"])
def test_arbitrary_list_labels_use_structural_bullet(
    tmp_path: Path,
    label: str,
) -> None:
    markdown = _render(
        tmp_path,
        "<list><list_item>"
        f"<label><text>{label}</text></label>"
        "<list_body><text>Keep this body</text></list_body>"
        "</list_item></list>",
    )

    body = markdown.split("\n\n", 2)[2]
    assert body == "- Keep this body\n"


def test_unordered_label_glyphs_remain_visible_in_list_body_text(
    tmp_path: Path,
) -> None:
    markdown = _render(
        tmp_path,
        "<list><list_item>"
        "<label><text>\u0141</text></label>"
        "<list_body><text>Literal \u0141 and \u0152 content</text></list_body>"
        "</list_item></list>",
    )

    assert "- Literal \u0141 and \u0152 content" in markdown


def test_list_preserves_unexpected_direct_text(tmp_path: Path) -> None:
    markdown = _render(
        tmp_path,
        """
        <list><text>Loose list text</text>
          <list_item><text>Regular item</text></list_item>
        </list>
        """,
    )

    assert "Loose list text" in markdown
    assert markdown.index("Loose list text") < markdown.index("Regular item")


def test_list_preserves_text_order_around_nested_list(tmp_path: Path) -> None:
    markdown = _render(
        tmp_path,
        """
        <list><list_item>
          <text>Before nested list</text>
          <list><list_item><text>Nested item</text></list_item></list>
          <text>After nested list</text>
        </list_item></list>
        """,
    )

    assert markdown.count("Before nested list") == 1
    assert markdown.count("Nested item") == 1
    assert markdown.count("After nested list") == 1
    assert markdown.index("Before nested list") < markdown.index("Nested item")
    assert markdown.index("Nested item") < markdown.index("After nested list")
    body = markdown.split("\n\n", 2)[2]
    assert sum(line.startswith("- ") for line in body.splitlines()) == 1
    assert "\n  After nested list\n" in markdown


def test_block_only_list_item_emits_parent_marker_before_nested_block(
    tmp_path: Path,
) -> None:
    markdown = _render(
        tmp_path,
        """
        <list><list_item>
          <list><list_item><text>Nested only</text></list_item></list>
        </list_item></list>
        """,
    )

    body = markdown.split("\n\n", 2)[2]
    assert body == "-\n  - Nested only\n"
    assert sum(line == "-" or line.startswith("- ") for line in body.splitlines()) == 1


def test_block_first_list_item_keeps_later_text_as_indented_continuation(
    tmp_path: Path,
) -> None:
    markdown = _render(
        tmp_path,
        """
        <list><list_item>
          <list><list_item><text>Nested first</text></list_item></list>
          <text>After block</text>
        </list_item></list>
        """,
    )

    body = markdown.split("\n\n", 2)[2]
    assert body == "-\n  - Nested first\n  After block\n"
    assert sum(line == "-" or line.startswith("- ") for line in body.splitlines()) == 1


def test_promoted_heading_first_list_item_keeps_one_marker_and_indented_tail(
    tmp_path: Path,
) -> None:
    report = _report(
        {
            "structure_path": "/list[0]/list_item[0]/paragraph[0]",
            "source_role": "Heading1",
            "semantic_role": "paragraph",
            "level": 1,
            "joined_text": "Promoted first",
            "title": None,
            "classification": "source_role_candidate",
        }
    )
    markdown = _render(
        tmp_path,
        """
        <list><list_item>
          <paragraph><text>Promoted first</text></paragraph>
          <text>Tail text</text>
        </list_item></list>
        """,
        report,
    )

    body = markdown.split("\n\n", 2)[2]
    assert body == "-\n  ## Promoted first\n  Tail text\n"
    assert sum(line == "-" or line.startswith("- ") for line in body.splitlines()) == 1


def test_promotes_heading_candidate_inside_list_without_duplicate_text(
    tmp_path: Path,
) -> None:
    report = _report(
        {
            "structure_path": "/list[0]/list_item[0]/paragraph[0]",
            "source_role": "Heading1",
            "semantic_role": "paragraph",
            "level": 1,
            "joined_text": "List heading",
            "title": None,
            "classification": "source_role_candidate",
        }
    )
    markdown = _render(
        tmp_path,
        """
        <list><list_item>
          <paragraph><text>List heading</text></paragraph>
          <text>List tail</text>
        </list_item></list>
        """,
        report,
    )

    assert "## List heading" in markdown
    assert markdown.count("List heading") == 1
    assert markdown.count("List tail") == 1
    assert markdown.index("## List heading") < markdown.index("List tail")


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


@pytest.mark.parametrize(
    ("table_body", "expected_texts"),
    [
        (
            """
            <table_row><table_cell><text>Data A</text></table_cell><table_cell><text>Data B</text></table_cell></table_row>
            <table_row><table_cell><text>Data C</text></table_cell><table_cell><text>Data D</text></table_cell></table_row>
            """,
            ("Data A", "Data B", "Data C", "Data D"),
        ),
        (
            """
            <table_row><table_header><text>Header A</text></table_header><table_cell><text>Not a header</text></table_cell></table_row>
            <table_row><table_cell><text>Data A</text></table_cell><table_cell><text>Data B</text></table_cell></table_row>
            """,
            ("Header A", "Not a header", "Data A", "Data B"),
        ),
        (
            """
            <table_row><table_header><text>Header A</text></table_header><table_header><text>Header B</text></table_header></table_row>
            <table_row><table_cell><attributes><attribute name="/ColSpan" value="2" /></attributes><text>Merged A</text></table_cell><table_cell><text>Merged B</text></table_cell></table_row>
            """,
            ("Header A", "Header B", "Merged A", "Merged B"),
        ),
        (
            """
            <table_row><table_header><text>Header A</text></table_header><table_header><text>Header B</text></table_header></table_row>
            <table_row><table_cell><attributes><attribute name="/RowSpan" value="2" /></attributes><text>Tall A</text></table_cell><table_cell><text>Data B</text></table_cell></table_row>
            """,
            ("Header A", "Header B", "Tall A", "Data B"),
        ),
        (
            """
            <table_row><table_header><text>Header A</text></table_header><table_header><text>Header B</text></table_header></table_row>
            <table_row><table_cell><attributes><attribute name="/ColSpan" value="unknown" /></attributes><text>Ambiguous A</text></table_cell><table_cell><text>Data B</text></table_cell></table_row>
            """,
            ("Header A", "Header B", "Ambiguous A", "Data B"),
        ),
        (
            """
            <table_row><table_header><text>Header A</text></table_header><table_header><text>Header B</text></table_header></table_row>
            <table_row><table_cell><list><list_item><text>Nested A</text></list_item></list></table_cell><table_cell><text>Data B</text></table_cell></table_row>
            """,
            ("Header A", "Header B", "Nested A", "Data B"),
        ),
    ],
    ids=(
        "data-only",
        "mixed-cell-roles",
        "column-span",
        "row-span",
        "ambiguous-span",
        "nested-block",
    ),
)
def test_unsafe_rectangular_tables_fall_back_to_labeled_rows_without_text_loss(
    tmp_path: Path,
    table_body: str,
    expected_texts: tuple[str, ...],
) -> None:
    markdown = _render(tmp_path, f"<table>{table_body}</table>")

    assert "| ---" not in markdown
    assert "- 행 1:" in markdown
    assert "- 행 2:" in markdown
    for text in expected_texts:
        assert markdown.count(text) == 1
    assert [markdown.index(text) for text in expected_texts] == sorted(
        markdown.index(text) for text in expected_texts
    )


def test_promotes_heading_candidate_inside_table_without_duplicate_or_lost_text(
    tmp_path: Path,
) -> None:
    report = _report(
        {
            "structure_path": "/table[0]/table_row[0]/table_cell[0]/paragraph[0]",
            "source_role": "Heading1",
            "semantic_role": "paragraph",
            "level": 1,
            "joined_text": "Table heading",
            "title": None,
            "classification": "source_role_candidate",
        }
    )
    markdown = _render(
        tmp_path,
        """
        <table><table_row><table_cell>
          <paragraph><text>Table heading</text></paragraph>
          <text>Cell tail</text>
        </table_cell></table_row></table>
        """,
        report,
    )

    assert "## Table heading" in markdown
    assert markdown.count("Table heading") == 1
    assert markdown.count("Cell tail") == 1
    assert markdown.index("## Table heading") < markdown.index("Cell tail")


@pytest.mark.parametrize(
    "container_tag",
    ["paragraph", "heading", "caption", "label", "figure"],
)
def test_promotes_descendant_heading_inside_atomic_container_in_source_order(
    tmp_path: Path,
    container_tag: str,
) -> None:
    report = _report(
        {
            "structure_path": f"/{container_tag}[0]/paragraph[1]",
            "source_role": "Heading1",
            "semantic_role": "paragraph",
            "level": 1,
            "joined_text": "Nested heading",
            "title": None,
            "classification": "source_role_candidate",
        }
    )
    markdown = _render(
        tmp_path,
        f"""
        <{container_tag}>
          <text>Before heading</text>
          <paragraph><text>Nested heading</text></paragraph>
          <text>After heading</text>
        </{container_tag}>
        """,
        report,
    )

    assert "## Nested heading" in markdown
    assert markdown.count("Before heading") == 1
    assert markdown.count("Nested heading") == 1
    assert markdown.count("After heading") == 1
    assert markdown.index("Before heading") < markdown.index("## Nested heading")
    assert markdown.index("## Nested heading") < markdown.index("After heading")


@pytest.mark.parametrize(
    "container_tag",
    ["paragraph", "heading", "caption", "label", "figure"],
)
def test_paragraph_like_container_preserves_text_around_nested_list(
    tmp_path: Path,
    container_tag: str,
) -> None:
    markdown = _render(
        tmp_path,
        f"""
        <{container_tag}>
          <text>Before list</text>
          <list><list_item><text>Nested item</text></list_item></list>
          <text>After list</text>
        </{container_tag}>
        """,
    )

    assert "- Nested item" in markdown
    for text in ("Before list", "Nested item", "After list"):
        assert markdown.count(text) == 1
    assert markdown.index("Before list") < markdown.index("- Nested item")
    assert markdown.index("- Nested item") < markdown.index("After list")


def test_paragraph_like_container_keeps_nested_table_and_empty_figure_semantics(
    tmp_path: Path,
) -> None:
    markdown = _render(
        tmp_path,
        """
        <paragraph>
          <text>Before table</text>
          <table>
            <table_row><table_header><text>Name</text></table_header></table_row>
            <table_row><table_cell><text>Value</text></table_cell></table_row>
          </table>
          <text>Between blocks</text>
          <figure />
          <text>After figure</text>
        </paragraph>
        """,
    )

    assert "| Name |\n| --- |\n| Value |" in markdown
    assert "[그림: 텍스트 없음]" in markdown
    for text in ("Before table", "Name", "Value", "Between blocks", "After figure"):
        assert markdown.count(text) == 1
    assert markdown.index("Before table") < markdown.index("| Name |")
    assert markdown.index("| Value |") < markdown.index("Between blocks")
    assert markdown.index("Between blocks") < markdown.index("[그림: 텍스트 없음]")
    assert markdown.index("[그림: 텍스트 없음]") < markdown.index("After figure")


def test_explicit_empty_text_figures_do_not_break_surrounding_osd_text(
    tmp_path: Path,
) -> None:
    markdown = _render(
        tmp_path,
        """
        <paragraph>
          <text>( &gt; left directional button &gt; </text>
          <figure><attributes><attribute name="/Placement" value="/Block" /></attributes><text /></figure>
          <text>Settings &gt; Support &gt; Open User Guide)</text>
        </paragraph>
        """,
    )

    assert (
        "( > left directional button > Settings > Support > Open User Guide)"
        in markdown
    )
    assert markdown.count("[그림: 텍스트 없음]") == 1
    assert markdown.count("left directional button") == 1


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


@pytest.mark.parametrize(
    ("source", "escaped"),
    [
        ("```python", r"\```python"),
        ("~~~", r"\~~~"),
        ("---", r"\---"),
        ("***", r"\***"),
        ("___", r"\___"),
        ("<div>raw HTML</div>", r"\<div>raw HTML</div>"),
        ("<!-- source comment -->", r"\<!-- source comment -->"),
    ],
)
def test_escapes_commonmark_block_openers_per_source_line(
    tmp_path: Path,
    source: str,
    escaped: str,
) -> None:
    markdown = _render(
        tmp_path,
        f"<paragraph><text>{source.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')}</text></paragraph>"
        "<paragraph><text>Following content</text></paragraph>",
    )

    assert f"\n{escaped}\n\nFollowing content\n" in markdown


def test_escapes_link_reference_definition_without_changing_following_reference(
    tmp_path: Path,
) -> None:
    markdown = _render(
        tmp_path,
        "<paragraph><text>[manual]: https://example.com/guide</text></paragraph>"
        "<paragraph><text>Read [manual] and keep [ordinary brackets].</text></paragraph>",
    )

    assert r"\[manual]: https://example.com/guide" in markdown
    assert "Read [manual] and keep [ordinary brackets]." in markdown
    assert r"Read \[manual]" not in markdown


def test_escapes_footnote_definition_without_changing_following_footnote_reference(
    tmp_path: Path,
) -> None:
    markdown = _render(
        tmp_path,
        "<paragraph><text>[^warning]: Source footnote text</text></paragraph>"
        "<paragraph><text>Keep [^warning] visible in source text.</text></paragraph>"
        "<paragraph><text>( &gt; Settings &gt; Support &gt; Open User Guide)</text></paragraph>",
    )

    assert r"\[^warning]: Source footnote text" in markdown
    assert "Keep [^warning] visible in source text." in markdown
    assert r"Keep \[^warning]" not in markdown
    assert "( > Settings > Support > Open User Guide)" in markdown


def test_escapes_reference_definition_with_escaped_closing_bracket_in_label(
    tmp_path: Path,
) -> None:
    markdown = _render(
        tmp_path,
        r"<paragraph><text>[foo\]]: https://example.com</text></paragraph>"
        r"<paragraph><text>Keep [foo\]] and [ordinary] visible.</text></paragraph>",
    )

    assert r"\[foo\]]: https://example.com" in markdown
    assert r"Keep [foo\]] and [ordinary] visible." in markdown
    assert r"Keep \[foo\]]" not in markdown


def test_escapes_footnote_definition_with_escaped_closing_bracket_in_label(
    tmp_path: Path,
) -> None:
    markdown = _render(
        tmp_path,
        r"<paragraph><text>[^note\]]: Footnote source</text></paragraph>"
        r"<paragraph><text>Keep [^note\]] and [ordinary text].</text></paragraph>",
    )

    assert r"\[^note\]]: Footnote source" in markdown
    assert r"Keep [^note\]] and [ordinary text]." in markdown
    assert r"Keep \[^note\]]" not in markdown


def test_replace_failure_keeps_existing_destination_and_removes_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    semantic = tmp_path / "semantic_document.xml"
    output = tmp_path / "semantic_document.md"
    _write_xml(semantic, "<paragraph><text>Replacement</text></paragraph>")
    output.write_bytes(b"existing destination")

    def fail_replace(source: str | Path, destination: str | Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(markdown_writer_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        MarkdownDocumentWriter().write(
            semantic, _report(), output, source_name="manual.pdf"
        )

    assert output.read_bytes() == b"existing destination"
    assert list(tmp_path.glob(f".{output.name}.*.tmp")) == []


@pytest.mark.parametrize("failure_point", ["write", "close"])
def test_write_or_close_failure_keeps_existing_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    semantic = tmp_path / "semantic_document.xml"
    output = tmp_path / "semantic_document.md"
    _write_xml(semantic, "<paragraph><text>Replacement</text></paragraph>")
    output.write_bytes(b"existing destination")
    real_named_temporary_file = markdown_writer_module.tempfile.NamedTemporaryFile

    class FailingTemporaryFile:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self._context = real_named_temporary_file(*args, **kwargs)
            self._file: object | None = None

        def __enter__(self) -> "FailingTemporaryFile":
            self._file = self._context.__enter__()
            self.name = self._file.name
            return self

        def write(self, value: str) -> int:
            if failure_point == "write":
                raise OSError("write failed")
            return self._file.write(value)

        def __exit__(
            self,
            exception_type: type[BaseException] | None,
            exception: BaseException | None,
            traceback: object,
        ) -> bool | None:
            result = self._context.__exit__(exception_type, exception, traceback)
            if failure_point == "close" and exception_type is None:
                raise OSError("close failed")
            return result

    monkeypatch.setattr(
        markdown_writer_module.tempfile,
        "NamedTemporaryFile",
        FailingTemporaryFile,
    )

    with pytest.raises(OSError, match=f"{failure_point} failed"):
        MarkdownDocumentWriter().write(
            semantic, _report(), output, source_name="manual.pdf"
        )

    assert output.read_bytes() == b"existing destination"
    assert list(tmp_path.glob(f".{output.name}.*.tmp")) == []


def test_cleanup_failure_does_not_mask_primary_publication_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    semantic = tmp_path / "semantic_document.xml"
    output = tmp_path / "semantic_document.md"
    _write_xml(semantic, "<paragraph><text>Replacement</text></paragraph>")
    output.write_bytes(b"existing destination")

    def fail_replace(source: str | Path, destination: str | Path) -> None:
        raise OSError("primary replace failed")

    def fail_unlink(self: Path, missing_ok: bool = False) -> None:
        raise OSError("secondary unlink failed")

    monkeypatch.setattr(markdown_writer_module.os, "replace", fail_replace)
    monkeypatch.setattr(markdown_writer_module.Path, "unlink", fail_unlink)

    with pytest.raises(OSError, match="primary replace failed"):
        MarkdownDocumentWriter().write(
            semantic, _report(), output, source_name="manual.pdf"
        )

    assert output.read_bytes() == b"existing destination"


def test_atomic_publication_replaces_from_temporary_sibling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    semantic = tmp_path / "semantic_document.xml"
    output = tmp_path / "review" / "semantic_document.md"
    _write_xml(semantic, "<paragraph><text>Published</text></paragraph>")
    replace_calls: list[tuple[Path, Path]] = []
    real_replace = markdown_writer_module.os.replace

    def record_replace(source: str | Path, destination: str | Path) -> None:
        temporary = Path(source)
        final = Path(destination)
        assert temporary.parent == output.parent
        assert temporary.name.startswith(f".{output.name}.")
        assert temporary.name.endswith(".tmp")
        assert temporary.exists()
        replace_calls.append((temporary, final))
        real_replace(temporary, final)

    monkeypatch.setattr(markdown_writer_module.os, "replace", record_replace)

    MarkdownDocumentWriter().write(
        semantic,
        _report(),
        output,
        source_name="manual.pdf",
    )

    assert len(replace_calls) == 1
    temporary, final = replace_calls[0]
    assert final == output
    assert not temporary.exists()
    assert output.read_text(encoding="utf-8").endswith("Published\n")
