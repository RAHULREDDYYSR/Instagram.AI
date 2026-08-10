"""Custom PDF: The Cat & The Fire — Two Scripts, One Truth. Magazine-quality compilation."""
from pathlib import Path
import re
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, NextPageTemplate, PageBreak,
    Paragraph, Spacer, Table, TableStyle, KeepTogether,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

# ── Paths ──
SCRIPTS = [
    "The_Cat_I_Brought_Her_Inside_She_Kept_Running_Back.md",
    "The_Fire_I_Kept_Feeding_It_It_Only_Knew_How_to_Burn.md",
]
SCRIPTS_DIR = Path("Brain/Scripts")
OUTPUT = Path("Brain/Scripts/The_Cat_And_The_Fire_2_Scripts.pdf")

# ── Premium palette (crimson + burnt orange fire theme) ──
CREAM     = HexColor("#fbf9f4")   # warm paper
INK       = HexColor("#1e1e24")   # deep charcoal
INK_SOFT  = HexColor("#5a5c64")   # secondary text
CRIMSON   = HexColor("#8b1a1a")   # deep crimson accent
BURNT     = HexColor("#b8451a")   # burnt orange / rust
GOLD      = HexColor("#b8952e")   # kept for legacy compatibility
RULE      = HexColor("#d8d2c7")   # thin beige rules
SHADE     = HexColor("#f6f2ea")   # zebra / callout background
SHADE2    = HexColor("#ede8de")   # grid lines
HEADER_BG = HexColor("#1a1a22")   # table header bg
GOOD      = HexColor("#3d6b4b")
WARN      = HexColor("#a07b3f")
BAD       = HexColor("#8b3a3a")

EMOJI_MAP = {
    "\U0001F516":"[SAVE]","\U0001F511":"[KEY]","\U0001F3C6":"[TROPHY]",
    "\U0001F4CC":"[PIN]","\U0001F4A1":"[BULB]","\u2705":"[OK]",
    "\U0001F525":"[FIRE]","\U0001F4AA":"[FLEX]","\u2728":"[*]",
    "\U0001F308":"[*]","\U0001F31F":"[*]","\u26A1":"[!]",
}

def strip_emoji(t):
    for k,v in EMOJI_MAP.items(): t=t.replace(k,v)
    return re.sub(r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF]","",t)

def esc(t):
    t = t.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    t = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', t)
    t = t.replace("__","")
    return t

