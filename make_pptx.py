#!/usr/bin/env python3
"""AI Knowledge株式会社 — PowerPoint 完全版（最適化版）"""

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.chart.data import ChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.oxml.ns import qn
from lxml import etree

# ── Colors ──────────────────────────────────────────────
NAVY    = RGBColor(0x0D, 0x2B, 0x5A)
NAVY2   = RGBColor(0x1B, 0x3A, 0x6B)
BLUE    = RGBColor(0x25, 0x58, 0xD4)
BLUEL   = RGBColor(0x4A, 0x7C, 0xE8)
ORANGE  = RGBColor(0xE8, 0x82, 0x0C)
ORANGEL = RGBColor(0xF4, 0xA6, 0x22)
GREEN   = RGBColor(0x1A, 0x8C, 0x5A)
WHITE   = RGBColor(0xFF, 0xFF, 0xFF)
GRAY    = RGBColor(0x6B, 0x72, 0x80)
DARK    = RGBColor(0x1F, 0x29, 0x37)
BG      = RGBColor(0xF0, 0xF4, 0xFB)
RED     = RGBColor(0xDC, 0x26, 0x26)
AMBER   = RGBColor(0xD9, 0x74, 0x06)
LGREEN  = RGBColor(0xD1, 0xFA, 0xE5)
LRED    = RGBColor(0xFE, 0xE2, 0xE2)
LAMBER  = RGBColor(0xFE, 0xF3, 0xC7)
LBLUE   = RGBColor(0xEF, 0xF6, 0xFF)

# ── Layout ─────────────────────────────────────────────
SW   = Inches(13.33)
SH   = Inches(7.5)
HDRH = Inches(0.65)
M    = Inches(0.4)
BX   = M
BY   = HDRH + Inches(0.18)
BW   = SW - M * 2
BH   = SH - BY - Inches(0.25)

# ── Anim ID ────────────────────────────────────────────
_aid = [1000]
def nid(): _aid[0] += 1; return str(_aid[0])

# ════════════════════════════════════════════════════════
#  LOW-LEVEL HELPERS
# ════════════════════════════════════════════════════════

def new_slide(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])

def set_bg(slide, color):
    f = slide.background.fill; f.solid(); f.fore_color.rgb = color

def shape(slide, x, y, w, h, fill=None, line=None, lw=0.75, rnd=False):
    sh = slide.shapes.add_shape(5 if rnd else 1, x, y, w, h)
    sh.fill.solid() if fill else sh.fill.background()
    if fill: sh.fill.fore_color.rgb = fill
    sh.line.fill.background()
    if line: sh.line.color.rgb = line; sh.line.width = Pt(lw)
    return sh

def tbox(slide, text, x, y, w, h, sz=10, bold=False,
         color=DARK, align=PP_ALIGN.LEFT, italic=False):
    """Plain textbox – handles \\n as paragraph breaks."""
    tx = slide.shapes.add_textbox(x, y, w, h)
    tf = tx.text_frame; tf.word_wrap = True
    lines = str(text).split('\n')
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run(); r.text = line
        r.font.size = Pt(sz); r.font.bold = bold; r.font.italic = italic
        if color: r.font.color.rgb = color
    return tx

# ════════════════════════════════════════════════════════
#  COMPONENT HELPERS  (all text lives inside shape.text_frame)
# ════════════════════════════════════════════════════════

def _tf_setup(sh, ml=0.1, mt=0.1, mr=0.1, mb=0.08, wrap=True, anchor=None):
    tf = sh.text_frame
    tf.word_wrap = wrap
    tf.margin_left   = Inches(ml)
    tf.margin_right  = Inches(mr)
    tf.margin_top    = Inches(mt)
    tf.margin_bottom = Inches(mb)
    if anchor: tf.vertical_anchor = anchor
    return tf

def _para(tf, text, sz, bold=False, color=WHITE, align=PP_ALIGN.LEFT, space_before=0):
    p = tf.add_paragraph() if tf.paragraphs else tf.paragraphs[0]
    # always call add_paragraph for lines after the first
    p.alignment = align
    if space_before: p.space_before = Pt(space_before)
    r = p.add_run(); r.text = str(text)
    r.font.size = Pt(sz); r.font.bold = bold
    if color: r.font.color.rgb = color
    return p

def kpi_block(slide, val, lbl, x, y, w, h, fill):
    """KPI colored box – everything inside shape.text_frame."""
    sh = shape(slide, x, y, w, h, fill=fill, rnd=True)
    tf = _tf_setup(sh, ml=0.06, mt=0.08, mr=0.06, mb=0.06,
                   anchor=MSO_ANCHOR.MIDDLE)
    # first paragraph
    p1 = tf.paragraphs[0]; p1.alignment = PP_ALIGN.CENTER
    r1 = p1.add_run(); r1.text = val
    r1.font.size = Pt(18); r1.font.bold = True; r1.font.color.rgb = WHITE
    # label
    p2 = tf.add_paragraph(); p2.alignment = PP_ALIGN.CENTER
    p2.space_before = Pt(3)
    r2 = p2.add_run(); r2.text = lbl
    r2.font.size = Pt(7); r2.font.color.rgb = RGBColor(0xCC,0xD8,0xFF)
    return sh

def white_card(slide, title, body, x, y, w, h,
               tc=None, icon=None):
    """White card with blue title + gray body – all inside shape.text_frame."""
    sh = shape(slide, x, y, w, h, fill=WHITE, rnd=True)
    # colored top bar
    if tc:
        bar = shape(slide, x, y, w, Pt(3.5), fill=tc)
    tf = _tf_setup(sh, ml=0.12, mt=0.14, mr=0.12, mb=0.08)
    # title
    p1 = tf.paragraphs[0]
    r1 = p1.add_run()
    r1.text = (icon + ' ' if icon else '') + title
    r1.font.size = Pt(10); r1.font.bold = True; r1.font.color.rgb = BLUE
    # spacer
    p2 = tf.add_paragraph(); p2.space_after = Pt(1)
    # body – handle \n
    for i, line in enumerate(body.split('\n')):
        p = tf.add_paragraph()
        r = p.add_run(); r.text = line
        r.font.size = Pt(8); r.font.color.rgb = GRAY
    return sh

def colored_card(slide, lines, x, y, w, h, fill,
                 sizes=None, bolds=None, colors=None,
                 aligns=None, anchor=MSO_ANCHOR.TOP, ml=0.12):
    """Colored card with custom per-line text."""
    sh = shape(slide, x, y, w, h, fill=fill, rnd=True)
    tf = _tf_setup(sh, ml=ml, mt=0.1, mr=0.12, mb=0.08, anchor=anchor)
    for i, line in enumerate(lines):
        sz    = sizes[i]  if sizes  else 10
        bold  = bolds[i]  if bolds  else False
        col   = colors[i] if colors else WHITE
        al    = aligns[i] if aligns else PP_ALIGN.LEFT
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
            if i == 1: p.space_before = Pt(4)
        p.alignment = al
        r = p.add_run(); r.text = str(line)
        r.font.size = Pt(sz); r.font.bold = bold
        if col: r.font.color.rgb = col
    return sh

def callout_box(slide, title, body, x, y, w, h):
    sh = shape(slide, x, y, w, h,
               fill=RGBColor(0xFF,0xF8,0xF0),
               line=ORANGEL, lw=0.75)
    tf = _tf_setup(sh, ml=0.14, mt=0.1, mr=0.14, mb=0.08)
    p1 = tf.paragraphs[0]
    r1 = p1.add_run(); r1.text = title
    r1.font.size = Pt(10); r1.font.bold = True; r1.font.color.rgb = ORANGE
    p2 = tf.add_paragraph(); p2.space_before = Pt(3)
    for line in body.split('\n'):
        p = tf.add_paragraph()
        r = p.add_run(); r.text = line
        r.font.size = Pt(8); r.font.color.rgb = DARK
    return sh

