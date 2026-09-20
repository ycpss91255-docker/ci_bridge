"""三階段 draw.io 審查工具鏈 ─ 第 1 步：抽取。
用法: python3 extract_pages.py <file.drawio> <outdir> [page_id ...]
每頁輸出 <outdir>/<id>.json（機器用）與 <outdir>/<id>.md（人讀摘要）；另寫 <outdir>/pages.json（頁 id→頁名清單）。
只讀 .drawio，不寫回。

JSON 結構：
  page   {id, name}
  nodes  [{id, kind, cls, text, fill, stroke, shape, parent, x, y, w, h, v2, legend}]
         kind: step|decision|end_ok|end_orange|end_red|entry|file|rule|header|note|term|other
         cls : 樣式類別（依 disc_v1_b.py 的常數命名）：W12 白步驟／SUB 藍步驟／IMG 紫 image／D12 菱形／G12 綠橢圓／R12 紅橢圓／
               O12 橙橢圓／ENTRY 白虛線橢圓／F12 虛線檔案框／FGRP 檔案容器／PRE 逐字框／RULE 橙規則框／INV 紅粗框不變量／
               HDR 灰表頭／NOTE 便條／PEND 黃便條／TERM_K／TERM_V 名詞表／CELL 一般表格格／BAND 分組（swimlane）／
               LEGEND 圖例項／TEXT 純文字／TITLE 頁標題／TAG（v2 小綠標，不列入 nodes，改記在本體的 v2=true）
         x,y  = 絕對座標（沿 parent 鏈加總）；v2 = 右上有綠色 v2 標籤；legend = 是圖例區的格子
  edges  [{id, source, target, label, exit, entry, dashed, points}]   exit/entry = [x,y] 比例（style 的 exitX/exitY…），沒有就 null
  terms  [{name, text}]   名詞表：id 形如 <prefix>_tk<i>（名詞）／<prefix>_tv<i>（說明）配對；表頭是 <prefix>_th「本頁名詞」
  xrefs  [{id, ref, kind}] 文字含「來自「X」頁」「續「X」頁」「見「X」頁」「（「X」頁）」抽出的頁名 X（kind = 來自/續/見/其他）
  fills  頁內出現的 fillColor 集合（不含圖例、不含 none）
  legend_fills 圖例區的 fillColor 集合
"""
import re, html, json, os, sys

# ---------- 顏色常數（gen57.py / disc_v1_b.py） ----------
GREEN, RED, ORANGE, YELLOW, PURPLE, GREY, NEUTRAL = "#d5e8d4", "#f8cecc", "#ffe6cc", "#FFF4C3", "#e1d5e7", "#CCCCCC", "#f5f5f5"
BLUE = "#dae8fc"; HDR_FILL = "#e6e6e6"; TAG_FILL = "#00b050"

XREF_RE = re.compile(r'(來自|續|見|回|→)?\s*「([^」]{1,60})」\s*頁')

def load(path):
    x = open(path, encoding='utf-8').read()
    for m in re.finditer(r'<diagram id="([^"]+)" name="([^"]*)">(.*?)</diagram>', x, re.S):
        pid, name, body = m.groups()
        cells = {}; order = []
        for c in re.finditer(r'<mxCell id="([^"]+)"([^>]*?)(?:/>|>(.*?)</mxCell>)', body, re.S):
            cid, attrs, inner = c.group(1), c.group(2) or "", c.group(3) or ""
            a = dict(re.findall(r'(\w+)="((?:[^"\\]|\\.)*)"', attrs))
            g = re.search(r'<mxGeometry ([^>]*)/?>', inner)
            geo = dict(re.findall(r'(\w+)="([^"]*)"', g.group(1))) if g else {}
            style = html.unescape(a.get('style', ''))
            st = dict(kv.split('=', 1) for kv in style.split(';') if '=' in kv)
            head = style.split(';')[0]
            pts = [(float(px), float(py)) for px, py in re.findall(r'<mxPoint x="([\d.-]+)" y="([\d.-]+)"(?! as="(?:offset|sourcePoint|targetPoint)")', inner)]
            cells[cid] = dict(id=cid, attrs=a, style=style, st=st, head=head, geo=geo, points=pts, raw_value=a.get('value', ''))
            order.append(cid)
        yield pid, html.unescape(name), cells, order