# ── Style catalogue ──
def build_styles():
    return {
        # Cover
        "cover_tag":   ParagraphStyle("ctg",fontName="Times-Roman",fontSize=9,leading=12,
                                      textColor=CRIMSON,alignment=TA_LEFT),
        "cover_h1":    ParagraphStyle("ch1",fontName="Times-Roman",fontSize=48,leading=52,
                                      textColor=INK),
        "cover_h2":    ParagraphStyle("ch2",fontName="Times-BoldItalic",fontSize=48,leading=52,
                                      textColor=BURNT),
        "cover_sub":   ParagraphStyle("cs",fontName="Times-Italic",fontSize=14,leading=22,
                                      textColor=INK_SOFT),
        "cover_line":  ParagraphStyle("cl",fontName="Times-Roman",fontSize=10,leading=16,
                                      textColor=INK_SOFT,alignment=TA_CENTER),
        "cover_foot":  ParagraphStyle("cf",fontName="Times-Italic",fontSize=8.5,leading=12,
                                      textColor=INK_SOFT),
        # TOC
        "toc_num":     ParagraphStyle("tn",fontName="Times-Roman",fontSize=28,leading=32,
                                      textColor=BURNT,alignment=TA_CENTER),
        "toc_title":   ParagraphStyle("tt",fontName="Times-Roman",fontSize=15,leading=22,
                                      textColor=INK),
        "toc_meta":    ParagraphStyle("tm",fontName="Times-Italic",fontSize=9,leading=14,
                                      textColor=INK_SOFT,alignment=TA_RIGHT),
        # Chapter header
        "kicker":      ParagraphStyle("k",fontName="Times-Roman",fontSize=8.5,leading=12,
                                      textColor=BURNT,spaceAfter=2),
        "script_title":ParagraphStyle("st",fontName="Times-Roman",fontSize=34,leading=38,
                                      textColor=INK,spaceAfter=4),
        "script_sub":  ParagraphStyle("ss",fontName="Times-Italic",fontSize=11.5,leading=16,
                                      textColor=INK_SOFT,spaceAfter=8),
        # Rubric badge
        "badge_num":   ParagraphStyle("bn",fontName="Times-Roman",fontSize=20,leading=24,
                                      textColor=INK,alignment=TA_CENTER),
        "badge_lbl":   ParagraphStyle("bl",fontName="Times-Roman",fontSize=8,leading=11,
                                      textColor=INK_SOFT,alignment=TA_CENTER),
        # Hooks
        "hook_label":  ParagraphStyle("hl",fontName="Times-Roman",fontSize=8.5,leading=12,
                                      textColor=BURNT,spaceBefore=2),
        "hook_text_p": ParagraphStyle("hx",fontName="Times-Roman",fontSize=10.5,leading=16,
                                      textColor=INK,spaceAfter=2),
        "hook_why_p":  ParagraphStyle("hw",fontName="Times-Italic",fontSize=9.5,leading=14,
                                      textColor=INK_SOFT,spaceAfter=2),
        # Body / structure
        "h2":          ParagraphStyle("h2",fontName="Times-Roman",fontSize=13.5,leading=18,
                                       textColor=INK,spaceBefore=12,spaceAfter=4,
                                       keepWithNext=2),
        "h3":          ParagraphStyle("h3",fontName="Times-Roman",fontSize=11,leading=15,
                                       textColor=BURNT,spaceBefore=8,spaceAfter=2,
                                       keepWithNext=2),
        "body":        ParagraphStyle("b",fontName="Times-Roman",fontSize=10.5,leading=14,
                                      textColor=INK,spaceAfter=4),
        "tag_body":    ParagraphStyle("tb",fontName="Times-Roman",fontSize=10,leading=14,
                                      textColor=INK_SOFT),
        "ts_pill":     ParagraphStyle("tsp",fontName="Times-Roman",fontSize=10,leading=12,
                                      textColor=BURNT,alignment=TA_LEFT),
        # Closing
        "close_title": ParagraphStyle("clo",fontName="Times-Roman",fontSize=22,leading=30,
                                      textColor=INK,alignment=TA_CENTER),
        "close_text":  ParagraphStyle("clt",fontName="Times-Italic",fontSize=12,leading=20,
                                      textColor=INK,alignment=TA_CENTER),
        "close_foot":  ParagraphStyle("clf",fontName="Times-Italic",fontSize=10,leading=14,
                                      textColor=INK_SOFT,alignment=TA_CENTER),
    }


# ═══════════════════════════════════════════════════════════════
#  DATA EXTRACTION
# ═══════════════════════════════════════════════════════════════

