"""Fresh PY and SQ MI XML review runs; all human approvals remain pending."""
import argparse
from pathlib import Path
import subprocess
from hashlib import sha256
from review_sheet_rollout import STARTUP_CODE_HASHES,POC,ROOT,prepare
from review_tk_xml import code_hashes,dump
from tagged_pdf_extractor.cli import _build_use_case

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    canonical=ROOT/'metadata/pdf_profile_mapping/pdf_profile_mapping.json'
    sources={'PY_ENRU':next((ROOT/'samples/SUG_RAW/TV_PY').glob('*.pdf')),
             'SQ_MI_HEAR':next((ROOT/'samples/SUG_RAW/TV_SQ_MI').glob('*.pdf'))}
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();runs=[]
    for buyer,source in sources.items():
        if STARTUP_CODE_HASHES!=code_hashes():raise RuntimeError('Runtime changed; start a fresh process/output')
        document,report,_=_build_use_case(canonical).run(source,out/buyer)
        if STARTUP_CODE_HASHES!=code_hashes():raise RuntimeError('Runtime changed during extraction')
        profile=document.readability_profile
        run=dict(buyer=buyer,pdf=str(source),sha256=sha256(source.read_bytes()).hexdigest(),head=head,
            code_sha256=STARTUP_CODE_HASHES,source_token=profile.source_token,doc_type=profile.doc_type,
            languages=profile.languages,output=str(out/buyer),bookmarks=[])
        review=prepare(run);runs.append(run)
        dump(out/'manifest.json',dict(head=head,runs=runs,canonical_profile_sha256=sha256(canonical.read_bytes()).hexdigest(),
            previous_pending_human_buyers=['MENA','XL','XT','TK','ZW'],human_approval=False))
        print(buyer,report.status,[k for k,v in review['hard_gates'].items() if not v],flush=True)
if __name__=='__main__':main()
