from tagged_pdf_extractor.domain.text_joining import join_text_parts


def test_trims_leading_whitespace_after_existing_trailing_space() -> None:
    text, decisions = join_text_parts(("Go to Settings > General", " > Accessibility."))

    assert text == "Go to Settings > General > Accessibility."
    assert decisions == ({"boundary": 0, "action": "trim_left"},)


def test_preserves_symbol_separated_text() -> None:
    text, decisions = join_text_parts(("Wi-Fi", " → Network / Status"))

    assert text == "Wi-Fi → Network / Status"
    assert decisions == ({"boundary": 0, "action": "trim_left"},)


def test_inserts_space_between_adjacent_words() -> None:
    text, decisions = join_text_parts(("This is", "a sentence."))

    assert text == "This is a sentence."
    assert decisions == ({"boundary": 0, "action": "insert_space"},)


def test_empty_parts_return_empty_text_and_no_decisions() -> None:
    assert join_text_parts(()) == ("", ())
