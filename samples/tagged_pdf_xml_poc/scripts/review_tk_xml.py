"""Fresh TK XML/Markdown review bundles and source crop evidence (no DB work)."""
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

ROOT=Path(__file__).resolve().parents[3]
POC=Path(__file__).resolve().parents[1]
SOURCES={
 'TK_L02':'BN68-26343A-00_SUG_Y26 TV ALL_TK_L02_260327.0.pdf',
 'TK_ARA':'BN68-26344A-00_SUG_Y26 TV ALL_TK_ARA_260327.0.pdf'}
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
def text(n):return ''.join(t.text or '' for t in n.iter('text'))
def norm(t):return ''.join(t.split())
def heading_display_text(node,headings):
    if node.tag=='heading' and node.get('numbered-label') is not None:
        # Use the same source-label validation as the Markdown heading writer.
        # Joining raw PDF text fragments alone would turn 01 into "0 1".
        W._render_element(node,headings)
        return node.get('numbered-label')+' '+W._element_text(node.find('list_body'))
    return W._element_text(node)
def code_hashes():
    return {str(p.relative_to(POC)):sha256(p.read_bytes()).hexdigest()
            for p in sorted((POC/'src').rglob('*.py'))}
def crop(pdf,n,path,header_only=False):
    boxes=[(int(t.get('page-index')),tuple(map(float,t.get('bbox').split(','))))
           for t in n.iter('text') if t.get('bbox')]
    source_pages={int(t.get('page-index')) for t in n.iter('text')}
    if len(source_pages)==1 and not header_only:
        for attrs in n.iter('attributes'):
            for a in attrs:
                if a.get('name')=='/BBox':
                    b=json.loads(a.get('value'))
                    if len(b)==4:boxes.append((next(iter(source_pages)),tuple(b)))
    # The text extractor's font advance can overestimate a cover-title width.
    # Prefer the nearest exact PDF text match for a short single-fragment region.
    if len(boxes)==1 and len(list(n.iter('text')))==1 and len(norm(text(n)))>5:
        p,b=boxes[0];matches=pdf[p].search_for(' '.join(text(n).split()))
        if matches:
            m=min(matches,key=lambda r:(r.x0-b[0])**2+(r.y0-(pdf[p].rect.height-b[3]))**2)
            boxes=[(p,(m.x0,pdf[p].rect.height-m.y1,m.x1,pdf[p].rect.height-m.y0))]
    if not boxes:
        for t in n.iter('text'):
            p=int(t.get('page-index'));value=' '.join((t.text or '').split())
            if len(value)<5:continue
            for rect in pdf[p].search_for(value):
                boxes.append((p,(rect.x0,pdf[p].rect.height-rect.y1,rect.x1,pdf[p].rect.height-rect.y0)))
    pages={p for p,b in boxes}
    if len(pages)!=1:return None
    p=next(iter(pages)); page=pdf[p]; bs=[b for _,b in boxes]
    rect=fitz.Rect(min(b[0] for b in bs)-(2 if header_only else 10),page.rect.height-max(b[3] for b in bs)-(2 if header_only else 12),
                   max(b[2] for b in bs)+(2 if header_only else 10),page.rect.height-min(b[1] for b in bs)+(2 if header_only else 18))&page.rect
    if rect.is_empty:return None
    page.get_pixmap(matrix=fitz.Matrix(2,2),clip=rect).save(path)
    return {'page':p+1,'rect':list(rect),'crop':str(path.resolve()),'source_ref':n.get('object-ref'),
            'source_path':n.get('source-structure-path')}