def note_strip(slide, text, x, y, w, h):
    sh = shape(slide, x, y, w, h, fill=LBLUE, line=BLUE, lw=0.5)
    tf = _tf_setup(sh, ml=0.1, mt=0.06, mr=0.1, mb=0.06,
                   anchor=MSO_ANCHOR.MIDDLE)
    p = tf.paragraphs[0]
    r = p.add_run(); r.text = text
    r.font.size = Pt(7); r.font.color.rgb = NAVY2
    return sh

def add_header(slide, title, num_str, nc=None):
    shape(slide, 0, 0, SW, HDRH, fill=NAVY)
    # badge
    bd = shape(slide, Inches(0.28), Inches(0.14), Inches(0.37), Inches(0.37),
               fill=(nc or ORANGE), rnd=True)
    tf = _tf_setup(bd, ml=0.02, mt=0.02, mr=0.02, mb=0.02,
                   anchor=MSO_ANCHOR.MIDDLE)
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = num_str
    r.font.size = Pt(10); r.font.bold = True; r.font.color.rgb = WHITE
    # title
    tbox(slide, title, Inches(0.76), Inches(0.1), Inches(12.2), Inches(0.48),
         sz=18, bold=True, color=WHITE)

# ════════════════════════════════════════════════════════
#  TABLE
# ════════════════════════════════════════════════════════

def make_table(slide, headers, rows, x, y, w, h,
               col_w=None, hdr_fill=NAVY, highlight_last=False):
    nc = len(headers); nr = len(rows) + 1
    tbl_shape = slide.shapes.add_table(nr, nc, x, y, w, h)
    tbl = tbl_shape.table
    if col_w:
        for i, cw in enumerate(col_w):
            tbl.columns[i].width = cw

    def fill_cell(cell, val, bg=None, fc=DARK, bold=False, sz=8,
                  align=PP_ALIGN.LEFT):
        # unpack tuple if needed
        if isinstance(val, tuple):
            fc   = val[1] if len(val) > 1 else fc
            bold = val[2] if len(val) > 2 else bold
            val  = val[0]
        cell.text = str(val)
        tf = cell.text_frame; tf.word_wrap = True
        p  = tf.paragraphs[0]; p.alignment = align
        if p.runs:
            r = p.runs[0]
            r.font.size = Pt(sz); r.font.bold = bold; r.font.color.rgb = fc
        if bg:
            cell.fill.solid(); cell.fill.fore_color.rgb = bg

    # header row
    for j, h_txt in enumerate(headers):
        fill_cell(tbl.cell(0, j), h_txt, bg=hdr_fill, fc=WHITE,
                  bold=True, sz=9, align=PP_ALIGN.CENTER)

    alt = RGBColor(0xF5, 0xF7, 0xFF)
    hl  = RGBColor(0xFF, 0xF5, 0xE6)
    for i, row in enumerate(rows):
        is_last = (i == len(rows) - 1)
        bg_row = hl if (highlight_last and is_last) else (alt if i % 2 else WHITE)
        for j, cell_val in enumerate(row):
            fill_cell(tbl.cell(i+1, j), cell_val, bg=bg_row, sz=8)

# ════════════════════════════════════════════════════════
#  CHART HELPER
# ════════════════════════════════════════════════════════

def add_chart(slide, ctype, cats, series, x, y, w, h, legend=False, legend_pos=XL_LEGEND_POSITION.BOTTOM):
    """series = [(name, values, RGBColor or None), ...]"""
    cd = ChartData(); cd.categories = cats
    for name, vals, _ in series: cd.add_series(name, vals)
    gf  = slide.shapes.add_chart(ctype, x, y, w, h, cd)
    ch  = gf.chart
    ch.has_title  = False
    ch.has_legend = legend
    if legend:
        ch.legend.position         = legend_pos
        ch.legend.include_in_layout = False
    try:
        for i, (_, _, col) in enumerate(series):
            if col and i < len(ch.series):
                ch.series[i].format.fill.solid()
                ch.series[i].format.fill.fore_color.rgb = col
        ch.value_axis.tick_labels.font.size    = Pt(8)
        ch.category_axis.tick_labels.font.size = Pt(8)
    except Exception:
        pass
    return ch

# ════════════════════════════════════════════════════════
#  TRANSITIONS & ANIMATIONS
# ════════════════════════════════════════════════════════

def fade_trans(slide, dur=600):
    t = slide._element.find(qn('p:transition'))
    if t is not None: slide._element.remove(t)
    xml = (f'<p:transition xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
           f' dur="{dur}"><p:fade/></p:transition>')
    slide._element.append(etree.fromstring(xml))

def entrance_anim(slide, shapes, step=180, base=0, dur=500):
    """Staggered fade-in on slide load for a list of shapes."""
    if not shapes: return
    parts = []
    for i, sh in enumerate(shapes):
        d = base + i * step
        i1,i2,i3,i4,i5 = nid(),nid(),nid(),nid(),nid()
        sid = sh.shape_id
        parts.append(f'''<p:par xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cTn id="{i1}" fill="hold"><p:stCondLst><p:cond delay="{d}"/></p:stCondLst>
  <p:childTnLst><p:par><p:cTn id="{i2}" fill="hold">
    <p:stCondLst><p:cond delay="0"/></p:stCondLst>
    <p:childTnLst><p:par>
      <p:cTn id="{i3}" presetID="10" presetClass="entr" presetSubtype="0"
             fill="hold" grpId="0" nodeType="withEffect" dur="{dur}">
        <p:stCondLst><p:cond delay="0"/></p:stCondLst>
        <p:childTnLst>
          <p:set><p:cBhvr><p:cTn id="{i4}" dur="1" fill="hold"/>
            <p:tgtEl><p:spTgt spid="{sid}"/></p:tgtEl>
            <p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>
          </p:cBhvr><p:to><p:strVal val="visible"/></p:to></p:set>
          <p:animEffect transition="in" filter="fade">
            <p:cBhvr><p:cTn id="{i5}" dur="{dur}"/>
              <p:tgtEl><p:spTgt spid="{sid}"/></p:tgtEl>
            </p:cBhvr></p:animEffect>
        </p:childTnLst></p:cTn>
    </p:par></p:childTnLst>
  </p:cTn></p:par></p:childTnLst></p:cTn>
</p:par>''')
    r1,r2,r3 = nid(),nid(),nid()
    xml = f'''<p:timing xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:tnLst><p:par><p:cTn id="{r1}" dur="indefinite" restart="whenNotActive" nodeType="tmRoot">
    <p:childTnLst><p:seq concurrent="1" nextAc="seek">
      <p:cTn id="{r2}" dur="indefinite" nodeType="mainSeq">
        <p:childTnLst><p:par>
          <p:cTn id="{r3}" fill="hold">
            <p:stCondLst><p:cond delay="0"/></p:stCondLst>
            <p:childTnLst>{''.join(parts)}</p:childTnLst>
          </p:cTn>
        </p:par></p:childTnLst>
      </p:cTn>
      <p:prevCondLst><p:cond evt="onPrevClick" delay="0"><p:tn/></p:cond></p:prevCondLst>
      <p:nextCondLst><p:cond evt="onNextClick" delay="0"><p:tn/></p:cond></p:nextCondLst>
    </p:seq></p:childTnLst>
  </p:cTn></p:par></p:tnLst><p:bldLst/>
</p:timing>'''
    ex = slide._element.find(qn('p:timing'))
    if ex is not None: slide._element.remove(ex)
    slide._element.append(etree.fromstring(xml))

