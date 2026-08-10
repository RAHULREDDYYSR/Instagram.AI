"""Premium PDF of 1–3 reel scripts — v5 luxury edition (generic build_pdf).

The premium renderer is exposed as build_pdf(script_paths, output_path,
topic=None) and via a flexible CLI (--scripts / --output / --topic). It
dynamically parses every script file (title, length, pillars, score, core
concept, hook teaser) instead of hardcoding filenames, titles, stats,
subtitles or hooks.

Legacy no-argument default (running with no flags) keeps the two-script
selection in SCRIPTS/OUTPUT below.
"""
from pathlib import Path
import argparse
import re
import sys
from datetime import date
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, white
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, NextPageTemplate, PageBreak,
    Paragraph, Spacer, Table, TableStyle, ListFlowable, ListItem, KeepTogether,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

SCRIPTS = ["The_Two_Bodies_You_Were_Chasing_At_16.md", "The_Two_Men_You_Wanted_To_Become.md"]
SCRIPTS_DIR = Path("Brain/Scripts")
OUTPUT = Path("Brain/Scripts/_pdfs/The_Two_Bodies__The_Two_Men.pdf")

# ── Premium palette ──
CREAM   = HexColor("#fbf9f4")
INK     = HexColor("#1e1e24")
INK_SOFT= HexColor("#5a5c64")
GOLD    = HexColor("#b8952e")
GOLD_LT = HexColor("#e8d396")
GOLD_PALE=HexColor("#f4ecd8")
RULE    = HexColor("#d8d2c7")
SHADE   = HexColor("#f6f2ea")
SHADE2  = HexColor("#ede8de")
GOOD    = HexColor("#3d6b4b")
WARN    = HexColor("#a07b3f")
BAD     = HexColor("#8b3a3a")
HEADING_BG = HexColor("#242530")

EMOJI_MAP = {
    "\U0001F516":"[SAVE]","\U0001F511":"[KEY]","\U0001F3C6":"[TROPHY]",
    "\U0001F4CC":"[PIN]","\U0001F4A1":"[BULB]","\u2705":"[OK]",
    "\U0001F525":"[FIRE]","\U0001F4AA":"[FLEX]","\u2728":"[*]",
}

def strip_emoji(t):
    for k,v in EMOJI_MAP.items(): t=t.replace(k,v)
    return re.sub(r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF]","",t)

def esc(t):
    t=t.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    t=re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', t)
    t=t.replace("__","")
    return t

