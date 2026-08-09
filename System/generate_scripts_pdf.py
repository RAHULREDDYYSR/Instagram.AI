"""Generate a polished PDF from 2-3 markdown script drafts.

Usage:
    uv run System/generate_scripts_pdf.py --scripts file1.md file2.md [file3.md]
                                         [--output draft_result/Topic.pdf]
                                         [--topic "Topic Name"]
"""

import argparse
import os
import re
import sys
from datetime import date

from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Frame,
    HRFlowable,
    PageBreak,
    PageTemplate,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ACCENT = HexColor("#C0392B")
DARK = HexColor("#1A1A2E")
MID = HexColor("#2D2D44")
LIGHT_BG = HexColor("#F4F4F8")
BODY_COLOR = HexColor("#333333")
MUTED = HexColor("#777777")
BORDER = HexColor("#DDDDDD")
GOLD = HexColor("#D4A017")


def on_page(canvas, doc):
    """Draw a subtle footer on every page."""
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawCentredString(
        A4[0] / 2, 1.2 * cm, f"Instagram.AI — Script Drafts  |  {date.today().strftime('%B %d, %Y')}"
    )
    canvas.restoreState()


def on_cover(canvas, doc):
    """Draw a darker footer on the cover page."""
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawCentredString(
        A4[0] / 2, 1.2 * cm, f"Instagram.AI — Script Drafts  |  {date.today().strftime('%B %d, %Y')}"
    )
    canvas.restoreState()


def make_styles():
    """Build all paragraph styles used in the PDF."""
    from reportlab.lib.styles import getSampleStyleSheet
    base = getSampleStyleSheet()

    return {
        "cover_title": ParagraphStyle(
            "CoverTitle", parent=base["Title"], fontSize=28, leading=34,
            textColor=white, alignment=TA_CENTER, spaceAfter=8,
        ),
        "cover_subtitle": ParagraphStyle(
            "CoverSub", parent=base["Normal"], fontSize=12, leading=16,
            textColor=HexColor("#CCCCCC"), alignment=TA_CENTER, spaceAfter=4,
        ),
        "cover_badge": ParagraphStyle(
            "CoverBadge", parent=base["Normal"], fontSize=10, leading=14,
            textColor=GOLD, alignment=TA_CENTER, spaceAfter=6,
        ),
        "script_title": ParagraphStyle(
            "ScriptTitle", parent=base["Heading1"], fontSize=20, leading=26,
            textColor=DARK, spaceAfter=6, spaceBefore=4,
        ),
        "score_badge": ParagraphStyle(
            "ScoreBadge", parent=base["Normal"], fontSize=13, leading=18,
            textColor=ACCENT, alignment=TA_LEFT, spaceAfter=8,
        ),
        "meta": ParagraphStyle(
            "Meta", parent=base["Normal"], fontSize=9, leading=14,
            textColor=MUTED, spaceAfter=4,
        ),
        "section_heading": ParagraphStyle(
            "SectionH", parent=base["Heading2"], fontSize=13, leading=17,
            textColor=DARK, spaceAfter=6, spaceBefore=14,
            borderPadding=(0, 0, 2, 0),
        ),
        "body": ParagraphStyle(
            "Body", parent=base["Normal"], fontSize=9.5, leading=14,
            textColor=BODY_COLOR, spaceAfter=5,
        ),
        "hook_item": ParagraphStyle(
            "HookItem", parent=base["Normal"], fontSize=9.5, leading=14,
            textColor=BODY_COLOR, spaceAfter=3, leftIndent=12, bulletIndent=4,
        ),
        "ts_label": ParagraphStyle(
            "TSLabel", parent=base["Normal"], fontSize=10, leading=14,
            textColor=DARK, spaceAfter=2, spaceBefore=10, fontName="Helvetica-Bold",
        ),
        "ts_block": ParagraphStyle(
            "TSBlock", parent=base["Code"], fontSize=8.2, leading=12,
            textColor=BODY_COLOR, backColor=LIGHT_BG,
            borderPadding=(7, 8, 7, 8), spaceAfter=6,
            fontName="Helvetica",
        ),
        "thumbnail_body": ParagraphStyle(
            "ThumbBody", parent=base["Normal"], fontSize=9.5, leading=14,
            textColor=BODY_COLOR, spaceAfter=5,
        ),
    }


