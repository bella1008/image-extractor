"""Fail-closed evidence for the reviewed ZW A3 vector Form and URI OBJRs.

This is not a general OBJR/Form extractor. Original diagnostics remain embedded
in resolved evidence, and raw structure/text are never rewritten here.
"""
from dataclasses import replace
from hashlib import sha256
from pypdf import PdfReader
from pypdf.generic import ContentStream
from tagged_pdf_extractor.domain.models import Diagnostic

SOURCE_SHA256='37e8ef8c16b250463c4a57f5efc199a0f65bd8f9a1e10eacc5562b727f82e99f'
FORM_SHA256='287a6030adaa733fe6ed5c7711dd899c1e0c7129766cb3f196849f2a813dbba8'

def _ref(value):
    value=getattr(value,'indirect_reference',value)
    return (value.idnum,value.generation) if hasattr(value,'idnum') else None

def _walk(nodes):
    for node in nodes:
        yield node
        yield from _walk(getattr(node,'children',()))

def _evidence(reader,document):
    if len(reader.pages)!=2:return None
    page=reader.pages[1]
    form=page['/Resources']['/XObject']['/Fm0']
    if _ref(form)!=(29,0) or form.get('/Subtype')!='/Form':return None
    if sha256(form.get_data()).hexdigest()!=FORM_SHA256:return None
    if set(form['/Resources'])!={'/ExtGState'}:return None
    operations=ContentStream(form,reader).operations
    allowed={b'q',b'Q',b're',b'W',b'n',b'cm',b'K',b'w',b'M',b'j',b'J',b'd',b'ri',b'gs',b'm',b'l',b'h',b'S'}
    if any(op not in allowed for _,op in operations):return None
    link=reader.get_object(57)
    if link.get('/S')!='/Link' or _ref(link.get('/Pg'))!=_ref(page):return None
    kids=link['/K']
    if len(kids)!=4 or list(kids[2:])!=[918,919]:return None
    nodes=[n for n in _walk(document.children) if getattr(n,'object_ref',None)=='57 0 R']
    if len(nodes)!=1:return None
    fragments=nodes[0].children
    if [(getattr(f,'page_index',None),getattr(f,'mcid',None),getattr(f,'text',None)) for f in fragments]!=[(1,918,'www.'),(1,919,'\nsamsung.com')]:return None
    annots={_ref(x) for x in page['/Annots']}
    evidence=[{'form_ref':'29 0 R','page_index':1,'resource_name':'/Fm0',
        'decoded_stream_sha256':FORM_SHA256,'text_operator_count':0,
        'operation_count':len(operations),'operators':sorted({op.decode('ascii') for _,op in operations}),
        'bbox':list(form['/BBox']),'description':'Vector wall outline behind Ethernet cable; no text operators or font/nested-XObject resources.'}]
    for kid,number,action_number,rect in zip(kids[:2],(31,32),(33,34),([662.008,1091.22,703.141,1083.22],[798.008,1103.22,816.156,1095.22])):
        if kid.get('/Type')!='/OBJR' or _ref(kid.get('/Obj'))!=(number,0):return None
        annotation=kid['/Obj'];action=annotation['/A']
        if (number,0) not in annots or annotation.get('/Type')!='/Annot' or annotation.get('/Subtype')!='/Link':return None
        if '/AP' in annotation or '/Contents' in annotation:return None
        if list(annotation['/Rect'])!=rect or list(annotation['/Border'])!=[0,0,0]:return None
        if annotation['/BS']['/W']!=0 or _ref(action)!=(action_number,0):return None
        if action.get('/S')!='/URI' or action.get('/URI')!='http://www.samsung.com':return None
        evidence.append({'annotation_ref':f'{number} 0 R','action_ref':f'{action_number} 0 R',
            'page_index':1,'link_structure_ref':'57 0 R','uri':str(action['/URI']),
            'rect':rect,'text_mcids':[918,919],'existing_text_parts':['www.','\nsamsung.com'],
            'description':'Zero-border URI annotation; visible URL already retained by sibling MCIDs.'})
    return evidence

def add_zw_object_evidence(document,profile):
    if (profile.source_token,profile.doc_type,profile.languages,profile.language_count)!=('ZW_TPE','A3',('TPE',),1):return document
    if sha256(document.source_path.read_bytes()).hexdigest()!=SOURCE_SHA256:return document
    expected=[('tagged_form_xobject_unsupported',{'page_index':1,'operand_repr':"'/Fm0'"}),
              ('unsupported_objr',{'page_index':1,'object_ref':None}),
              ('unsupported_objr',{'page_index':1,'object_ref':None})]
    selected=[d for d in document.diagnostics if d.code in {'tagged_form_xobject_unsupported','unsupported_objr'}]
    if [(d.code,d.context) for d in selected]!=expected:return document
    try:
        evidence=_evidence(PdfReader(document.source_path),document)
    except (KeyError,TypeError,ValueError,AttributeError,IndexError):
        return document
    if evidence is None:return document
    replacements={id(d):Diagnostic('warning',code,'Verified source object resolved without dropping text.',
        {'source_sha256':SOURCE_SHA256,'original_diagnostic':{'severity':d.severity,'code':d.code,'message':d.message,'context':dict(d.context)},'evidence':item})
        for d,code,item in zip(selected,('zw_vector_form_resolved','zw_link_objr_resolved','zw_link_objr_resolved'),evidence)}
    return replace(document,source_sha256=SOURCE_SHA256,diagnostics=tuple(replacements.get(id(d),d) for d in document.diagnostics))