def extract_metadata(md_text):
    """Extract structured metadata from a script .md file."""
    data = {}

    # Concept line
    m = re.search(r'\*\*Concept \(1 line\):\*\*\s*(.+?)(?:\n|$)', md_text)
    data['concept'] = m.group(1).strip() if m else ""

    # Rubric total score
    m = re.search(r'\*\*Total\*\*\s*\|\s*\*?\*?(\d+)/80\*?\*?', md_text)
    data['rubric_score'] = int(m.group(1)) if m else 0

    # Target length
    m = re.search(r'\*\*Target length:\*\*\s*(\d+)\s*seconds', md_text)
    data['length'] = m.group(1) if m else "?"

    # CTA
    m = re.search(r'\*\*CTA:\*\*\s*(.+?)(?:\n|$)', md_text)
    data['cta'] = m.group(1).strip() if m else ""

    # Hook alternatives (state machine within ## Hook Alternatives section)
    hooks = []
    in_hook_section = False
    current_label = ""
    lines = md_text.splitlines()
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("## Hook Alternatives"):
            in_hook_section = True
            continue
        if not in_hook_section:
            continue
        if s.startswith("## ") or s.startswith("# ") or s == "---":
            in_hook_section = False
            continue
        m_h = re.match(r"^###\s+(Alt \d).*$", s)
        if m_h:
            current_label = m_h.group(1)
            continue
        if current_label:
            m_q = re.match(r'^\*\*"(.+)"\*\*$', s)
            if m_q:
                hooks.append({
                    'label': current_label,
                    'text': m_q.group(1),
                    'why': '',
                })
                current_label = ""
                # Next line should be the *Why it wins:* line
                if i+1 < len(lines):
                    why_line = lines[i+1].strip()
                    m_why = re.match(r'^\*(.+)$', why_line)
                    if m_why:
                        hooks[-1]['why'] = m_why.group(1).strip()
                continue
    data['hooks'] = hooks

    # Thumbnail concept
    m = re.search(r'### Thumbnail concept\n(.+?)(?=\n###|\n\n\*\*|\Z)', md_text, re.DOTALL)
    data['thumbnail'] = m.group(1).strip() if m else ""

    # Instagram caption
    m = re.search(r'### Full Instagram caption\n(.+)', md_text, re.DOTALL)
    data['caption'] = m.group(1).strip() if m else ""

    return data


def extract_timestamp_blocks(md_text):
    """Extract timestamp blocks from the 'Final Script' section."""
    blocks = []
    in_final = False
    current = None

    for line in md_text.splitlines():
        s = line.strip()

        if s.startswith("## Final Script"):
            in_final = True
            continue
        if not in_final:
            continue
        if (s.startswith("---") and current and
            (current.get('voice') or current.get('visual'))):
            if current:
                blocks.append(current)
                current = None
            continue
        if s.startswith("## Thumbnail") or s.startswith("## Rubric"):
            if current and (current.get('voice') or current.get('visual')):
                blocks.append(current)
            break

        # Timestamp heading: ### 0:00–0:03  (en-dash or regular)
        m = re.match(r"^###\s+(\d+:\d+[\u2013\u2014\-]\d+:\d+)\s*$", s)
        if m:
            if current and (current.get('voice') or current.get('visual')):
                blocks.append(current)
            current = {'timestamp': m.group(1), 'voice': '', 'visual': '', 'on_screen': ''}
            continue

        if current is None:
            continue

        if s.startswith("**Voice:**"):
            current['voice'] = strip_emoji(s[len("**Voice:**"):].strip().strip('"'))
        elif s.startswith("**Visual:**"):
            current['visual'] = strip_emoji(s[len("**Visual:**"):].strip())
        elif s.startswith("**On-Screen Text:**"):
            current['on_screen'] = strip_emoji(s[len("**On-Screen Text:**"):].strip())

    if current and (current.get('voice') or current.get('visual')):
        blocks.append(current)

    return blocks


# ═══════════════════════════════════════════════════════════════
#  PAGE DECORATOR
# ═══════════════════════════════════════════════════════════════

class PageDeco:
    def __init__(self, label="", show_header=True, show_page_num=True):
        self.label = label
        self.show_header = show_header
        self.show_page_num = show_page_num

    def __call__(self, canv, doc):
        canv.saveState()
        pw, ph = LETTER

        if self.show_header and self.label:
            canv.setStrokeColor(BURNT)
            canv.setLineWidth(0.3)
            canv.line(1*inch, ph-0.55*inch, pw-1*inch, ph-0.55*inch)
            canv.setFont("Times-Roman", 7.5)
            canv.setFillColor(BURNT)
            canv.drawString(1*inch, ph-0.53*inch, "TWO SCRIPTS \u00b7 ONE TRUTH")
            canv.setFillColor(INK_SOFT)
            canv.drawRightString(pw-1*inch, ph-0.53*inch, self.label.upper())

        if self.show_page_num:
            canv.setStrokeColor(RULE)
            canv.setLineWidth(0.2)
            canv.line(1*inch, 0.55*inch, pw-1*inch, 0.55*inch)
            canv.setFont("Times-Italic", 8)
            canv.setFillColor(INK_SOFT)
            canv.drawRightString(pw-1*inch, 0.42*inch, f"Instagram.AI \u00b7 p. {doc.page}")

        canv.restoreState()


