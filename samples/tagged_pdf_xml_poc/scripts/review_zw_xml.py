"""Fresh ZW extraction with per-MCID overprint accounting and review evidence."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace
from xml.etree import ElementTree as E

import pymupdf as fitz
from tagged_pdf_extractor.cli import _build_use_case
from tagged_pdf_extractor.infrastructure.markdown_writer import MarkdownDocumentWriter as W
from review_tk_xml import code_hashes, crop, dump, norm, text

POC=Path(__file__).resolve().parents[1]
SOURCE=Path('C:/Users/bella/image-extractor/samples/SUG_RAW/2_TV_ZW/BN68-24973D-00_SUG_Y26 TV ALL_ZW_TPE_260327.0.pdf')

def prepare(folder, run):
    root=E.parse(folder/'semantic_document.xml').getroot()
    raw=E.parse(folder/'raw_structure.xml').getroot()
    report=json.loads((folder/'extraction_report.json').read_text(encoding='utf8'))
    document=root.find('document')
    headings=W._resolve_heading_candidates(root,SimpleNamespace(heading_hierarchy=report['heading_hierarchy']))
    labels=[l for item in document.iter('list_item') for l in item.findall('label')]
    excluded={t for l in labels if norm(text(l)) in {'•','–','°','¯','\x80'} or re.fullmatch(r'[0-9]+\.',norm(text(l))) for t in l.iter('text')}
    source_text=lambda n: ''.join(t.text or '' for t in n.iter('text') if t not in excluded)
    units=[]
    def walk(n):
        if n.tag in ('attributes','label'):return
        cs=[c for c in n if c.tag!='attributes']
        if (n.tag in ('list','table') or cs and all(c.tag in ('text','span','link','figure') for c in cs)) and list(n.iter('text')):
            units.append(dict(text=source_text(n),markdown='\n\n'.join(W._render_element(n,headings)),
                source_path=n.get('source-structure-path'),object_ref=n.get('object-ref'),tag=n.tag))
        else:
            for c in cs:walk(c)
    walk(document)
    identity=lambda n:(n.get('page-index'),n.get('mcid'),n.get('object-ref'))
    raw_map={identity(n):norm(''.join(p.text or '' for p in n.iter('part'))) for n in raw.iter('fragment')}
    sem_map={identity(n):norm(n.text or '') for n in document.iter('text')}
    expected=dict(raw_map)
    overprints=next(d['context']['overprints'] for d in report['diagnostics'] if d['code']=='zw_source_text')
    proof=[]
    for p in overprints:
        keys=[k for k in expected if k[:2]==(str(p['page_index']),str(p['removed_mcid']))]
        retained=[k for k in expected if k[:2]==(str(p['page_index']),str(p['retained_mcid']))]
        valid=len(keys)==len(retained)==1 and raw_map[keys[0]]==raw_map[retained[0]]==norm(p['text'])
        if valid:expected[keys[0]]=''
        proof.append({**p,'raw_owner_pair_verified':valid})
    gates={**report['hard_gates'],'source_review_complete':False,
        'source_fragment_identity':Counter(map(identity,raw.iter('fragment')))==Counter(map(identity,document.iter('text'))),
        'overprint_raw_owner_proof':all(p['raw_owner_pair_verified'] for p in proof),
        'mcid_nonspace_character_ownership':expected==sem_map,
        'all_source_nodes_traceable':all(n.get('source-structure-path') for n in document.iter() if n.get('object-ref') and n.tag!='text')}
    stats={'heading_texts':[W._element_text(n) for n in document.iter() if n.tag=='heading' or n in headings or n.get('display-role')=='section-heading'],
           'blocks':dict(Counter(n.tag for n in document.iter() if n.tag in ('paragraph','list','list_item','table','figure','heading'))),
           'review_units':len(units),'tables':[{'ref':n.get('object-ref'),'rows':len(n.findall('table_row')),'cells':len(n.findall('.//table_cell')),'figures':len(list(n.iter('figure')))} for n in document.iter('table')]}
    evidence=[];checks=[]
    with fitz.open(SOURCE) as pdf:
        for page in pdf:
            page.get_pixmap(matrix=fitz.Matrix(1.5,1.5)).save(folder/f'pdf_p{page.number+1}.png')
        article=document.find('article')
        regions=[n for n in article if n.tag!='attributes'][:-1]
        regions += list(document.iter('table'))
        # Source-critical structures and both cover contacts/code are cropped.
        for n in regions:
            ref=n.get('object-ref','unknown').split()[0]
            if p:=crop(pdf,n,folder/f'source_{ref}.png'):
                evidence.append(p)
                checks.append(dict(label=f'TPE {n.tag} {ref}',source_ref=n.get('object-ref'),language='TPE',crop=Path(p['crop']).name,
                    markdown='\n\n'.join(W._render_element(n,headings)),source_text=text(n)))
        for name,page,rect in [('document_code',0,[332,570,414,600]),('power',0,[657,54,853,136]),('rohs',1,[450,628,845,1188])]:
            pdf[page].get_pixmap(matrix=fitz.Matrix(3,3),clip=fitz.Rect(rect)).save(folder/f'{name}.png')
            evidence.append({'crop':str(folder/f'{name}.png'),'page':page+1,'rect':rect,'kind':'manual_source_region'})
    dump(folder/'render_input.json',dict(source_text=source_text(document),units=units,ownership=[],expected_ltr_models=[]))
    review=dict(source=run,hard_gates=gates,language_stats={'TPE':stats},source_crops=evidence,visual_checks=checks,
        overprint_proof=proof,source_fidelity_mismatches=[{'identity':k,'expected':v,'actual':sem_map.get(k)} for k,v in expected.items() if sem_map.get(k)!=v],
        status='pending_html_and_source_review')
    dump(folder/'review_document.json',review)
    dump(folder/'review_run.json',dict(start_head=run['head'],source_sha256=run['sha256'],runtime_code_sha256=run['code_sha256'],
        extraction_status=report['status'],review_status=review['status'],artifact_sha256={p.name:sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.name in ('raw_structure.xml','semantic_document.xml','semantic_document.md','extraction_report.json')}))
    return review

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    hashes=code_hashes();head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    folder=out/'ZW_TPE'
    _build_use_case().run(SOURCE,folder)
    if hashes!=code_hashes():raise RuntimeError('Runtime changed during extraction')
    run=dict(buyer='ZW_TPE',doc_type='A3',languages=['TPE'],pdf=str(SOURCE),output=str(folder),head=head,
        sha256=sha256(SOURCE.read_bytes()).hexdigest(),code_sha256=hashes)
    review=prepare(folder,run);dump(out/'manifest.json',{'runs':[run]})
    print(json.dumps({'failed_gates':[k for k,v in review['hard_gates'].items() if not v],
                      'stats':review['language_stats'],'output':str(out)},ensure_ascii=False))

if __name__=='__main__':main()
