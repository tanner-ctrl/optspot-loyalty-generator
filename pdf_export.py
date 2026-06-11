"""pdf_export.py — OptSpot branded PDF export for loyalty program messages."""

import html
import io

from PIL import Image as _PILImage

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame,
    Paragraph, Spacer, Table, TableStyle,
    KeepTogether, HRFlowable, Image as RLImage,
)
from reportlab.pdfgen import canvas as pdfgen_canvas
from reportlab.lib.utils import ImageReader

# ── Brand ──────────────────────────────────────────────────────────────────────

NAVY      = colors.HexColor("#264078")
BLUE      = colors.HexColor("#23A3EA")
DARK_GRAY = colors.HexColor("#333333")
LIGHT_GRAY = colors.HexColor("#888888")
TINY_GRAY  = colors.HexColor("#AAAAAA")
MSG_BG     = colors.Color(0.90, 0.96, 1.0)   # ~#23A3EA at 10% on white

# ── Page geometry ──────────────────────────────────────────────────────────────

PAGE_W, PAGE_H = letter   # 612 × 792 pt
MARGIN = int(0.75 * 72)   # 54 pt

# Header: OptSpot logo + "Loyalty Program Messages" label + bright blue rule
HEADER_RULE_Y = PAGE_H - MARGIN - 4

# Footer: bright blue rule + left/right text
FOOTER_RULE_Y = MARGIN - 14
FOOTER_TEXT_Y = FOOTER_RULE_Y - 12

# Content frame sits between header rule and footer rule (8 pt gap each side)
FRAME_LEFT   = MARGIN
FRAME_BOTTOM = FOOTER_RULE_Y + 10
FRAME_TOP    = HEADER_RULE_Y - 8
FRAME_W      = PAGE_W - 2 * MARGIN
FRAME_H      = FRAME_TOP - FRAME_BOTTOM


# ── Styles ─────────────────────────────────────────────────────────────────────

def _styles() -> dict:
    s = {}
    s["name"] = ParagraphStyle("name",
        fontName="Helvetica-Bold", fontSize=22, textColor=NAVY,
        leading=28, spaceAfter=4)
    s["program"] = ParagraphStyle("program",
        fontName="Helvetica", fontSize=11, textColor=DARK_GRAY,
        leading=16, spaceAfter=2)
    s["date"] = ParagraphStyle("date",
        fontName="Helvetica", fontSize=9, textColor=TINY_GRAY,
        leading=13, spaceAfter=0)
    s["section_title"] = ParagraphStyle("section_title",
        fontName="Helvetica-Bold", fontSize=12, textColor=NAVY,
        leading=17, spaceBefore=14, spaceAfter=3)
    s["section_intro"] = ParagraphStyle("section_intro",
        fontName="Helvetica", fontSize=8.5, textColor=LIGHT_GRAY,
        leading=13, spaceAfter=8)
    s["card_label"] = ParagraphStyle("card_label",
        fontName="Helvetica-Bold", fontSize=8.5, textColor=NAVY,
        leading=13, spaceAfter=2)
    s["card_msg"] = ParagraphStyle("card_msg",
        fontName="Helvetica", fontSize=10, textColor=DARK_GRAY,
        leading=15)
    s["char_count"] = ParagraphStyle("char_count",
        fontName="Helvetica", fontSize=7.5, textColor=TINY_GRAY,
        alignment=TA_RIGHT, leading=11)
    s["strategy"] = ParagraphStyle("strategy",
        fontName="Helvetica-Oblique", fontSize=8, textColor=LIGHT_GRAY,
        leading=12, spaceAfter=12)
    return s


# ── Numbered canvas — header, footer, Page X of Y ─────────────────────────────