# ═══════════════════════════════════════════════════════════════
#  BUILDERS
# ═══════════════════════════════════════════════════════════════

def build_cover(story, styles):
    """Build the magazine-style cover page."""
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph("AUGUST 2026  \u00b7  SCRIPT COMPILATION", styles["cover_tag"]))
    story.append(Spacer(1, 0.5*inch))
    story.append(Paragraph("Two Scripts,", styles["cover_h1"]))
    story.append(Paragraph("One Truth", styles["cover_h2"]))
    story.append(Spacer(1, 0.15*inch))

    # Burnt-orange accent rule
    rule = Table([[""]], colWidths=[2.2*inch], rowHeights=[0.02*inch],
                 style=TableStyle([("BACKGROUND", (0,0), (-1,-1), BURNT)]))
    story.append(rule)
    story.append(Spacer(1, 0.15*inch))

    story.append(Paragraph(
        "Loving Her Was Easy. Watching Her Go Back Was The Hard Part.",
        styles["cover_sub"]
    ))
    story.append(Spacer(1, 0.08*inch))
    story.append(Paragraph(
        "Same concept. Two metaphors. Shoot the one that feels like you.",
        styles["cover_line"]
    ))
    story.append(Spacer(1, 0.35*inch))

    # Double hairline divider
    rule2 = Table([[""]], colWidths=[7.5*inch], rowHeights=[0.01*inch],
                  style=TableStyle([("BACKGROUND", (0,0), (-1,-1), RULE)]))
    story.append(rule2)
    story.append(Spacer(1, 0.04*inch))
    story.append(rule2)
    story.append(Spacer(1, 0.22*inch))

    # Chapter list (TOC)
    chapters = [
        ("01", "The Cat",
         "I Brought Her Inside. She Kept Running Back.",
         "36s \u00b7 vulnerable \u00b7 53/80"),
        ("02", "The Fire",
         "I Kept Feeding It. It Only Knew How to Burn.",
         "37s \u00b7 dramatic \u00b7 55/80"),
    ]
    toc_rows = []
    for num, title, subtitle, meta in chapters:
        toc_rows.append([
            Paragraph(num, styles["toc_num"]),
            Paragraph(f"<b>{title}</b><br/>"
                      f'<font size="10" color="{INK_SOFT.hexval()}">{subtitle}</font>',
                      styles["toc_title"]),
            Paragraph(meta, styles["toc_meta"]),
        ])

    toc = Table(toc_rows, colWidths=[0.6*inch, 4.5*inch, 2.4*inch])
    toc.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LINEBELOW", (0,0), (-1,-2), 0.4, RULE),
        # Alternate row shading — row 1 gets shade
        ("BACKGROUND", (0,1), (-1,1), SHADE),
    ]))
    story.append(toc)
    story.append(Spacer(1, 0.25*inch))
    story.append(Paragraph("Instagram.AI  \u00b7  Script Intelligence Pipeline", styles["cover_foot"]))


