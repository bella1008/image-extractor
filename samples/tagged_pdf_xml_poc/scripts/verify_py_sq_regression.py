"""Re-extract the 13 existing profile fixtures without changing their outputs."""
import argparse,json
from pathlib import Path
from hashlib import sha256
from review_tk_xml import POC,code_hashes,dump
from tagged_pdf_extractor.cli import _build_use_case

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    before=POC/'outputs/xml_review_mena_xl_xt_20260917_final_regression'
    entries=json.loads((POC/'outputs/xml_review_mena_xl_xt_20260917_regression/comparison.json').read_text(encoding='utf8'))
    for row in entries:row['reference']=str(before/row['buyer'])
    ready=POC/'outputs/xml_review_mena_xl_xt_20260917_ready'
    for run in json.loads((ready/'manifest.json').read_text(encoding='utf8'))['runs']:
        entries.append(dict(buyer=run['buyer'],pdf=run['pdf'],reference=str(ready/run['buyer'])))
    hashes=code_hashes();results=[]
    for entry in entries:
        if hashes!=code_hashes():raise RuntimeError('Runtime changed during regression')
        _,report,_=_build_use_case(ready/'profile_mapping_review.json').run(Path(entry['pdf']),out/entry['buyer'])
        artifacts={name:sha256((out/entry['buyer']/name).read_bytes()).hexdigest()==sha256((Path(entry['reference'])/name).read_bytes()).hexdigest()
            for name in ('raw_structure.xml','semantic_document.xml','semantic_document.md')}
        results.append({**entry,'status':report.status,'artifacts':artifacts})
        dump(out/'comparison.json',results);print(entry['buyer'],report.status,artifacts,flush=True)
    if hashes!=code_hashes() or any(r['status']!='pass' or not all(r['artifacts'].values()) for r in results):
        raise SystemExit('Regression changed')
    dump(out/'runtime_code_sha256.json',hashes)
if __name__=='__main__':main()