def _prep_logo(logo_path: str, target_h: float):
    """
    Open the logo with PIL, flatten its alpha channel onto white, and return
    a stable in-memory ImageReader plus the correct (width, height) to draw at.
    Using PIL for dimensions is reliable; pre-compositing on white removes any
    mask="auto" distortion that occurs with RGBA PNGs in some ReportLab builds.
    """
    pil = _PILImage.open(logo_path).convert("RGBA")
    iw, ih = pil.size
    display_w = target_h * iw / ih

    # Flatten alpha onto pure white so the logo renders cleanly on the white PDF.
    bg = _PILImage.new("RGB", (iw, ih), (255, 255, 255))
    bg.paste(pil.convert("RGB"), mask=pil.split()[3])  # alpha channel as mask

    buf = io.BytesIO()
    bg.save(buf, format="PNG")
    # Create a fresh BytesIO from the fully-written bytes so ImageReader gets
    # a complete, seek-able stream with no dependency on the original buffer.
    reader = ImageReader(io.BytesIO(buf.getvalue()))

    return reader, display_w, target_h


def _canvas_factory(logo_path: str):
    """Returns a Canvas subclass that stamps header/footer on every page."""

    # Pre-process once — logo reader is shared across all page stamps.
    try:
        _logo_reader, _logo_w, _logo_h = _prep_logo(logo_path, 36)
    except Exception:
        _logo_reader = None
        _logo_w = _logo_h = 0

    class _Canvas(pdfgen_canvas.Canvas):
        def __init__(self, filename, **kwargs):
            super().__init__(filename, **kwargs)
            self._saved = []

        def showPage(self):
            self._saved.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved)
            for state in self._saved:
                self.__dict__.update(state)
                self._stamp(total)
                pdfgen_canvas.Canvas.showPage(self)
            pdfgen_canvas.Canvas.save(self)

        def _stamp(self, total_pages: int):
            self.saveState()

            # ── Header ──
            ry = HEADER_RULE_Y
            if _logo_reader is not None:
                self.drawImage(
                    _logo_reader, MARGIN, ry + 5,
                    width=_logo_w, height=_logo_h,
                )
            else:
                self.setFont("Helvetica-Bold", 12)
                self.setFillColor(NAVY)
                self.drawString(MARGIN, ry + 9, "OptSpot")

            self.setFont("Helvetica", 7.5)
            self.setFillColor(NAVY)
            self.drawRightString(PAGE_W - MARGIN, ry + 13, "Loyalty Program Messages")

            self.setStrokeColor(BLUE)
            self.setLineWidth(1.5)
            self.line(MARGIN, ry, PAGE_W - MARGIN, ry)

            # ── Footer ──
            fy = FOOTER_RULE_Y
            self.setStrokeColor(BLUE)
            self.setLineWidth(0.75)
            self.line(MARGIN, fy, PAGE_W - MARGIN, fy)

            self.setFont("Helvetica", 7)
            self.setFillColor(TINY_GRAY)
            self.drawString(MARGIN, FOOTER_TEXT_Y, "OptSpot — Loyalty Program Messages")
            self.drawRightString(
                PAGE_W - MARGIN, FOOTER_TEXT_Y,
                f"Page {self._pageNumber} of {total_pages}",
            )

            self.restoreState()

    return _Canvas


# ── Message card ───────────────────────────────────────────────────────────────