def clean_text(raw):
    """XML 屬性值 → 畫面上的字：XML 解跳脫一次得到 HTML；<br>→⏎；去標籤；再解一次 HTML 實體（&lt;repo&gt; → <repo>）。"""
    v = html.unescape(raw)
    v = re.sub(r'<br\s*/?>', '⏎', v, flags=re.I)
    v = re.sub(r'</?(div|p)[^>]*>', '⏎', v, flags=re.I)
    v = re.sub(r'<[^>]+>', '', v)
    v = html.unescape(v)
    v = v.replace(' ', ' ')
    v = re.sub(r'⏎{2,}', '⏎', v).strip('⏎ ')
    return v

def absbox(cells, cid):
    c = cells[cid]; g = c['geo']
    x0, y0, w, h = float(g.get('x', 0)), float(g.get('y', 0)), float(g.get('width', 0)), float(g.get('height', 0))
    p = c['attrs'].get('parent')
    while p and p not in ('0', '1') and p in cells:
        pg = cells[p]['geo']; x0 += float(pg.get('x', 0)); y0 += float(pg.get('y', 0)); p = cells[p]['attrs'].get('parent')
    return round(x0), round(y0), round(w), round(h)

def is_legend_id(cid):
    return bool(re.search(r'_lg\d+$|_lgt$|_lgx_', cid))

def classify(c, text):
    """回傳 (kind, cls)。順序：先看形狀／id 型態，再看顏色。"""
    cid = c['id']; st = c['st']; head = c['head']; fill = st.get('fillColor', '-'); stroke = st.get('strokeColor', '-')
    dashed = st.get('dashed') == '1'; bold = st.get('fontStyle') == '1'
    if fill == TAG_FILL: return 'other', 'TAG'
    if is_legend_id(cid): return 'other', 'LEGEND'
    if head == 'text' or head.startswith('text;'):
        if cid == 'title': return 'other', 'TITLE'
        return 'other', 'TEXT'
    if st.get('shape') == 'note' or head == 'shape=note':
        return 'note', ('PEND' if fill == '#fff2cc' else 'NOTE')
    if head == 'swimlane': return 'other', 'BAND'
    if head == 'rhombus' or st.get('shape') == 'rhombus': return 'decision', 'D12'
    if head == 'ellipse' or st.get('shape') == 'ellipse':
        if fill == GREEN: return 'end_ok', 'G12'
        if fill == RED: return 'end_red', 'R12'
        if fill == ORANGE: return 'end_orange', 'O12'
        if fill == '#ffffff' and dashed: return 'entry', 'ENTRY'
        return 'other', 'ELLIPSE'
    if re.search(r'_tk\d+$', cid): return 'term', 'TERM_K'
    if re.search(r'_tv\d+$', cid): return 'term', 'TERM_V'
    if cid.endswith('_th'): return 'header', 'TERM_H'
    if fill == HDR_FILL: return 'header', 'HDR'
    if fill == ORANGE and stroke == '#d79b00': return 'rule', 'RULE'
    if fill == '#ffffff' and stroke == '#b85450': return 'rule', 'INV'
    if fill == BLUE and stroke == '#6c8ebf': return 'step', 'SUB'
    if fill == PURPLE and stroke == '#9673a6': return 'other', 'IMG'
    if stroke == '#666666': return 'file', 'PRE'
    if stroke.startswith('light-dark'):
        if dashed: return 'file', ('FGRP' if bold else 'F12')
        if fill == '#ffffff': return 'step', 'W12'
        return 'other', 'LEAF'
    if dashed: return 'file', 'FILEBOX'
    if stroke == '#999999': return 'other', 'CELL'
    return 'other', 'RECT'

