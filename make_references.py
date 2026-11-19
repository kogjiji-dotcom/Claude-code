#!/usr/bin/env python3
"""参考文献一覧 PowerPoint 生成"""

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

NAVY   = RGBColor(0x0D, 0x2B, 0x5A)
NAVY2  = RGBColor(0x1B, 0x3A, 0x6B)
BLUE   = RGBColor(0x25, 0x58, 0xD4)
ORANGE = RGBColor(0xE8, 0x82, 0x0C)
WHITE  = RGBColor(0xFF, 0xFF, 0xFF)
GRAY   = RGBColor(0x55, 0x65, 0x78)
BG     = RGBColor(0xF0, 0xF4, 0xFB)
LBLUE  = RGBColor(0xEF, 0xF6, 0xFF)
GREEN  = RGBColor(0x1A, 0x8C, 0x5A)
AMBER  = RGBColor(0xD9, 0x74, 0x06)

SW = Inches(13.33)
SH = Inches(7.5)

refs = [
    # (category, title, source_label, url)
    ("グローバル市場",
     "AI in Knowledge Management Market（市場規模 $6.7B→$62.4B, CAGR 25%）",
     "Market.us",
     "https://market.us/report/ai-in-knowledge-management-market/"),

    ("グローバル市場",
     "AI in Knowledge Management Market — News（$62B by 2033）",
     "Market.us",
     "https://scoop.market.us/ai-in-knowledge-management-market-news/"),

    ("グローバル市場",
     "Knowledge Management Software Market 2024–2029（CAGR 14.3%）",
     "Technavio",
     "https://www.technavio.com/report/knowledge-management-software-market-industry-analysis"),

    ("グローバル市場",
     "Knowledge Management Software Market — Press Release",
     "Technavio / PR Newswire",
     "https://newsroom.technavio.org/knowledge-management-software-market-industry-analysis"),

    ("日本市場",
     "Japan Artificial Intelligence Market Size & Growth（CAGR 34.4%）",
     "Fortune Business Insights",
     "https://www.fortunebusinessinsights.com/japan-artificial-intelligence-market-113971"),

    ("日本市場",
     "Japan AI Systems Forecast 2024–2028",
     "IDC Japan",
     "https://my.idc.com/getdoc.jsp?containerId=JPE50869924"),

    ("日本市場",
     "国内AIシステム市場予測（2024年 1.34兆円・CAGR 25.6%）",
     "IDC Japan プレスリリース",
     "https://my.idc.com/getdoc.jsp?containerId=prJPJ53362125"),

    ("日本SMB調査",
     "中小企業のデジタルシフト・DX実態調査（2025年1月）",
     "東京商工会議所",
     "https://www.tokyo-cci.or.jp/page.jsp?id=1205152"),

    ("日本SMB調査",
     "中小企業のデジタルシフト・DX実態調査 詳細版PDF",
     "東京商工会議所",
     "https://www.tokyo-cci.or.jp/file.jsp?id=1205203"),

    ("日本SMB調査",
     "中小企業AI導入実態調査2026（導入率12%・未活用率88%）",
     "東京新聞×PR TIMES",
     "https://adv.tokyo-np.co.jp/prtimes/article154643/"),

    ("日本SMB調査",
     "令和7年版 情報通信白書 — 企業におけるAI利用の現状",
     "総務省",
     "https://www.soumu.go.jp/johotsusintokei/whitepaper/ja/r07/html/nd112220.html"),

    ("調査・統計",
     "47% of Digital Workers Struggle to Find Information（2022年調査）",
     "Gartner",
     "https://www.gartner.com/en/newsroom/press-releases/2023-05-10-gartner-survey-reveals-47-percent-of-digital-workers-struggle-to-find-the-information-needed-to-effectively-perform-their-jobs"),

    ("競合データ",
     "Glean raises $150M Series F at $7.2B valuation（2025年6月）",
     "TechCrunch",
     "https://techcrunch.com/2025/06/10/enterprise-ai-startup-glean-lands-a-7-2b-valuation/"),

    ("競合データ",
     "Glean hits $200M ARR（2025年12月）",
     "Fortune",
     "https://fortune.com/2025/12/08/exclusive-glean-hits-200-million-arr-up-from-100-million-nine-months-back/"),

    ("競合データ",
     "Glean at $200M ARR — Revenue & Growth Analysis",
     "Sacra",
     "https://sacra.com/research/glean-at-200m-arr/"),

    ("競合データ",
     "Notion crosses $500M revenue riding AI wave（2025年9月）",
     "CNBC",
     "https://www.cnbc.com/2025/09/18/notion-launches-ai-agent-as-it-crosses-500-million-in-annual-revenue.html"),

    ("競合データ",
     "Notion Revenue 2025: $600M ARR, $10B Valuation",
     "Latka",
     "https://getlatka.com/companies/notion"),

    ("競合データ",
     "トヨクモ Research Memo — NotePM ARR 46億円・YoY+59.3%",
     "株探ニュース",
     "https://kabutan.jp/news/marketnews/?b=n202503110577"),

    ("競合データ",
     "トヨクモ 2025年4月 Monthly Report（IR note）",
     "トヨクモ株式会社",
     "https://note.com/toyokumo_ir/n/n8439d3f88d57"),
]

# category → color mapping
CAT_COLORS = {
    "グローバル市場": BLUE,
    "日本市場":       RGBColor(0x05, 0x60, 0xA0),
    "日本SMB調査":    GREEN,
    "調査・統計":     AMBER,
    "競合データ":     ORANGE,
}