def prepare(run,output):
    folder=Path(run['output']);root=E.parse(folder/'semantic_document.xml').getroot()
    raw=E.parse(folder/'raw_structure.xml').getroot()
    report=json.loads((folder/'extraction_report.json').read_text(encoding='utf8'))
    document=root.find('document')
    headings=W._resolve_heading_candidates(root,SimpleNamespace(heading_hierarchy=report['heading_hierarchy']))
    labels=[label for item in document.iter('list_item') for label in item.findall('label')]
    native=[l for l in labels if norm(text(l)) in {'•','–','°','¯','\x80'} or re.fullmatch(r'[0-9]+\.',norm(text(l)))]
    excluded={t for l in native for t in l.iter('text')}
    source_text=lambda n:''.join(t.text or '' for t in n.iter('text') if t not in excluded)
    units=[]
    def walk(n):
        if n.tag in ('attributes','label'):return
        cs=[c for c in n if c.tag!='attributes']
        if (n.tag in ('list','table') or cs and all(c.tag in ('text','span','link','figure') for c in cs)) and list(n.iter('text')):
            units.append(dict(text=source_text(n),markdown='\n\n'.join(W._render_element(n,headings)),
                source_path=n.get('source-structure-path'),object_ref=n.get('object-ref'),tag=n.tag,
                pages=sorted({int(t.get('page-index')) for t in n.iter('text')})))
            return
        for c in cs:walk(c)
    walk(document)
    identity=lambda n:(n.get('page-index'),n.get('mcid'),n.get('object-ref'))
    expected=Counter(map(identity,raw.iter('fragment')))
    split_proof=[]
    for d in report['diagnostics']:
        if d['code']=='tk_arabic_split_fragment':
            for s in d['context']['splits']:
                owners=[k for k in expected if k[:2]==(str(s['page_index']),str(s['mcid']))]
                parts=s['source_parts'];source=s['original_text']
                offsets=[i for p in parts for i in range(*p['slice'])]
                valid=(len(owners)==1 and sorted(offsets)==list(range(len(source)))
                    and all(source[slice(*p['slice'])]==p['text'] for p in parts))
                if valid:expected[owners[0]]+=len(parts)-1
                split_proof.append({**s,'disjoint_complete_source_slices':valid})
    raw_chars=Counter(norm(''.join(p.text or '' for p in raw.iter('part'))))
    sem_chars=Counter(norm(text(document)))
    def ownership(nodes,raw_view=False):
        result={}
        for n in nodes:
            value=''.join(p.text or '' for p in n.iter('part')) if raw_view else n.text or ''
            result.setdefault(identity(n),Counter()).update(norm(value))
        return result
    gates={**report['hard_gates'],
       'source_review_complete':False,
       'source_fragment_identity':expected==Counter(map(identity,document.iter('text'))),
       'documented_split_source_coverage':all(s['disjoint_complete_source_slices'] for s in split_proof),
       'raw_semantic_character_bag':raw_chars==sem_chars,
       'mcid_nonspace_character_ownership':ownership(raw.iter('fragment'),True)==ownership(document.iter('text')),
       'all_source_nodes_traceable':all(n.get('source-structure-path') for n in document.iter()
           if n.get('object-ref') and n.tag!='text')}
    stats={}
    for lang in run['languages']:
        def belongs(n):return n.get('language')==lang
        nodes=[n for n in document.iter() if belongs(n)]
        hs=[n for n in nodes if n.tag=='heading' or n in headings or n.get('display-role')=='section-heading']
        stats[lang]={'headings':len(hs),'heading_texts':[heading_display_text(n,headings) for n in hs],
            'blocks':dict(Counter(n.tag for n in nodes if n.tag in ('paragraph','list','list_item','table','figure','heading'))),
            'review_units':sum(bool(u['pages']) and (len(run['languages'])==1
                or all(p==run['languages'].index(lang) for p in u['pages'])) for u in units),
            'tables':[dict(ref=n.get('object-ref'),rows=len(n.findall('table_row')),
                cells=len(n.findall('.//table_cell')),figures=len(list(n.iter('figure')))) for n in nodes if n.tag=='table'],
            'display_roles':dict(Counter(n.get('display-role') for n in nodes if n.get('display-role')))}
    evidence=[];contact_tables=[]
    visual_checks=[]
    with fitz.open(run['pdf']) as pdf:
        for page in pdf:
            path=folder/f'pdf_p{page.number+1}.png'
            page.get_pixmap(matrix=fitz.Matrix(1.3,1.3)).save(path)
        # All cover stories precede their body in the semantic Article.
        article=document.find('article')
        if article is not None:
            for n in article:
                if n.tag=='attributes':continue
                pages={int(t.get('page-index')) for t in n.iter('text')}
                # Body story is much longer than the reviewed cover regions.
                if len(text(n))<8000:
                    for region in ([n] if len(text(n))<150 else [c for c in n if c.tag!='attributes']):
                        ref=region.get('object-ref','').split(' ')[0]
                        if ref and (proof:=crop(pdf,region,folder/f'cover_region_{ref}.png')):evidence.append(proof)
        for n in document.iter('table'):
            if proof:=crop(pdf,n,folder/f'table_{n.get("object-ref", "unknown").split(" ")[0]}.png'):evidence.append(proof)
            if '444 77 11' in text(n):
                rows=n.findall('table_row');header=rows[0]
                proof=crop(pdf,header,folder/f'contact_header_{n.get("object-ref").split(" ")[0]}.png',header_only=True)
                contact_tables.append(dict(ref=n.get('object-ref'),language=n.get('language'),
                    source_header=[W._element_text(c) for c in header if c.tag in ('table_cell','table_header')],
                    data_rows=[[W._element_text(c) for c in row if c.tag in ('table_cell','table_header')] for row in rows[1:]],
                    header_only_crop=proof))
        if run['buyer']=='TK_L02':
            # Whole printed importer badge, including image-only role title.
            rect=fitz.Rect(1488,635,1690,733)
            pdf[1].get_pixmap(matrix=fitz.Matrix(2,2),clip=rect).save(folder/'tur_importer_badge.png')
            evidence.append({'page':2,'rect':list(rect),'crop':str(folder/'tur_importer_badge.png'),
                'source_ref':'941 0 R','note':'Includes image-only İthalatçı Firma; no OCR claim.'})
        refs=({'389 0 R':'TUR power','301 0 R':'TUR fee','932 0 R':'TUR manufacturer rowspan',
               '905 0 R':'TUR lab rowspan','558 0 R':'TUR source wording 1','510 0 R':'TUR source wording 2'}
              if run['buyer']=='TK_L02' else {'436 0 R':'ARA power','339 0 R':'ARA fee',
               '196 0 R':'ARA microphone models','295 0 R':'ARA output models',
               '298 0 R':'ARA inch/output condition','302 0 R':'ARA second inch/output condition',
               '72 0 R':'ARA source installation condition'})
        parents={c:n for n in document.iter() for c in n}
        for ref,label in refs.items():
            n=next(n for n in document.iter() if n.get('object-ref')==ref)
            if label.endswith('power'):
                n=parents[parents[n]] if parents[n].tag=='list_body' else n
            if label.endswith('fee'):
                n=parents[parents[parents[n]]]
            path=folder/f'check_{ref.split(" ")[0]}.png'
            proof=crop(pdf,n,path)
            item=n if n.tag=='list_item' else parents[n] if n.tag=='list_body' else None
            rendered=('\n'.join(W._render_list_item(item,headings,indent='')) if item is not None
                      else '\n\n'.join(W._render_element(n,headings)))
            visual_checks.append(dict(label=label,source_ref=ref,crop=path.name if proof else None,
                markdown=rendered,language=n.get('language'),source_text=text(n)))
    ltr_models=[W._element_text(n) for n in document.iter('span')
        if any(a.get('name')=='review-inline' and a.get('value')=='ltr-model-token'
               for a in n.findall('attributes/attribute'))]
    dump(folder/'render_input.json',dict(source_text=source_text(document),units=units,ownership=[],expected_ltr_models=ltr_models))
    review=dict(source=run,hard_gates=gates,language_stats=stats,source_crops=evidence,
        contact_tables=contact_tables,
        source_fragment_splits=split_proof,
        visual_checks=visual_checks,
        raw_semantic_character_difference={'missing':dict(raw_chars-sem_chars),'added':dict(sem_chars-raw_chars)},
        status='pending_html_and_source_review')
    dump(folder/'review_document.json',review)
    dump(folder/'review_run.json',dict(start_head=run['head'],source_sha256=run['sha256'],
        runtime_code_sha256=run['code_sha256'],
        extraction_status=report['status'],review_status=review['status'],artifact_sha256={
            p.name:sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.name in
            ('raw_structure.xml','semantic_document.xml','semantic_document.md','extraction_report.json')}))
    return review

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    runs=[];reviews=[]
    for buyer,name in SOURCES.items():
        source=ROOT.parent/'xml-extractor-release/samples/SUG_RAW/TV_TK'/name
        before_code=code_hashes()
        document,report,_=_build_use_case().run(source,out/buyer)
        if before_code!=code_hashes():raise RuntimeError('Runtime changed during extraction; use a fresh output folder')
        profile=document.readability_profile
        run=dict(buyer=buyer,pdf=str(source),sha256=sha256(source.read_bytes()).hexdigest(),head=head,
            code_sha256=before_code,
            source_token=profile.source_token,doc_type=profile.doc_type,languages=profile.languages,
            output=str(out/buyer),bookmarks=[])
        runs.append(run);reviews.append(prepare(run,out));print(buyer,report.status,flush=True)
    dump(out/'manifest.json',dict(head=head,runs=runs))
    dump(out/'review_summary.json',[{'buyer':r['source']['buyer'],'language_stats':r['language_stats'],
        'hard_gates':r['hard_gates']} for r in reviews])

if __name__=='__main__':main()