def _card(
    label: str,
    text: str,
    strategy: str,
    styles: dict,
    width: float,
    mode: str = "SMS",
    image_data: bytes = None,
) -> KeepTogether:
    char_count = len(text)
    safe_text     = html.escape(text).replace("\n", "<br/>")
    safe_label    = html.escape(label)
    safe_strategy = html.escape(strategy)

    badge_color = "#23A3EA" if mode == "MMS" else "#888888"
    label_html = (
        f'{safe_label}&nbsp;&nbsp;'
        f'<font color="{badge_color}"><b>{mode}</b></font>'
    )

    msg_table = Table(
        [
            [Paragraph(safe_text, styles["card_msg"])],
            [Paragraph(f"{char_count} chars", styles["char_count"])],
        ],
        colWidths=[width],
    )
    msg_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), MSG_BG),
        ("BOX",           (0, 0), (-1, -1), 0.75, BLUE),
        ("TOPPADDING",    (0, 0), (0, 0),   8),
        ("BOTTOMPADDING", (0, 0), (0, 0),   4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 1), (0, 1),   2),
        ("BOTTOMPADDING", (0, 1), (0, 1),   8),
        ("ALIGN",         (0, 1), (0, 1),   "RIGHT"),
    ]))

    elements = [
        Paragraph(label_html, styles["card_label"]),
        Spacer(1, 3),
    ]

    if mode == "MMS" and image_data:
        try:
            pil = _PILImage.open(io.BytesIO(image_data))
            iw, ih = pil.size
            scale = min(width / iw, 200 / ih)
            draw_w, draw_h = iw * scale, ih * scale
            rl_img = RLImage(io.BytesIO(image_data), width=draw_w, height=draw_h)
            elements.append(rl_img)
            elements.append(Spacer(1, 3))
            elements.append(Paragraph("<i>Image attached to MMS</i>", styles["section_intro"]))
            elements.append(Spacer(1, 5))
        except Exception:
            pass

    elements += [
        msg_table,
        Spacer(1, 4),
        Paragraph(f"<i>{safe_strategy}</i>", styles["strategy"]),
    ]

    return KeepTogether(elements)


# ── Program Loop callout (single-tier only) ────────────────────────────────────

def _loop_callout(width: float) -> KeepTogether:
    """Navy-header callout box explaining single-tier program reset behavior."""
    CALLOUT_BG = colors.HexColor("#EEF2F8")

    header_style = ParagraphStyle(
        "callout_header",
        fontName="Helvetica-Bold",
        fontSize=10.5,
        textColor=colors.white,
        leading=16,
    )
    body_style = ParagraphStyle(
        "callout_body",
        fontName="Helvetica",
        fontSize=9.5,
        textColor=DARK_GRAY,
        leading=14,
    )

    body = (
        "After the customer redeems their reward, their progress resets to 0. "
        "The next wash they take will trigger the progress message, "
        "starting the cycle over."
    )

    tbl = Table(
        [
            [Paragraph("Program Loop — How It Resets", header_style)],
            [Paragraph(body, body_style)],
        ],
        colWidths=[width],
    )
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, 0), NAVY),
        ("BACKGROUND",    (0, 1), (0, 1), CALLOUT_BG),
        ("BOX",           (0, 0), (-1, -1), 0.75, NAVY),
        ("TOPPADDING",    (0, 0), (0, 0), 8),
        ("BOTTOMPADDING", (0, 0), (0, 0), 8),
        ("TOPPADDING",    (0, 1), (0, 1), 10),
        ("BOTTOMPADDING", (0, 1), (0, 1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
    ]))

    return KeepTogether([tbl])


# ── Incentives Summary block ───────────────────────────────────────────────────