def rubric_badge(score, styles):
    """Small visual badge showing X/80."""
    pct = (score / 80) * 100
    color = "#3d6b4b" if pct >= 65 else ("#a07b3f" if pct >= 55 else "#8b3a3a")
    accent = HexColor(color)

    inner = Table([
        [Paragraph(f"{score}<font size='9' color='{INK_SOFT.hexval()}'>/80</font>",
                   styles["badge_num"])],
        [Paragraph("RUBRIC", styles["badge_lbl"])],
    ], colWidths=[0.75*inch])
    inner.setStyle(TableStyle([
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (0,0), 7),
        ("BOTTOMPADDING", (0,1), (0,1), 6),
        ("BOX", (0,0), (-1,-1), 1.2, accent),
        ("BACKGROUND", (0,0), (-1,-1), SHADE),
    ]))
    return inner


def build_script_chapter(story, md_text, styles, chapter_num, script_title, subtitle):
    """Build one complete script chapter."""
    data = extract_metadata(md_text)
    blocks = extract_timestamp_blocks(md_text)

    # ── Chapter opener ──
    story.append(KeepTogether([
        Table([[""]], colWidths=[7.5*inch], rowHeights=[0.03*inch],
              style=TableStyle([("BACKGROUND", (0,0), (-1,-1), BURNT)])),
        Spacer(1, 0.18*inch),
        Paragraph(f"CHAPTER {chapter_num:02d}", styles["kicker"]),
        Paragraph(script_title, styles["script_title"]),
        Paragraph(subtitle, styles["script_sub"]),
    ]))
    story.append(Spacer(1, 0.12*inch))

    # ── Metaphor + Rubric badge ──
    metaphor_text = data.get('concept', '')
    if len(metaphor_text) > 250:
        metaphor_text = metaphor_text[:250] + "\u2026"

    # The metaphor + badge as a KeepTogether table row
    meta_row = Table([
        [
            Paragraph(
                f'<font color="{BURNT.hexval()}" size="9"><b>METAPHOR</b></font><br/>'
                f'{esc(metaphor_text)}',
                styles["tag_body"]),
            rubric_badge(data.get('rubric_score', 0), styles),
        ]
    ], colWidths=[6.45*inch, 1.05*inch])
    meta_row.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (0,0), 0),
        ("RIGHTPADDING", (0,1), (0,1), 0),
    ]))
    story.append(KeepTogether(meta_row))
    story.append(Spacer(1, 0.18*inch))

    # ── Alternative Hooks ──
    story.append(KeepTogether([
        Table([[""]], colWidths=[7.5*inch], rowHeights=[0.012*inch],
              style=TableStyle([("BACKGROUND", (0,0), (-1,-1), RULE)])),
        Spacer(1, 0.06*inch),
        Paragraph("ALTERNATIVE HOOKS", styles["h3"]),
    ]))
    story.append(Spacer(1, 0.04*inch))

    hooks = data.get('hooks', [])
    for h in hooks:
        hook_elems = [
            Paragraph(f'<b>{h["label"]}</b>', styles["hook_label"]),
            Paragraph(f'\u201c{esc(h["text"])}\u201d', styles["hook_text_p"]),
        ]
        if h.get('why'):
            hook_elems.append(Paragraph(esc(h["why"]), styles["hook_why_p"]))

        hook_block = Table([[e] for e in hook_elems], colWidths=[7.5*inch])
        hook_block.setStyle(TableStyle([
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("LEFTPADDING", (0,0), (-1,-1), 12),
            ("RIGHTPADDING", (0,0), (-1,-1), 12),
            ("TOPPADDING", (0,0), (-1,-1), 8),
            ("BOTTOMPADDING", (0,0), (-1,-1), 8),
            ("BACKGROUND", (0,0), (-1,-1), SHADE),
            ("LINEBEFORE", (0,0), (0,-1), 3, BURNT),
            ("TOPPADDING", (0,0), (0,0), 10),
            ("BOTTOMPADDING", (0,-1), (0,-1), 10),
        ]))
        story.append(hook_block)
        story.append(Spacer(1, 0.06*inch))

    # ── Full Shooting Script ──
    story.append(Spacer(1, 0.04*inch))
    story.append(KeepTogether([
        Table([[""]], colWidths=[7.5*inch], rowHeights=[0.012*inch],
              style=TableStyle([("BACKGROUND", (0,0), (-1,-1), RULE)])),
        Spacer(1, 0.06*inch),
        Paragraph("FULL SHOOTING SCRIPT", styles["h2"]),
    ]))
    story.append(Spacer(1, 0.04*inch))

    # Timestamp blocks — sticky-head strategy
    for block in blocks:
        elements = []

        # Timestamp pill
        elements.append(Paragraph(
            f'\u2014\u2002{block["timestamp"]}\u2002\u2014',
            styles["ts_pill"]))
        elements.append(Spacer(1, 2))

        # Voice
        if block.get('voice'):
            elements.append(Paragraph(
                f'<font color="{BURNT.hexval()}" size="9"><b>Voice:</b></font> '
                f'{esc(strip_emoji(block["voice"]))}',
                styles["body"]))
        # Visual
        if block.get('visual'):
            elements.append(Paragraph(
                f'<font color="{BURNT.hexval()}" size="9"><b>Visual:</b></font> '
                f'{esc(strip_emoji(block["visual"]))}',
                styles["body"]))
        # On-Screen Text
        if block.get('on_screen'):
            elements.append(Paragraph(
                f'<font color="{BURNT.hexval()}" size="9"><b>On-Screen Text:</b></font> '
                f'{esc(strip_emoji(block["on_screen"]))}',
                styles["body"]))

        elements.append(Spacer(1, 4))

        # Sticky-head: KeepTogether(heading + spacer + first body line)
        if len(elements) >= 3:
            story.append(KeepTogether(elements[:3]))
            for item in elements[3:]:
                story.append(item)
        else:
            story.append(KeepTogether(elements))

    # ── Thumbnail ──
    story.append(Spacer(1, 0.06*inch))
    story.append(KeepTogether([
        Table([[""]], colWidths=[7.5*inch], rowHeights=[0.012*inch],
              style=TableStyle([("BACKGROUND", (0,0), (-1,-1), RULE)])),
        Spacer(1, 0.06*inch),
        Paragraph("THUMBNAIL CONCEPT", styles["h2"]),
    ]))

    thumb = data.get('thumbnail', '')
    if thumb:
        thumb_block = Table([
            [Paragraph(esc(thumb), styles["body"])]
        ], colWidths=[7.5*inch])
        thumb_block.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), SHADE),
            ("LEFTPADDING", (0,0), (-1,-1), 14),
            ("RIGHTPADDING", (0,0), (-1,-1), 14),
            ("TOPPADDING", (0,0), (-1,-1), 12),
            ("BOTTOMPADDING", (0,0), (-1,-1), 12),
            ("LINEBEFORE", (0,0), (0,-1), 3, BURNT),
        ]))
        story.append(thumb_block)

    # ── Instagram Caption ──
    story.append(Spacer(1, 0.08*inch))
    story.append(Paragraph("INSTAGRAM CAPTION", styles["h2"]))

    caption = data.get('caption', '')
    if caption:
        for cl in caption.split('\n'):
            cs = cl.strip()
            if not cs:
                continue
            # Labels like **Hook:** **Body:** **CTA:** **Hashtags:**
            if cs.startswith("**") and ":**" in cs:
                label_text = cs.replace("**", "").strip()
                story.append(Paragraph(f'<b>{esc(strip_emoji(label_text))}</b>', styles["body"]))
            else:
                story.append(Paragraph(esc(strip_emoji(cs)), styles["body"]))

    story.append(Spacer(1, 0.15*inch))


