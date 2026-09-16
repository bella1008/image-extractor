from collections import Counter
from dataclasses import replace

import pytest

from tagged_pdf_extractor.domain.models import ContentFragment, Diagnostic, StructureElement


def frag(mcid, value):
    return ContentFragment(1, mcid, (value,))


def node(ref, *children):
    return StructureElement('P', 'paragraph', object_ref=ref, language='ARA', children=children)


def evidence(*entries):
    runs = []
    for mcid, value, left in entries:
        runs.append(dict(mcid=mcid, glyphs=list(value), actual_text=False,
                         operation_index=mcid, baseline_y=20.0, font_name='Source', font_size=7,
                         glyph_boxes=[[left+i, 20., left+i+1, 27.] for i in range(len(value))]))
    return (Diagnostic('warning', 'africa_rtl_glyph_source', '',
                       {'page_index': 1, 'lines': [{'runs': runs}]}),)


def run(children, diagnostics):
    from tagged_pdf_extractor.domain.mena_source_text import repair_mena_source
    return repair_mena_source(children, diagnostics)


def leaves(n):
    if isinstance(n, ContentFragment):
        yield n
    else:
        for c in n.children:
            yield from leaves(c)


def test_model_star_moves_only_with_proven_source_owner_and_complete_audit():
    original = node('174 0 R', frag(1085, 'U9***H'), frag(1084, '*/\u200f'), frag(1083, 'LS03H'))
    ev = evidence((1083, 'LS03H', 100), (1084, '*/', 105), (1085, 'U9***H', 108))
    result, audit = run((original,), ev)
    assert ''.join(f.text for f in leaves(result[0])) == 'U9***H/\u200fLS03H*'
    assert Counter(''.join(f.text for f in leaves(result[0]))) == Counter(''.join(f.text for f in leaves(original)))
    assert [f.mcid for f in leaves(result[0])] == [1085, 1084, 1083]
    transfer = audit.context['changes'][0]
    assert transfer['kind'] == 'model_suffix_source_ownership'
    assert transfer['from_mcid'] == 1084 and transfer['to_mcid'] == 1083
    assert transfer['glyph'] == '*' and transfer['glyph_box'] == [105, 20., 106, 27.]
    assert {x['mcid']: (x['before'], x['after']) for x in transfer['fragment_changes']} == {
        1084: ('*/\u200f', '/\u200f'), 1083: ('LS03H', 'LS03H*')}


def test_sound_line_break_slash_remains_between_models():
    original = node('517 0 R', frag(1731, '\u200f/'), frag(1729, ' /'), frag(1730, 'QN1EH'), frag(1750, 'M1EH'))
    result, audit = run((original,), evidence((1729, '/', 100), (1730, 'QN1EH', 101)))
    assert [f.mcid for f in result[0].children] == [1731, 1730, 1729, 1750]
    assert Counter(result[0].children) == Counter(original.children)
    assert audit.context['changes'][0]['kind'] == 'sound_model_boundary_slash'


def test_wifi_brackets_enclose_whole_heading_without_changing_source_characters():
    original = node('553 0 R', frag(1889, ' احتياطات استخدام شبكة ['), frag(1888, 'Wi-Fi'),
                    frag(1881, ' ]) جيجاهرتز '))
    # Physical left-to-right glyph sequence inside Arabic MCID owners.
    ev = evidence((1889, ' ةكبش مادختسا تاطايتحا[', 120), (1881, ']زترهاجيج )', 100))
    result, audit = run((original,), ev)
    assert result[0].children[0].text == ' [احتياطات استخدام شبكة '
    assert result[0].children[-1].text == ' ) جيجاهرتز] '
    assert Counter(''.join(f.text for f in leaves(result[0]))) == Counter(''.join(f.text for f in leaves(original)))
    assert audit.context['changes'][0]['kind'] == 'wifi_source_bracket_order'


def test_wifi_preserves_real_parts_with_synthetic_newline_style():
    from tagged_pdf_extractor.domain.models import TextStyle
    font = TextStyle('Source', 7)
    first = replace(frag(1889, ''), text_parts=(' ', 'احتياطات استخدام شبكة', '['), text_styles=(font,)*3)
    last = replace(frag(1881, ''), text_parts=('\n', ']', ') جيجاهرتز '),
                   text_styles=(TextStyle('Source', 1), font, font), text_bboxes=(None, (100,20,101,27), (100,20,110,27)))
    original = node('553 0 R', first, last)
    ev = evidence((1889, ' ةكبش مادختسا تاطايتحا[', 120), (1881, ']زترهاجيج )', 100))
    repaired, audit = run((original,), ev)
    assert len(audit.context['changes']) == 1
    assert repaired[0].children[0].text == ' [احتياطات استخدام شبكة'
    assert repaired[0].children[-1].text == '\n) جيجاهرتز] '
    assert repaired[0].children[-1].text_styles == (font,)


def test_changed_visible_typography_refuses_wifi_collapse():
    from tagged_pdf_extractor.domain.models import TextStyle
    first = frag(1889, ' احتياطات استخدام شبكة [')
    last = replace(frag(1881, ''), text_parts=(']', ') جيجاهرتز'),
                   text_styles=(TextStyle('Source', 7), TextStyle('Other', 7)))
    original = node('553 0 R', first, last)
    ev = evidence((1889, ' ةكبش مادختسا تاطايتحا[', 120), (1881, ']زترهاجيج )', 100))
    repaired, audit = run((original,), ev)
    assert repaired == (original,) and not audit.context['changes']