def _incentives_summary(context: dict, styles: dict, story: list, width: float) -> None:
    """Navy-header callout listing all loyalty program incentive rules for client review."""
    CALLOUT_BG = colors.HexColor("#EEF2F8")

    items = []

    # 1. Check-in offer — first tier
    tiers = context.get("tiers", [])
    if tiers:
        first = tiers[0]
        visits = first.get("visits", "")
        reward = first.get("reward", "")
        if visits and reward:
            items.append(f"Earn a {reward} after {visits} visits")

    # 2–5. HPO fields (skip if empty / default-only)
    hpo_offer = (context.get("hpo_membership_offer") or "").strip()
    if hpo_offer:
        items.append(f"HPO Membership Offer: {hpo_offer}")

    hpo_days = context.get("hpo_timeframe_days")
    if hpo_days:
        items.append(f"HPO Timeframe: {hpo_days} days")

    hpo_min = context.get("hpo_min_visits")
    if hpo_min:
        items.append(f"HPO Minimum Visits: {hpo_min}")

    hpo_max = context.get("hpo_max_checkins")
    if hpo_max:
        items.append(f"HPO Maximum Check-ins: {hpo_max}")

    # 6. Auto-Engage offer entries only
    for ae in context.get("auto_engage", []):
        if ae.get("type", "offer") == "offer" and (ae.get("offer") or "").strip():
            items.append(f"{ae['days']} Day Offer: {ae['offer']}")

    if not items:
        return

    header_style = ParagraphStyle(
        "incentives_header",
        fontName="Helvetica-Bold",
        fontSize=11,
        textColor=colors.white,
        leading=16,
    )
    body_style = ParagraphStyle(
        "incentives_body",
        fontName="Helvetica",
        fontSize=11,
        textColor=DARK_GRAY,
        leading=17,
    )

    rows = [[Paragraph("Program Incentives Summary", header_style)]]
    for item in items:
        rows.append([Paragraph(f"•  {html.escape(item)}", body_style)])

    tbl = Table(rows, colWidths=[width])

    style_cmds = [
        ("BACKGROUND",    (0, 0), (0, 0),  NAVY),
        ("BOX",           (0, 0), (-1, -1), 0.75, NAVY),
        ("TOPPADDING",    (0, 0), (0, 0),  8),
        ("BOTTOMPADDING", (0, 0), (0, 0),  8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
    ]
    for r in range(1, len(rows)):
        style_cmds += [
            ("BACKGROUND",    (0, r), (0, r), CALLOUT_BG),
            ("TOPPADDING",    (0, r), (0, r), 5),
            ("BOTTOMPADDING", (0, r), (0, r), 5),
        ]
    tbl.setStyle(TableStyle(style_cmds))

    story.append(HRFlowable(
        width="100%", thickness=0.4, color=NAVY,
        spaceBefore=12, spaceAfter=8,
    ))
    story.append(KeepTogether([tbl]))
    story.append(Spacer(1, 8))


# ── Section helper ─────────────────────────────────────────────────────────────

def _section(
    title: str,
    intro: str,
    items: list,          # list of (label, text, strategy, mode, image_data)
    styles: dict,
    story: list,
    width: float,
) -> None:
    if not items:
        return
    story.append(HRFlowable(
        width="100%", thickness=0.4, color=NAVY,
        spaceBefore=12, spaceAfter=8,
    ))
    story.append(Paragraph(html.escape(title), styles["section_title"]))
    story.append(Paragraph(html.escape(intro),  styles["section_intro"]))
    for label, text, strategy, mode, image_data in items:
        story.append(_card(label, text, strategy, styles, width, mode, image_data))


# ── Public API ─────────────────────────────────────────────────────────────────

def build_pdf(
    context: dict,
    messages: dict,
    logo_path: str = "assets/optspot_logo.png",
) -> bytes:
    """
    context:
        car_wash_name   str
        program_type    "visit-based" | "points-based"
        generated_date  str  (e.g. "2026-05-20")

    messages:
        welcome         {label, text, strategy}  | absent
        tracked         {label, text, strategy}  | absent
        progress        {label, text, strategy}  | absent
        rewards         [{label, text, strategy}, ...]
        auto_engage     [{label, text, strategy, days}, ...]  (sorted by days in PDF)
        hot_prospect    {label, text, strategy}  | absent

    Returns PDF bytes.
    """
    buf = io.BytesIO()
    styles = _styles()

    frame = Frame(
        FRAME_LEFT, FRAME_BOTTOM, FRAME_W, FRAME_H,
        id="body",
        leftPadding=0, rightPadding=0,
        topPadding=0,  bottomPadding=0,
    )
    doc = BaseDocTemplate(buf, pagesize=letter)
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame])])

    story = []

    # ── Title block ────────────────────────────────────────────────────────────
    car_wash   = context.get("car_wash_name") or "Car Wash"
    prog_type  = context.get("program_type", "visit-based")
    gen_date   = context.get("generated_date", "")
    prog_label = "Visit-based" if prog_type == "visit-based" else "Points-based"

    story.append(Paragraph(html.escape(car_wash), styles["name"]))
    story.append(Paragraph(f"Loyalty Program Type: {prog_label}", styles["program"]))
    if gen_date:
        story.append(Paragraph(f"Generated {gen_date}", styles["date"]))
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=0.75, color=NAVY, spaceAfter=8))

    # ── Incentives Summary ─────────────────────────────────────────────────────
    _incentives_summary(context, styles, story, FRAME_W)

    # ── Welcome & Onboarding ───────────────────────────────────────────────────
    welcome_items = []
    if messages.get("welcome"):
        m = messages["welcome"]
        welcome_items.append((m["label"], m["text"], m["strategy"], m.get("mode", "SMS"), m.get("image_data")))

    welcome_intro = "Sent immediately when a customer joins your loyalty program."
    if context.get("signup_reward_enabled") and context.get("signup_reward"):
        sr = context["signup_reward"]
        sr_days = context.get("signup_reward_expires_days", 7)
        welcome_intro += f" Signup reward: {sr} — expires in {sr_days} days."

    _section(
        "Welcome & Onboarding",
        welcome_intro,
        welcome_items, styles, story, FRAME_W,
    )

    # ── Visit Experience ───────────────────────────────────────────────────────
    visit_items = []
    if context.get("visit_tracked_enabled", True) and messages.get("tracked"):
        m = messages["tracked"]
        visit_items.append((m["label"], m["text"], m["strategy"], m.get("mode", "SMS"), m.get("image_data")))
    if messages.get("progress"):
        m = messages["progress"]
        visit_items.append((m["label"], m["text"], m["strategy"], m.get("mode", "SMS"), m.get("image_data")))
    _section(
        "Visit Experience",
        "Sent after each wash to confirm the visit and keep customers engaged.",
        visit_items, styles, story, FRAME_W,
    )

    # ── Reward Unlocks ─────────────────────────────────────────────────────────
    reward_items = [
        (m["label"], m["text"], m["strategy"], m.get("mode", "SMS"), m.get("image_data"))
        for m in messages.get("rewards", [])
    ]
    _section(
        "Reward Unlocks",
        "Sent when a customer hits a reward milestone.",
        reward_items, styles, story, FRAME_W,
    )

    # ── Program Loop (single-tier visit-based only) ────────────────────────────
    is_single_tier = len(context.get("tiers", [])) == 1
    if prog_type == "visit-based" and is_single_tier:
        story.append(HRFlowable(
            width="100%", thickness=0.4, color=NAVY,
            spaceBefore=12, spaceAfter=8,
        ))
        story.append(_loop_callout(FRAME_W))

    # ── Re-Engagement ──────────────────────────────────────────────────────────
    ae_items = [
        (m["label"], m["text"], m["strategy"], m.get("mode", "SMS"), m.get("image_data"))
        for m in sorted(messages.get("auto_engage", []), key=lambda x: x.get("days", 0))
    ]
    _section(
        "Re-Engagement",
        "Sent when customers haven't visited in a while. Designed to bring them back.",
        ae_items, styles, story, FRAME_W,
    )

    # ── VIP Offers ─────────────────────────────────────────────────────────────
    vip_items = []
    if messages.get("hot_prospect"):
        m = messages["hot_prospect"]
        vip_items.append((m["label"], m["text"], m["strategy"], m.get("mode", "SMS"), m.get("image_data")))
    _section(
        "VIP Offers",
        "Sent to high-frequency customers as a thank-you and upgrade incentive.",
        vip_items, styles, story, FRAME_W,
    )

    doc.build(story, canvasmaker=_canvas_factory(logo_path))
    return buf.getvalue()
