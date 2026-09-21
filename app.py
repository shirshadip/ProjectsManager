"""
Freelance Project Manager + Invoice Generator
==============================================
A single-file Flask application backed by Supabase (PostgreSQL) for
managing freelance projects and generating professional PDF invoices.

Run with:  python app.py
"""

import os
from datetime import date, timedelta
from functools import wraps
from io import BytesIO
from urllib.parse import quote

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from supabase import create_client

import qrcode
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

load_dotenv()

# =============================================================================
# 1. EASY-TO-EDIT CONFIGURATION
#    Change these values to match your own business. No other code changes
#    are required to rebrand the app or change the login credentials.
# =============================================================================

# --- Login credentials --------------------------------------------------
# This is a deliberately simple, hard-coded login for a single-user,
# personal application. See the "Authentication" note near the bottom of
# this file for why this is NOT appropriate for a public deployment.
ADMIN_USERNAME = os.getenv("Username")
ADMIN_PASSWORD = os.getenv("Password")

# --- Business details (shown on invoices and in the sidebar) -----------
BUSINESS_NAME = os.getenv("BUSINESS_NAME")
BUSINESS_OWNER = os.getenv("BUSINESS_OWNER")
SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL")
SUPPORT_PHONE = os.getenv("SUPPORT_PHONE")

# --- Payments -------------------------------------------------------------
UPI_ID = os.getenv("UPI_ID")

REFUND_POLICY = (
    "Refunds are subject to the terms agreed upon with the client at the "
    "start of the project. Completed and delivered work may not be "
    "refundable. Partial refunds for in-progress work are considered on a "
    "case-by-case basis."
)

# --- Fixed choices used in dropdowns and database CHECK constraints -----
PROJECT_STATUSES = ["Planning", "In Progress", "On Hold", "Completed", "Cancelled"]
PAYMENT_METHODS = ["UPI", "Net Banking", "Card", "Cash", "Other", "Not Paid"]


# =============================================================================
# 2. APP SETUP
# =============================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INVOICES_DIR = os.path.join(BASE_DIR, "invoices")
FONTS_DIR = os.path.join(BASE_DIR, "fonts")
os.makedirs(INVOICES_DIR, exist_ok=True)

app = Flask(__name__)

# Flask needs a secret key to sign session cookies. Set FLASK_SECRET_KEY in
# your .env file for anything beyond local experimentation.
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-only-change-this-secret-key")

# Secure session cookie configuration.
app.config["SESSION_COOKIE_HTTPONLY"] = True   # JavaScript can't read the cookie
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"  # basic CSRF hardening
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
# If you deploy this behind HTTPS, also uncomment the line below:
# app.config["SESSION_COOKIE_SECURE"] = True


# =============================================================================
# 3. SUPABASE CONNECTION
# =============================================================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as exc:  # pragma: no cover - defensive startup guard
        print(f"[freelance-manager] Could not create Supabase client: {exc}")
else:
    print(
        "[freelance-manager] WARNING: SUPABASE_URL / SUPABASE_KEY are not set. "
        "Copy .env.example to .env and add your Supabase project details. "
        "The app will still start, but any page that touches the database "
        "will show a friendly 'not configured' message until you do."
    )


class DatabaseNotConfigured(Exception):
    """Raised when Supabase credentials are missing from the environment."""


def get_client():
    if supabase is None:
        raise DatabaseNotConfigured(
            "Supabase is not configured. Copy .env.example to .env and add "
            "your SUPABASE_URL and SUPABASE_KEY, then restart the app."
        )
    return supabase


# =============================================================================
# 4. REGISTER A UNICODE FONT FOR PDF GENERATION
#    ReportLab's built-in fonts (Helvetica, Times) cannot render the Indian
#    Rupee sign (₹) - it shows up as a solid black box. DejaVu Sans (bundled
#    in fonts/) supports it, so we register it once at startup and use it
#    for every piece of text in the invoice PDF.
# =============================================================================