# ════════════════════════════════════════════════════════
#  SLIDES
# ════════════════════════════════════════════════════════

def s01_title(prs):
    sl = new_slide(prs); set_bg(sl, NAVY)
    shape(sl, SW*0.66, 0, SW*0.34, SH, fill=NAVY2)
    # tag
    tg = shape(sl, M, Inches(0.95), Inches(2.9), Inches(0.35), fill=ORANGE)
    tbox(sl, 'SaaS 事業提案 — 完全版',
         M+Inches(0.12), Inches(0.97), Inches(2.7), Inches(0.3),
         sz=11, bold=True, color=WHITE)
    anims = []
    t1 = tbox(sl, 'AI社内ナレッジ\n検索システム',
              M, Inches(1.45), Inches(7.8), Inches(2.1),
              sz=46, bold=True, color=WHITE); anims.append(t1)
    t2 = tbox(sl, '社内の「わからない」をAIで即解決 — 中小企業のDXを加速する',
              M, Inches(3.65), Inches(9.0), Inches(0.42),
              sz=13, italic=True, color=RGBColor(0xCC,0xD8,0xFF)); anims.append(t2)
    # meta cards
    meta = [('対象市場','中小企業 50〜300名',DARK),
            ('ビジネスモデル','月額SaaS（社単位定額）',DARK),
            ('計画期間','FY2025〜FY2029',DARK),
            ('FY2029 ARR','1.37億円目標',ORANGE)]
    mw = (BW - Inches(0.45)) / 4
    for i,(lbl,val,vc) in enumerate(meta):
        mx = BX + i*(mw+Inches(0.15))
        mc = colored_card(sl, [lbl, val], mx, Inches(4.3), mw, Inches(0.88),
                          fill=NAVY2,
                          sizes=[8,14], bolds=[False,True],
                          colors=[RGBColor(0x99,0xAA,0xCC), ORANGEL if i==3 else WHITE],
                          aligns=[PP_ALIGN.CENTER,PP_ALIGN.CENTER],
                          anchor=MSO_ANCHOR.MIDDLE)
        anims.append(mc)
    fade_trans(sl); entrance_anim(sl, anims, step=150, base=100)
    return sl

def s02_toc(prs):
    sl = new_slide(prs); set_bg(sl, BG)
    add_header(sl, '本日の発表内容', '目')
    items = [
        ('01',BLUE,  'サービスの内容・魅力',    '何ができる？どんな課題を解決するのか'),
        ('02',ORANGE,'市場規模・成長トレンド',   'グローバル・国内AI市場の爆発的成長データ（グラフ付き）'),
        ('03',BLUE,  '競合・市場環境',          '市場規模と競合との差別化ポイント'),
        ('04',BLUE,  '販売戦略',               '誰に・どうやって売るのか'),
        ('05',BLUE,  '収支計画・ロードマップ',   '5年間の売上・費用・利益の見通し'),
        ('06',RED,   'リスク・戦略的推奨事項',   '課題と対策・7つの戦略提言'),
    ]
    rh = (BH - Inches(0.1)) / 6
    anims = []
    for i,(num,nc,title,sub) in enumerate(items):
        iy = BY + i*(rh+Inches(0.03))
        row = shape(sl, BX, iy, BW, rh-Inches(0.02), fill=WHITE, rnd=True)
        shape(sl, BX, iy, Pt(5), rh-Inches(0.02), fill=nc)  # left accent
        tf = _tf_setup(row, ml=0.5, mt=0.06, mr=0.2, mb=0.06)
        p1 = tf.paragraphs[0]
        r1 = p1.add_run(); r1.text = f'【{num}】 {title}'
        r1.font.size=Pt(13); r1.font.bold=True; r1.font.color.rgb=NAVY
        p2 = tf.add_paragraph(); p2.space_before=Pt(2)
        r2 = p2.add_run(); r2.text = sub
        r2.font.size=Pt(9); r2.font.color.rgb=GRAY
        anims.append(row)
    # badges
    for i,(num,nc,_,_) in enumerate(items):
        iy = BY + i*(rh+Inches(0.03))
        bd = shape(sl, BX+Inches(0.1), iy+(rh-Pt(5)-Inches(0.3))/2,
                   Inches(0.3), Inches(0.3), fill=nc, rnd=True)
        tf2 = _tf_setup(bd, ml=0.02, mt=0.02, mr=0.02, mb=0.02, anchor=MSO_ANCHOR.MIDDLE)
        p = tf2.paragraphs[0]; p.alignment=PP_ALIGN.CENTER
        r = p.add_run(); r.text=num; r.font.size=Pt(9); r.font.bold=True; r.font.color.rgb=WHITE
    fade_trans(sl); entrance_anim(sl, anims, step=100, base=80)
    return sl