def extract(pid, name, cells, order):
    nodes = []; edges = []; terms_k = {}; terms_v = {}; xrefs = []; fills = set(); legend_fills = set()
    tagged = {cid[:-3] for cid in cells if cid.endswith('_v2') and cells[cid]['st'].get('fillColor') == TAG_FILL}
    for cid in order:
        c = cells[cid]; a = c['attrs']
        if a.get('vertex') == '1':
            text = clean_text(c['raw_value'])
            kind, cls = classify(c, text)
            if cls == 'TAG': continue
            x, y, w, h = absbox(cells, cid)
            fill = c['st'].get('fillColor', '-')
            legend = cls == 'LEGEND'
            n = dict(id=cid, kind=kind, cls=cls, text=text, fill=fill, stroke=c['st'].get('strokeColor', '-'), shape=c['head'],
                     parent=a.get('parent'), x=x, y=y, w=w, h=h, v2=cid in tagged, legend=legend)
            nodes.append(n)
            if legend: legend_fills.add(fill)
            elif fill not in ('none', '-', ''): fills.add(fill)
            m = re.search(r'_tk(\d+)$', cid)
            if m: terms_k[(cid[:m.start()], int(m.group(1)))] = text
            m = re.search(r'_tv(\d+)$', cid)
            if m: terms_v[(cid[:m.start()], int(m.group(1)))] = text
            for mm in XREF_RE.finditer(text):
                xrefs.append(dict(id=cid, ref=mm.group(2).strip(), kind=mm.group(1) or '其他'))
        elif a.get('edge') == '1':
            st = c['st']
            ex = [float(st['exitX']), float(st['exitY'])] if 'exitX' in st and 'exitY' in st else None
            en = [float(st['entryX']), float(st['entryY'])] if 'entryX' in st and 'entryY' in st else None
            label = clean_text(c['raw_value'])
            edges.append(dict(id=cid, source=a.get('source'), target=a.get('target'), label=label, exit=ex, entry=en,
                              dashed=st.get('dashed') == '1', points=c['points']))
            for mm in XREF_RE.finditer(label):
                xrefs.append(dict(id=cid, ref=mm.group(2).strip(), kind=mm.group(1) or '其他'))
    terms = [dict(name=terms_k[k], text=terms_v.get(k, '')) for k in sorted(terms_k, key=lambda k: (k[0], k[1]))]
    # 名詞表也可能有 tv 沒 tk（不太會發生）→ 補上
    for k in sorted(set(terms_v) - set(terms_k)): terms.append(dict(name='', text=terms_v[k]))
    return dict(page=dict(id=pid, name=name), nodes=nodes, edges=edges, terms=terms, xrefs=xrefs,
                fills=sorted(fills), legend_fills=sorted(legend_fills))

def to_md(d):
    byid = {n['id']: n for n in d['nodes']}
    def short(cid, n=30):
        if cid is None: return '(無)'
        t = byid[cid]['text'] if cid in byid else '?'
        t = t.replace('⏎', ' ')
        return f"{cid}({t[:n]}{'…' if len(t) > n else ''})"
    L = [f"# {d['page']['id']}  {d['page']['name']}", "",
         f"nodes {len(d['nodes'])}（不含 v2 小標）／edges {len(d['edges'])}／terms {len(d['terms'])}／xrefs {len(d['xrefs'])}", "",
         "## nodes"]
    for n in d['nodes']:
        flag = (' [v2]' if n['v2'] else '') + (' [legend]' if n['legend'] else '')
        L.append(f"- [{n['kind']}/{n['cls']}] {n['id']}{flag}: {n['text']}")
    L += ["", "## edges"]
    for e in d['edges']:
        lab = e['label'].replace('⏎', ' ') or '(無標籤)'
        dash = ' (虛線)' if e['dashed'] else ''
        L.append(f"- {e['id']}: {short(e['source'])} --{lab}--> {short(e['target'])}{dash}")
    L += ["", "## terms"]
    for t in d['terms']: L.append(f"- {t['name']}: {t['text']}")
    L += ["", "## xrefs"]
    for x in d['xrefs']: L.append(f"- {x['id']}: {x['kind']}「{x['ref']}」頁")
    L += ["", f"## fills（非圖例）: {' '.join(d['fills'])}", f"## legend_fills: {' '.join(d['legend_fills'])}", ""]
    return "\n".join(L)

def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(2)
    path, outdir = sys.argv[1], sys.argv[2]; want = set(sys.argv[3:])
    os.makedirs(outdir, exist_ok=True)
    pages = []
    for pid, name, cells, order in load(path):
        pages.append(dict(id=pid, name=name))
        if want and pid not in want: continue
        d = extract(pid, name, cells, order)
        with open(os.path.join(outdir, f"{pid}.json"), 'w', encoding='utf-8') as f: json.dump(d, f, ensure_ascii=False, indent=1)
        with open(os.path.join(outdir, f"{pid}.md"), 'w', encoding='utf-8') as f: f.write(to_md(d))
        print(f"{pid:10s} nodes={len(d['nodes']):4d} edges={len(d['edges']):3d} terms={len(d['terms']):2d} xrefs={len(d['xrefs']):2d}  {name}")
    with open(os.path.join(outdir, "pages.json"), 'w', encoding='utf-8') as f: json.dump(pages, f, ensure_ascii=False, indent=1)
    print(f"共 {len(pages)} 頁 → {outdir}/")

if __name__ == '__main__':
    main()
