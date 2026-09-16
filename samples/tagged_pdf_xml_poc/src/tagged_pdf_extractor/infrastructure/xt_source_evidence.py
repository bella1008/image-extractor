"""XT source operations, with glyph identity verified against embedded outlines.

The subset fonts have broken ToUnicode clusters and broken ActualText. Their
CIDToGIDMap is Identity. All observed outlines matched Tahoma's original glyph
IDs byte-for-byte; cmap supplied Unicode for base glyphs. Contextual tone glyphs
1143–1147/1183 were inspected as glyph outlines (not translated words).
Only the two pinned embedded subsets and the pinned PDF are authorized.
"""
from collections import defaultdict
from dataclasses import replace
from hashlib import sha256
from pypdf import PdfReader
from tagged_pdf_extractor.domain.models import Diagnostic
from tagged_pdf_extractor.domain.xt_sheet import SOURCE_SHA, xt_scope
from tagged_pdf_extractor.infrastructure.africa_glyphs import RtlGlyphObserver

_FONTS = {
    'JUTTYV+Tahoma-Bold': '441f54ea667df1db75fd29f017fdce1dbdc2830f7af94f29283d13b0a9963bea',
    'TRRBIB+Tahoma': '067b77a5ed18b8756efe37d1432b6d13bef0374b0210675c5979ad7109070c09',
}
_GLYPHS = {
    1076:'ก',1077:'ข',1079:'ค',1081:'ฆ',1082:'ง',1083:'จ',1084:'ฉ',1085:'ช',1086:'ซ',
    1088:'ญ',1090:'ฏ',1091:'ฐ',1092:'ฑ',1094:'ณ',1095:'ด',1096:'ต',1097:'ถ',1098:'ท',
    1099:'ธ',1100:'น',1101:'บ',1102:'ป',1103:'ผ',1104:'ฝ',1105:'พ',1106:'ฟ',1107:'ภ',
    1108:'ม',1109:'ย',1110:'ร',1112:'ล',1114:'ว',1115:'ศ',1116:'ษ',1117:'ส',1118:'ห',
    1120:'อ',1121:'ฮ',1123:'ะ',1124:'ั',1125:'า',1127:'ิ',1128:'ี',1129:'ึ',1130:'ื',
    1131:'ุ',1132:'ู',1135:'เ',1136:'แ',1137:'โ',1138:'ใ',1139:'ไ',1141:'ๆ',1142:'็',
    1143:'่',1144:'้',1145:'๊',1146:'๋',1147:'์',1148:'ํ',1173:'่',1174:'้',1175:'๊',
    1177:'์',1183:'้',
}

def add_xt_source_evidence(document, profile):
    if not xt_scope(profile):
        return document
    digest = sha256(document.source_path.read_bytes()).hexdigest()
    if digest != SOURCE_SHA:
        raise ValueError('XT source revision needs review')
    reader = PdfReader(document.source_path)
    verified = set()
    records = []
    for page_index, page in enumerate(reader.pages):
        for font in page['/Resources']['/Font'].values():
            font = font.get_object()
            name = str(font['/BaseFont']).lstrip('/')
            if name not in _FONTS:
                continue
            desc = font['/DescendantFonts'][0].get_object()
            data = desc['/FontDescriptor']['/FontFile2'].get_data()
            if desc.get('/CIDToGIDMap') != '/Identity' or sha256(data).hexdigest() != _FONTS[name]:
                raise ValueError('XT embedded glyph font needs review')
            verified.add(name)
        grouped = defaultdict(list)
        for line in RtlGlyphObserver().collect(page):
            for run in line['runs']:
                value = dict(run)
                name = run['font_name'].lstrip('/')
                if page_index == 1 and name in _FONTS:
                    if name not in verified or not run['raw_hex']:
                        raise ValueError('XT glyph operation needs review')
                    raw = bytes.fromhex(run['raw_hex'])
                    if len(raw) % 2 or len(raw) // 2 != len(run['glyphs']):
                        raise ValueError('XT glyph code width needs review')
                    cids = [int.from_bytes(raw[i:i+2], 'big') for i in range(0, len(raw), 2)]
                    if any(cid >= 1076 and cid not in _GLYPHS for cid in cids):
                        raise ValueError('XT unseen Thai glyph needs review')
                    value['verified_glyphs'] = [_GLYPHS.get(cid, glyph) for cid, glyph in zip(cids, run['glyphs'])]
                    value['source_cids'] = cids
                else:
                    value['verified_glyphs'] = run['glyphs']
                grouped[run['mcid']].append(value)
        records.extend({'page_index': page_index, 'mcid': mcid, 'runs': runs} for mcid, runs in grouped.items())
    if verified != set(_FONTS):
        raise ValueError('XT glyph evidence font coverage changed')
    return replace(document, source_sha256=digest, diagnostics=(*document.diagnostics,
        Diagnostic('warning', 'xt_source_operations',
                   'Observed source glyph codes; Thai Unicode verified from embedded glyph outlines.',
                   {'sha256': digest, 'font_sha256': _FONTS, 'fragments': records})))
