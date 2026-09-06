from xml.etree import ElementTree as ET

import pytest

from .readability_assertions import (
    assert_generic_figure_fallback,
    assert_navigation_flows_preserved,
)


def _navigation_root() -> ET.Element:
    return ET.fromstring(
        "<document><paragraph>"
        "<text>Menu (</text>"
        '<figure display-role="inline-icon"><text /></figure>'
        "<text>&gt; Settings / [Panel])</text>"
        "</paragraph></document>"
    )


def test_navigation_flow_preserves_text_icon_order_and_characters() -> None:
    assert_navigation_flows_preserved(
        _navigation_root(),
        "Menu ( [아이콘] > Settings / [Panel])",
    )


def test_navigation_flow_uses_source_text_joining_before_closing_punctuation() -> None:
    root = ET.fromstring(
        "<document><paragraph>"
        "<text>Menu (</text>"
        '<figure display-role="inline-icon"><text /></figure>'
        "<text>&gt; Settings</text><text>)</text>"
        "</paragraph></document>"
    )

    assert_navigation_flows_preserved(root, "Menu ( [아이콘] > Settings)")


def test_navigation_flow_rejects_reordered_or_incomplete_markdown() -> None:
    with pytest.raises(AssertionError, match="navigation flow"):
        assert_navigation_flows_preserved(
            _navigation_root(),
            "Menu ( > Settings [아이콘] / Panel)",
        )


def test_generic_figure_fallback_requires_complete_empty_figure_coverage() -> None:
    root = ET.fromstring(
        "<document>"
        "<figure><text /></figure>"
        "<figure><text /></figure>"
        "</document>"
    )

    with pytest.raises(AssertionError):
        assert_generic_figure_fallback(
            root,
            "[그림: 텍스트 없음]\n",
        )


def test_textual_generic_figure_is_not_counted_as_empty_fallback() -> None:
    root = ET.fromstring(
        "<document>"
        "<figure><text>Visible figure text</text></figure>"
        "<figure><text /></figure>"
        "</document>"
    )

    assert_generic_figure_fallback(
        root,
        "Visible figure text\n\n[그림: 텍스트 없음]\n",
    )