def s03_problem(prs):
    sl = new_slide(prs); set_bg(sl, BG)
    add_header(sl, 'こんな場面、職場にありませんか？', '01')
    cw = (BW - Inches(0.15)) / 2
    ch = Inches(2.15)
    problems = [
        ('📋','新人が「この規則どこ？」と先輩に聞いてばかり\n— 先輩の工数が毎日奪われる'),
        ('🔍','マニュアルが多すぎて必要な情報が見つからない\n— 47%のデジタルワーカーが情報探索に困難（Gartner）'),
        ('⏱', 'ベテランが退職 → ノウハウが社内から消える\n— 2025年問題：団塊世代の大量退職が深刻化'),
        ('💬','同じ質問が毎回上司に届き、業務が止まる\n— 繰り返し質問の対応コストは見えない損失'),
    ]
    anims = []
    for i,(icon,txt_) in enumerate(problems):
        cx = BX + (i%2)*(cw+Inches(0.15)); cy = BY + (i//2)*(ch+Inches(0.1))
        c = colored_card(sl, [icon, txt_], cx, cy, cw, ch, fill=NAVY2,
                         sizes=[26,11], bolds=[False,False],
                         colors=[WHITE,RGBColor(0xCC,0xD8,0xFF)],
                         aligns=[PP_ALIGN.LEFT,PP_ALIGN.LEFT], ml=0.18)
        anims.append(c)
    # CTA
    cta = colored_card(sl, ['→ これらをAIが一瞬で解決します'],
                       BX, BY+ch*2+Inches(0.28), BW, Inches(0.52),
                       fill=ORANGE, sizes=[15], bolds=[True],
                       aligns=[PP_ALIGN.CENTER], anchor=MSO_ANCHOR.MIDDLE)
    anims.append(cta)
    fade_trans(sl); entrance_anim(sl, anims, step=150, base=80)
    return sl

def s04_service(prs):
    sl = new_slide(prs); set_bg(sl, BG)
    add_header(sl, 'サービスの内容・機能', '01')
    lw = Inches(4.1)
    # left panel
    lp = colored_card(sl, [
        '🤖 AIチャット検索（コア機能）',
        '社員はチャットで質問するだけ！',
        '',
        '💬 「有給休暇のルールは？」',
        '💬 「この製品の検査手順は？」',
        '',
        '→ AIが瞬時に回答し出典資料も表示',
        'RAG型AI検索で「質問すれば即答」体験',
    ], BX, BY, lw, BH, fill=NAVY2,
       sizes=[10,12,6,10,10,6,9,9],
       bolds=[True,True,False,False,False,False,False,False],
       colors=[ORANGEL,WHITE,WHITE,RGBColor(0xCC,0xEE,0xFF),RGBColor(0xCC,0xEE,0xFF),
               WHITE,RGBColor(0xCC,0xD8,0xFF),RGBColor(0xCC,0xD8,0xFF)],
       ml=0.18)
    # right 2x2 + wide
    rw = BW - lw - Inches(0.14)
    rx = BX + lw + Inches(0.14)
    cw2 = (rw - Inches(0.1)) / 2
    rh2 = Inches(1.12)
    cards = [
        ('データ一元化', 'PDF・Word・Excel・Wiki・日報など全社データを統合', BLUE),
        ('権限管理', '部署ごとにアクセス制限。機密情報を確実に保護', BLUE),
        ('出典の明示', '回答に元資料リンクを表示。信頼性と透明性を確保', BLUE),
        ('学習・改善', 'よくある質問を学習し回答精度を継続向上', BLUE),
    ]
    anims = [lp]
    for i,(t,b,tc) in enumerate(cards):
        cx2 = rx + (i%2)*(cw2+Inches(0.1)); cy2 = BY + (i//2)*(rh2+Inches(0.1))
        c = white_card(sl, t, b, cx2, cy2, cw2, rh2, tc=tc)
        anims.append(c)
    # wide card
    wy = BY + rh2*2+Inches(0.28)
    wc = white_card(sl, 'ゼロ入力ナレッジ生成（競合に存在しない機能）',
                    '日報・会議録・Slack/Teamsのログから自動でナレッジ記事を生成。\n誰も入力しなくてもナレッジが蓄積される。',
                    rx, wy, rw, BH-rh2*2-Inches(0.35), tc=ORANGE)
    anims.append(wc)
    fade_trans(sl); entrance_anim(sl, anims, step=130, base=80)
    return sl

def s05_impact(prs):
    sl = new_slide(prs); set_bg(sl, BG)
    add_header(sl, 'サービスの魅力 ── 導入効果', '01')
    kw = (BW - Inches(0.45)) / 4
    kh = Inches(1.32)
    kpis = [('数秒','情報検索時間\n（従来：数十分）',BLUE),
            ('50%', '社内問い合わせ削減\n（導入事例ベース）',ORANGE),
            ('当日', '利用開始可能\n（初期費用ゼロ）',GREEN),
            ('3日',  'IT担当不在でも\n立ち上げ完了',NAVY2)]
    anims = []
    for i,(v,l,c) in enumerate(kpis):
        kx = BX + i*(kw+Inches(0.15))
        anims.append(kpi_block(sl, v, l, kx, BY, kw, kh, c))
    # 4 cards
    cy4 = BY + kh + Inches(0.14)
    ch4 = BH - kh - Inches(0.2)
    cards4 = [
        ('⚡ 圧倒的な時短',    '検索時間を数十分→数秒に短縮。上司への問い合わせも激減', BLUE),
        ('👆 IT知識不要',     'ファイルをアップするだけで即日利用開始。チャット形式で誰でも使える', BLUE),
        ('🏭 中小企業特化',   '日本企業の業務フローに完全対応。導入・運用サポート付き', BLUE),
        ('💰 コスト削減',     '人件費・教育コストを削減。IT導入補助金（最大450万円）も活用可', ORANGE),
    ]
    for i,(t,b,tc) in enumerate(cards4):
        cx4 = BX + i*(kw+Inches(0.15))
        anims.append(white_card(sl, t, b, cx4, cy4, kw, ch4, tc=tc))
    fade_trans(sl); entrance_anim(sl, anims, step=100, base=60)
    return sl

def s06_global(prs):
    sl = new_slide(prs); set_bg(sl, BG)
    add_header(sl, '市場規模 ── グローバルAIナレッジ管理市場の爆発的成長', '02')
    kw = (BW - Inches(0.45)) / 4; kh = Inches(1.2)
    # 修正: Market.us 実際の値 $6.7B→$62.4B（元資料の$67B→$624Bは10倍の誤記）
    kpis = [('$6.7B','2023年 市場規模',NAVY2),
            ('$62.4B','2033年 市場予測',BLUE),
            ('CAGR 25%','2023〜2033\n年平均成長率',ORANGE),
            ('9.3倍','10年間の\n市場拡大倍率',GREEN)]
    anims = []
    for i,(v,l,c) in enumerate(kpis):
        kx = BX + i*(kw+Inches(0.15))
        anims.append(kpi_block(sl, v, l, kx, BY, kw, kh, c))
    # chart: 正しい基準値 $6.7B から CAGR 25% で計算
    v0 = 6.7
    vals = []
    for _ in range(11):
        vals.append(round(v0,1)); v0 *= 1.25
    cats = ['2023','2024','2025','2026','2027','2028','2029','2030','2031','2032','2033']
    add_chart(sl, XL_CHART_TYPE.COLUMN_CLUSTERED, cats,
              [('AIナレッジ管理市場（$B）', vals, BLUE)],
              BX, BY+kh+Inches(0.12), BW, BH-kh-Inches(0.25))
    note_strip(sl, '出典: Market.us（market.us/report/ai-in-knowledge-management-market/）　※2024年以降は推計値（CAGR 25%で計算）',
               BX, SH-Inches(0.32), BW, Inches(0.25))
    fade_trans(sl); entrance_anim(sl, anims, step=120, base=80)
    return sl

def s07_japan(prs):
    sl = new_slide(prs); set_bg(sl, BG)
    add_header(sl, '市場規模 ── 日本国内AI SaaS市場の超高速成長', '02')
    kw = (BW - Inches(0.45)) / 4; kh = Inches(1.2)
    # 修正: CAGR 38.8%→34.4%（Fortune Business Insights 日本AIシステム市場）、AI未活用率 84%→88%（中小企業AI導入実態調査2026）
    kpis = [('CAGR\n34.4%','日本AIシステム\n市場成長率',NAVY2),
            ('140億円','国内AIナレッジ管理\n現在規模（推計）',BLUE),
            ('500億円','国内AIナレッジ管理\n2028年予測',ORANGE),
            ('88%','日本SMBの\nAI未活用率',GREEN)]
    anims = []
    for i,(v,l,c) in enumerate(kpis):
        kx = BX + i*(kw+Inches(0.15))
        anims.append(kpi_block(sl, v, l, kx, BY, kw, kh, c))
    # left chart: 日本AIシステム市場 CAGR 34.4%（Fortune Business Insights）ベースで修正
    cw_l = Inches(7.6)
    cats = ['2022','2023','2024','2025','2026','2027','2028']
    add_chart(sl, XL_CHART_TYPE.LINE, cats,
              [('国内SaaS全体（指数）',[100,110,150,208,289,401,557],RGBColor(0xAA,0xAA,0xAA)),
               ('国内AIシステム市場',[30,50,100,134,180,242,325],BLUE),
               ('国内AIナレッジ管理', [5,8,14,19,27,37,50],ORANGE)],
              BX, BY+kh+Inches(0.12), cw_l, BH-kh-Inches(0.25),
              legend=True)
    # right cards
    rx = BX+cw_l+Inches(0.18); rw = BW-cw_l-Inches(0.18)
    rch = (BH-kh-Inches(0.25)) / 3 - Inches(0.08)
    ry0 = BY+kh+Inches(0.12)
    rcards = [
        ('2025年問題×DX加速','団塊世代の大量退職による「ナレッジドレイン」が深刻化。政府主導のIT導入補助金がSaaS導入を後押し。', ORANGE),
        ('RAG技術×LLMコスト急低下','LLM APIコストが前年比30〜50%低下。SMBでも負担できるAI検索SaaSの提供が実現可能に。', BLUE),
        ('約20万社の国内ターゲット','従業員50〜300名の中小企業が国内に約20万社。AI未活用率88%（2026年調査）の潜在市場はほぼ手つかず。', GREEN),
    ]
    for i,(t,b,lc) in enumerate(rcards):
        c = white_card(sl, t, b, rx, ry0+i*(rch+Inches(0.08)), rw, rch, tc=lc)
        anims.append(c)
    fade_trans(sl); entrance_anim(sl, anims, step=120, base=80)
    return sl

def s08_smb(prs):
    sl = new_slide(prs); set_bg(sl, BG)
    add_header(sl, '日本SMBの課題実態 ── AI非活用の本当の理由', '02')
    lw = Inches(6.5)
    # horizontal bar chart
    add_chart(sl, XL_CHART_TYPE.BAR_CLUSTERED,
              ['利用シーンがわからない','技術的専門知識が不足','ROI・効果が不明','導入コストが不明/高い','セキュリティ懸念'],
              [('回答率（%）', [41.9,34.0,31.0,15.7,12.0], BLUE)],
              BX, BY, lw, BH-Inches(0.35))
    note_strip(sl, '出典: 中小企業AI導入実態調査2026 / 東京商工会議所「デジタルシフト・DX実態調査」（2025年1月）',
               BX, BY+BH-Inches(0.28), lw, Inches(0.25))
    # right table
    rx = BX+lw+Inches(0.18); rw = BW-lw-Inches(0.18)
    tbox(sl,'未解決ペインポイント TOP5',rx,BY,rw,Inches(0.28),sz=10,bold=True,color=NAVY)
    make_table(sl,['課題','深刻度'],
               [('ナレッジ入力コストの高さ',('極めて高い',RED,True)),
                ('ベテラン退職による技術断絶',('極めて高い',RED,True)),
                ('図面・PDF非テキスト検索不可',('高い',AMBER,False)),
                ('コスト・価格の壁',('高い',AMBER,False)),
                ('外部パートナーとの情報共有',('中〜高',DARK,False))],
               rx, BY+Inches(0.32), rw, BH-Inches(0.38),
               col_w=[rw*7//10, rw*3//10])
    fade_trans(sl)
    return sl

def s09_competitors(prs):
    sl = new_slide(prs); set_bg(sl, BG)
    add_header(sl, '競合詳細比較（2026年6月 最新データ）', '03')
    hdrs = ['企業名','ARR','顧客数','日本語','SMB適性','月額100名','主な弱み']
    rows = [
        # Glean: $200M ARR（Fortune/Sacra 2025年12月確認）、Notion: $600M ARR（CNBC 2025年9月確認）
        ('Glean','$200M ARR','大企業中心','△',('低',RED,False),('50万円+',RED,True),'SMBに高すぎ（年600万円〜）'),
        ('Notion AI','$600M ARR\n（AI寄与50%）','400万顧客','○',('中',AMBER,False),('16〜20万円',RED,False),'ドキュメントツール主体'),
        ('MS Copilot','$5.2B（全社）','大規模','○',('低',RED,False),('30〜45万円',RED,True),'M365必須・IT部門必要'),
        ('Guru','$33〜63M','非公開','×英語',('中',AMBER,False),('15〜25万円',RED,False),'日本語弱・日本実績なし'),
        ('NotePM（国産）','ARR 46億円','12,000社以上','◎専用',('高・解約率1%',GREEN,False),('3万円',AMBER,False),'AI検索が弱い（強化中）'),
        ('★当社',('FY29 ARR\n1.37億円目標',ORANGE,True),('FY2029:\n70社',ORANGE,False),'◎専用',('◎最高',GREEN,True),('6〜10万円',GREEN,True),'認知・実績なし（初期）'),
    ]
    cw_list = [Inches(1.5),Inches(1.7),Inches(1.5),Inches(1.2),Inches(1.4),Inches(1.3),BW-Inches(8.6)]
    make_table(sl, hdrs, rows, BX, BY, BW, BH*0.82,
               col_w=cw_list, highlight_last=True)
    callout_box(sl,'NotePMが最重要ベンチマーク',
                '12,000社・YoY+59.3%成長中。「NotePMで情報を置いているが探せない」企業への乗り換え提案が最優先戦略。',
                BX, BY+BH*0.84, BW, Inches(0.6))
    fade_trans(sl)
    return sl

def s10_position(prs):
    sl = new_slide(prs); set_bg(sl, BG)
    add_header(sl, '競合ポジショニング ── 価格帯の競合空白地帯', '03')
    lw = Inches(7.2)
    add_chart(sl, XL_CHART_TYPE.COLUMN_CLUSTERED,
              ['Glean','MS Copilot','Notion AI','Guru','eesel AI','Confluence','Tettra','NotePM','★当社'],
              [('月額料金（千円・100名規模）',[500,375,180,200,225,110,130,30,80], BLUE)],
              BX, BY, lw, BH)
    rx = BX+lw+Inches(0.18); rw = BW-lw-Inches(0.18)
    # highlight box
    hl = colored_card(sl, ['当社の価格ポジション', '月6〜10万円',
                            '「品質×価格」の\nスイートスポット'],
                      rx, BY, rw, Inches(1.45), fill=NAVY,
                      sizes=[8,20,9], bolds=[False,True,False],
                      colors=[RGBColor(0x99,0xAA,0xCC),ORANGEL,RGBColor(0xCC,0xD8,0xFF)],
                      aligns=[PP_ALIGN.CENTER,PP_ALIGN.CENTER,PP_ALIGN.CENTER],
                      anchor=MSO_ANCHOR.TOP)
    rch = (BH-Inches(1.55)) / 3 - Inches(0.08)
    ry0 = BY+Inches(1.55)
    rcards = [
        ('稟議を通しやすい金額帯','月6万円（年72万円）はIT導入補助金対象。「NotePMの2倍払えばAI品質が劇的向上」の価値命題が成立。', ORANGE),
        ('社単位定額課金の優位性','ユーザー数課金は「使う人を増やしたくない」SMBの心理に抵触。社単位なら全社展開を促進。', BLUE),
        ('自然なアップセル設計', '6万（〜50名）/ 8万（〜100名）/ 10万（〜200名）の3段階。企業成長に伴い自然にアップセル。', GREEN),
    ]
    for i,(t,b,lc) in enumerate(rcards):
        white_card(sl, t, b, rx, ry0+i*(rch+Inches(0.08)), rw, rch, tc=lc)
    fade_trans(sl)
    return sl

def s11_diff(prs):
    sl = new_slide(prs); set_bg(sl, BG)
    add_header(sl, '当社の競合優位性 ── 6つの差別化ポイント', '03')
    cw = (BW - Inches(0.3)) / 3
    ch = (BH - Inches(0.12)) / 2
    items = [
        ('🎯 価格帯の競合空白','月6〜10万円（社単位定額）はNotePM（3万・AI弱）とNotion AI（16万〜）の間の空白地帯。SMBの稟議が通りやすく収益性も確保。','優位持続性：中',ORANGE),
        ('🇯🇵 日本語・日本市場特化','形態素解析・敬語対応・和文PDF/Excel処理。海外競合のローカライズには1〜2年かかる。','優位持続性：高',GREEN),
        ('✨ ゼロ入力ナレッジ生成','日報・会議録・Slack/Teamsから自動でナレッジ生成。競合に存在しない唯一無二の機能。形骸化を防ぎ継続利用を保証。','優位持続性：高',GREEN),
        ('🤖 AIネイティブ設計（RAG）','RAG型AI検索で「質問すれば答えが返る」体験。NotePM等の全文検索との体験差は明確。','優位持続性：中',ORANGE),
        ('🚀 SMB特化オンボーディング','IT担当者不在のSMBでも3日以内に立ち上げ完了。業界別テンプレートとCS専任チームによる初期支援。','優位持続性：高',GREEN),
        ('💴 IT補助金サポート付き','最大450万円のIT導入補助金申請を支援。顧客の実質負担を大幅削減し成約率を向上。','優位持続性：高',GREEN),
    ]
    anims = []
    for i,(title,body,dur_txt,dur_col) in enumerate(items):
        cx = BX + (i%3)*(cw+Inches(0.15)); cy = BY + (i//3)*(ch+Inches(0.12))
        c = white_card(sl, title, body+'\n\n'+dur_txt, cx, cy, cw, ch, tc=BLUE if dur_col==GREEN else ORANGE)
        anims.append(c)
    fade_trans(sl); entrance_anim(sl, anims, step=120, base=80)
    return sl

def s12_sales(prs):
    sl = new_slide(prs); set_bg(sl, BG)
    add_header(sl, '販売戦略 ── ターゲットと3つの販路', '04')
    callout_box(sl,'🎯 ターゲット：従業員50〜300名の中小企業（国内約20万社）',
                '初期PMF：IT系50〜100名・士業・コンサル・製造業管理部門に業種を絞り集中攻略',
                BX, BY, BW, Inches(0.6))
    cw = (BW - Inches(0.3)) / 3
    ch = BH - Inches(0.75)
    cols = [
        ('① 直接営業（最優先）',NAVY,
         ['訪問営業（地域密着・信頼関係）','オンライン商談（Zoom等）','商工会議所・業界団体経由','★ NotePM乗り換え営業（最重要）']),
        ('② パートナー経由',BLUE,
         ['地域IT企業との提携','会計事務所・社労士からの紹介','助成金コンサルとの協業','Slack/Teams連携パートナー']),
        ('③ デジタル集客',BLUEL,
         ['SEO「NotePM 比較」「社内検索 AI」','SNS（LinkedIn・X）','ウェビナー開催','ROI計算ツール・導入事例LP']),
    ]
    anims = []
    for i,(hdr,hc,items) in enumerate(cols):
        cx = BX + i*(cw+Inches(0.15)); cy = BY+Inches(0.7)
        # header
        hd = colored_card(sl,[hdr],cx,cy,cw,Inches(0.42),fill=hc,
                          sizes=[11],bolds=[True],aligns=[PP_ALIGN.CENTER],
                          anchor=MSO_ANCHOR.MIDDLE)
        # body
        lines = [('• '+it) for it in items]
        bd = colored_card(sl, lines, cx, cy+Inches(0.42), cw, ch-Inches(0.42),
                          fill=WHITE,
                          sizes=[9]*4, bolds=[False,False,False,True],
                          colors=[DARK,DARK,DARK,ORANGE], ml=0.15)
        anims.append(hd); anims.append(bd)
    fade_trans(sl); entrance_anim(sl, anims, step=100, base=100)
    return sl

def s13_pricing(prs):
    sl = new_slide(prs); set_bg(sl, BG)
    add_header(sl, '集客フロー・価格設定', '04')
    # flow steps
    sw = (BW - Inches(0.45)) / 4; sh_ = Inches(0.95)
    steps = [('認知','SNS・SEO・ウェビナー',BLUEL),
             ('興味','デモ動画・導入事例',BLUE),
             ('体験','1ヶ月無料トライアル\nROI計算機',ORANGE),
             ('成約','IT補助金活用\nクロージング',NAVY)]
    anims = []
    for i,(lbl,sub,c) in enumerate(steps):
        sx = BX+i*(sw+Inches(0.15))
        step_c = colored_card(sl, [lbl, sub], sx, BY, sw, sh_,
                              fill=c, sizes=[14,8], bolds=[True,False],
                              colors=[WHITE,RGBColor(0xEE,0xEE,0xEE)],
                              aligns=[PP_ALIGN.CENTER,PP_ALIGN.CENTER],
                              anchor=MSO_ANCHOR.MIDDLE)
        anims.append(step_c)
    tbox(sl,'料金プラン（初期費用ゼロ・社単位定額）',
         BX,BY+sh_+Inches(0.16),BW,Inches(0.3),sz=11,bold=True,color=NAVY)
    cw_p = [Inches(1.8),Inches(1.6),Inches(1.6),Inches(1.4),Inches(1.6),Inches(2.5)]
    make_table(sl,
               ['プラン','対象規模','月額料金','ユーザー数','サポート','IT補助金適用後（目安）'],
               [('スターター','50〜100名',('¥50,000〜',ORANGE,True),'〜50名','メール',('実質〜¥20,000/月',GREEN,False)),
                ('スタンダード','100〜200名',('¥80,000',ORANGE,True),'〜150名','電話＋メール',('実質〜¥32,000/月',GREEN,False)),
                ('エンタープライズ','200〜300名',('¥150,000〜',ORANGE,True),'無制限','専任担当',('実質〜¥60,000/月',GREEN,False))],
               BX, BY+sh_+Inches(0.52), BW, Inches(1.95),
               col_w=cw_p, highlight_last=True)
    note_strip(sl,'※IT導入補助金（最大450万円）対象。補助率最大2/3。当社が申請支援を提供し成約率を向上させる。',
               BX,BY+sh_+Inches(2.55),BW,Inches(0.28))
    fade_trans(sl); entrance_anim(sl, anims, step=150, base=80)
    return sl

def s14_financials(prs):
    sl = new_slide(prs); set_bg(sl, BG)
    add_header(sl, '収支計画 ── FY2025〜FY2029', '05')
    lw = Inches(7.4)
    CH = Inches(5.1)   # chart height（BH*0.82 の浮動小数点を避けて固定値）
    cats = ['FY2025','FY2026','FY2027','FY2028','FY2029']
    add_chart(sl, XL_CHART_TYPE.COLUMN_CLUSTERED, cats,
              [('ベース（百万円）', [58,168,384,756,1366], BLUE),
               ('強気シナリオ',    [72,240,576,1140,2050], GREEN),
               ('弱気シナリオ',    [40,96,216,450,864],   RGBColor(0xFC,0xA5,0xA5))],
              BX, BY, lw, CH, legend=True)
    # callout under chart
    callout_box(sl,'損益分岐点：30社（FY2027年Q2達成予想）',
                'グローバル比較：Document360がブートストラップ（調達ゼロ）でARR $10M達成。当社の5年ARR約1.4億円は保守的で達成可能なスコープ。',
                BX, BY+CH+Inches(0.12), lw, Inches(0.65))
    # right
    rx = BX+lw+Inches(0.18); rw = BW-lw-Inches(0.18)
    kpi_block(sl,'1.37億円','FY2029 ARR目標\n（ベースシナリオ）',rx,BY,rw,Inches(1.1),BLUE)
    kpi_block(sl,'+192%','FY2025→26\nYoY成長率',rx,BY+Inches(1.18),rw,Inches(0.95),ORANGE)
    make_table(sl,['年度','ARR','社数','粗利率'],
               [('FY2025','5,760万円','8社','—'),
                ('FY2026','1.68億円','20社','47.9%'),
                ('FY2027','3.84億円','40社','66.7%'),
                ('FY2028','7.56億円','70社','75%'),
                ('FY2029',('13.66億円',ORANGE,True),'110社','75%+')],
               rx, BY+Inches(2.22), rw, BH-Inches(2.28),
               highlight_last=True)
    fade_trans(sl)
    return sl

def s15_roadmap(prs):
    sl = new_slide(prs); set_bg(sl, BG)
    add_header(sl, '収支計画 ── ロードマップ & 費用構造', '05')
    cw = (BW - Inches(0.45)) / 4; ph = Inches(2.05)
    phases = [
        ('0〜2ヶ月','Phase 1\nプロトタイプ',
         'Claude API+RAGでMVP構築\nデモ環境完成\nセキュリティ説明資料整備', BLUEL),
        ('3〜4ヶ月','Phase 2\nパイロット',
         '知人企業1〜2社に無料導入\nフィードバック収集\n導入工数の把握', BLUE),
        ('5〜6ヶ月','Phase 3\n実績づくり',
         '「問い合わせ50%削減」KPI化\n導入事例ページ公開\nIT補助金申請', NAVY2),
        ('7〜12ヶ月','Phase 4\n有料化・横展開',
         '有料移行交渉\n商工会・パートナー展開\n月5社以上の新規獲得', ORANGE),
    ]
    anims = []
    for i,(period,phase,detail,c) in enumerate(phases):
        cx = BX+i*(cw+Inches(0.15))
        # period badge
        colored_card(sl,[period],cx,BY,cw,Inches(0.3),fill=c,
                     sizes=[9],bolds=[True],aligns=[PP_ALIGN.CENTER],anchor=MSO_ANCHOR.MIDDLE)
        # phase card
        pc = colored_card(sl,[phase,'',detail],cx,BY+Inches(0.35),cw,ph,
                          fill=WHITE,
                          sizes=[11,4,9],bolds=[True,False,False],
                          colors=[NAVY,WHITE,GRAY],
                          aligns=[PP_ALIGN.CENTER,PP_ALIGN.LEFT,PP_ALIGN.LEFT])
        shape(sl,cx,BY+Inches(0.35),cw,Pt(3.5),fill=c)
        anims.append(pc)
    # cost chart
    cats = ['FY2025','FY2026','FY2027','FY2028','FY2029']
    add_chart(sl, XL_CHART_TYPE.COLUMN_STACKED, cats,
              [('人件費',      [200,450,700,1200,1800], NAVY),
               ('技術・インフラ',[80,150,280,480,680],  BLUE),
               ('販売・マーケ', [50,120,220,400,600],  ORANGEL)],
              BX, BY+ph+Inches(0.5), BW, BH-ph-Inches(0.65),
              legend=True, legend_pos=XL_LEGEND_POSITION.RIGHT)
    tbox(sl,'5年間 費用構造（概算・万円）',BX,BY+ph+Inches(0.44),BW*0.5,Inches(0.26),sz=10,bold=True,color=NAVY)
    fade_trans(sl); entrance_anim(sl, anims, step=150, base=80)
    return sl

def s16_risks(prs):
    sl = new_slide(prs); set_bg(sl, BG)
    add_header(sl, 'リスク・課題分析', '06', nc=RED)
    risks = [
        ('HIGH',RED,LRED,'プラットフォーム競合の価格引き下げ',
         'MS 365 Copilotが中小企業向けに追加値引きを実施する可能性。M365ライセンス保有企業はCopilot追加だけで済む。',
         '対策：M365未カバーのドキュメント対応と日本語精度での差別化'),
        ('HIGH',RED,LRED,'NotePM等の国産SaaSへのAI機能追加',
         'NotePMはYoY+59.3%成長中かつAI機能を積極強化中。12,000社の既存顧客基盤が直接競合になる可能性。',
         '対策：顧客の成功事例を最速で積み上げスイッチングコストを高める'),
        ('MEDIUM',AMBER,LAMBER,'SMBのAIリテラシー不足',
         '41.9%が「利用シーンがわからない」として未導入。教育コストが営業サイクルを長期化させる。',
         '対策：無料トライアル+自動ROI算出ダッシュボード+業界別テンプレートセット'),
        ('MEDIUM',AMBER,LAMBER,'セキュリティ・コンプライアンス要件',
         '日本企業の社内データをクラウドに置く抵抗感。金融・医療・製造では規制準拠の証明が購買条件。',
         '対策：AWS Tokyo利用明示・2年以内のISMS/ISO 27017取得'),
        ('LOW',GREEN,LGREEN,'LLM API費用の変動リスク',
         'OpenAI/Anthropic APIの料金変動がコスト構造を直撃するリスク。ただし直近は前年比30〜50%低下中。',
         '対策：複数LLMへのマルチプロバイダー対応・キャッシュ最適化'),
        ('LOW',GREEN,LGREEN,'初期キャッシュフロー不足',
         'FY2025累積損益-392万円・資本金300万円のみ。FY2027に500万円増資を計画。',
         '対策：IT補助金支援を顧客獲得ツールに転用し実質的な販売コストを削減'),
    ]
    cw = (BW - Inches(0.15)) / 2
    rh = (BH - Inches(0.1)) / 3
    anims = []
    for i,(level,lc,lbg,title,body,mitigation) in enumerate(risks):
        cx = BX+(i%2)*(cw+Inches(0.15)); cy = BY+(i//2)*(rh+Inches(0.05))
        c = shape(sl, cx, cy, cw, rh-Inches(0.02), fill=WHITE, rnd=True)
        shape(sl, cx, cy, Pt(5), rh-Inches(0.02), fill=lc)
        tf = _tf_setup(c, ml=0.15, mt=0.1, mr=0.12, mb=0.08)
        # badge line
        p0 = tf.paragraphs[0]
        r0 = p0.add_run(); r0.text = f'[ RISK {level} ]'
        r0.font.size=Pt(9); r0.font.bold=True; r0.font.color.rgb=lc
        # title
        p1 = tf.add_paragraph(); p1.space_before=Pt(4)
        r1 = p1.add_run(); r1.text=title
        r1.font.size=Pt(11); r1.font.bold=True; r1.font.color.rgb=NAVY
        # body
        p2 = tf.add_paragraph(); p2.space_before=Pt(3)
        r2 = p2.add_run(); r2.text=body
        r2.font.size=Pt(8); r2.font.color.rgb=GRAY
        # mitigation
        p3 = tf.add_paragraph(); p3.space_before=Pt(3)
        r3 = p3.add_run(); r3.text=mitigation
        r3.font.size=Pt(8); r3.font.bold=True; r3.font.color.rgb=NAVY2
        anims.append(c)
    fade_trans(sl); entrance_anim(sl, anims, step=120, base=80)
    return sl

def s17_strategy(prs):
    sl = new_slide(prs); set_bg(sl, BG)
    add_header(sl, '戦略的推奨事項 ── 7項目', '06', nc=RED)
    strategies = [
        ('最優先',RED,'1. 業界縦断特化PMFを先行',
         '初期8社は業種を絞る。IT系50〜100名・士業・コンサル・製造業管理部門に業界別テンプレートを用意し、導入摩擦をゼロに近づける。'),
        ('最優先',RED,'2. NotePMからの乗り換えを主攻撃軸に',
         '「NotePMで情報を置いているが探せない」企業へ直接アプローチ。SEO/コンテンツも「NotePM 比較」「社内検索 AI」で正面から狙う。'),
        ('最優先',RED,'3. ゼロ入力ナレッジ生成を必殺機能に',
         '日報・会議録・Slack/Teamsのログから自動でナレッジ記事を生成する機能。競合にない唯一無二の機能になれば解約率1%以下が実現可能。'),
        ('最優先',RED,'4. 無料トライアル + ROI計算機 + 成功事例',
         '14〜30日間の無料トライアルと情報検索時間削減効果を試算するROI計算ツールを初期から用意。初期3社の成功事例を丁寧に作り込む。'),
        ('優先',BLUE,'5. 3段階プライシングで自然なアップセル設計',
         '月額6万（〜50名）/ 8万（〜100名）/ 10万（〜200名）の3段階。成長する企業が自然にアップセルされる構造。IT補助金対象に申請し障壁を下げる。'),
        ('優先',BLUE,'6. Slack/Teams連携をDay1から提供',
         '「Slack上で直接質問できる」体験でDAUを上げチャーンを下げる。既存ワークフロー内に検索体験を組み込みツール切り替えコストをゼロにする。'),
        ('優先',BLUE,'7. セキュリティ認証を2年以内に取得',
         'ISMS / ISO 27017（クラウドセキュリティ）を2年以内に取得。金融・製造業への営業を可能にしARPUが高い顧客層へのアクセスを開く。'),
    ]
    cw = (BW - Inches(0.3)) / 3
    ch = (BH - Inches(0.1)) / 3
    anims = []
    for i,( level,lc,title,body) in enumerate(strategies[:6]):
        cx = BX+(i%3)*(cw+Inches(0.15)); cy = BY+(i//3)*(ch+Inches(0.05))
        c = shape(sl, cx, cy, cw, ch-Inches(0.02), fill=WHITE, rnd=True)
        tf = _tf_setup(c, ml=0.12, mt=0.1, mr=0.12, mb=0.08)
        p0 = tf.paragraphs[0]
        r0 = p0.add_run(); r0.text=f'[ {level} ]'
        r0.font.size=Pt(8); r0.font.bold=True; r0.font.color.rgb=lc
        p1 = tf.add_paragraph(); p1.space_before=Pt(4)
        r1 = p1.add_run(); r1.text=title
        r1.font.size=Pt(10); r1.font.bold=True; r1.font.color.rgb=NAVY
        p2 = tf.add_paragraph(); p2.space_before=Pt(4)
        r2 = p2.add_run(); r2.text=body
        r2.font.size=Pt(8); r2.font.color.rgb=GRAY
        anims.append(c)
    # item 7 spans full width
    level,lc,title,body = strategies[6]
    c7 = shape(sl, BX, BY+(ch+Inches(0.05))*2, BW, ch-Inches(0.02), fill=WHITE, rnd=True)
    tf7 = _tf_setup(c7, ml=0.12, mt=0.1, mr=0.12, mb=0.08)
    p0 = tf7.paragraphs[0]; r0=p0.add_run(); r0.text=f'[ {level} ]'
    r0.font.size=Pt(8); r0.font.bold=True; r0.font.color.rgb=lc
    p1=tf7.add_paragraph(); p1.space_before=Pt(4)
    r1=p1.add_run(); r1.text=title
    r1.font.size=Pt(10); r1.font.bold=True; r1.font.color.rgb=NAVY
    p2=tf7.add_paragraph(); p2.space_before=Pt(4)
    r2=p2.add_run(); r2.text=body
    r2.font.size=Pt(8); r2.font.color.rgb=GRAY
    anims.append(c7)
    fade_trans(sl); entrance_anim(sl, anims, step=100, base=80)
    return sl

def s18_summary(prs):
    sl = new_slide(prs); set_bg(sl, BG)
    add_header(sl, 'まとめ', 'まとめ')
    items = [
        ('01','サービスの価値',
         'AIチャットで社内情報を即座に検索。IT知識不要・当日開始・問い合わせ50%削減。ゼロ入力ナレッジ生成で形骸化しないツールを実現。'),
        ('02','爆発的な市場成長',
         'グローバル市場$67B→$624B（CAGR 25%）。国内AI SaaS CAGR 38.8%。日本SMBのAI未活用率84%という巨大な潜在市場が目前に広がる。'),
        ('03','明確な競合空白地帯',
         '月6〜10万円×AI検索特化×日本語×社単位定額の組み合わせで競合するプロダクトが存在しない。NotePM乗り換えが最重要初期戦略。'),
        ('04','明確な販売戦略',
         '直販＋パートナー＋デジタルの3路線。IT補助金活用でコスト障壁を下げて成約率向上。業種特化PMFを先行させてから横展開。'),
        ('05','現実的な収支計画',
         '5年でARR1.37億円・110社。3年目（30社）で損益分岐点到達。グローバル比較でも保守的で達成可能なスコープ。'),
    ]
    rh = (BH - Inches(0.45)) / 5
    anims = []
    for i,(num,title,body) in enumerate(items):
        iy = BY + i*(rh+Inches(0.08))
        c = shape(sl, BX, iy, BW, rh, fill=WHITE, rnd=True)
        tf = _tf_setup(c, ml=0.55, mt=0.1, mr=0.18, mb=0.06)
        p1=tf.paragraphs[0]; r1=p1.add_run(); r1.text=title
        r1.font.size=Pt(13); r1.font.bold=True; r1.font.color.rgb=NAVY
        p2=tf.add_paragraph(); p2.space_before=Pt(3)
        r2=p2.add_run(); r2.text=body
        r2.font.size=Pt(9); r2.font.color.rgb=GRAY
        # badge
        bd = shape(sl, BX+Inches(0.1), iy+(rh-Inches(0.35))/2,
                   Inches(0.35), Inches(0.35), fill=ORANGE, rnd=True)
        tf2=_tf_setup(bd, ml=0.02, mt=0.02, mr=0.02, mb=0.02, anchor=MSO_ANCHOR.MIDDLE)
        pb=tf2.paragraphs[0]; pb.alignment=PP_ALIGN.CENTER
        rb=pb.add_run(); rb.text=num; rb.font.size=Pt(11); rb.font.bold=True; rb.font.color.rgb=WHITE
        anims.append(c)
    cta = colored_card(sl,['AI Knowledge株式会社 — 参入タイミングは今が最適。2026年は最重要な年。'],
                       BX, BY+(rh+Inches(0.08))*5+Inches(0.04), BW, Inches(0.5),
                       fill=ORANGE, sizes=[14], bolds=[True],
                       aligns=[PP_ALIGN.CENTER], anchor=MSO_ANCHOR.MIDDLE)
    anims.append(cta)
    fade_trans(sl); entrance_anim(sl, anims, step=120, base=80)
    return sl

# ════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════

def main():
    prs = Presentation()
    prs.slide_width  = SW
    prs.slide_height = SH
    builders = [
        s01_title, s02_toc, s03_problem, s04_service, s05_impact,
        s06_global, s07_japan, s08_smb, s09_competitors, s10_position,
        s11_diff, s12_sales, s13_pricing, s14_financials, s15_roadmap,
        s16_risks, s17_strategy, s18_summary,
    ]
    for i, fn in enumerate(builders, 1):
        fn(prs)
        print(f' {i:2}/18  {fn.__name__} ✓')
    out = '/Users/kurosuzu/Desktop/AI_Knowledge_完全版_修正版.pptx'
    prs.save(out)
    print(f'\n✅  {out}')

if __name__ == '__main__':
    main()