pdfmetrics.registerFont(TTFont("DejaVuSans", os.path.join(FONTS_DIR, "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", os.path.join(FONTS_DIR, "DejaVuSans-Bold.ttf")))
pdfmetrics.registerFont(TTFont("DejaVuSans-Oblique", os.path.join(FONTS_DIR, "DejaVuSans-Oblique.ttf")))
pdfmetrics.registerFontFamily(
    "DejaVuSans",
    normal="DejaVuSans",
    bold="DejaVuSans-Bold",
    italic="DejaVuSans-Oblique",
    boldItalic="DejaVuSans-Bold",
)


# =============================================================================
# 5. HELPER FUNCTIONS
# =============================================================================

def format_inr(amount, show_decimals=False):
    """Format a number as Indian Rupees with Indian-style digit grouping,
    e.g. 1234567 -> '₹12,34,567' (lakh/crore grouping, not western)."""
    try:
        amount = float(amount or 0)
    except (TypeError, ValueError):
        amount = 0.0

    negative = amount < 0
    amount = abs(amount)

    if show_decimals:
        whole = int(amount)
        decimals = f"{amount:.2f}".split(".")[1]
    else:
        whole = int(round(amount))
        decimals = None

    whole_str = str(whole)
    if len(whole_str) > 3:
        last3 = whole_str[-3:]
        rest = whole_str[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        whole_str = ",".join(groups) + "," + last3

    formatted = f"\u20b9{whole_str}"
    if decimals is not None:
        formatted += f".{decimals}"
    return f"-{formatted}" if negative else formatted


def slugify(value):
    """'In Progress' -> 'in-progress', used for CSS badge classes."""
    return str(value or "").strip().lower().replace(" ", "-")


def payment_breakdown(project):
    """Given a project row, work out remaining amount and payment status."""
    project_amount = float(project.get("project_amount") or 0)
    paid_amount = float(project.get("paid_amount") or 0)
    remaining_amount = round(project_amount - paid_amount, 2)
    if remaining_amount < 0:
        remaining_amount = 0.0

    if remaining_amount <= 0:
        status, label = "paid", "Paid"
    elif paid_amount > 0:
        status, label = "partial", "Partially paid"
    else:
        status, label = "unpaid", "Unpaid"

    return {
        "project_amount": project_amount,
        "paid_amount": paid_amount,
        "remaining_amount": remaining_amount,
        "status": status,
        "label": label,
    }


# Make these available inside every Jinja template.
app.jinja_env.filters["inr"] = format_inr
app.jinja_env.filters["slugify"] = slugify
app.jinja_env.globals["payment_breakdown"] = payment_breakdown


@app.context_processor
def inject_globals():
    return {
        "business_name": BUSINESS_NAME,
        "current_year": date.today().year,
        "is_logged_in": bool(session.get("logged_in")),
    }


def login_required(view_func):
    """Decorator that redirects anonymous visitors to /login."""

    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.path))
        return view_func(*args, **kwargs)

    return wrapped_view


def validate_project_form(form):
    """Validate a project form submission.

    Returns (errors, cleaned_data). If errors is non-empty, cleaned_data
    is None and the form should be re-rendered with the errors flashed.
    """
    errors = []

    client_name = (form.get("client_name") or "").strip()
    project_name = (form.get("project_name") or "").strip()
    project_status = form.get("project_status") or ""
    paid_via = form.get("paid_via") or ""
    is_completed = form.get("is_completed") == "on"

    if not client_name:
        errors.append("Client name is required.")
    if not project_name:
        errors.append("Project name is required.")
    if project_status not in PROJECT_STATUSES:
        errors.append("Please choose a valid project status.")
    if paid_via not in PAYMENT_METHODS:
        errors.append("Please choose a valid payment method.")

    project_amount = None
    try:
        project_amount = round(float(form.get("project_amount", "")), 2)
        if project_amount < 0:
            errors.append("Project amount cannot be negative.")
    except (TypeError, ValueError):
        errors.append("Project amount must be a valid number.")

    paid_amount = None
    try:
        paid_amount = round(float(form.get("paid_amount", "")), 2)
        if paid_amount < 0:
            errors.append("Paid amount cannot be negative.")
    except (TypeError, ValueError):
        errors.append("Paid amount must be a valid number.")

    if errors:
        return errors, None

    cleaned = {
        "client_name": client_name,
        "project_name": project_name,
        "project_amount": project_amount,
        "paid_amount": paid_amount,
        "project_status": project_status,
        "is_completed": is_completed,
        "paid_via": paid_via,
    }
    return errors, cleaned