def build_closing(story, styles):
    """Build the closing / note page."""
    story.append(Spacer(1, 1.5*inch))

    # Centered crimson rule
    rule = Table([[""]], colWidths=[1.5*inch], rowHeights=[0.025*inch],
                 style=TableStyle([("BACKGROUND", (0,0), (-1,-1), BURNT),
                                   ("ALIGN", (0,0), (-1,-1), "CENTER")]))
    rule.hAlign = "CENTER"
    story.append(rule)
    story.append(Spacer(1, 0.3*inch))

    story.append(Paragraph("A Final Note", styles["close_title"]))
    story.append(Spacer(1, 0.25*inch))

    closing_text = (
        "Pick the metaphor that matches your face. "
        "The Fire is more dramatic, more masculine, more destructive. "
        "The Cat is quieter, more emotional, more vulnerable. "
        "Both are you. Shoot the one that doesn\u2019t make you perform."
    )

    wrap = Table([
        [Paragraph(closing_text, styles["close_text"])]
    ], colWidths=[5.5*inch])
    wrap.setStyle(TableStyle([
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("LEFTPADDING", (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
    ]))
    wrap.hAlign = "CENTER"
    story.append(wrap)

    story.append(Spacer(1, 0.5*inch))

    rule2 = Table([[""]], colWidths=[1.5*inch], rowHeights=[0.025*inch],
                  style=TableStyle([("BACKGROUND", (0,0), (-1,-1), BURNT),
                                    ("ALIGN", (0,0), (-1,-1), "CENTER")]))
    rule2.hAlign = "CENTER"
    story.append(rule2)
    story.append(Spacer(1, 0.3*inch))

    story.append(Paragraph(
        "Instagram.AI \u00b7 Script Intelligence Pipeline \u00b7 August 2026",
        styles["close_foot"]
    ))


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    styles = build_styles()
    margin = 1 * inch

    doc = BaseDocTemplate(
        str(OUTPUT),
        pagesize=LETTER,
        leftMargin=margin, rightMargin=margin,
        topMargin=0.85*inch, bottomMargin=0.7*inch,
        title="Two Scripts, One Truth \u2014 The Cat & The Fire",
        author="Instagram.AI",
    )

    # ── Assemble story ──
    story = []
    build_cover(story, styles)

    chapter_labels = ["THE CAT", "THE FIRE"]
    subtitles = [
        "I Brought Her Inside. She Kept Running Back. \u00b7 36s \u00b7 vulnerable register",
        "I Kept Feeding It. It Only Knew How to Burn. \u00b7 37s \u00b7 dramatic register",
    ]

    for i, (name, label, sub) in enumerate(zip(SCRIPTS, chapter_labels, subtitles)):
        story.append(NextPageTemplate(f"s{i}"))
        story.append(PageBreak())
        md_path = SCRIPTS_DIR / name
        md_text = md_path.read_text(encoding="utf-8")
        build_script_chapter(story, md_text, styles, i + 1, label, sub)

    # Closing page
    story.append(NextPageTemplate("closing"))
    story.append(PageBreak())
    build_closing(story, styles)

    # ── Page templates ──
    # Cover: no header, no page number
    cf = Frame(margin, 0.7*inch, LETTER[0]-2*margin, LETTER[1]-1.4*inch, id="cover")
    ct = PageTemplate(id="cover", frames=[cf],
                      onPage=PageDeco("", show_header=False, show_page_num=False))
    doc.addPageTemplates([ct])

    # Script chapters: header + page number
    for i, label in enumerate(chapter_labels):
        f = Frame(margin, 0.85*inch, LETTER[0]-2*margin, LETTER[1]-1.7*inch, id=f"s{i}")
        t = PageTemplate(id=f"s{i}", frames=[f], onPage=PageDeco(label))
        doc.addPageTemplates([t])

    # Closing: no header, no page number
    cf2 = Frame(margin, 0.7*inch, LETTER[0]-2*margin, LETTER[1]-1.4*inch, id="closing")
    ct2 = PageTemplate(id="closing", frames=[cf2],
                       onPage=PageDeco("", show_header=False, show_page_num=False))
    doc.addPageTemplates([ct2])

    doc.build(story)
    return OUTPUT


if __name__ == "__main__":
    out = main()
    size_kb = out.stat().st_size / 1024
    print(f"Built: {out.resolve()}")
    print(f"Size: {size_kb:.1f} KB")