# ── Styles ──
def build_styles():
    return {
        "cover_tag":   ParagraphStyle("ctg",fontName="Times-Roman",fontSize=9,leading=12,
                                      textColor=GOLD_LT,alignment=TA_LEFT),
        "cover_h1":    ParagraphStyle("ch1",fontName="Times-Roman",fontSize=56,leading=60,
                                      textColor=INK),
        "cover_h2":    ParagraphStyle("ch2",fontName="Times-BoldItalic",fontSize=56,leading=60,
                                      textColor=GOLD),
        "cover_sub":   ParagraphStyle("cs",fontName="Times-Roman",fontSize=13,leading=20,
                                      textColor=INK_SOFT),
        "cover_foot":  ParagraphStyle("cf",fontName="Times-Italic",fontSize=8.5,leading=12,
                                      textColor=INK_SOFT),
        "stat_num":    ParagraphStyle("sn",fontName="Times-Roman",fontSize=44,leading=48,
                                      textColor=GOLD,alignment=TA_CENTER),
        "stat_lbl":    ParagraphStyle("sl",fontName="Times-Roman",fontSize=10,leading=14,
                                      textColor=INK_SOFT,alignment=TA_CENTER),
        "toc_num":     ParagraphStyle("tn",fontName="Times-Roman",fontSize=28,leading=32,
                                      textColor=GOLD,alignment=TA_CENTER),
        "toc_title":   ParagraphStyle("tt",fontName="Times-Roman",fontSize=14,leading=20,
                                      textColor=INK),
        "toc_meta":    ParagraphStyle("tm",fontName="Times-Italic",fontSize=9,leading=14,
                                      textColor=INK_SOFT,alignment=TA_RIGHT),
        "kicker":      ParagraphStyle("k",fontName="Times-Roman",fontSize=8.5,leading=12,
                                      textColor=GOLD,spaceAfter=2,
                                      alignment=TA_LEFT),
        "script_title":ParagraphStyle("st",fontName="Times-Roman",fontSize=38,leading=42,
                                      textColor=INK,spaceAfter=4),
        "script_sub":  ParagraphStyle("ss",fontName="Times-Italic",fontSize=11.5,leading=16,
                                      textColor=INK_SOFT,spaceAfter=8),
        "big_score":   ParagraphStyle("bs",fontName="Times-Roman",fontSize=22,leading=26,
                                      textColor=INK),
        "hook_teaser": ParagraphStyle("ht",fontName="Times-Italic",fontSize=10.5,leading=15,
                                      textColor=INK_SOFT),
        "h1":          ParagraphStyle("h1",fontName="Times-Roman",fontSize=19,leading=24,
                                      textColor=INK,spaceBefore=6,spaceAfter=6),
        "h2":          ParagraphStyle("h2",fontName="Times-Roman",fontSize=13.5,leading=18,
                                       textColor=INK,spaceBefore=14,spaceAfter=4,
                                       keepWithNext=2),
        "h3":          ParagraphStyle("h3",fontName="Times-Roman",fontSize=11,leading=15,
                                       textColor=GOLD,spaceBefore=8,spaceAfter=2,
                                       keepWithNext=2),
        "body":        ParagraphStyle("b",fontName="Times-Roman",fontSize=10.5,leading=14,
                                      textColor=INK,spaceAfter=4),
        "bullet":      ParagraphStyle("bu",fontName="Times-Roman",fontSize=10.5,leading=14,
                                      textColor=INK,spaceAfter=1),
        "quote_text":  ParagraphStyle("qt",fontName="Times-Italic",fontSize=11,leading=17,
                                      textColor=INK),
        "cell":        ParagraphStyle("ce",fontName="Times-Roman",fontSize=9.5,leading=13,
                                      textColor=INK),
        "th":          ParagraphStyle("th",fontName="Times-Roman",fontSize=9.5,leading=13,
                                      textColor=CREAM),
        "ts_pill":     ParagraphStyle("tsp",fontName="Times-Roman",fontSize=10,leading=12,
                                      textColor=GOLD,alignment=TA_LEFT),
    }

# ── Cover ──
def _avg_stat(metas, key, convert, fmt):
    """Mean of a parsed stat across scripts; '—' when none are available."""
    vals = []
    for m in metas:
        v = m.get(key)
        if v is None or v == "":
            continue
        try:
            vals.append(convert(v))
        except (TypeError, ValueError):
            continue
    if not vals:
        return "\u2014"
    return fmt(sum(vals) / len(vals))

