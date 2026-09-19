"""Reviewed SQ MI sound specifications with explicit source glyph ownership."""
from collections import Counter
from dataclasses import replace
import unicodedata as ud
from tagged_pdf_extractor.domain.models import ContentFragment, Diagnostic, StructureElement
from tagged_pdf_extractor.domain.tk_arabic_source import source_inventory

SOURCE_SHA='28831342b1433d01fbc93a8276bb4de1692dbc7cc7c5996d95204a468b9bcf18'
_MODELS='U8***H/U9***H/M7*H/M8*H/M9*H/S8*H/QN7*H/QN1EH/M1EH'
_ROWS={
 '1256 0 R':(0,1,(tuple(range(471,457,-1))+tuple(range(480,471,-1)),),(_MODELS+': 20 W',)),
 '1257 0 R':(0,2,(tuple(range(488,480,-1)),),('R8*H/QN8*H: 30 W',)),
 '1258 0 R':(0,3,(tuple(range(494,488,-1)),),('S90H: 40 W',)),
 '1259 0 R':(0,4,(tuple(range(502,494,-1)),),('S95H/R9*H: 70 W',)),
 '1260 0 R':(0,5,(tuple(range(508,502,-1)),),('QN9**H: 90 W',)),
 '1261 0 R':(0,6,(tuple(range(525,517,-1)),tuple(range(516,508,-1))),('LS03HE (43"): 20 W','LS03HE (98"): 40 W')),
 '1262 0 R':(0,7,(tuple(range(533,525,-1)),),('LS03HA/LS03HW: 40 W',)),
 '328 0 R':(1,1,(tuple(range(1605,1592,-1))+tuple(range(1614,1605,-1)),),(_MODELS+': 20 واط',)),
 '330 0 R':(1,2,(tuple(range(1621,1614,-1)),),('R8*H/QN8*H: 30 واط',)),
 '331 0 R':(1,3,(tuple(range(1626,1621,-1)),),('S90H: 40 واط',)),
 '332 0 R':(1,4,(tuple(range(1633,1626,-1)),),('S95H/R9*H: 70 واط',)),
 '333 0 R':(1,5,(tuple(range(1638,1633,-1)),),('QN9**H: 90 واط',)),
 '334 0 R':(1,6,(tuple(range(1653,1646,-1)),tuple(range(1645,1638,-1))),('LS03HE (43"): 20 واط','LS03HE (98"): 40 واط')),
 '335 0 R':(1,7,(tuple(range(1660,1653,-1)),),('LS03HA/LS03HW: 40 واط',)),
}
# Writer allowlist: original paragraph path -> exact groups of original leaves.
SPEC_LTR_GROUPS={
 (0,0,1 if page==0 else 10,85,0,1,0,row):tuple(
  {'identities':tuple((page,mcid,None) for mcid in ids),'text':text}
  for ids,text in zip(groups,texts))
 for page,row,groups,texts in _ROWS.values()
}


def _visible(text):
 return ''.join(c for c in text if not c.isspace() and ud.category(c)!='Cf')


def _fragments(n):
 if isinstance(n,ContentFragment):yield n
 else:
  for c in n.children:yield from _fragments(c)


