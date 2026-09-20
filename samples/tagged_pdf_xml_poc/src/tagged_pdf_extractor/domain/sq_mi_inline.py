"""Exact-source LTR islands inside SQ MI Hebrew and Arabic prose."""
from dataclasses import replace
from tagged_pdf_extractor.domain.models import ContentFragment,StructureElement
from tagged_pdf_extractor.domain.sq_mi_sheet import SOURCE_SHA

INLINE_GROUPS={
 '1425 0 R':((0,0,1,51,0,4,0,0),0,((119,121),)),
 '1166 0 R':((0,0,1,53),0,((634,635),)),
 '146 0 R':((0,0,10,51,0,4,0,0),1,((1247,),)),
 '381 0 R':((0,0,10,53),1,((1753,1754),)),
 '1324 0 R':((0,0,1,72,0,1),0,tuple((i,) for i in [356,353,350,347,344,378,375,372,369,366,363])+((359,360),)),
 '276 0 R':((0,0,10,72,0,1),1,tuple((i,) for i in [1483,1480,1477,1500,1497,1494,1491,1488,1512,1509,1506])+((1502,1503),)),
}

def wrap_sq_inline(children):
    def visit(n):
        if isinstance(n,ContentFragment):return n
        cs=tuple(visit(c) for c in n.children)
        if n.object_ref=='1207 0 R':
            ids=(1095,1094,1093,1092)
            start=next(i for i,c in enumerate(cs) if isinstance(c,ContentFragment) and c.mcid==1095)
            group=cs[start:start+4]
            if (n.source_structure_path!=(0,0,1,90,0,0,0,0)
                    or tuple(getattr(c,'mcid',None) for c in group)!=ids
                    or tuple(c.text for c in group)!=('Wi-Fi','\u200f',' ','5.925')):
                raise ValueError('SQ MI Wi-Fi source whitespace scope changed')
            wrapper=StructureElement('ReviewSpan','span',page_index=0,language='HEB',source_structure_path=n.source_structure_path,
                children=group,attributes=(('review-whitespace','source-boundary'),('review-whitespace-source-token','SQ MI_HEAR'),
                    ('review-whitespace-source-sha256',SOURCE_SHA)))
            return replace(n,children=(*cs[:start],wrapper,*cs[start+4:]))
        if n.object_ref not in INLINE_GROUPS:return replace(n,children=cs)
        path,page,groups=INLINE_GROUPS[n.object_ref]
        if n.source_structure_path!=path:raise ValueError('SQ MI inline source path changed')
        for ids in groups:
            indexes=[i for i,c in enumerate(cs) if isinstance(c,ContentFragment) and c.mcid in ids]
            if len(indexes)!=len(ids) or indexes!=list(range(indexes[0],indexes[0]+len(ids))):
                raise ValueError('SQ MI inline model ownership changed')
            group=cs[indexes[0]:indexes[-1]+1]
            if tuple(c.mcid for c in group)!=ids:raise ValueError('SQ MI inline model order changed')
            wrapper=StructureElement('ReviewSpan','span',page_index=page,language=n.language,source_structure_path=path,
                children=group,attributes=(('review-inline','ltr-model-token'),('review-source-token','SQ MI_HEAR'),
                    ('review-source-sha256',SOURCE_SHA),('review-source-owner',n.object_ref)))
            cs=(*cs[:indexes[0]],wrapper,*cs[indexes[-1]+1:])
        return replace(n,children=cs)
    return tuple(visit(n) for n in children)

def validate_sq_inline(element):
    """Writer allowlist rejects unknown paths, owners, text, or source revisions."""
    import re,unicodedata
    from tagged_pdf_extractor.infrastructure.xml_writer import decode_data_element
    attrs={a.get('name'):a.get('value') for a in element.findall('attributes/attribute')}
    expected={'review-inline':'ltr-model-token','review-source-token':'SQ MI_HEAR','review-source-sha256':SOURCE_SHA}
    path=tuple(int(i) for i in element.get('source-structure-path','').split('/') if i)
    leaves=list(element.iter('text'))
    identities=tuple((int(t.get('page-index')),int(t.get('mcid')),t.get('object-ref')) for t in leaves)
    value=''.join(decode_data_element(t) for t in leaves)
    compact=lambda s:''.join(c for c in s if not c.isspace() and unicodedata.category(c)!='Cf')
    owner=attrs.get('review-source-owner')
    if owner:
        if owner not in INLINE_GROUPS:raise ValueError('Unknown SQ MI inline owner')
        scope,page,groups=INLINE_GROUPS[owner];expected['review-source-owner']=owner
        if path!=scope or identities not in [tuple((page,i,None) for i in ids) for ids in groups]:
            raise ValueError('Invalid SQ MI inline identities')
        if owner in {'1425 0 R','1166 0 R','146 0 R','381 0 R'}:
            if value!='The Frame (LS03HA)':raise ValueError('Invalid SQ MI model condition')
        else:
            models=('R9*H','R8*H','QN1EH','QN7*H','QN8*H','QN9**H','S8*H','S9*H','M8*H','M9*H','U9***H','LS03H*')
            index=[tuple((page,i,None) for i in ids) for ids in groups].index(identities)
            if value!=models[index]:raise ValueError('Invalid SQ MI source model token')
    else:
        from tagged_pdf_extractor.domain.sq_mi_spec_text import SPEC_LTR_GROUPS
        group=next((g for g in SPEC_LTR_GROUPS.get(path,()) if g['identities']==identities),None)
        if (group is None or compact(value)!=compact(group['text'])
                or any(unicodedata.category(c)=='Cf' for c in value)):
            raise ValueError('Invalid SQ MI specification island')
        page=identities[0][0]
    if (element.tag!='span' or attrs!=expected or len(element.findall('attributes/attribute'))!=len(expected)
            or element.get('page-index')!=str(page) or element.get('language')!=('HEB','ARA')[page]
            or any(n.tag not in {'span','attributes','attribute','text'} for n in element.iter())):
        raise ValueError('Invalid SQ MI source-owned LTR marker')
    return value

def validate_sq_source_space(element):
    from tagged_pdf_extractor.infrastructure.xml_writer import decode_data_element
    attributes=element.findall('attributes/attribute')
    expected={'review-whitespace':'source-boundary','review-whitespace-source-token':'SQ MI_HEAR','review-whitespace-source-sha256':SOURCE_SHA}
    cs=[c for c in element if c.tag!='attributes']
    if (element.tag!='span' or element.get('source-structure-path')!='0/0/1/90/0/0/0/0'
            or element.get('page-index')!='0' or element.get('language')!='HEB'
            or len(attributes)!=3 or {a.get('name'):a.get('value') for a in attributes}!=expected
            or len(cs)!=4 or any(c.tag!='text' or len(c) for c in cs)
            or [(c.get('page-index'),c.get('mcid')) for c in cs]!=[('0',str(i)) for i in (1095,1094,1093,1092)]
            or tuple(decode_data_element(c) for c in cs)!=('Wi-Fi','\u200f',' ','5.925')):
        raise ValueError('Invalid SQ MI source word-space boundary')
    return ''.join(decode_data_element(c) for c in cs)