def cover_page(story, styles, metas, topic=None):
    n = len(metas)
    story.append(Spacer(1,0.25*inch))
    story.append(Paragraph("VOLUME I  \u00b7  " + date.today().strftime("%B %Y").upper(),
                           styles["cover_tag"]))
    story.append(Spacer(1,0.35*inch))
    story.append(Paragraph("REEL SCRIPT",styles["cover_h1"]))
    story.append(Paragraph("PLAYBOOK",styles["cover_h2"]))
    story.append(Spacer(1,0.1*inch))
    rule = Table([[""]],colWidths=[1.6*inch],rowHeights=[0.015*inch],
                 style=TableStyle([("BACKGROUND",(0,0),(-1,-1),GOLD)]))
    story.append(rule)
    story.append(Spacer(1,0.12*inch))
    sub = f"{n} ready-to-shoot script{'s' if n != 1 else ''}. Distilled from the pipeline."
    if topic:
        topic_clean = strip_emoji(topic).strip()
        if topic_clean:
            sub += "  \u00b7  " + esc(topic_clean)
    story.append(Paragraph(sub,styles["cover_sub"]))
    story.append(Spacer(1,0.25*inch))
    avg_len   = _avg_stat(metas, "length_secs", int,   lambda v: f"{v:.0f}s")
    avg_score = _avg_stat(metas, "score",        float, lambda v: f"{v:.1f}")
    stats = Table([[
        Paragraph(str(n),styles["stat_num"]),
        Paragraph(avg_len,styles["stat_num"]),
        Paragraph(avg_score,styles["stat_num"]),
    ],[
        Paragraph("scripts",styles["stat_lbl"]),
        Paragraph("avg. length",styles["stat_lbl"]),
        Paragraph("avg. rating",styles["stat_lbl"]),
    ]],colWidths=[2.5*inch,2.5*inch,2.5*inch])
    stats.setStyle(TableStyle([
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("ALIGN",(0,0),(-1,-1),"CENTER"),
        ("TOPPADDING",(0,0),(-1,0),2),("BOTTOMPADDING",(0,0),(-1,0),0),
        ("TOPPADDING",(0,1),(-1,1),0),("BOTTOMPADDING",(0,1),(-1,1),2),
    ]))
    story.append(stats)
    story.append(Spacer(1,0.2*inch))
    rule2 = Table([[""]],colWidths=[7.5*inch],rowHeights=[0.01*inch],
                  style=TableStyle([("BACKGROUND",(0,0),(-1,-1),RULE)]))
    story.append(rule2)
    story.append(Spacer(1,0.04*inch))
    story.append(rule2)
    story.append(Spacer(1,0.2*inch))
    toc_rows = []
    for i,meta in enumerate(metas,1):
        meta_line = "  \u00b7  ".join(x for x in
                                      (meta["length_label"], meta["pillars"]) if x)
        toc_rows.append([
            Paragraph(f'{i:02d}',styles["toc_num"]),
            Paragraph(esc(strip_emoji(meta["title"])),styles["toc_title"]),
            Paragraph(esc(meta_line) if meta_line else "\u2014",styles["toc_meta"]),
        ])
    toc = Table(toc_rows,colWidths=[0.6*inch,4.2*inch,2.7*inch])
    toc.setStyle(TableStyle([
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("LEFTPADDING",(0,0),(-1,-1),8),
        ("RIGHTPADDING",(0,0),(-1,-1),8),
        ("TOPPADDING",(0,0),(-1,-1),9),
        ("BOTTOMPADDING",(0,0),(-1,-1),9),
        ("LINEBELOW",(0,0),(-1,-2),0.4,RULE),
    ]))
    story.append(toc)
    story.append(Spacer(1,0.2*inch))
    story.append(Paragraph("Instagram.AI  \u00b7  Script Intelligence Pipeline",styles["cover_foot"]))