@pytest.mark.parametrize('mutation', ['missing', 'changed_geometry', 'changed_glyph', 'actual_text', 'other_language', 'other_ref', 'changed_text'])
def test_model_transfer_refuses_unproven_input(mutation):
    original = node('174 0 R', frag(1085, 'U9***H'), frag(1084, '*/\u200f'), frag(1083, 'LS03H'))
    ev = evidence((1083, 'LS03H', 100), (1084, '*/', 105), (1085, 'U9***H', 108))
    if mutation == 'missing': ev = ()
    elif mutation == 'changed_geometry': ev[0].context['lines'][0]['runs'][1]['glyph_boxes'][0][0] += 50
    elif mutation == 'changed_glyph': ev[0].context['lines'][0]['runs'][1]['glyphs'][0] = '+'
    elif mutation == 'actual_text': ev[0].context['lines'][0]['runs'][1]['actual_text'] = True
    elif mutation == 'other_language': original = replace(original, language='ENG')
    elif mutation == 'other_ref': original = replace(original, object_ref='OTHER')
    elif mutation == 'changed_text': original = replace(original, children=(frag(1085, 'U9***H'), frag(1084, '*/\u200f'), frag(1083, 'LS04H')))
    result, audit = run((original,), ev)
    assert result == (original,)
    assert not audit.context['changes']


def test_repairs_are_idempotent():
    original = node('174 0 R', frag(1085, 'U9***H'), frag(1084, '*/\u200f'), frag(1083, 'LS03H'))
    ev = evidence((1083, 'LS03H', 100), (1084, '*/', 105), (1085, 'U9***H', 108))
    once, _ = run((original,), ev)
    twice, audit = run(once, ev)
    assert twice == once and not audit.context['changes']


def test_copyright_uses_source_glyph_positions_around_copyright_symbol():
    original = node('119 0 R', frag(943, ' عام© حقوق النشر'), frag(942, '2026'))
    ev = evidence((943, ' ماع © رشنلا قوقح', 100))
    repaired, audit = run((original,), ev)
    assert repaired[0].children[0].text == 'حقوق النشر © عام '
    assert repaired[0].children[1] is original.children[1]
    change = audit.context['changes'][0]
    assert change['kind'] == 'copyright_source_glyph_order'
    assert change['fragment_changes'] == [{'mcid': 943, 'before': ' عام© حقوق النشر', 'after': 'حقوق النشر © عام '}]
    twice, second_audit = run(repaired, ev)
    assert twice == repaired and not second_audit.context['changes']


@pytest.mark.parametrize('mutation', ['geometry', 'glyph', 'actual_text', 'source_text'])
def test_copyright_repair_requires_complete_source_proof(mutation):
    original = node('119 0 R', frag(943, ' عام© حقوق النشر'))
    ev = evidence((943, ' ماع © رشنلا قوقح', 100))
    run_data = ev[0].context['lines'][0]['runs'][0]
    if mutation == 'geometry': run_data['glyph_boxes'][3][0] = 80
    elif mutation == 'glyph': run_data['glyphs'][5] = '+'
    elif mutation == 'actual_text': run_data['actual_text'] = True
    elif mutation == 'source_text': original = node('119 0 R', frag(943, 'other source'))
    repaired, audit = run((original,), ev)
    assert repaired == (original,) and not audit.context['changes']


def test_real_source_operations_authorize_all_three_repairs():
    from pathlib import Path
    from tagged_pdf_extractor.domain.models import PdfProfile
    from tagged_pdf_extractor.infrastructure.pypdf_reader import TaggedPdfReader

    relative = 'samples/SUG_RAW/2_TV_MENA/BN68-25031L-00_SUG_Y26 TV ALL_MENA_L02_260114.0.pdf'
    path = next((root / relative for root in Path(__file__).resolve().parents if (root / relative).is_file()), None)
    if path is None:
        pytest.skip('MENA source sample unavailable')
    document = TaggedPdfReader().read_for_profile(path, PdfProfile('MENA_L02', 'A2', ('ENG', 'ARA'), 2))
    from tagged_pdf_extractor.domain.mena_sheet import prepare_mena_sheet
    prepared = prepare_mena_sheet(document, PdfProfile('MENA_L02', 'A2', ('ENG', 'ARA'), 2))
    integrated = next(d for d in prepared.diagnostics if d.code == 'mena_source_text')
    assert len(integrated.context['changes']) == 4
    copyright = next(f for c in prepared.children for f in leaves(c) if f.page_index == 1 and f.mcid == 943)
    assert copyright.text == 'حقوق النشر © عام '
    original = (
        node('174 0 R', frag(1085, 'U9***H'), frag(1084, '*/\u200f'), frag(1083, 'LS03H')),
        node('517 0 R', frag(1731, '\u200f/'), frag(1729, ' /'), frag(1730, 'QN1EH'), frag(1750, 'M1EH')),
        node('553 0 R', frag(1889, ' احتياطات استخدام شبكة ['), frag(1888, 'Wi-Fi'), frag(1881, ' ]) جيجاهرتز ')),
    )
    repaired, audit = run(original, document.diagnostics)
    assert {c['kind'] for c in audit.context['changes']} == {
        'model_suffix_source_ownership', 'sound_model_boundary_slash', 'wifi_source_bracket_order'}
    assert repaired[0].children[-1].text == 'LS03H*'
    assert [f.mcid for f in repaired[1].children] == [1731, 1730, 1729, 1750]
    assert repaired[2].children[0].text.lstrip().startswith('[')