def repair_sq_mi_specs(children,diagnostics):
 runs,_=source_inventory(diagnostics)
 changes=[]
 def visit(n):
  if isinstance(n,ContentFragment):return n
  cs=tuple(visit(c) for c in n.children)
  if n.object_ref not in _ROWS:return replace(n,children=cs)
  page,row,groups,expected=_ROWS[n.object_ref]
  path=(0,0,1 if page==0 else 10,85,0,1,0,row)
  if n.source_structure_path!=path or n.language!=('HEB','ARA')[page]:
   raise ValueError('SQ MI sound specification source scope changed')
  if any(dict(getattr(c,'attributes',())).get('review-inline')=='ltr-model-token' for c in cs):
   raise ValueError('SQ MI sound specification already prepared')
  leaves=[f for c in cs for f in _fragments(c)]
  byid={f.mcid:f for f in leaves}
  comma=517 if page==0 else 1646
  required=[m for g in groups for m in g]+([comma] if len(groups)==2 else [])
  if len(byid)!=len(leaves) or set(byid)!=set(required):
   raise ValueError('SQ MI sound specification fragment topology changed')
  places={}
  for f in leaves:
   rr=runs.get((page,f.mcid),())
   if not rr or any(not r.get('glyph_boxes') or not r.get('axis_aligned') for r in rr):
    raise ValueError('SQ MI sound specification glyph geometry missing')
   boxes=[b for r in rr for b in r['glyph_boxes']]
   if max(b[1] for b in boxes)-min(b[1] for b in boxes)>.05:
    raise ValueError('SQ MI sound specification atom spans source lines')
   places[f.mcid]=(round(boxes[0][1],1),min(b[0] for b in boxes),max(b[2] for b in boxes))
   glyphs=''.join(''.join(r['glyphs']) for r in rr)
   if Counter(_visible(glyphs))!=Counter(_visible(f.text)):
    raise ValueError('SQ MI sound specification glyph inventory changed')
  # Every model sequence follows descending physical X on each original line;
  # source line wrapping keeps the next model group below the previous one.
  for ids in groups:
   positions=[places[m] for m in ids if _visible(byid[m].text)]
   if any(a[0]<b[0] or (a[0]==b[0] and a[1]<b[1]-.05) for a,b in zip(positions,positions[1:])):
    raise ValueError('SQ MI sound specification physical RTL order changed')
  updates={}
  for f in leaves:
   value=''.join(c for c in f.text if ud.category(c)!='Cf').strip()
   if not value and f.text.strip()=='':value=' '
   if value==':':value=': '
   updates[f.mcid]=value
  transfers=[]
  if len(groups)==2:
   for ids in groups:
    model,opening,size,closing,number,space,unit,*tail=ids
    if (_visible(byid[model].text)!='LS03HE' or _visible(byid[size].text) not in {'43','98'}
      or Counter(_visible(byid[opening].text))!=Counter('("')
      or Counter(_visible(byid[closing].text))!=Counter('):')):
     raise ValueError('SQ MI dimension punctuation source changed')
    # One original quote glyph is attached after its measured size digits.
    # Raw fragments retain the source owner; this diagnostic records the move.
    updates[opening]=' ('
    updates[closing]='"): '
    transfers.append({'glyph':'"','source_mcid':opening,'target_mcid':closing,
                      'size_mcid':size,'source_runs':runs[page,opening]})
   updates[comma]=', '
  def update(c):
   if not isinstance(c,ContentFragment):return replace(c,children=tuple(update(x) for x in c.children))
   value=updates[c.mcid]
   styles={s for part,s in zip(c.text_parts,c.text_styles) if part.strip() and s.font_name is not None}
   if len(styles)>1:raise ValueError('SQ MI sound fragment typography changed')
   style=next(iter(styles),None)
   return replace(c,text_parts=(value,),text_styles=(style,) if style else (),text_bboxes=(c.bbox,))
  owners={}
  for c in cs:
   ff=list(_fragments(c))
   if len(ff)!=1:raise ValueError('SQ MI sound inline owner shape changed')
   owners[ff[0].mcid]=update(c)
  arranged=[]
  for i,(ids,text) in enumerate(zip(groups,expected)):
   group=tuple(owners[m] for m in ids)
   observed=''.join(f.text for c in group for f in _fragments(c))
   if _visible(observed)!=_visible(text):raise ValueError('SQ MI sound model/value association changed')
   wrapper=StructureElement('ReviewSpan','span',page_index=page,language=n.language,
    source_structure_path=path,children=group,
    attributes=(('review-inline','ltr-model-token'),('review-source-token','SQ MI_HEAR'),('review-source-sha256',SOURCE_SHA)))
   if i:arranged.append(owners[comma])
   arranged.append(wrapper)
  before=Counter(_visible(''.join(f.text for f in leaves)))
  after=Counter(_visible(''.join(f.text for c in arranged for f in _fragments(c))))
  if before!=after:raise ValueError('SQ MI sound source character inventory changed')
  changes.append({'source_path':path,'object_ref':n.object_ref,'page_index':page,
   'source_fragment_order':[f.mcid for f in leaves],'logical_groups':groups,
   'fragment_changes':[{'page_index':page,'mcid':f.mcid,'before':f.text,'after':updates[f.mcid]} for f in leaves if f.text!=updates[f.mcid]],
   'control_removals':dict(Counter('U+%04X'%ord(c) for f in leaves for c in f.text if ud.category(c)=='Cf')),
   'visible_character_counter_before':dict(before),'visible_character_counter_after':dict(after),
   'glyph_positions':[{ 'mcid':m,'baseline':places[m][0],'x0':places[m][1],'x1':places[m][2]} for m in required],
   'punctuation_glyph_transfers':transfers,'visible_character_inventory_preserved':True})
  return replace(n,children=tuple(arranged),display_direction=None)
 result=tuple(visit(c) for c in children)
 if len(changes)!=14:raise ValueError('SQ MI sound source row coverage changed')
 return result,Diagnostic('warning','sq_mi_sound_source_order',
  'Sound model/value associations follow measured RTL source order; original quote owners retained in audit.',
  {'sha256':SOURCE_SHA,'changes':changes})