# ── Section header ──
def section_header(title, subtitle, story, styles, score, hook):
    bar = Table([[""]],colWidths=[7.5*inch],rowHeights=[0.025*inch],
                style=TableStyle([("BACKGROUND",(0,0),(-1,-1),GOLD)]))
    story.append(bar)
    story.append(Spacer(1,0.2*inch))
    story.append(Paragraph("SCRIPT",styles["kicker"]))
    story.append(Paragraph(esc(strip_emoji(title)),styles["script_title"]))
    if subtitle:
        story.append(Paragraph(esc(subtitle),styles["script_sub"]))
    story.append(Spacer(1,0.14*inch))
    # Score + hook callout
    score_disp = score if score else "\u2014"
    hook_text = f'<i>&ldquo;{esc(hook)}&rdquo;</i>' if hook else ""
    callout = Table([[
        Paragraph(f'<font color="{GOLD.hexval()}">{score_disp}</font>&nbsp;<font color="#5a5c64">/10</font>',styles["big_score"]),
        Paragraph(hook_text,styles["hook_teaser"]),
    ]],colWidths=[1.6*inch,5.9*inch])
    callout.setStyle(TableStyle([
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("LEFTPADDING",(0,0),(0,0),16),("RIGHTPADDING",(0,0),(0,0),6),
        ("LEFTPADDING",(0,1),(0,1),12),("RIGHTPADDING",(0,1),(0,1),10),
        ("TOPPADDING",(0,0),(-1,-1),14),("BOTTOMPADDING",(0,0),(-1,-1),14),
        ("BACKGROUND",(0,0),(-1,-1),SHADE),
        ("LINEBEFORE",(0,0),(0,-1),3,GOLD),
    ]))
    story.append(callout)
    story.append(Spacer(1,0.2*inch))

# ── Dynamic source parsing (1–3 scripts, dash variants normalized) ──
TS_DASH = r"[–—\-]"   # en dash / em dash / hyphen

_TS_BLOCK_RE = re.compile(
    r"^#{2,3}\s+(\d+:\d{2})\s*" + TS_DASH + r"\s*(\d+:\d{2})\s*$", re.MULTILINE)

def _ts_blocks(md):
    """Yield (start, end, body) for every '### M:SS–M:SS' block."""
    for m in _TS_BLOCK_RE.finditer(md):
        end = m.end()
        body_m = re.search(r"(?P<body>.*?)(?=^#{2,3}\s|\Z)", md[end:],
                           re.MULTILINE | re.DOTALL)
        yield m.group(1), m.group(2), (body_m.group("body") if body_m else "")

def extract_hook(md):
    """Hook teaser = the **Voice:** line of the first timestamp block.

    Duration-agnostic: matches '0:00–0:03', '0:00–0:04', … across en/em
    dash and hyphen variants, and prefers a block that starts at 0:00.
    """
    blocks = list(_ts_blocks(md))
    if not blocks:
        return ""
    body = next((b for s, e, b in blocks if s == "0:00"), blocks[0][2])
    vm = re.search(r'\*\*Voice:\*\*\s*"([^"]+)"', body)
    if not vm:
        vm = re.search(r'(?m)^Voice:\s*"([^"]+)"', body)   # legacy label
    return vm.group(1).strip() if vm else ""

def parse_score(md):
    # Prefer the rubric-derived 'Overall Retention Score' (matches preflight's
    # own scoring logic and the legacy extract_highlights). Falls back to the
    # metadata 'Estimated Performance Score'. Handles both bold placements:
    # '**Overall Retention Score: 7.4 / 10**', '**Estimated Performance
    # Score:** 8.2 / 10' and '**Estimated Performance Score**: 8.5/10 (…)'.
    for label in (r"Overall\s+Retention\s+Score",
                  r"Estimated\s+Performance\s+Score"):
        m = re.search(label + r"\s*\**:\**\s*([\d.]+)\s*/\s*10", md, re.IGNORECASE)
        if m:
            return m.group(1)
    return ""

def parse_length(md):
    """(seconds:int, label:str) from a declared **Length** field, or (None,'')."""
    m = re.search(r"\*\*Length\s*\(s\):\*\*\s*(\d+)", md)
    if m:
        s = int(m.group(1)); return s, f"{s}s"
    m = re.search(r"\*\*Length:\*\*[^\n]*?\((\d+):(\d{2})[^)]*?" + TS_DASH +
                  r"\s*(\d+):(\d{2})\)", md)
    if m:
        s = int(m.group(3)) * 60 + int(m.group(4)); return s, f"{s}s"
    return None, ""

def _last_ts_end(md):
    ends = [int(e.split(":")[0]) * 60 + int(e.split(":")[1])
            for _s, e, _b in _ts_blocks(md)]
    return max(ends) if ends else None