def parse_script_file(path):
    """Convert a markdown script file into a structured dict."""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    title = _extract(text, r"^# Script:?\s*(.+)$", "Untitled")
    title = title.replace("_", " ").strip()

    score = _extract(text, r"\*\*Estimated Performance Score:\*\*\s*([\d.]+)", "—")
    pitch = _extract(text, r"\*\*Core Concept:\*\*\s*(.+?)(?:\n|$)", "—")
    framework = _extract(text, r"\*\*Framework:\*\*\s*(.+?)(?:\n|$)", "—")
    if framework == "—":
        framework = _extract(text, r"\*\*Pattern tags:\*\*\s*(.+?)(?:\n|$)", "—")

    thumbnail = _extract(
        text, r"##\s*Thumbnail.*?\n+(.+?)(?:\n##|\n---|\Z)", "—", flags=re.DOTALL
    )
    caption = _extract(
        text, r"##\s*Caption.*?\n+[>]?\s*(.+?)(?:\n##|\n---|\n#+|\Z)", "—", flags=re.DOTALL
    )

    # Alternative hooks
    hooks = []
    hook_section = re.search(
        r"(?:##\s*\d*\.?\s*Alternative Hooks?.*?\n)((?:.*?(?:\n|$))+?)(?=\n##|\n---|\Z)",
        text, re.IGNORECASE
    )
    if hook_section:
        for line in hook_section.group(1).strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            line = re.sub(r"^\d+\.\s*\**", "", line).rstrip("*").strip()
            if len(line) > 5:
                hooks.append(line)

    # Timestamped script blocks
    timestamps = _parse_timestamps(text)

    return {
        "title": title,
        "score": score,
        "pitch": pitch,
        "framework": framework,
        "hooks": hooks,
        "timestamps": timestamps,
        "thumbnail": thumbnail.strip(),
        "caption": caption.strip(),
    }


def _extract(text, pattern, default, flags=0):
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else default


def _parse_timestamps(text):
    """Parse timestamp blocks like:
    ### 0:00–0:04
    **Voice:** "..."
    **Visual:** "..."
    **On-Screen Text:** "..."
    """
    blocks = re.findall(
        r"###?\s*(\d+:\d+[–\-]\d+:\d+)\n(.*?)(?=\n###?\s*\d+:\d+|\n##|\n---|\Z)",
        text, re.DOTALL
    )
    result = []
    for ts, body in blocks:
        voice = _extract(body, r"\*\*Voice:\*\*\s*(.+?)(?:\n\*\*|\Z)", "", re.DOTALL)
        visual = _extract(body, r"\*\*Visual:\*\*\s*(.+?)(?:\n\*\*|\Z)", "", re.DOTALL)
        ost = _extract(body, r"\*\*On-Screen Text:\*\*\s*(.+?)(?:\n\*\*|\Z)", "", re.DOTALL)
        result.append((ts.strip(), voice.strip(), visual.strip(), ost.strip()))
    return result


