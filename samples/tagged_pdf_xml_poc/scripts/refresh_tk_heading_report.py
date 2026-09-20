"""Refresh heading display metadata in a new copy of a validated TK bundle."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
from xml.etree import ElementTree as E
from review_tk_xml import dump, heading_display_text, W

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('previous',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();old=args.previous.resolve();out=args.output.resolve()
    if out.exists():raise FileExistsError(out)
    shutil.copytree(old,out)
    def remap(v):
        if isinstance(v,dict):return {k:remap(x) for k,x in v.items()}
        if isinstance(v,list):return [remap(x) for x in v]
        if isinstance(v,str):
            for a,b in ((str(old),str(out)),(old.as_posix(),out.as_posix())):
                if v.startswith(a):return b+v[len(a):]
        return v
    for name in ('manifest.json','source_findings.json'):
        path=out/name
        if path.is_file():dump(path,remap(json.loads(path.read_text(encoding='utf8'))))
    changes=[];summary=[]
    for run in json.loads((out/'manifest.json').read_text(encoding='utf8'))['runs']:
        folder=out/run['buyer'];old_folder=old/run['buyer']
        root=E.parse(folder/'semantic_document.xml').getroot()
        extraction=json.loads((folder/'extraction_report.json').read_text(encoding='utf8'))
        headings=W._resolve_heading_candidates(root,SimpleNamespace(heading_hierarchy=extraction['heading_hierarchy']))
        review=remap(json.loads((folder/'review_document.json').read_text(encoding='utf8')))
        for language,stats in review['language_stats'].items():
            nodes=[n for n in root.find('document').iter() if n.get('language')==language and
                   (n.tag=='heading' or n in headings or n.get('display-role')=='section-heading')]
            values=[heading_display_text(n,headings) for n in nodes]
            if len(values)!=stats['headings']:raise ValueError('Heading count changed')
            for before,after in zip(stats['heading_texts'],values):
                if before!=after:changes.append({'language':language,'before':before,'after':after})
            stats['heading_texts']=values
        dump(folder/'review_document.json',review)
        log=remap(json.loads((folder/'review_run.json').read_text(encoding='utf8')))
        preserved={n:sha256((folder/n).read_bytes()).hexdigest()==sha256((old_folder/n).read_bytes()).hexdigest()
                   for n in ('raw_structure.xml','semantic_document.xml','semantic_document.md','extraction_report.json','semantic_document.preview.html')}
        if not all(preserved.values()):raise ValueError('Extraction or full preview changed')
        log['heading_report_refresh']={'previous_bundle':str(old),'unchanged_artifacts':preserved}
        dump(folder/'review_run.json',log)
        summary.append({'buyer':run['buyer'],'language_stats':review['language_stats'],'hard_gates':review['hard_gates']})
    dump(out/'review_summary.json',summary)
    dump(out/'heading_report_changes.json',{'previous_bundle':str(old),'changes':changes})
    print(json.dumps(changes,ensure_ascii=False))

if __name__=='__main__':main()