prs = Presentation()
prs.slide_width  = SW
prs.slide_height = SH

sl = prs.slides.add_slide(prs.slide_layouts[6])

# ── background
bg = sl.background.fill; bg.solid(); bg.fore_color.rgb = BG

# ── header bar
def rect(slide, x, y, w, h, fill):
    sh = slide.shapes.add_shape(1, x, y, w, h)
    sh.fill.solid(); sh.fill.fore_color.rgb = fill
    sh.line.fill.background()
    return sh

rect(sl, 0, 0, SW, Inches(0.6), NAVY)

# title
tx = sl.shapes.add_textbox(Inches(0.35), Inches(0.08), Inches(10), Inches(0.46))
tf = tx.text_frame; p = tf.paragraphs[0]
r = p.add_run(); r.text = '参考文献一覧（元PDFを除く全19件）'
r.font.size=Pt(17); r.font.bold=True; r.font.color.rgb=WHITE

# date badge
db = sl.shapes.add_textbox(Inches(11.2), Inches(0.1), Inches(1.9), Inches(0.38))
dtf = db.text_frame; dp = dtf.paragraphs[0]; dp.alignment=PP_ALIGN.RIGHT
dr = dp.add_run(); dr.text='調査基準: 2026年6月'
dr.font.size=Pt(8); dr.font.color.rgb=RGBColor(0xCC,0xD8,0xFF)

# ── layout constants
M   = Inches(0.28)
TOP = Inches(0.68)
COL_W  = [Inches(1.55), Inches(4.55), Inches(1.62), Inches(5.12)]
COL_X  = [M,
           M + COL_W[0] + Inches(0.06),
           M + COL_W[0] + Inches(0.06) + COL_W[1] + Inches(0.06),
           M + COL_W[0] + Inches(0.06) + COL_W[1] + Inches(0.06) + COL_W[2] + Inches(0.06)]
ROW_H  = Inches(0.316)
N      = len(refs)

# ── column header row
hdr_y = TOP
hdrh  = Inches(0.28)
hdrs  = ['カテゴリ', '文献・レポート名', '発行元・媒体', 'URL']
for j, (hx, hw, ht) in enumerate(zip(COL_X, COL_W, hdrs)):
    hb = sl.shapes.add_shape(1, hx, hdr_y, hw, hdrh)
    hb.fill.solid(); hb.fill.fore_color.rgb = NAVY2
    hb.line.fill.background()
    htx = sl.shapes.add_textbox(hx+Inches(0.06), hdr_y+Inches(0.03), hw-Inches(0.1), hdrh)
    htf = htx.text_frame; hp = htf.paragraphs[0]
    hr = hp.add_run(); hr.text = ht
    hr.font.size=Pt(8); hr.font.bold=True; hr.font.color.rgb=WHITE

# ── data rows
row_top = TOP + hdrh + Inches(0.03)
ALT = RGBColor(0xE8, 0xEE, 0xFB)

for i, (cat, title, src, url) in enumerate(refs):
    ry = row_top + i * ROW_H
    bg_c = WHITE if i % 2 == 0 else ALT
    cat_c = CAT_COLORS.get(cat, BLUE)

    # row background
    rb = sl.shapes.add_shape(1, M, ry, SW - M*2, ROW_H - Inches(0.02))
    rb.fill.solid(); rb.fill.fore_color.rgb = bg_c
    rb.line.fill.background()

    # left accent bar (category color)
    ab = sl.shapes.add_shape(1, M, ry, Inches(0.04), ROW_H - Inches(0.02))
    ab.fill.solid(); ab.fill.fore_color.rgb = cat_c
    ab.line.fill.background()

    cells = [cat, title, src, url]
    for j, (cx, cw, val) in enumerate(zip(COL_X, COL_W, cells)):
        ctx = sl.shapes.add_textbox(cx + Inches(0.07), ry + Inches(0.04),
                                    cw - Inches(0.1), ROW_H - Inches(0.05))
        ctf = ctx.text_frame; ctf.word_wrap = True
        cp = ctf.paragraphs[0]
        cr = cp.add_run(); cr.text = val
        if j == 0:   # category
            cr.font.size=Pt(7.5); cr.font.bold=True; cr.font.color.rgb=cat_c
        elif j == 3: # URL
            cr.font.size=Pt(6.5); cr.font.color.rgb=BLUE
        elif j == 2: # source
            cr.font.size=Pt(7.5); cr.font.bold=True; cr.font.color.rgb=GRAY
        else:        # title
            cr.font.size=Pt(8); cr.font.color.rgb=RGBColor(0x1F,0x29,0x37)

# ── footer
fy = SH - Inches(0.26)
fb = sl.shapes.add_shape(1, 0, fy, SW, Inches(0.26))
fb.fill.solid(); fb.fill.fore_color.rgb = NAVY
fb.line.fill.background()
ftx = sl.shapes.add_textbox(Inches(0.3), fy+Inches(0.04), SW-Inches(0.6), Inches(0.2))
ftf = ftx.text_frame; fp = ftf.paragraphs[0]; fp.alignment=PP_ALIGN.LEFT
fr = fp.add_run()
fr.text = 'AI Knowledge株式会社 — 市場調査・競合分析レポート 参考文献  |  調査基準日: 2026年6月7日  |  CONFIDENTIAL'
fr.font.size=Pt(7); fr.font.color.rgb=RGBColor(0xAA,0xBB,0xDD)

out = '/Users/kurosuzu/Desktop/参考文献一覧.pptx'
prs.save(out)
print(f'✅  {out}')