def sanitize(text):
    """Escape XML special chars for reportlab Paragraphs."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def build_cover(topic, styl):
    """Build the cover page elements."""
    elements = []
    elements.append(Spacer(1, 5 * cm))

    # Dark header bar
    header_data = [[
        Paragraph(topic.upper(), styl["cover_title"]),
    ]]
    header_table = Table(header_data, colWidths=[16 * cm])
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), DARK),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 30),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 30),
        ("LEFTPADDING", (0, 0), (-1, -1), 20),
        ("RIGHTPADDING", (0, 0), (-1, -1), 20),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 1.2 * cm))

    elements.append(Paragraph(
        f"Generated {date.today().strftime('%B %d, %Y')}",
        styl["cover_subtitle"]
    ))
    elements.append(Paragraph(
        "Powered by Instagram.AI Brain",
        styl["cover_subtitle"]
    ))
    elements.append(Spacer(1, 0.6 * cm))
    elements.append(Paragraph("Fitness • Bodybuilding • Lifestyle • Masculinity • Self-Improvement", styl["cover_badge"]))

    # Accent divider
    elements.append(Spacer(1, 1.5 * cm))
    elements.append(HRFlowable(
        width="40%", thickness=3, color=ACCENT, spaceAfter=8, spaceBefore=0
    ))
    elements.append(Paragraph("READY-TO-SHOOT SCRIPT DRAFTS", styl["cover_subtitle"]))

    return elements


def build_script_section(script, styl, is_last=False):
    """Build a script's full section in the PDF."""
    elements = []
    title = sanitize(script["title"])

    # Script header with accent left border via a nested table
    elements.append(Paragraph(title, styl["script_title"]))
    elements.append(Paragraph(
        f"<b>Score: {sanitize(script['score'])} / 10</b>",
        styl["score_badge"]
    ))
    elements.append(Paragraph(
        f"<b>Framework:</b> {sanitize(script['framework'])}",
        styl["meta"]
    ))
    elements.append(Paragraph(
        f"<b>Concept:</b> {sanitize(script['pitch'])}",
        styl["meta"]
    ))

    elements.append(Spacer(1, 0.2 * cm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=10, spaceBefore=4))

    # Alternative Hooks
    if script["hooks"]:
        elements.append(Paragraph("Alternative Hooks", styl["section_heading"]))
        for h in script["hooks"]:
            elements.append(Paragraph(f"• {sanitize(h)}", styl["hook_item"]))
        elements.append(Spacer(1, 0.1 * cm))

    # Timestamped Script
    elements.append(Paragraph("Timestamp Shooting Script (0:00–0:30)", styl["section_heading"]))
    for ts, voice, visual, ost in script["timestamps"]:
        elements.append(Paragraph(f"[{ts}]", styl["ts_label"]))
        block_text = ""
        if voice:
            block_text += f"<b>VOICE:</b> {sanitize(voice)}<br/>"
        if visual:
            block_text += f"<b>VISUAL:</b> {sanitize(visual)}<br/>"
        if ost:
            block_text += f"<b>ON-SCREEN TEXT:</b> {sanitize(ost)}"
        elements.append(Paragraph(block_text, styl["ts_block"]))

    # Thumbnail
    elements.append(Spacer(1, 0.2 * cm))
    elements.append(Paragraph("Thumbnail Idea", styl["section_heading"]))
    elements.append(Paragraph(sanitize(script["thumbnail"]), styl["thumbnail_body"]))

    # Caption
    elements.append(Paragraph("Caption Suggestion", styl["section_heading"]))
    elements.append(Paragraph(sanitize(script["caption"]), styl["thumbnail_body"]))

    return elements


def main():
    parser = argparse.ArgumentParser(description="Generate a polished PDF from script drafts")
    parser.add_argument("--scripts", nargs="+", required=True, help="Paths to markdown script files (2-3)")
    parser.add_argument("--output", default=None, help="Output PDF path")
    parser.add_argument("--topic", default="Script Drafts", help="Topic name for the cover page")
    args = parser.parse_args()

    scripts = [parse_script_file(p) for p in args.scripts]
    if not scripts:
        print("No scripts parsed. Exiting.", file=sys.stderr)
        sys.exit(1)

    output = args.output
    if not output:
        topic_slug = re.sub(r"[^\w\s-]", "", args.topic).strip().replace(" ", "_")
        os.makedirs("draft_result", exist_ok=True)
        output = f"draft_result/{topic_slug}.pdf"

    os.makedirs(os.path.dirname(output) or "draft_result", exist_ok=True)

    styl = make_styles()

    # Page templates
    cover_frame = Frame(2 * cm, 2 * cm, A4[0] - 4 * cm, A4[1] - 4 * cm, id="cover_frame")
    body_frame = Frame(2 * cm, 2.2 * cm, A4[0] - 4 * cm, A4[1] - 3.4 * cm, id="body_frame")

    doc = SimpleDocTemplate(
        output, pagesize=A4,
        rightMargin=0, leftMargin=0, topMargin=0, bottomMargin=0,
    )
    doc.addPageTemplates([
        PageTemplate(id="Cover", frames=[cover_frame], onPage=on_cover),
        PageTemplate(id="Body", frames=[body_frame], onPage=on_page),
    ])

    story = []
    # Cover page
    story.extend(build_cover(args.topic, styl))
    story.append(PageBreak())

    # Script pages
    for i, script in enumerate(scripts):
        story.extend(build_script_section(script, styl, is_last=(i == len(scripts) - 1)))
        if i < len(scripts) - 1:
            story.append(PageBreak())

    try:
        doc.build(story)
        print(f"PDF generated: {output}")
    except Exception as e:
        print(f"Failed to generate PDF: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
