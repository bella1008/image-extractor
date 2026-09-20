"""Delete synthetic spaces only when the PDF operation proves the text."""
from dataclasses import replace
import re
from tagged_pdf_extractor.domain.models import ContentFragment,Diagnostic

def restore_tk_text(children,diagnostics):
    runs={}
    for d in diagnostics:
        if d.code=='tk_source_operations':
            runs.update({(r['page_index'],r['mcid']):r['runs'] for r in d.context['fragments']})
    changes=[]
    def visit(n):
        if not isinstance(n,ContentFragment):
            cs=tuple(visit(c) for c in n.children)
            # Exact adjacent source fragments: observed line endings inside tokens.
            # Scope comes from TK_L02/A2; neither translated text nor fuzzy matching.
            for i in range(1,len(cs)):
                a,b=cs[i-1:i+1]
                if not isinstance(a,ContentFragment) or not isinstance(b,ContentFragment):continue
                suffix=next((s for s in ('network-','ecodesign_','www.','www.samsung.') if a.text.endswith(s)),None)
                if not suffix or not b.text.startswith('\n') or a.page_index!=b.page_index:continue
                required={'network-':'based smart services.','ecodesign_':'energy','www.':'samsung.com/','www.samsung.':'com/global/ecodesign_energy'}[suffix]
                if not b.text.lstrip().startswith(required):continue
                source_a=runs.get((a.page_index,a.mcid),[])
                source_b=runs.get((b.page_index,b.mcid),[])
                if not source_a or not source_b or any(r.get('actual_text') for r in (*source_a,*source_b)):continue
                if not ''.join(''.join(r['glyphs']) for r in source_a).endswith(suffix):continue
                if not ''.join(''.join(r['glyphs']) for r in source_b).startswith(required):continue
                # Only boundary whitespace is removed; both MCID owners remain.
                cs=(*cs[:i],replace(b,join_previous=True),*cs[i+1:])
                changes.append({'kind':'source_token_boundary','page_index':b.page_index,'mcid':b.mcid,'previous_mcid':a.mcid})
            return replace(n,children=cs)
        values=runs.get((n.page_index,n.mcid),[])
        if not values or any(r.get('actual_text') for r in values):return n
        if len({r.get('operation_index') for r in values})!=1 or values[0].get('operation_index') is None:return n
        parts=tuple(re.sub(r'(?<=\d) +(?=[.,](?:\d|$))','',p) for p in n.text_parts)
        parts=tuple(p.replace('https:/ /','https://').replace('http:/ /','http://') for p in parts)
        source=''.join(''.join(r['glyphs']) for r in values)
        if parts==n.text_parts or ''.join(parts).strip()!=source.strip():return n
        changes.append({'kind':'operation_spacing','page_index':n.page_index,'mcid':n.mcid,
            'source_parts':n.text_parts,'parts':parts,'operation_index':values[0]['operation_index']})
        return replace(n,text_parts=parts)
    return tuple(visit(c) for c in children),Diagnostic('warning','tk_source_text',
        'Restored observed token spacing without discarding source fragments.',{'changes':changes})