def parse_pillars(md):
    m = re.search(r"\*\*Pillars?\*?:\*\*\s*([^\n]+)", md)
    return m.group(1).strip() if m else ""

def parse_title(md, path):
    m = re.search(r"^\s*[-*]\s*\*\*Title:\*\*\s*([^\n]+)", md, re.MULTILINE)
    if not m:
        m = re.search(r"(?m)^#\s+(?:Script\s*Draft:?\s*|Script:?\s*)?(.+?)\s*$", md)
    if m:
        return re.sub(r"[\s_]+", " ", m.group(1)).strip()
    return Path(path).stem.replace("_", " ")

def parse_core(md):
    m = re.search(r"\*\*Core\s+Concept:\*\*\s*([^\n]+)", md)
    return m.group(1).strip() if m else ""

def parse_meta(path):
    """Parse title/length/pillars/score/core/hook from one script file.

    Fallbacks (filename-derived title, timestamp-derived length, '—' score)
    are explicit and reported on stderr — never silent 'Untitled' labels.
    """
    md = Path(path).read_text(encoding="utf-8")
    warnings = []
    title = parse_title(md, path)
    used_filename = (
        not re.search(r"^\s*[-*]\s*\*\*Title:\*\*", md, re.MULTILINE) and
        not re.search(r"(?m)^#\s+", md)
    )
    if used_filename:
        warnings.append(
            f"  [fallback] {path}: no '# Script' or '**Title:**' heading; "
            f"used filename-derived title {title!r}")
    secs, label = parse_length(md)
    if secs is None:
        last = _last_ts_end(md)
        if last is not None:
            secs, label = last, f"{last}s"
            warnings.append(
                f"  [fallback] {path}: no declared length; derived {label} "
                f"from the last timestamp block")
    score = parse_score(md)
    if not score:
        warnings.append(
            f"  [fallback] {path}: no Overall/Estimated score found; cover shows '\u2014'")
    return {
        "path": str(path),
        "title": title,
        "length_secs": secs,
        "length_label": label,
        "score": score,
        "pillars": parse_pillars(md),
        "core": parse_core(md),
        "hook": extract_hook(md),
        "md": md,
    }, warnings

def make_subtitle(meta):
    """Section subtitle: core-concept first sentence + 'length · pillars'."""
    parts = []
    core = (meta.get("core") or "").strip()
    if core:
        core_short = re.split(r"(?<=[.!?])\s+", core, maxsplit=1)[0]
        if len(core_short) > 200:
            core_short = core_short[:197].rstrip() + "\u2026"
        parts.append(core_short)
    tail = " \u00b7 ".join(x for x in (meta.get("length_label") or "",
                                       meta.get("pillars") or "") if x)
    if tail:
        parts.append(tail)
    return " \u00b7 ".join(parts)

