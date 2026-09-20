"""Source-backed SQ MI sound model/value associations."""
from collections import Counter
from pathlib import Path
import unicodedata as ud
import pytest
from tagged_pdf_extractor.cli import _build_use_case
from tagged_pdf_extractor.domain.sq_mi_sheet import prepare_sq_mi_sheet
from tagged_pdf_extractor.domain.models import ContentFragment
from .acceptance_support import require_sample

ROOT=Path(__file__).resolve().parents[3]
SOURCE=next((ROOT/'samples/SUG_RAW').rglob('*SQ MI_HEAR*.pdf'))

def fragments(n):
    if isinstance(n,ContentFragment):yield n
    else:
        for c in n.children:yield from fragments(c)

def visible(s):return ''.join(c for c in s if not c.isspace() and ud.category(c)!='Cf')

def nodes(n):
    if not isinstance(n,ContentFragment):
        yield n
        for c in n.children:yield from nodes(c)

@pytest.fixture(scope='module')
def prepared():
    require_sample(SOURCE,'SQ MI_HEAR')
    u=_build_use_case();p=u.profile_repository.lookup(SOURCE)
    document=prepare_sq_mi_sheet(u.reader.read_for_profile(SOURCE,p),p)
    if not any(d.code=="sq_mi_sound_source_order" for d in document.diagnostics):
        from dataclasses import replace
        from tagged_pdf_extractor.domain.sq_mi_spec_text import repair_sq_mi_specs
        children,proof=repair_sq_mi_specs(document.children,document.diagnostics)
        document=replace(document,children=children,diagnostics=(*document.diagnostics,proof))
    return document

@pytest.mark.parametrize('ref,expected',[
 ('1256 0 R','U8***H/U9***H/M7*H/M8*H/M9*H/S8*H/QN7*H/QN1EH/M1EH:20W'),
 ('1257 0 R','R8*H/QN8*H:30W'),('1258 0 R','S90H:40W'),('1259 0 R','S95H/R9*H:70W'),('1260 0 R','QN9**H:90W'),
 ('1261 0 R','LS03HE(43"):20W,LS03HE(98"):40W'),('1262 0 R','LS03HA/LS03HW:40W'),
 ('328 0 R','U8***H/U9***H/M7*H/M8*H/M9*H/S8*H/QN7*H/QN1EH/M1EH:20واط'),
 ('330 0 R','R8*H/QN8*H:30واط'),('331 0 R','S90H:40واط'),('332 0 R','S95H/R9*H:70واط'),('333 0 R','QN9**H:90واط'),
 ('334 0 R','LS03HE(43"):20واط,LS03HE(98"):40واط'),('335 0 R','LS03HA/LS03HW:40واط')])
def test_sq_sound_rows_keep_source_model_value_associations(prepared,ref,expected):
    node=next(n for c in prepared.children for n in nodes(c) if n.object_ref==ref)
    assert visible(''.join(f.text for f in fragments(node)))==expected

def test_sq_sound_proof_records_every_changed_fragment_and_control(prepared):
    proof=next(d for d in prepared.diagnostics if d.code=='sq_mi_sound_source_order')
    assert len(proof.context['changes'])==14
    for row in proof.context['changes']:
        assert row['fragment_changes']
        assert all({'mcid','before','after'}<=change.keys() for change in row['fragment_changes'])
        assert isinstance(row['control_removals'],dict)
        assert row['visible_character_inventory_preserved'] is True
    transfers=[t for row in proof.context['changes'] for t in row['punctuation_glyph_transfers']]
    assert len(transfers)==4
    assert all(t['source_runs'] and t['glyph']=='"' for t in transfers)

def test_sq_sound_rows_retain_fragment_identities_and_source_characters(prepared):
    from tagged_pdf_extractor.domain.sq_mi_spec_text import SPEC_LTR_GROUPS
    raw={n.object_ref:n for c in prepared.raw_children for n in nodes(c)}
    final={n.object_ref:n for c in prepared.children for n in nodes(c) if n.object_ref}
    refs=['1256 0 R','1257 0 R','1258 0 R','1259 0 R','1260 0 R','1261 0 R','1262 0 R','328 0 R','330 0 R','331 0 R','332 0 R','333 0 R','334 0 R','335 0 R']
    identity=lambda f:(f.page_index,f.mcid,f.object_ref)
    for ref in refs:
        before=list(fragments(raw[ref]));after=list(fragments(final[ref]))
        assert Counter(map(identity,before))==Counter(map(identity,after))
        assert Counter(visible(''.join(f.text for f in before)))==Counter(visible(''.join(f.text for f in after)))
        wrappers=[c for c in final[ref].children if dict(getattr(c,'attributes',())).get('review-inline')=='ltr-model-token']
        definitions=SPEC_LTR_GROUPS[final[ref].source_structure_path]
        assert len(wrappers)==len(definitions)
        for wrapper,definition in zip(wrappers,definitions):
            assert tuple(map(identity,fragments(wrapper)))==definition['identities']
            assert visible(''.join(f.text for f in fragments(wrapper)))==visible(definition['text'])

def test_sq_sound_proof_is_json_serializable(prepared):
    import json
    proof=next(d for d in prepared.diagnostics if d.code=='sq_mi_sound_source_order')
    json.dumps(proof.context,ensure_ascii=False)
    assert sum(len(row['punctuation_glyph_transfers']) for row in proof.context['changes'])==4
    for row in proof.context['changes']:
        assert row['visible_character_counter_before']==row['visible_character_counter_after']

def test_sq_sound_islands_clear_obsolete_direct_numeric_direction(prepared):
    from tagged_pdf_extractor.domain.sq_mi_spec_text import SPEC_LTR_GROUPS
    rows=[n for c in prepared.children for n in nodes(c) if n.object_ref and n.source_structure_path in SPEC_LTR_GROUPS]
    assert len(rows)==14
    assert all(n.display_direction is None for n in rows)