def fetch_all_projects():
    """Return (projects, error_message)."""
    try:
        client = get_client()
        response = client.table("projects").select("*").order("created_at", desc=True).execute()
        return response.data or [], None
    except DatabaseNotConfigured as exc:
        return [], str(exc)
    except Exception as exc:
        app.logger.error("Could not fetch projects: %s", exc)
        return [], "Could not reach the database. Check your Supabase connection and try again."


def fetch_project(project_id):
    """Return (project_dict_or_None, error_message)."""
    try:
        client = get_client()
        response = client.table("projects").select("*").eq("id", project_id).execute()
        rows = response.data or []
        return (rows[0] if rows else None), None
    except DatabaseNotConfigured as exc:
        return None, str(exc)
    except Exception as exc:
        app.logger.error("Could not fetch project %s: %s", project_id, exc)
        return None, "Could not reach the database. Check your Supabase connection and try again."


def generate_invoice_number():
    """Generate the next sequential invoice number, e.g. INV-00007.

    We look at every invoice_number already stored (not the project id or
    row count) so numbering stays sequential even if projects without an
    invoice are deleted later.
    """
    highest = 0
    try:
        client = get_client()
        response = client.table("projects").select("invoice_number").execute()
        for row in response.data or []:
            value = row.get("invoice_number")
            if value and value.startswith("INV-"):
                try:
                    highest = max(highest, int(value.split("-")[1]))
                except (IndexError, ValueError):
                    continue
    except Exception as exc:
        app.logger.error("Could not determine next invoice number: %s", exc)
    return f"INV-{highest + 1:05d}"


# =============================================================================
# 6. PDF INVOICE GENERATION
# =============================================================================

PDF_COLORS = {
    "primary": colors.HexColor("#12433F"),
    "primary_dark": colors.HexColor("#0B2E2B"),
    "accent": colors.HexColor("#C98A2C"),
    "text": colors.HexColor("#16211F"),
    "muted": colors.HexColor("#667069"),
    "border": colors.HexColor("#E1E4DE"),
    "surface": colors.HexColor("#F5F6F4"),
    "success": colors.HexColor("#1E7F4C"),
    "success_soft": colors.HexColor("#E3F3E9"),
    "danger": colors.HexColor("#B3402A"),
    "danger_soft": colors.HexColor("#FBE7E1"),
    "warning": colors.HexColor("#B7791F"),
    "warning_soft": colors.HexColor("#FBF0DB"),
    "white": colors.white,
}

CONTENT_WIDTH = 174 * mm  # A4 width (210mm) minus 18mm margins on each side