# ── Markdown → flowables ──
def md_to_flowables(md_text,styles,skip_first_h1=False):
    flow=[]
    lines=md_text.splitlines()
    i=0; skipped=False
    ts_buf = []
    last_h2_pos = -1  # flow index of last ## heading block (for table anchoring)

    def flush_ts():
        nonlocal ts_buf
        if not ts_buf: return
        if len(ts_buf) >= 3:
            flow.append(KeepTogether(ts_buf[:3]))
            for item in ts_buf[3:]:
                flow.append(item)
        else:
            flow.append(KeepTogether(ts_buf))
        ts_buf=[]

    while i < len(lines):
        raw = lines[i].rstrip(); s=raw.strip()

        if s=="---":
            flush_ts();i+=1;continue
        if not s:
            flush_ts(); flow.append(Spacer(1,4)); i+=1; continue

        # Timestamp heading — start a KeepTogether block
        m = re.match(r"^###\s+(0?[\d:]+\s*[–—\-]\s*[\d:]+)\s*$", raw)
        if m:
            flush_ts()
            ts = m.group(1)
            inner = Paragraph(
                f'<font color="{GOLD.hexval()}">&mdash;&ensp;{ts}&ensp;&mdash;</font>',
                styles["ts_pill"])
            ts_buf.append(inner)
            ts_buf.append(Spacer(1,4))
            i+=1; continue

        if raw.startswith("### "):
            flush_ts()
            flow.append(Paragraph(esc(strip_emoji(raw[4:].strip())),styles["h3"]))
            i+=1;continue
        if raw.startswith("## "):
            flush_ts()
            bar = Table([[""]],colWidths=[0.5*inch],rowHeights=[0.025*inch],
                        style=TableStyle([("BACKGROUND",(0,0),(-1,-1),GOLD)]))
            heading = Paragraph(esc(strip_emoji(raw[3:].strip())),styles["h2"])
            flow.append(bar)
            flow.append(Spacer(1,4))
            flow.append(heading)
            last_h2_pos = len(flow)  # track for table relocation
            i+=1;continue
        if raw.startswith("# "):
            flush_ts()
            if skip_first_h1 and not skipped:
                skipped=True;i+=1;continue
            flow.append(Paragraph(esc(strip_emoji(raw[2:].strip())),styles["h1"]))
            i+=1;continue

        if raw.lstrip().startswith("|") and "|" in raw[1:]:
            flush_ts()
            block=[]
            while i<len(lines) and lines[i].lstrip().startswith("|"):
                block.append(lines[i]);i+=1
            # Count non-separator data rows
            data_rows=sum(1 for b in block
                          if b.lstrip().startswith("|")
                          and not all(c in "-: " for c in b.strip().strip("|").split("|")[0]))
            # If table is large and sits right after an H2 heading (ignoring spacers)
            if data_rows >= 6 and last_h2_pos > 0:
                trailing = flow[last_h2_pos:]
                if all(isinstance(x, Spacer) for x in trailing):
                    # Relocate heading + trailing spacers to a fresh page
                    relocated = flow[last_h2_pos - 3:]
                    del flow[last_h2_pos - 3:]
                    flow.append(PageBreak())
                    flow.extend(relocated)
                    last_h2_pos = -1
            t = render_table(block,styles)
            if t: flow.append(t)
            continue

        if raw.lstrip().startswith(">"):
            flush_ts()
            b=[]
            while i<len(lines) and lines[i].lstrip().startswith(">"):
                b.append(lines[i].lstrip()[1:].strip());i+=1
            text=" ".join(x for x in b if x)
            flow.append(callout_quote(text,styles))
            continue

        m = re.match(r"^(\s*)[-*]\s+(.*)$",raw)
        if m:
            flush_ts()
            items=[]
            while i<len(lines):
                m2=re.match(r"^(\s*)[-*]\s+(.*)$",lines[i])
                if not m2:break
                items.append(esc(strip_emoji(m2.group(2).strip())));i+=1
            flow.append(bullet_list(items,styles))
            continue

        m = re.match(r"^(\s*)(\d+)\.\s+(.*)$",raw)
        if m:
            flush_ts()
            items=[]
            while i<len(lines):
                m2=re.match(r"^(\s*)(\d+)\.\s+(.*)$",lines[i])
                if not m2:break
                items.append(esc(strip_emoji(m2.group(3).strip())));i+=1
            flow.append(numbered_list(items,styles))
            continue

        # Regular body line — goes into timestamp buffer if open, else plain
        if ts_buf:
            ts_buf.append(Paragraph(esc(strip_emoji(raw)),styles["body"]))
        else:
            flow.append(Paragraph(esc(strip_emoji(raw)),styles["body"]))
        i+=1

    flush_ts()
    return flow

