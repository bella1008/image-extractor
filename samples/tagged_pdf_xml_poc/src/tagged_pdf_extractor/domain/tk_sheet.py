"""Source-verified TK sheets; preserve raw tags and source paths."""
from dataclasses import replace
from tagged_pdf_extractor.domain.models import ContentFragment, Diagnostic

def tk_l02_scope(profile):
    return (profile is not None and profile.source_token=='TK_L02'
            and profile.doc_type=='A2' and profile.languages==('ENG','TUR'))

def fragments(node):
    if isinstance(node,ContentFragment): yield node
    else:
        for c in node.children: yield from fragments(c)

def prepare_tk_sheet(document,profile):
    if not tk_l02_scope(profile): return document
    if document.raw_children is not None: raise ValueError('TK sheet already prepared')
    changes=[]
    def annotate(n,path):
        if isinstance(n,ContentFragment):return n
        pages={f.page_index for f in fragments(n)}
        lang=profile.languages[next(iter(pages))] if len(pages)==1 and pages<={0,1} else n.language
        return replace(n,source_structure_path=path,language=lang,
            children=tuple(annotate(c,(*path,i)) for i,c in enumerate(n.children)))
    def visit(n):
        if isinstance(n,ContentFragment):return n
        children=tuple(visit(c) for c in n.children)
        if n.semantic_role=='table' and n.language=='TUR':
            spans=tuple(tuple(dict(cell.attributes).get('/RowSpan','1') for cell in row.children)
                for row in children if not isinstance(row,ContentFragment)
                and row.semantic_role=='table_row'
                and all(not isinstance(cell,ContentFragment) and cell.semantic_role in {'table_cell','table_header'} for cell in row.children))
            if len(spans)==len(children) and spans in ((('2','1'),('1',)),
                    (('4','1'),('1',),('1',),('1',),('4','1'),('1',),('1',),('1',))):
                n=replace(n,attributes=(*n.attributes,('review-table','source-spans')))
        if n.source_role=='Article':
            # The observed A2 article contains ENG and TUR label/body/cover groups.
            starts=[i for i,c in enumerate(children) if not isinstance(c,ContentFragment)
                and c.source_role=='Story' and len(c.children)==1
                and getattr(c.children[0],'source_role',None)=='Language']
            if len(starts)!=2 or starts[0]!=0: raise ValueError('TK language story layout needs review')
            reordered=[]
            for page,(start,end) in enumerate(zip(starts,(*starts[1:],len(children)))):
                group=children[start:end]
                labels=''.join(f.text for f in fragments(group[0])).strip()
                covers=[c for c in group[2:] if any(getattr(x,'source_role',None)=='Cover_Title' for x in getattr(c,'children',()))]
                if (labels!=profile.languages[page] or len(covers)!=1
                    or getattr(group[1],'source_role',None)!='Story'
                    or {f.page_index for c in group for f in fragments(c)}!={page}):
                    raise ValueError('TK cover/body source evidence changed')
                reordered.extend((group[0],*group[2:],group[1]))
                changes.append({'language':labels,'body_source_path':group[1].source_structure_path,
                    'cover_source_paths':[c.source_structure_path for c in group[2:]]})
            children=tuple(reordered)
        return replace(n,children=children)
    children=tuple(visit(annotate(c,(i,))) for i,c in enumerate(document.children))
    from tagged_pdf_extractor.domain.tk_source_text import restore_tk_text
    children,evidence=restore_tk_text(children,document.diagnostics)
    return replace(document,raw_children=document.children,children=children,
        diagnostics=(*document.diagnostics,Diagnostic('warning','tk_cover_order',
          'Moved source cover stories before body, retaining original paths.',{'changes':changes}),evidence))