def _invoice_styles():
    return {
        "business": ParagraphStyle(
            "business", fontName="DejaVuSans-Bold", fontSize=16,
            textColor=PDF_COLORS["primary_dark"], leading=19,
        ),
        "business_sub": ParagraphStyle(
            "business_sub", fontName="DejaVuSans", fontSize=9,
            textColor=PDF_COLORS["muted"], leading=12,
        ),
        "invoice_title": ParagraphStyle(
            "invoice_title", fontName="DejaVuSans-Bold", fontSize=20,
            textColor=PDF_COLORS["primary"], alignment=TA_RIGHT, leading=24,
        ),
        "meta": ParagraphStyle(
            "meta", fontName="DejaVuSans", fontSize=9.5,
            textColor=PDF_COLORS["muted"], alignment=TA_RIGHT, leading=14,
        ),
        "label": ParagraphStyle(
            "label", fontName="DejaVuSans-Bold", fontSize=8.5,
            textColor=PDF_COLORS["muted"], leading=11, spaceAfter=2,
        ),
        "value": ParagraphStyle(
            "value", fontName="DejaVuSans-Bold", fontSize=12,
            textColor=PDF_COLORS["text"], leading=15,
        ),
        "value_small": ParagraphStyle(
            "value_small", fontName="DejaVuSans", fontSize=9.5,
            textColor=PDF_COLORS["muted"], leading=13,
        ),
        "section_heading": ParagraphStyle(
            "section_heading", fontName="DejaVuSans-Bold", fontSize=9.5,
            textColor=PDF_COLORS["primary"], leading=14, spaceBefore=2, spaceAfter=6,
        ),
        "normal": ParagraphStyle(
            "normal", fontName="DejaVuSans", fontSize=10,
            textColor=PDF_COLORS["text"], leading=15,
        ),
        "muted": ParagraphStyle(
            "muted", fontName="DejaVuSans", fontSize=8.5,
            textColor=PDF_COLORS["muted"], leading=13,
        ),
        "table_header": ParagraphStyle(
            "table_header", fontName="DejaVuSans-Bold", fontSize=9.5,
            textColor=PDF_COLORS["white"], leading=12,
        ),
        "table_cell": ParagraphStyle(
            "table_cell", fontName="DejaVuSans", fontSize=10,
            textColor=PDF_COLORS["text"], leading=13,
        ),
        "table_cell_right": ParagraphStyle(
            "table_cell_right", fontName="DejaVuSans", fontSize=10,
            textColor=PDF_COLORS["text"], leading=13, alignment=TA_RIGHT,
        ),
        "table_cell_bold_right": ParagraphStyle(
            "table_cell_bold_right", fontName="DejaVuSans-Bold", fontSize=10.5,
            textColor=PDF_COLORS["text"], leading=14, alignment=TA_RIGHT,
        ),
        "status_banner": ParagraphStyle(
            "status_banner", fontName="DejaVuSans-Bold", fontSize=12,
            leading=16, alignment=TA_CENTER,
        ),
        "pay_amount": ParagraphStyle(
            "pay_amount", fontName="DejaVuSans-Bold", fontSize=16,
            textColor=PDF_COLORS["danger"], leading=20,
        ),
        "paid_note": ParagraphStyle(
            "paid_note", fontName="DejaVuSans", fontSize=10.5,
            textColor=PDF_COLORS["success"], leading=15,
        ),
        "footer": ParagraphStyle(
            "footer", fontName="DejaVuSans-Bold", fontSize=11,
            textColor=PDF_COLORS["primary_dark"], alignment=TA_CENTER, leading=14,
        ),
        "footer_muted": ParagraphStyle(
            "footer_muted", fontName="DejaVuSans", fontSize=8.5,
            textColor=PDF_COLORS["muted"], alignment=TA_CENTER, leading=12,
        ),
    }