def render_table(block,styles):
    rows=[];header=None
    for raw in block:
        if not raw.lstrip().startswith("|"):continue
        cells=[c.strip() for c in raw.strip().strip("|").split("|")]
        if all(set(c)<=set("-: ") for c in cells):continue
        if header is None:
            header=[Paragraph(esc(strip_emoji(c)),styles["th"]) for c in cells]
        else:
            rows.append([Paragraph(esc(strip_emoji(c)),styles["cell"]) for c in cells])
    if not header and not rows:return None
    data=[header]+rows if header else rows
    n=len(data[0])
    if n==3: widths=[2.3*inch,0.65*inch,4.55*inch]
    elif n==2: widths=[1.7*inch,5.8*inch]
    else: widths=[7.5*inch/n]*n

    t=Table(data,colWidths=widths,repeatRows=1)
    ts=[("VALIGN",(0,0),(-1,-1),"TOP"),
        ("BACKGROUND",(0,0),(-1,0),HEADING_BG),
        ("TEXTCOLOR",(0,0),(-1,0),CREAM),
        ("LEFTPADDING",(0,0),(-1,-1),9),
        ("RIGHTPADDING",(0,0),(-1,-1),9),
        ("TOPPADDING",(0,0),(-1,-1),7),
        ("BOTTOMPADDING",(0,0),(-1,-1),7),
        ("BOX",(0,0),(-1,-1),0.4,RULE),
        ("INNERGRID",(0,0),(-1,-1),0.2,SHADE2)]
    for i,row in enumerate(rows,1):
        if i%2==0: ts.append(("BACKGROUND",(0,i),(-1,i),SHADE))
    if n>=3:
        for i in range(1,len(data)):
            sc=data[i][1].text.strip() if hasattr(data[i][1],"text") else ""
            try:
                val=float(re.match(r"[\d.]+",sc).group())
            except: val=None
            if val is not None:
                c=GOOD if val>=7 else(WARN if val>=5 else BAD)
                ts.append(("TEXTCOLOR",(1,i),(1,i),c))
                ts.append(("FONTNAME",(1,i),(1,i),"Times-Bold"))
    t.setStyle(TableStyle(ts))
    return t

def bullet_list(items,styles):
    li=[ListItem(Paragraph(it,styles["bullet"]),leftIndent=16) for it in items]
    return ListFlowable(li,bulletType="bullet",leftIndent=22,
                        bulletFontSize=6,bulletColor=GOLD,
                        spaceBefore=2,spaceAfter=6)

def numbered_list(items,styles):
    li=[ListItem(Paragraph(it,styles["bullet"]),leftIndent=16) for it in items]
    return ListFlowable(li,bulletType="1",leftIndent=22,
                        bulletFontSize=9,bulletColor=GOLD,
                        spaceBefore=2,spaceAfter=6)

def callout_quote(text,styles):
    inner=Paragraph(esc(strip_emoji(text)),styles["quote_text"])
    wrap=Table([[inner]],colWidths=[7.0*inch])
    wrap.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),SHADE),
        ("LEFTPADDING",(0,0),(-1,-1),18),
        ("RIGHTPADDING",(0,0),(-1,-1),18),
        ("TOPPADDING",(0,0),(-1,-1),14),
        ("BOTTOMPADDING",(0,0),(-1,-1),14),
        ("LINEBEFORE",(0,0),(0,-1),3,GOLD),
    ]))
    return wrap

