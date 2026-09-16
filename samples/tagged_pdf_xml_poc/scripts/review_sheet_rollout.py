"""Fresh MENA/XL/XT review bundles with source ownership and rendering inputs."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace
from xml.etree import ElementTree as E
POC=Path(__file__).resolve().parents[1]
STARTUP_CODE_HASHES={str(p.relative_to(POC)):sha256(p.read_bytes()).hexdigest() for p in sorted((POC/'src').rglob('*.py'))}
import pymupdf as fitz
from tagged_pdf_extractor.cli import _build_use_case
from tagged_pdf_extractor.infrastructure.markdown_writer import MarkdownDocumentWriter as W
from review_tk_xml import code_hashes, crop, dump, norm, text, heading_display_text

POC=Path(__file__).resolve().parents[1]
ROOT=POC.parents[1]
SOURCES={
 'MENA_L02':('2_TV_MENA','BN68-25031L-00_SUG_Y26 TV ALL_MENA_L02_260114.0.pdf'),
 'XL_ENG':('2_TV_XL','BN68-25031J-00_SUG_Y26 TV ALL_XL_ENG_260306.0.pdf'),
 'XT_L02':('2_TV_XT','BN68-25031M-00_SUG_Y26 TV ALL_XT_L02_260113.0.pdf')}

def prepare(run):
    folder=Path(run['output'])
    root=E.parse(folder/'semantic_document.xml').getroot();document=root.find('document')
    raw=E.parse(folder/'raw_structure.xml').getroot()
    report=json.loads((folder/'extraction_report.json').read_text(encoding='utf8'))
    headings=W._resolve_heading_candidates(root,SimpleNamespace(heading_hierarchy=report['heading_hierarchy']))
    labels=[l for item in document.iter('list_item') for l in item.findall('label')]
    excluded={t for l in labels if norm(text(l)) in {'•','–','°','¯','\x80'} or re.fullmatch(r'[0-9]+\.',norm(text(l))) for t in l.iter('text')}
    source_text=lambda n:''.join(t.text or '' for t in n.iter('text') if t not in excluded)
    units=[]
    def walk(n):
        if n.tag in ('attributes','label'):return
        cs=[c for c in n if c.tag!='attributes']
        if (n.tag in ('list','table','heading') or cs and all(c.tag in ('text','span','link','figure') for c in cs)) and list(n.iter('text')):
            units.append(dict(text=source_text(n),markdown='\n\n'.join(W._render_element(n,headings)),
                source_path=n.get('source-structure-path'),object_ref=n.get('object-ref'),tag=n.tag,language=n.get('language')))
        else:
            for c in cs:walk(c)
    walk(document)
    identity=lambda n:(n.get('page-index'),n.get('mcid'),n.get('object-ref'))
    raw_map={identity(n):Counter(norm(''.join(p.text or '' for p in n.iter('part')))) for n in raw.iter('fragment')}
    sem_map={identity(n):Counter(norm(n.text or '')) for n in document.iter('text')}
    expected=dict(raw_map)
    source_transfers=[]
    if run['buyer']=='MENA_L02':
        diagnostic=next(d for d in report['diagnostics'] if d['code']=='mena_source_text')
        for change in diagnostic['context']['changes']:
            if change['kind']!='model_suffix_source_ownership':continue
            changes=change['fragment_changes']
            before=Counter(norm(''.join(c['before'] for c in changes)))
            after=Counter(norm(''.join(c['after'] for c in changes)))
            if before!=after or change['glyph']!='*' or change['from_mcid']!=1084 or change['to_mcid']!=1083:
                raise ValueError('Unproved MENA ownership transfer')
            for c in changes:
                keys=[k for k in expected if k[:2]==('1',str(c['mcid']))]
                if len(keys)!=1 or expected[keys[0]]!=Counter(norm(c['before'])):
                    raise ValueError('MENA transfer original owner does not match')
                expected[keys[0]]=Counter(norm(c['after']))
            source_transfers.append(change)
    # XT's broken PDF Unicode is checked against independently observed glyphs,
    # not accepted merely because the rewritten text differs from the baseline.
    if run['buyer']=='XT_L02':
        diagnostic=next(d for d in report['diagnostics'] if d['code']=='xt_source_operations')
        for record in diagnostic['context']['fragments']:
            if record['page_index']!=1:continue
            keys=[k for k in expected if k[:2]==('1',str(record['mcid']))]
            if len(keys)!=1:continue
            expected[keys[0]]=Counter(norm(''.join(''.join(r['verified_glyphs']) for r in record['runs'])))
    differences=[{'identity':k,'missing':dict(v-sem_map.get(k,Counter())),
        'added':dict(sem_map.get(k,Counter())-v)} for k,v in expected.items() if v!=sem_map.get(k)]
    gates={**report['hard_gates'],'source_review_complete':False,
        'source_fragment_identity':Counter(map(identity,raw.iter('fragment')))==Counter(map(identity,document.iter('text'))),
        'mcid_source_character_ownership':not differences,
        'all_source_nodes_traceable':all(n.get('source-structure-path') for n in document.iter() if n.get('object-ref') and n.tag!='text')}
    stats={}
    for lang in run['languages']:
        ns=[n for n in document.iter() if n.get('language')==lang]
        hs=[n for n in ns if n.tag=='heading' or n in headings or n.get('display-role')=='section-heading']
        stats[lang]={'headings':len(hs),'heading_texts':[heading_display_text(n,headings) for n in hs],
          'blocks':dict(Counter(n.tag for n in ns if n.tag in ('paragraph','list','list_item','table','figure','heading'))),
          'review_units':sum(u['language']==lang for u in units),
          'tables':[dict(ref=n.get('object-ref'),rows=len(n.findall('table_row')),cells=len(n.findall('.//table_cell')),figures=len(list(n.iter('figure')))) for n in ns if n.tag=='table']}
    evidence=[];checks=[];contacts=[]
    with fitz.open(run['pdf']) as pdf:
        for page in pdf:page.get_pixmap(matrix=fitz.Matrix(1.3,1.3)).save(folder/f'pdf_p{page.number+1}.png')
        article=document.find('article')
        regions=[n for n in article if n.tag!='attributes' and len(text(n))<8000]
        regions+=list(document.iter('table'))
        parents={c:n for n in document.iter() for c in n}
        important={'MENA_L02':{'174 0 R','517 0 R','553 0 R','1175 0 R','390 0 R'},
                   'XL_ENG':{'549 0 R'},'XT_L02':{'1123 0 R','336 0 R'}}[run['buyer']]
        for n in document.iter():
            if n.get('object-ref') not in important:continue
            target=parents[n] if parents.get(n) is not None and parents[n].tag=='list_body' else n
            if target.tag=='list_body':target=parents[target]
            regions.append(target)
        for n in regions:
            ref=n.get('object-ref','unknown').split()[0]
            p=crop(pdf,n,folder/f'source_{ref}.png')
            if run['buyer']=='MENA_L02' and n.get('language')=='ARA' and n.tag in {'paragraph','list_item'}:
                ids={int(t.get('mcid')) for t in n.iter('text') if t.get('mcid')}
                boxes=[b for d in report['diagnostics'] if d['code']=='africa_rtl_glyph_source' and d['context']['page_index']==1
                       for line in d['context']['lines'] for r in line['runs'] if r['mcid'] in ids for b in (r.get('glyph_boxes') or [])]
                if boxes:
                    page=pdf[1];rect=fitz.Rect(min(b[0] for b in boxes)-10,page.rect.height-max(b[3] for b in boxes)-12,
                        max(b[2] for b in boxes)+10,page.rect.height-min(b[1] for b in boxes)+18)&page.rect
                    path=folder/f'source_{ref}.png';page.get_pixmap(matrix=fitz.Matrix(2,2),clip=rect).save(path)
                    p=dict(page=2,rect=list(rect),crop=str(path.resolve()),source_ref=n.get('object-ref'),source_path=n.get('source-structure-path'),bounds_basis='original_pdf_glyph_operations')
            if p:
                evidence.append(p)
                rendered=('\n'.join(W._render_list_item(n,headings,indent='')) if n.tag=='list_item'
                          else '\n\n'.join(W._render_element(n,headings)))
                checks.append(dict(label=f"{run['buyer']} {n.get('language')} {n.tag}",source_ref=n.get('object-ref'),
                    language=n.get('language'),crop=Path(p['crop']).name,markdown=rendered,source_text=text(n)))
            attrs={a.get('name'):a.get('value') for a in n.findall('attributes/attribute')}
            if n.tag=='table' and attrs.get('review-table')=='source-spans':
                rows=n.findall('table_row');header=rows[0]
                contacts.append(dict(ref=n.get('object-ref'),language=n.get('language'),
                    source_header=[W._element_text(c) for c in header if c.tag in ('table_cell','table_header')],
                    data_rows=[[W._element_text(c) for c in r if c.tag in ('table_cell','table_header')] for r in rows[1:]],
                    header_only_crop=crop(pdf,header,folder/f'header_{ref}.png',header_only=True)))
    ltr_models=[W._element_text(n) for n in document.iter('span') if any(a.get('name')=='review-inline' and a.get('value')=='ltr-model-token' for a in n.findall('attributes/attribute'))]
    dump(folder/'render_input.json',dict(source_text=source_text(document),units=units,ownership=[],expected_ltr_models=ltr_models))
    review=dict(source=run,hard_gates=gates,language_stats=stats,source_crops=evidence,visual_checks=checks,
        contact_tables=contacts,source_owner_transfers=source_transfers,source_fidelity_mismatches=differences,status='pending_source_and_html_review')
    dump(folder/'review_document.json',review)
    dump(folder/'review_run.json',dict(start_head=run['head'],source_sha256=run['sha256'],runtime_code_sha256=run['code_sha256'],
        extraction_status=report['status'],review_status=review['status'],human_approval=False,
        artifact_sha256={name:sha256((folder/name).read_bytes()).hexdigest() for name in ('raw_structure.xml','semantic_document.xml','semantic_document.md','extraction_report.json')}))
    return review

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path)
    p.add_argument('--buyers',nargs='+',choices=SOURCES,default=list(SOURCES));a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    canonical=ROOT/'metadata/pdf_profile_mapping/pdf_profile_mapping.json'
    rows=json.loads(canonical.read_text(encoding='utf8'))
    overlay=json.loads((POC/'config/review_profile_overrides.json').read_text(encoding='utf8'))
    for row in overlay['profiles']:
        if any(r['source_token']==row['source_token'] for r in rows):raise ValueError('Review override conflicts with canonical profile')
        rows.append({**row,'languages':';'.join(row['languages'])})
    mapping=out/'profile_mapping_review.json';dump(mapping,rows)
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    runs=[]
    # Main checkout is only a read-only source PDF library.
    sample_root=ROOT.parent.parent/'samples/SUG_RAW'
    for buyer in a.buyers:
        source=sample_root.joinpath(*SOURCES[buyer]);hashes=STARTUP_CODE_HASHES
        if hashes!=code_hashes():raise RuntimeError('Runtime changed since process startup; use a fresh process and output folder')
        document,report,_=_build_use_case(profile_mapping_path=mapping).run(source,out/buyer)
        if hashes!=code_hashes():raise RuntimeError('Runtime changed; extract again into a fresh folder')
        profile=document.readability_profile
        run=dict(buyer=buyer,pdf=str(source),sha256=sha256(source.read_bytes()).hexdigest(),head=head,code_sha256=hashes,
            source_token=profile.source_token,doc_type=profile.doc_type,languages=profile.languages,output=str(out/buyer),bookmarks=[])
        review=prepare(run);runs.append(run)
        print(buyer,report.status,'pending:',[k for k,v in review['hard_gates'].items() if not v],flush=True)
        dump(out/'manifest.json',dict(head=head,runs=runs,canonical_profile_sha256=sha256(canonical.read_bytes()).hexdigest(),review_only_overrides=overlay))
if __name__=='__main__':main()