def generate_upi_qr_image(amount, invoice_number):
    """Build a UPI payment QR code and return it as an in-memory PNG."""
    note = f"Invoice {invoice_number}"
    upi_uri = (
        f"upi://pay?pa={quote(UPI_ID)}&pn={quote(BUSINESS_OWNER)}"
        f"&am={amount:.2f}&cu=INR&tn={quote(note)}"
    )
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=1)
    qr.add_data(upi_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#12433F", back_color="#FFFFFF").convert("RGB")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def build_invoice_pdf(project, invoice_number):
    """Build the invoice PDF for a project and return an in-memory buffer."""
    styles = _invoice_styles()
    breakdown = payment_breakdown(project)
    project_amount = breakdown["project_amount"]
    paid_amount = breakdown["paid_amount"]
    remaining_amount = breakdown["remaining_amount"]

    if breakdown["status"] == "paid":
        payment_label, banner_bg, banner_fg = "PAID", PDF_COLORS["success_soft"], PDF_COLORS["success"]
    elif breakdown["status"] == "partial":
        payment_label, banner_bg, banner_fg = "PARTIALLY PAID", PDF_COLORS["warning_soft"], PDF_COLORS["warning"]
    else:
        payment_label, banner_bg, banner_fg = "UNPAID", PDF_COLORS["danger_soft"], PDF_COLORS["danger"]

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=16 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        title=f"Invoice {invoice_number}",
    )

    story = []

    # --- Header: business name (left) and "INVOICE" (right) -------------
    header = Table(
        [[
            [
                Paragraph(BUSINESS_NAME, styles["business"]),
                Paragraph(BUSINESS_OWNER, styles["business_sub"]),
            ],
            [
                Paragraph("INVOICE", styles["invoice_title"]),
                Paragraph(f"Invoice #: {invoice_number}", styles["meta"]),
                Paragraph(f"Date: {date.today().strftime('%d %b %Y')}", styles["meta"]),
            ],
        ]],
        colWidths=[CONTENT_WIDTH * 0.55, CONTENT_WIDTH * 0.45],
    )
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header)
    story.append(Spacer(1, 6 * mm))
    story.append(HRFlowable(width="100%", thickness=1.2, color=PDF_COLORS["primary"], spaceAfter=6 * mm))

    # --- Client / project two-column block -------------------------------
    client_block = [
        Paragraph("Bill to", styles["label"]),
        Paragraph(project.get("client_name", ""), styles["value"]),
    ]
    project_block = [
        Paragraph("Project", styles["label"]),
        Paragraph(project.get("project_name", ""), styles["value"]),
        Spacer(1, 1.5 * mm),
        Paragraph(f"Status: {project.get('project_status', '')}", styles["value_small"]),
    ]
    two_col = Table([[client_block, project_block]], colWidths=[CONTENT_WIDTH * 0.5, CONTENT_WIDTH * 0.5])
    two_col.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(two_col)
    story.append(Spacer(1, 9 * mm))

    # --- Payment summary table -------------------------------------------
    story.append(Paragraph("PAYMENT DETAILS", styles["section_heading"]))
    summary_rows = [
        [Paragraph("Description", styles["table_header"]), Paragraph("Amount", styles["table_header"])],
        [Paragraph("Project amount", styles["table_cell"]), Paragraph(format_inr(project_amount, True), styles["table_cell_right"])],
        [Paragraph("Paid amount", styles["table_cell"]), Paragraph(format_inr(paid_amount, True), styles["table_cell_right"])],
        [Paragraph("Remaining amount", styles["table_cell"]), Paragraph(format_inr(remaining_amount, True), styles["table_cell_bold_right"])],
    ]
    summary_table = Table(summary_rows, colWidths=[CONTENT_WIDTH * 0.7, CONTENT_WIDTH * 0.3])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PDF_COLORS["primary"]),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
        ("TOPPADDING", (0, 0), (-1, 0), 7),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
        ("TOPPADDING", (0, 1), (-1, -1), 6),
        ("LINEBELOW", (0, 1), (-1, -2), 0.6, PDF_COLORS["border"]),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, PDF_COLORS["primary"]),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 0.6, PDF_COLORS["border"]),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 5 * mm))

    # --- Payment status banner -------------------------------------------
    banner_style = ParagraphStyle("banner", parent=styles["status_banner"], textColor=banner_fg)
    banner = Table(
        [[Paragraph(f"PAYMENT STATUS: {payment_label}", banner_style)]],
        colWidths=[CONTENT_WIDTH],
    )
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), banner_bg),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 0, colors.white),
    ]))
    story.append(banner)
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(f"Payment method: {project.get('paid_via', 'Not Paid')}", styles["normal"]))
    story.append(Spacer(1, 8 * mm))

    # --- UPI payment information (only shown if something is still due) --
    if remaining_amount > 0:
        story.append(Paragraph("PAYMENT INFORMATION", styles["section_heading"]))
        qr_buffer = generate_upi_qr_image(remaining_amount, invoice_number)
        qr_image = Image(qr_buffer, width=30 * mm, height=30 * mm)
        upi_text = [
            Paragraph("Scan with any UPI app to pay", styles["value_small"]),
            Paragraph(f"UPI ID: {UPI_ID}", styles["value"]),
            Spacer(1, 3 * mm),
            Paragraph(f"PAY {format_inr(remaining_amount, True)}", styles["pay_amount"]),
        ]
        upi_table = Table([[qr_image, upi_text]], colWidths=[36 * mm, CONTENT_WIDTH - 36 * mm])
        upi_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(upi_table)
    else:
        story.append(Paragraph("Your project has been paid in full. Thank you!", styles["paid_note"]))
    story.append(Spacer(1, 9 * mm))

    # --- Support -----------------------------------------------------------
    story.append(Paragraph("SUPPORT", styles["section_heading"]))
    story.append(Paragraph(f"Email: {SUPPORT_EMAIL}", styles["normal"]))
    story.append(Paragraph(f"Phone: {SUPPORT_PHONE}", styles["normal"]))
    story.append(Spacer(1, 8 * mm))

    # --- Refund policy -------------------------------------------------------
    story.append(Paragraph("REFUND POLICY", styles["section_heading"]))
    story.append(Paragraph(REFUND_POLICY, styles["muted"]))
    story.append(Spacer(1, 10 * mm))

    story.append(HRFlowable(width="100%", thickness=0.8, color=PDF_COLORS["border"], spaceAfter=6 * mm))
    story.append(Paragraph("Think , Build and publish with us - Thank You", styles["footer"]))
    story.append(Paragraph(BUSINESS_NAME, styles["footer_muted"]))

    doc.build(story)
    buffer.seek(0)
    return buffer