# ── Page decorator ──
class PageDeco:
    def __init__(self,label,show_header=True):
        self.label=label;self.show_header=show_header
    def __call__(self,canv,doc):
        canv.saveState()
        pw,ph=LETTER
        if self.show_header and self.label:
            # Top header: thin gold rule + label
            canv.setStrokeColor(GOLD)
            canv.setLineWidth(0.3)
            canv.line(1*inch,ph-0.6*inch,pw-1*inch,ph-0.6*inch)
            canv.setFont("Times-Roman",7.5)
            canv.setFillColor(GOLD)
            canv.drawString(1*inch,ph-0.58*inch,"REEL SCRIPT PLAYBOOK")
            canv.setFillColor(INK_SOFT)
            canv.drawRightString(pw-1*inch,ph-0.58*inch,self.label.upper())
        # Footer
        canv.setStrokeColor(RULE)
        canv.setLineWidth(0.2)
        canv.line(1*inch,0.55*inch,pw-1*inch,0.55*inch)
        canv.setFont("Times-Italic",8)
        canv.setFillColor(INK_SOFT)
        canv.drawRightString(pw-1*inch,0.42*inch,f"Instagram.AI \u00b7 p. {doc.page}")
        canv.restoreState()

# ── Main ──
def build_pdf(script_paths, output_path, topic=None):
    """Build the premium playbook PDF from 1–3 script markdown files.

    script_paths : iterable of paths to script .md files
    output_path  : destination PDF path (any extension, parent created)
    topic        : optional topic line shown on the cover
    Returns the output path. Fallback-parsing warnings go to stderr.
    """
    metas, warnings = [], []
    for p in script_paths:
        meta, ws = parse_meta(p)
        metas.append(meta)
        warnings.extend(ws)
    for w in warnings:
        print(w, file=sys.stderr)

    styles = build_styles()
    margin = 1 * inch
    doc = BaseDocTemplate(
        str(output_path), pagesize=LETTER,
        leftMargin=margin, rightMargin=margin,
        topMargin=0.85 * inch, bottomMargin=0.7 * inch,
        title="Instagram.AI - Script Sample", author="Instagram.AI",
    )

    story = []
    cover_page(story, styles, metas, topic)
    for i, meta in enumerate(metas):
        story.append(NextPageTemplate(f"s{i}"))
        story.append(PageBreak())
        section_header(meta["title"], make_subtitle(meta), story, styles,
                       meta["score"], meta["hook"])
        story.extend(md_to_flowables(meta["md"], styles, skip_first_h1=True))

    # Cover template (no header)
    cf = Frame(margin, 0.7 * inch, LETTER[0] - 2 * margin, LETTER[1] - 1.4 * inch, id="cover")
    ct = PageTemplate(id="cover", frames=[cf], onPage=PageDeco("", show_header=False))
    doc.addPageTemplates([ct])
    # Script templates
    for i, meta in enumerate(metas):
        f = Frame(margin, 0.85 * inch, LETTER[0] - 2 * margin, LETTER[1] - 1.7 * inch, id=f"s{i}")
        t = PageTemplate(id=f"s{i}", frames=[f], onPage=PageDeco(meta["title"]))
        doc.addPageTemplates([t])

    doc.build(story)
    print(f"Wrote {Path(output_path).resolve()}")
    return str(output_path)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Premium playbook PDF of 1–3 reel scripts (v5 luxury edition).")
    parser.add_argument("--scripts", nargs="+", default=None,
                        help="Paths to 1–3 script .md files "
                             "(default: legacy two-script selection in SCRIPTS)")
    parser.add_argument("--output", default=None, help="Output PDF path")
    parser.add_argument("--topic", default=None,
                        help="Optional topic line on the cover")
    args = parser.parse_args(argv)

    if args.scripts is None:
        # Legacy no-argument default: the user's current two-script selection.
        scripts = [str(SCRIPTS_DIR / n) for n in SCRIPTS]
        output = OUTPUT
    else:
        scripts = args.scripts
        if not 1 <= len(scripts) <= 3:
            print(f"--scripts expects 1–3 files, got {len(scripts)}", file=sys.stderr)
            return 2
        if args.output:
            output = Path(args.output)
        else:
            slug = re.sub(r"[^\w\s-]", "", args.topic or "Script_Drafts").strip() \
                       .replace(" ", "_") or "Script_Drafts"
            output = Path("draft_result") / f"{slug}.pdf"
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    build_pdf(scripts, output, topic=args.topic)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