# =============================================================================
# 7. AUTH ROUTES
# =============================================================================

@app.route("/")
def index():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        next_url = request.form.get("next") or url_for("dashboard")

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session.clear()
            session["logged_in"] = True
            session.permanent = True
            flash("Welcome back!", "success")
            if next_url.startswith("/"):
                return redirect(next_url)
            return redirect(url_for("dashboard"))

        flash("Invalid username or password.", "error")

    next_url = request.args.get("next", "")
    return render_template("login.html", next_url=next_url)


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# =============================================================================
# 8. DASHBOARD
# =============================================================================

@app.route("/dashboard")
@login_required
def dashboard():
    projects, error = fetch_all_projects()
    if error:
        flash(error, "error")

    total_projects = len(projects)
    completed_projects = sum(1 for p in projects if p.get("is_completed"))
    pending_projects = total_projects - completed_projects
    total_revenue = sum(float(p.get("paid_amount") or 0) for p in projects)
    total_unpaid = sum(
        max(float(p.get("project_amount") or 0) - float(p.get("paid_amount") or 0), 0)
        for p in projects
    )
    recent_projects = projects[:5]

    return render_template(
        "dashboard.html",
        total_projects=total_projects,
        completed_projects=completed_projects,
        pending_projects=pending_projects,
        total_revenue=total_revenue,
        total_unpaid=total_unpaid,
        recent_projects=recent_projects,
    )


# =============================================================================
# 9. PROJECT CRUD ROUTES
# =============================================================================

@app.route("/projects")
@login_required
def projects_list():
    projects, error = fetch_all_projects()
    if error:
        flash(error, "error")
    return render_template("projects.html", projects=projects, statuses=PROJECT_STATUSES)


@app.route("/projects/add", methods=["GET", "POST"])
@login_required
def add_project():
    if request.method == "POST":
        errors, cleaned = validate_project_form(request.form)
        if errors:
            for message in errors:
                flash(message, "error")
            return render_template(
                "add_project.html", form=request.form,
                statuses=PROJECT_STATUSES, payment_methods=PAYMENT_METHODS,
            ), 400

        try:
            client = get_client()
            client.table("projects").insert(cleaned).execute()
            flash("Project created successfully.", "success")
            return redirect(url_for("projects_list"))
        except DatabaseNotConfigured as exc:
            flash(str(exc), "error")
        except Exception as exc:
            app.logger.error("Insert failed: %s", exc)
            flash("Could not save the project. Please try again.", "error")

        return render_template(
            "add_project.html", form=request.form,
            statuses=PROJECT_STATUSES, payment_methods=PAYMENT_METHODS,
        ), 500

    return render_template(
        "add_project.html", form={}, statuses=PROJECT_STATUSES, payment_methods=PAYMENT_METHODS
    )


@app.route("/projects/<int:project_id>")
@login_required
def project_details(project_id):
    project, error = fetch_project(project_id)
    if error:
        flash(error, "error")
        return redirect(url_for("projects_list"))
    if not project:
        flash("Project not found.", "error")
        return redirect(url_for("projects_list"))

    return render_template("project_details.html", project=project, payment=payment_breakdown(project))


@app.route("/projects/<int:project_id>/edit", methods=["GET", "POST"])
@login_required
def edit_project(project_id):
    project, error = fetch_project(project_id)
    if error:
        flash(error, "error")
        return redirect(url_for("projects_list"))
    if not project:
        flash("Project not found.", "error")
        return redirect(url_for("projects_list"))

    if request.method == "POST":
        errors, cleaned = validate_project_form(request.form)
        if errors:
            for message in errors:
                flash(message, "error")
            merged = dict(project)
            merged.update(request.form)
            merged["is_completed"] = request.form.get("is_completed") == "on"
            return render_template(
                "edit_project.html", project=merged,
                statuses=PROJECT_STATUSES, payment_methods=PAYMENT_METHODS,
            ), 400

        try:
            client = get_client()
            client.table("projects").update(cleaned).eq("id", project_id).execute()
            flash("Project updated successfully.", "success")
            return redirect(url_for("project_details", project_id=project_id))
        except DatabaseNotConfigured as exc:
            flash(str(exc), "error")
        except Exception as exc:
            app.logger.error("Update failed: %s", exc)
            flash("Could not update the project. Please try again.", "error")

    return render_template(
        "edit_project.html", project=project, statuses=PROJECT_STATUSES, payment_methods=PAYMENT_METHODS
    )


@app.route("/projects/<int:project_id>/delete", methods=["POST"])
@login_required
def delete_project(project_id):
    try:
        client = get_client()
        client.table("projects").delete().eq("id", project_id).execute()
        flash("Project deleted successfully.", "success")
    except DatabaseNotConfigured as exc:
        flash(str(exc), "error")
    except Exception as exc:
        app.logger.error("Delete failed: %s", exc)
        flash("Could not delete the project. Please try again.", "error")

    return redirect(url_for("projects_list"))


# =============================================================================
# 10. INVOICE ROUTE
# =============================================================================

@app.route("/invoice/<int:project_id>")
@login_required
def invoice(project_id):
    project, error = fetch_project(project_id)
    if error:
        flash(error, "error")
        return redirect(url_for("projects_list"))
    if not project:
        flash("Project not found.", "error")
        return redirect(url_for("projects_list"))
    if not project.get("is_completed"):
        flash("Invoice available after project completion.", "error")
        return redirect(url_for("project_details", project_id=project_id))

    invoice_number = project.get("invoice_number")
    if not invoice_number:
        invoice_number = generate_invoice_number()
        try:
            client = get_client()
            client.table("projects").update({"invoice_number": invoice_number}).eq("id", project_id).execute()
        except Exception as exc:
            app.logger.error("Could not persist invoice number: %s", exc)

    try:
        pdf_buffer = build_invoice_pdf(project, invoice_number)
    except Exception as exc:
        app.logger.error("PDF generation failed: %s", exc)
        flash("Could not generate the invoice PDF. Please try again.", "error")
        return redirect(url_for("project_details", project_id=project_id))

    filename = f"invoice_{invoice_number}.pdf"

    # Keep a copy on disk for your own records.
    try:
        with open(os.path.join(INVOICES_DIR, filename), "wb") as f:
            f.write(pdf_buffer.getvalue())
    except OSError as exc:
        app.logger.warning("Could not save a local copy of the invoice: %s", exc)

    pdf_buffer.seek(0)
    flash("Invoice generated successfully.", "success")
    return send_file(pdf_buffer, mimetype="application/pdf", as_attachment=True, download_name=filename)


# =============================================================================
# 11. ERROR HANDLERS
# =============================================================================

@app.errorhandler(404)
def not_found(_e):
    return render_template("404.html"), 404


@app.errorhandler(500)
def server_error(e):
    app.logger.error("Server error: %s", e)
    return render_template("500.html"), 500


# =============================================================================
# 12. ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)