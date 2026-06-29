import base64
import hmac
import html as _html
import json
import re
from datetime import date, datetime
from PIL import Image
import streamlit as st
import streamlit.components.v1 as components
from streamlit_local_storage import LocalStorage
from message_engine import generate_message, is_demo_mode
from pdf_export import build_pdf
from docx_export import build_loyalty_docx, _incentive_items, _code_items
import resend

# ── Page config ────────────────────────────────────────────────────────────────

_favicon = Image.open("assets/optspot_logo.png")
st.set_page_config(
    page_title="OptSpot Loyalty Message Generator",
    page_icon=_favicon,
    layout="wide",
)

# ── Sidebar width ──────────────────────────────────────────────────────────────

st.markdown("""
<style>
    [data-testid="stSidebar"] {
        min-width: 450px !important;
        max-width: 520px !important;
    }
    [data-testid="stSidebar"] > div:first-child {
        width: 470px !important;
    }
</style>
""", unsafe_allow_html=True)

# ── Password gate ──────────────────────────────────────────────────────────────

def check_password():
    """Single shared-password gate."""
    def password_entered():
        if hmac.compare_digest(
            st.session_state.get("password", ""),
            st.secrets.get("app_password", "")
        ):
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if st.session_state.get("password_correct", False):
        return True

    st.markdown("### OptSpot Loyalty Message Generator")
    st.text_input("Enter team password", type="password", on_change=password_entered, key="password")
    if "password_correct" in st.session_state and not st.session_state["password_correct"]:
        st.error("Incorrect password. Contact Tanner for access.")
    return False

# if not check_password():
   #     st.stop()

# ── Feedback form via Resend ───────────────────────────────────────────────────

def send_feedback_via_resend(am_name, message, screenshot=None):
    resend.api_key = st.secrets.get("resend_api_key")
    if not resend.api_key:
        raise ValueError("resend_api_key not configured in secrets")

    feedback_to = st.secrets.get("feedback_to", "tanner@optspot.com")
    sender = st.secrets.get("resend_sender", "OptSpot Feedback <onboarding@resend.dev>")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html_body = f"""
    <h3>New feedback from {am_name}</h3>
    <p><strong>Submitted:</strong> {timestamp}</p>
    <hr>
    <p><strong>Message:</strong></p>
    <p>{message.replace(chr(10), '<br>')}</p>
    """

    email_payload = {
        "from": sender,
        "to": [feedback_to],
        "subject": f"[Loyalty Generator] Feedback from {am_name}",
        "html": html_body,
    }

    if screenshot is not None:
        img_bytes = screenshot.read()
        email_payload["attachments"] = [{
            "filename": screenshot.name,
            "content": list(img_bytes),
        }]

    resend.Emails.send(email_payload)

localS = LocalStorage()

# ── localStorage persistence ───────────────────────────────────────────────────

_LS_KEY = "optspot_loyalty_config"

_SCALAR_PERSIST_KEYS = [
    "car_wash_name", "program_type",
    "signup_reward_enabled", "signup_reward", "signup_reward_expires_days",
    "visit_tracked_enabled",
    "default_mode",
    "view_mode",
    "hpo_enabled",
    "hpo_membership_offer", "hpo_timeframe_days", "hpo_min_visits", "hpo_max_checkins",
    "hpo_execution",
    "points_rewards_enabled",
    "uses_redemption_codes",
    "codes_location", "code_format_example", "codes_provider", "code_delivery_method",
    "user_optspot_email",
]


def _load_from_storage():
    if st.session_state.get("_storage_loaded_this_run", False):
        return
    try:
        saved = localS.getItem(_LS_KEY)
        if saved and isinstance(saved, dict):
            for k, v in saved.items():
                if k not in st.session_state:
                    st.session_state[k] = v
        st.session_state["_storage_loaded_this_run"] = True
    except Exception as e:
        print(f"[storage] load failed: {e}")
        st.session_state["_storage_loaded_this_run"] = True


def _save_to_storage():
    # Guard: only run once per script run to prevent duplicate localStorage calls
    if st.session_state.get("_storage_saved_this_run", False):
        return
    try:
        config = {k: st.session_state[k] for k in _SCALAR_PERSIST_KEYS if k in st.session_state}
        # Rebuild list data from widget keys — Streamlit updates widget session state
        # keys BEFORE calling on_change, so these reflect the latest user input even
        # when the backing list dict hasn't been reassigned yet.
        n_tiers = len(st.session_state.get("tiers", []))
        config["tiers"] = [
            {
                "visits": st.session_state.get(
                    f"tier_visits_{i}",
                    st.session_state.tiers[i]["visits"] if i < n_tiers else 5,
                ),
                "reward": st.session_state.get(
                    f"tier_reward_{i}",
                    st.session_state.tiers[i]["reward"] if i < n_tiers else "",
                ),
            }
            for i in range(n_tiers)
        ]
        n_wps = len(st.session_state.get("wash_packages", []))
        config["wash_packages"] = [
            {
                "name": st.session_state.get(
                    f"wash_pkg_name_{i}",
                    st.session_state.wash_packages[i]["name"] if i < n_wps else "",
                ),
                "earn_points": st.session_state.get(
                    f"wash_pkg_earn_{i}",
                    st.session_state.wash_packages[i]["earn_points"] if i < n_wps else 1,
                ),
                "redeem_cost": st.session_state.get(
                    f"wash_pkg_redeem_{i}",
                    st.session_state.wash_packages[i]["redeem_cost"] if i < n_wps else 4,
                ),
            }
            for i in range(n_wps)
        ]
        n_ae = len(st.session_state.get("auto_engage", []))
        config["auto_engage"] = [
            {
                "days": st.session_state.get(
                    f"ae_days_{i}",
                    st.session_state.auto_engage[i]["days"] if i < n_ae else 30,
                ),
                "type": st.session_state.get(
                    f"ae_type_{i}",
                    st.session_state.auto_engage[i].get("type", "offer") if i < n_ae else "offer",
                ),
                "offer": st.session_state.get(
                    f"ae_offer_{i}",
                    st.session_state.auto_engage[i].get("offer", "") if i < n_ae else "",
                ),
            }
            for i in range(n_ae)
        ]
        localS.setItem(_LS_KEY, config, key="ls_save_config")
        st.session_state["_storage_saved_this_run"] = True
    except Exception as e:
        print(f"[storage] save failed: {e}")


_load_from_storage()


# ── Session state defaults ─────────────────────────────────────────────────────

if "default_mode" not in st.session_state:
    st.session_state["default_mode"] = "SMS"

if "global_upload_counter" not in st.session_state:
    st.session_state["global_upload_counter"] = 0

# ── Helpers ────────────────────────────────────────────────────────────────────

def _img_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


# Order matches the docx/PDF exports. (section name, messages_data key)
_HTML_SECTIONS = [
    ("Welcome", "welcome"),
    ("Visit Tracked", "tracked"),
    ("Progress", "progress"),
    ("Rewards", "rewards"),
    ("Auto-Engage", "auto_engage"),
    ("Hot Prospect", "hot_prospect"),
]


def build_loyalty_html(context: dict, messages_data: dict) -> str:
    """Render the loyalty draft as semantic, inline-styled HTML.

    Mirrors the docx/PDF content. Inline styles only (no <style> blocks) so it
    pastes cleanly into Google Docs with headings, bullets, and message blocks.
    Disabled sections are skipped (they're simply absent from messages_data).
    """
    esc = _html.escape
    FAM = "font-family:Arial,sans-serif;"
    NAVY = "color:#264078;"
    BLUE = "color:#23A3EA;"
    GRAY = "color:#888888;"

    car_wash = context.get("car_wash_name") or "Car Wash"
    parts = [
        f'<h1 style="{FAM}{NAVY}">{esc(car_wash)} — Loyalty Message Draft</h1>',
        f'<p style="{FAM}{GRAY}"><em>Prepared by OptSpot. '
        f'Review, edit, and return for finalization.</em></p>',
    ]

    # ── Program Incentives Summary ──
    parts.append(f'<h2 style="{FAM}{NAVY}">Program Incentives Summary</h2>')
    items = _incentive_items(context)
    code_items = _code_items(context)
    if items:
        parts.append("<ul>")
        parts += [f'<li style="{FAM}">{esc(it)}</li>' for it in items]
        parts.append("</ul>")
    if code_items:
        parts.append(f'<h3 style="{FAM}{NAVY}">Redemption Codes</h3>')
        parts.append("<ul>")
        parts += [f'<li style="{FAM}">{esc(it)}</li>' for it in code_items]
        parts.append("</ul>")
    if not items and not code_items:
        parts.append(f'<p style="{FAM}">No incentives configured.</p>')

    # ── Message sections ──
    for section_name, key in _HTML_SECTIONS:
        payload = messages_data.get(key)
        if not payload:
            continue
        entries = payload if isinstance(payload, list) else [payload]
        entries = [m for m in entries if m and m.get("text")]
        if not entries:
            continue

        parts.append(f'<h2 style="{FAM}{NAVY}">{esc(section_name)}</h2>')
        multi = len(entries) > 1
        for m in entries:
            mode = m.get("mode", "SMS")
            heading = f"{m.get('label', section_name)} ({mode})" if multi else mode
            parts.append(f'<h3 style="{FAM}{BLUE}">{esc(heading)}</h3>')
            body = esc(m.get("text", "")).replace("\n", "<br>")
            parts.append(f'<p style="{FAM}">{body}</p>')
        parts.append("<br><br>")

    parts.append(
        f'<p style="{FAM}{GRAY}"><em>OptSpot Internal Draft — '
        f'for client review only.</em></p>'
    )
    return "".join(parts)


def _gdocs_copy_button_html(rendered_html: str, user_email: str = "") -> str:
    """Build a self-contained HTML/JS button that copies rich HTML to the
    clipboard and opens a blank Google Doc. Falls back to plain text when the
    rich clipboard API is unavailable, and surfaces permission errors clearly.
    """
    # Escape for safe embedding inside a JS template literal:
    #   backslash first, then backtick and $ (template interpolation), and
    #   neutralize any "</script>" so the HTML parser can't close the tag early.
    safe = (
        rendered_html.replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("$", "\\$")
        .replace("</", "<\\/")
    )
    # json.dumps yields a safely-escaped JS string literal (quotes included).
    email_js = json.dumps((user_email or "").strip())
    return f"""
<button id="copyDocsBtn" style="
    width:100%;background-color:#23A3EA;color:#FFFFFF;border:none;border-radius:4px;
    font-weight:700;font-size:0.92rem;letter-spacing:0.02em;padding:0.55rem 0.8rem;
    cursor:pointer;box-shadow:0 3px 10px rgba(35,163,234,0.35);
    font-family:'Source Sans Pro',Arial,sans-serif;">
    📋 Copy + Open in Google Docs
</button>
<script>
document.getElementById('copyDocsBtn').addEventListener('click', async () => {{
    const html = `{safe}`;
    const userEmail = {email_js};
    // Force the new doc to open under the AM's OptSpot account when set;
    // otherwise fall back to the browser's default Google account.
    const docUrl = userEmail
        ? `https://docs.google.com/document/create?authuser=${{encodeURIComponent(userEmail)}}`
        : 'https://docs.google.com/document/create';
    try {{
        if (navigator.clipboard && navigator.clipboard.write && window.ClipboardItem) {{
            const blob = new Blob([html], {{type: 'text/html'}});
            const item = new ClipboardItem({{'text/html': blob}});
            await navigator.clipboard.write([item]);
            window.open(docUrl, '_blank');
        }} else {{
            throw new Error('Rich clipboard not supported');
        }}
    }} catch (err) {{
        // Fallback: copy plain text so the AM still gets the draft content.
        try {{
            const tmp = document.createElement('div');
            tmp.innerHTML = html;
            const plain = tmp.innerText || tmp.textContent || '';
            await navigator.clipboard.writeText(plain);
            window.open(docUrl, '_blank');
            alert('Copied as plain text (rich formatting is unavailable in this browser). Paste with Cmd+V.');
        }} catch (err2) {{
            const msg = (err2 && err2.message) ? err2.message : String(err);
            if (err2 && (err2.name === 'NotAllowedError' || /denied|permission/i.test(msg))) {{
                alert('Clipboard access is blocked. Enable clipboard permission for this site in your browser, then try again.');
            }} else {{
                alert('Clipboard copy failed: ' + msg);
            }}
        }}
    }}
}});
</script>
"""


# ── Custom CSS ─────────────────────────────────────────────────────────────────

st.markdown("""
<style>
/* === Brand Variables === */
:root {
    --optspot-navy: #264078;
    --optspot-blue: #23A3EA;
    --optspot-bg: #0E1729;
    --optspot-card: #1A2540;
    --optspot-text: #FFFFFF;
    --optspot-muted: #8FA3C2;
}

/* === Layout === */
.main .block-container {
    padding-top: 1.5rem;
    padding-bottom: 3rem;
}

/* === App header === */
.optspot-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 0 16px 0;
    border-bottom: 2px solid var(--optspot-blue);
    margin-bottom: 24px;
}
.optspot-header-logo {
    background: rgba(255, 255, 255, 0.04);
    padding: 8px 16px;
    border-radius: 8px;
    display: inline-block;
}
.optspot-header-logo img {
    height: 48px;
    display: block;
}
.optspot-header-title {
    text-align: right;
}
.optspot-header-title h1 {
    color: var(--optspot-text) !important;
    font-size: 1.45rem !important;
    font-weight: 700 !important;
    margin: 0 !important;
    line-height: 1.2 !important;
}
.optspot-header-title p {
    color: var(--optspot-muted) !important;
    font-size: 0.82rem !important;
    margin: 4px 0 0 0 !important;
    letter-spacing: 0.04em !important;
}

/* === Sidebar === */
[data-testid="stSidebar"] {
    background-color: #1A2847 !important;
    border-right: 1px solid #264078;
}
[data-testid="stSidebar"] .stMarkdown p {
    color: #C5D3E8;
    font-size: 0.88rem;
}

.sidebar-section {
    color: var(--optspot-blue) !important;
    font-size: 0.7rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.12em !important;
    text-transform: uppercase !important;
    margin: 1.1rem 0 0.15rem 0 !important;
    padding: 2px 0 2px 8px !important;
    border-left: 3px solid var(--optspot-navy) !important;
}

/* === Primary buttons (Generate, Regenerate, Submit) === */
button[data-testid="baseButton-primary"] {
    background-color: var(--optspot-blue) !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 4px !important;
    font-weight: 600 !important;
    transition: background-color 0.18s ease, transform 0.12s ease, box-shadow 0.18s ease !important;
    box-shadow: 0 2px 6px rgba(35, 163, 234, 0.25) !important;
}
button[data-testid="baseButton-primary"]:hover {
    background-color: #1a8fd1 !important;
    color: #FFFFFF !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 12px rgba(35, 163, 234, 0.4) !important;
}
button[data-testid="baseButton-primary"]:active {
    background-color: #1578b3 !important;
    transform: translateY(0) !important;
}

/* === Secondary / utility buttons (Reset, ×) === */
button[data-testid="baseButton-secondary"] {
    background-color: transparent !important;
    border: 1px solid #264078 !important;
    color: var(--optspot-muted) !important;
    border-radius: 4px !important;
    font-weight: 500 !important;
    transition: all 0.18s ease !important;
}
button[data-testid="baseButton-secondary"]:hover {
    background-color: rgba(38, 64, 120, 0.35) !important;
    color: #FFFFFF !important;
    border-color: var(--optspot-blue) !important;
}

/* === PDF / Download button — prominent === */
.stDownloadButton > button {
    background-color: var(--optspot-blue) !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 4px !important;
    font-weight: 700 !important;
    font-size: 0.92rem !important;
    letter-spacing: 0.02em !important;
    padding: 0.6rem 1.2rem !important;
    box-shadow: 0 3px 10px rgba(35, 163, 234, 0.35) !important;
    transition: background-color 0.18s ease, transform 0.12s ease, box-shadow 0.18s ease !important;
}
.stDownloadButton > button:hover {
    background-color: #1a8fd1 !important;
    color: #FFFFFF !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 5px 16px rgba(35, 163, 234, 0.5) !important;
}

/* === Message cards === */
[data-testid="stVerticalBlockBorderWrapper"] {
    background-color: var(--optspot-card) !important;
    border: 1px solid #234062 !important;
    border-radius: 8px !important;
    padding: 4px 4px !important;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.4) !important;
    margin-bottom: 1rem !important;
    transition: box-shadow 0.2s ease !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:hover {
    box-shadow: 0 4px 18px rgba(35, 163, 234, 0.12) !important;
}

/* === Tabs === */
.stTabs [data-baseweb="tab-list"] {
    background-color: transparent !important;
    gap: 2px !important;
    border-bottom: 2px solid #264078 !important;
    padding-bottom: 0 !important;
}
.stTabs [data-baseweb="tab"] {
    color: var(--optspot-muted) !important;
    background-color: transparent !important;
    border-radius: 6px 6px 0 0 !important;
    padding: 0.55rem 1.1rem !important;
    font-weight: 500 !important;
    border: none !important;
    transition: all 0.15s ease !important;
    font-size: 0.9rem !important;
}
.stTabs [data-baseweb="tab"]:hover {
    color: #E8EDF5 !important;
    background-color: rgba(38, 64, 120, 0.35) !important;
}
.stTabs [aria-selected="true"] {
    color: var(--optspot-blue) !important;
    font-weight: 700 !important;
    background-color: rgba(26, 37, 64, 0.6) !important;
}
.stTabs [data-baseweb="tab-highlight"] {
    background-color: var(--optspot-blue) !important;
    height: 3px !important;
}
.stTabs [data-baseweb="tab-panel"] {
    padding-top: 1.25rem !important;
    background-color: transparent !important;
}

/* === Text inputs / textareas / number inputs === */
.stTextInput input,
.stTextArea textarea,
.stNumberInput input {
    background-color: #0A1225 !important;
    color: #E8EDF5 !important;
    border: 1px solid #264078 !important;
    border-radius: 6px !important;
    transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
}
.stTextInput input:focus,
.stTextArea textarea:focus,
.stNumberInput input:focus {
    border-color: var(--optspot-blue) !important;
    box-shadow: 0 0 0 2px rgba(35, 163, 234, 0.2) !important;
    outline: none !important;
}
.stTextInput input::placeholder,
.stTextArea textarea::placeholder {
    color: #3D5573 !important;
}

/* === Toggle switches — ON state in bright blue === */
[data-testid="stToggle"] label span[data-checked="true"],
.stToggle span[aria-checked="true"] {
    background-color: var(--optspot-blue) !important;
}
[role="switch"][aria-checked="true"] {
    background-color: var(--optspot-blue) !important;
    border-color: var(--optspot-blue) !important;
}

/* === Labels === */
label,
.stTextInput label,
.stTextArea label,
.stNumberInput label,
[data-testid="stRadio"] label,
[data-testid="stCheckbox"] label {
    color: #C5D3E8 !important;
    font-size: 0.84rem !important;
}

/* === Dividers === */
hr {
    border: none !important;
    border-top: 1px solid #264078 !important;
    margin: 0.75rem 0 !important;
}

/* === Code blocks (copy areas) === */
.stCode > div,
pre {
    background-color: #0A1225 !important;
    color: #C5D3E8 !important;
    border: 1px solid #264078 !important;
    border-radius: 6px !important;
    font-size: 0.82rem !important;
}

/* === Expander === */
[data-testid="stExpander"] {
    border: 1px solid #264078 !important;
    border-radius: 8px !important;
    background-color: #1A2847 !important;
}
[data-testid="stExpander"] summary p,
[data-testid="stExpander"] summary svg {
    color: #C5D3E8 !important;
}

/* === Number input step buttons === */
.stNumberInput button {
    background-color: #264078 !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 4px !important;
}

/* === Captions === */
.stCaption,
[data-testid="stCaptionContainer"] p {
    color: #7A99C4 !important;
    font-size: 0.82rem !important;
}

/* === Warning / info alerts === */
[data-testid="stAlert"] {
    border-radius: 8px !important;
}

/* === Spinner — bright blue === */
.stSpinner > div {
    border-top-color: var(--optspot-blue) !important;
}
[data-testid="stSpinner"] svg circle {
    stroke: var(--optspot-blue) !important;
}

/* === Scrollbar === */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: #0F1A35; }
::-webkit-scrollbar-thumb { background: #264078; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #23A3EA; }

/* === File uploader === */
[data-testid="stFileUploader"] {
    background-color: #1A2847 !important;
    border: 1px dashed #264078 !important;
    border-radius: 8px !important;
    padding: 8px !important;
}
[data-testid="stFileUploaderDropzone"] {
    background-color: transparent !important;
    border: none !important;
}
[data-testid="stFileUploaderDropzoneInstructions"] p,
[data-testid="stFileUploaderDropzoneInstructions"] span {
    color: #7A99C4 !important;
}

/* === SMS/MMS radio inline === */
.sms-mms-radio [data-baseweb="radio"] {
    margin-right: 0.5rem !important;
}

/* === App footer === */
.optspot-footer {
    border-top: 1px solid var(--optspot-navy);
    margin-top: 48px;
    padding: 14px 0 8px 0;
    text-align: center;
    color: var(--optspot-muted);
    font-size: 0.75rem;
    letter-spacing: 0.03em;
}
</style>
""", unsafe_allow_html=True)


# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    logo_b64 = _img_b64("assets/optspot_logo.png")
    st.markdown(
        f"""<div style="padding:14px 0 10px 0;">
              <img src="data:image/png;base64,{logo_b64}"
                   style="max-height:48px;display:block;" />
            </div>
            <hr style="border:none;border-top:1px solid #264078;margin:0 0 14px 0;" />""",
        unsafe_allow_html=True,
    )

    # ── Per-AM account (not client config; preserved across Reset) ──
    with st.expander("👤 Your Account", expanded=False):
        user_optspot_email = st.text_input(
            "Your OptSpot email",
            value=st.session_state.get("user_optspot_email", ""),
            key="user_optspot_email",
            placeholder="firstname@optspot.com",
            on_change=_save_to_storage,
        )
        st.caption("Used to open Google Docs in your OptSpot account, not your personal one. Saved on this browser.")
        if user_optspot_email and not user_optspot_email.strip().lower().endswith("@optspot.com"):
            st.warning("This doesn't look like an @optspot.com email — Google Docs may open under the wrong account.")

    st.markdown('<p class="sidebar-section">Program Setup</p>', unsafe_allow_html=True)

    car_wash_name = st.text_input(
        "Car wash name",
        placeholder="e.g. Speedy Shine Car Wash",
        key="car_wash_name",
        on_change=_save_to_storage,
    )

    program_type = st.radio(
        "Program type",
        options=["visit-based", "points-based"],
        format_func=lambda x: "Visit-based" if x == "visit-based" else "Points-based",
        key="program_type",
        on_change=_save_to_storage,
    )
    st.caption(
        "Every new member starts with 1 "
        + ("point" if program_type == "points-based" else "visit")
        + " upon joining."
    )

    visit_tracked_enabled = st.toggle(
        "Include Visit Tracked messages",
        value=True,
        key="visit_tracked_enabled",
        on_change=_save_to_storage,
    )
    st.caption("Sends a thank-you text right after each wash. Turn off if the client doesn't want post-visit messages.")

    st.divider()

    # ── Signup reward ──
    st.markdown('<p class="sidebar-section">Signup Reward</p>', unsafe_allow_html=True)
    signup_reward_enabled = st.checkbox(
        "Include signup reward",
        key="signup_reward_enabled",
        on_change=_save_to_storage,
    )
    if signup_reward_enabled:
        st.text_input("Reward", placeholder="Free Basic Wash", key="signup_reward",
                      on_change=_save_to_storage)
        st.number_input(
            "Expires in (days)", min_value=1, max_value=90, value=7,
            key="signup_reward_expires_days",
            on_change=_save_to_storage,
        )

    st.divider()

    # ── Visit-based tiers ──
    if program_type == "visit-based":
        st.markdown('<p class="sidebar-section">Reward Tiers</p>', unsafe_allow_html=True)
        if "tiers" not in st.session_state:
            st.session_state.tiers = [{"visits": 5, "reward": "Free Basic Wash"}]

        tiers_to_delete = []
        for i, tier in enumerate(st.session_state.tiers):
            with st.container():
                col1, col2, col3 = st.columns([2, 3, 1])
                with col1:
                    tier["visits"] = st.number_input(
                        "Visits", min_value=1, value=tier["visits"],
                        key=f"tier_visits_{i}", on_change=_save_to_storage,
                    )
                with col2:
                    tier["reward"] = st.text_input(
                        "Reward", value=tier["reward"],
                        key=f"tier_reward_{i}", on_change=_save_to_storage,
                    )
                with col3:
                    st.write("")
                    st.write("")
                    if st.button("✕", key=f"del_tier_{i}") and len(st.session_state.tiers) > 1:
                        tiers_to_delete.append(i)

        for i in reversed(tiers_to_delete):
            st.session_state.tiers.pop(i)
        if tiers_to_delete:
            _save_to_storage()

        def _add_tier():
            st.session_state.tiers.append({"visits": 10, "reward": ""})
            _save_to_storage()

        st.button("+ Add tier", on_click=_add_tier)

    # ── Points-based wash packages ──
    else:
        st.markdown('<p class="sidebar-section">💧 Wash Packages</p>', unsafe_allow_html=True)
        st.caption("Configure each wash package customers can purchase. Earn points and redeem cost are unique per package.")
        if "wash_packages" not in st.session_state:
            st.session_state.wash_packages = [
                {"name": "Basic", "earn_points": 1, "redeem_cost": 4},
                {"name": "Ultimate", "earn_points": 3, "redeem_cost": 12},
                {"name": "Platinum", "earn_points": 5, "redeem_cost": 20},
            ]

        wps_to_delete = []
        for i, pkg in enumerate(st.session_state.wash_packages):
            with st.container():
                col1, col2, col3, col4 = st.columns([3, 2, 2, 0.5])
                with col1:
                    pkg["name"] = st.text_input(
                        "Package Name", value=pkg["name"],
                        key=f"wash_pkg_name_{i}", on_change=_save_to_storage,
                    )
                with col2:
                    pkg["earn_points"] = st.number_input(
                        "Earn Points", min_value=1, value=pkg["earn_points"],
                        key=f"wash_pkg_earn_{i}", on_change=_save_to_storage,
                    )
                with col3:
                    pkg["redeem_cost"] = st.number_input(
                        "Redeem Cost", min_value=1, value=pkg["redeem_cost"],
                        key=f"wash_pkg_redeem_{i}", on_change=_save_to_storage,
                    )
                with col4:
                    st.write("")
                    st.write("")
                    if st.button("✕", key=f"del_wp_{i}") and len(st.session_state.wash_packages) > 1:
                        wps_to_delete.append(i)

        for i in reversed(wps_to_delete):
            st.session_state.wash_packages.pop(i)
        if wps_to_delete:
            _save_to_storage()

        def _add_wash_package():
            st.session_state.wash_packages.append({"name": "", "earn_points": 1, "redeem_cost": 4})
            _save_to_storage()

        st.button("+ Add wash package", on_click=_add_wash_package)

        st.divider()
        st.toggle(
            "Enable Rewards messages",
            value=st.session_state.get("points_rewards_enabled", False),
            key="points_rewards_enabled",
            on_change=_save_to_storage,
        )
        st.caption("Off by default — OptSpot doesn't host rewards messages for points programs unless requested by the client.")

    st.divider()

    # ── Auto-engage messages ──
    st.markdown('<p class="sidebar-section">Auto-Engage Messages</p>', unsafe_allow_html=True)
    if "auto_engage" not in st.session_state:
        st.session_state.auto_engage = [
            {"days": 30, "type": "offer", "offer": "10% off your next wash"},
            {"days": 60, "type": "offer", "offer": "Free upgrade to Deluxe"},
            {"days": 90, "type": "offer", "offer": "Free Basic Wash on us"},
        ]

    ae_to_delete = []
    for i, ae in enumerate(st.session_state.auto_engage):
        # Backfill "type" key for entries created before this field existed
        ae.setdefault("type", "offer")
        with st.container():
            col_days, col_type, col_offer, col_del = st.columns([1, 2, 2, 0.4])
            with col_days:
                ae["days"] = st.number_input(
                    "Days", min_value=1, value=ae["days"],
                    key=f"ae_days_{i}", on_change=_save_to_storage,
                )
            with col_type:
                ae["type"] = st.radio(
                    "Type",
                    options=["offer", "reminder"],
                    format_func=lambda x: "Offer" if x == "offer" else "Reminder",
                    index=0 if ae["type"] == "offer" else 1,
                    key=f"ae_type_{i}",
                    horizontal=True,
                    on_change=_save_to_storage,
                )
            with col_offer:
                if ae["type"] == "offer":
                    ae["offer"] = st.text_input(
                        "Offer", value=ae.get("offer", ""),
                        key=f"ae_offer_{i}", on_change=_save_to_storage,
                    )
                else:
                    st.text_input(
                        "Offer", value="", key=f"ae_offer_{i}",
                        disabled=True, placeholder="N/A — reminder only",
                    )
                    ae["offer"] = ""
            with col_del:
                st.write("")
                st.write("")
                if st.button("✕", key=f"del_ae_{i}") and len(st.session_state.auto_engage) > 1:
                    ae_to_delete.append(i)

    for i in reversed(ae_to_delete):
        st.session_state.auto_engage.pop(i)
    if ae_to_delete:
        _save_to_storage()

    def _add_ae():
        st.session_state.auto_engage.append({"days": 120, "type": "offer", "offer": ""})
        _save_to_storage()

    st.button("+ Add auto-engage", on_click=_add_ae)

    st.divider()

    # ── HPO config (PDF-only) ──
    st.markdown('<p class="sidebar-section">🔥 Hot Prospect Offer (HPO)</p>', unsafe_allow_html=True)
    hpo_enabled = st.toggle(
        "Enable Hot Prospect Offer",
        value=st.session_state.get("hpo_enabled", True),
        key="hpo_enabled",
        on_change=_save_to_storage,
    )
    st.caption("Turn off if the client doesn't use HPO.")
    if hpo_enabled:
        st.text_input(
            "HPO Membership Offer", placeholder="e.g. Free Graphene Wash",
            key="hpo_membership_offer", on_change=_save_to_storage,
        )
        st.number_input(
            "HPO Timeframe (days)", min_value=1, value=st.session_state.get("hpo_timeframe_days", 30),
            key="hpo_timeframe_days", on_change=_save_to_storage,
        )
        st.number_input(
            "HPO Minimum Visits", min_value=1, value=st.session_state.get("hpo_min_visits", 3),
            key="hpo_min_visits", on_change=_save_to_storage,
        )
        st.number_input(
            "HPO Maximum Check-ins", min_value=1, value=st.session_state.get("hpo_max_checkins", 10),
            key="hpo_max_checkins", on_change=_save_to_storage,
        )
        _hpo_exec_opts = ["link", "onsite", "redeem"]
        st.radio(
            "HPO Execution Type",
            options=_hpo_exec_opts,
            format_func=lambda x: {
                "link": "Link to ecommerce",
                "onsite": "On-site redemption",
                "redeem": "Hard offer (redeem code)",
            }[x],
            index=_hpo_exec_opts.index(st.session_state.get("hpo_execution", "redeem")),
            key="hpo_execution",
            horizontal=False,
            on_change=_save_to_storage,
        )
        st.caption("How the customer redeems the HPO offer.")

    st.divider()

    # ── Redemption Codes (PDF-only, informational) ──
    st.markdown('<p class="sidebar-section">🎟️ Redemption Codes</p>', unsafe_allow_html=True)
    uses_redemption_codes = st.toggle(
        "Uses redemption codes?",
        value=st.session_state.get("uses_redemption_codes", False),
        key="uses_redemption_codes",
        on_change=_save_to_storage,
    )
    st.caption("Toggle on if this program requires unique codes for reward redemption.")
    if uses_redemption_codes:
        st.text_input(
            "Where are codes managed?",
            placeholder="e.g., iVision Mobile, internal database, manual list",
            key="codes_location", on_change=_save_to_storage,
        )
        st.text_input(
            "Code format example",
            placeholder="e.g., WASH-12345, OPTSPOT-XYZ",
            key="code_format_example", on_change=_save_to_storage,
        )
        st.text_input(
            "Who provides codes to OptSpot?",
            placeholder="e.g., Client marketing team, weekly batch",
            key="codes_provider", on_change=_save_to_storage,
        )
        _code_delivery_opts = [
            "Code included in the SMS",
            "Customer texts back to receive a code",
            "Code given in-store at redemption",
            "Auto-recognized at kiosk (LPR — no code needed)",
            "Other",
        ]
        st.radio(
            "How does the customer redeem the reward?",
            options=_code_delivery_opts,
            index=_code_delivery_opts.index(
                st.session_state.get("code_delivery_method", _code_delivery_opts[0])
            ) if st.session_state.get("code_delivery_method") in _code_delivery_opts else 0,
            key="code_delivery_method",
            on_change=_save_to_storage,
        )
        st.caption("Pick the option that best matches how this client's reward gets delivered.")

    st.divider()
    generate_btn = st.button("Generate Messages", type="primary", use_container_width=True)

    st.divider()
    st.markdown('<p class="sidebar-section">Danger Zone</p>', unsafe_allow_html=True)

    def _confirm_reset():
        st.session_state["_confirm_reset"] = True

    def _cancel_reset():
        st.session_state["_confirm_reset"] = False

    def _do_reset():
        # Clear config keys (everything except internal flags starting with _).
        # Preserve per-AM account config — it's not client data and must survive Reset.
        _preserve = {"user_optspot_email"}
        keys_to_clear = [
            k for k in st.session_state.keys()
            if not k.startswith("_") and k not in _preserve
        ]
        for k in keys_to_clear:
            del st.session_state[k]
        # Reset guards so next render will load defaults from storage (or empty)
        st.session_state["_storage_saved_this_run"] = False
        st.session_state["_storage_loaded_this_run"] = False

    if st.session_state.get("_confirm_reset"):
        st.warning("This will clear all settings and messages.")
        rc1, rc2 = st.columns(2)
        with rc1:
            st.button("Yes, reset", on_click=_do_reset, use_container_width=True)
        with rc2:
            st.button("Cancel", on_click=_cancel_reset, use_container_width=True)
    else:
        st.button(
            "Reset Everything",
            on_click=_confirm_reset,
            use_container_width=True,
        )

    st.divider()

    # ── Feedback form ──
    with st.expander("📩 Send Feedback"):
        with st.form("feedback_form", clear_on_submit=True):
            am_name = st.text_input("Your name")
            feedback_msg = st.text_area("Your feedback", height=120)
            screenshot = st.file_uploader("Screenshot (optional)", type=["png", "jpg", "jpeg"])
            submitted = st.form_submit_button("Send Feedback")
            if submitted:
                if not am_name or not feedback_msg:
                    st.error("Please fill in your name and feedback.")
                else:
                    try:
                        send_feedback_via_resend(am_name, feedback_msg, screenshot)
                        st.success("Thanks! Your feedback was sent.")
                    except Exception as e:
                        st.error(f"Send failed: {e}")

    st.divider()
    st.caption("Internal Prototype — OptSpot use only. Not production-final.")


# ── Main area header ───────────────────────────────────────────────────────────

if is_demo_mode():
    st.markdown(
        """<div style="border-left:4px solid #23A3EA;background:rgba(35,163,234,0.07);
                       padding:10px 16px;border-radius:0 8px 8px 0;margin-bottom:20px;">
             <span style="color:#23A3EA;font-weight:600;">Demo Mode</span>
             <span style="color:#9BB3D4;font-size:0.9rem;">
               &nbsp;— Messages are templated. Add your API key to .env for AI-generated copy.
             </span>
           </div>""",
        unsafe_allow_html=True,
    )

_main_logo_b64 = _img_b64("assets/optspot_logo.png")
st.markdown(
    f"""<div class="optspot-header">
          <div class="optspot-header-logo">
            <img src="data:image/png;base64,{_main_logo_b64}" style="height:48px;display:block;" />
          </div>
          <div class="optspot-header-title">
            <h1>Loyalty Message Generator</h1>
            <p>Configure &rarr; Generate &rarr; Approve</p>
          </div>
        </div>""",
    unsafe_allow_html=True,
)


# ── Context builder ────────────────────────────────────────────────────────────

def build_base_context():
    ctx = {
        "car_wash_name": car_wash_name or "our car wash",
        "program_type": program_type,
        "signup_reward_enabled": st.session_state.get("signup_reward_enabled", False),
        "signup_reward": st.session_state.get("signup_reward", ""),
        "signup_reward_expires_days": st.session_state.get("signup_reward_expires_days", 7),
    }
    if program_type == "visit-based":
        ctx["tiers"] = st.session_state.tiers
    else:
        ctx["wash_packages"] = st.session_state.get("wash_packages", [])
    return ctx


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_image(msg_key: str):
    """Return (image_bytes, source) — source is 'custom', 'global', or 'none'."""
    custom = st.session_state.get(f"img_{msg_key}")
    if custom:
        return custom, "custom"
    global_img = st.session_state.get("global_mms_image")
    if global_img:
        return global_img, "global"
    return None, "none"


# ── Message card renderer ──────────────────────────────────────────────────────

def render_message_card(
    label: str,
    strategy: str,
    msg_key: str,
    context: dict,
    msg_type: str,
    extra_ctx: dict = None,
    show_regen: bool = True,
):
    if msg_key not in st.session_state:
        return

    mode_key    = f"mode_{msg_key}"
    img_key     = f"img_{msg_key}"
    counter_key = f"upload_counter_{msg_key}"
    radio_key   = f"radio_{msg_key}"

    if mode_key not in st.session_state:
        st.session_state[mode_key] = st.session_state.get("default_mode", "SMS")
    if counter_key not in st.session_state:
        st.session_state[counter_key] = 0

    current_mode = st.session_state[mode_key]

    # Regenerate callback — runs BEFORE the script re-executes, so writing to
    # msg_key (which is also the textarea's widget key) is valid at this point.
    def _do_regen():
        mode = st.session_state.get(mode_key, "SMS")
        full_ctx = {**context, **(extra_ctx or {})}
        new_msg = generate_message(msg_type, full_ctx, temperature=0.9, mode=mode)
        st.session_state[msg_key] = new_msg
        print(f"[regen] msg_key={msg_key}, mode={mode}, len={len(new_msg)}")

    with st.container(border=True):
        # ── Header row: label + SMS/MMS toggle ──
        header_col, toggle_col = st.columns([3, 2])
        with header_col:
            st.markdown(f"**{label}**")
            st.caption(strategy)
        with toggle_col:
            if radio_key not in st.session_state:
                st.session_state[radio_key] = current_mode
            new_mode = st.radio(
                "Mode",
                options=["SMS", "MMS"],
                index=0 if st.session_state[radio_key] == "SMS" else 1,
                key=radio_key,
                horizontal=True,
                label_visibility="collapsed",
            )

        # Apply mode change
        if new_mode != current_mode:
            st.session_state[mode_key] = new_mode
            current_mode = new_mode

        # ── MMS image upload ──
        if current_mode == "MMS":
            resolved_img, img_source = _resolve_image(msg_key)

            def _do_remove_img():
                st.session_state[img_key] = None
                st.session_state[counter_key] += 1
                st.session_state[f"_img_err_{msg_key}"] = None

            def _on_upload():
                up_key = f"uploader_{msg_key}_{st.session_state[counter_key]}"
                file = st.session_state.get(up_key)
                if file is not None:
                    data = file.getvalue()
                    if len(data) > 1_000_000:
                        st.session_state[f"_img_err_{msg_key}"] = "too_large"
                    else:
                        st.session_state[f"_img_err_{msg_key}"] = "warn" if len(data) > 500_000 else None
                        st.session_state[img_key] = data
                    st.session_state[counter_key] += 1

            if img_source == "custom":
                img_col, rm_col = st.columns([3, 1])
                with img_col:
                    st.image(resolved_img, width=200)
                    st.caption("Custom image attached")
                with rm_col:
                    st.write("")
                    st.write("")
                    st.button("Remove", key=f"rm_img_{msg_key}", on_click=_do_remove_img)
            else:
                if img_source == "global":
                    st.image(resolved_img, width=200)
                    st.caption("Using global MMS image — upload below to override.")
                up_key = f"uploader_{msg_key}_{st.session_state[counter_key]}"
                st.file_uploader(
                    "Attach image (JPG only, max 1 MB)",
                    type=["jpg", "jpeg"],
                    key=up_key,
                    label_visibility="visible",
                    on_change=_on_upload,
                )
                err = st.session_state.get(f"_img_err_{msg_key}")
                if err == "too_large":
                    st.error("Image too large. iVision Mobile blocks images over 1 MB.")
                elif err == "warn":
                    st.warning("Over 500 KB — iVision Mobile recommends staying under 500 KB.")

        # ── Message text + char count ──
        # Read from session state BEFORE rendering the textarea so char count
        # reflects the latest value (post-regen or post-edit) on every run.
        msg = st.session_state[msg_key]
        char_count = len(msg)
        char_limit = 500 if current_mode == "MMS" else 160
        if char_count > char_limit:
            char_color = "#FF5252"
        elif char_count > int(char_limit * 0.9):
            char_color = "#FFA726"
        else:
            char_color = "#4CAF50"

        count_left, count_right = st.columns([5, 1])
        with count_right:
            st.markdown(
                f"<div style='text-align:right;padding-top:4px;'>"
                f"<span style='color:{char_color};font-size:0.82rem;font-weight:700;'>{char_count}</span>"
                f"<span style='color:#4A6080;font-size:0.75rem;'> / {char_limit}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # Use msg_key as the widget key so Streamlit keeps session state in sync
        # with user edits automatically — no manual sync step needed.
        edited = st.text_area(
            "Message",
            value=msg,
            key=msg_key,
            label_visibility="collapsed",
            height=120 if current_mode == "MMS" else 100,
        )

        if show_regen:
            rcol, ccol = st.columns([1, 1])
            with rcol:
                # on_click fires before the next script execution — writing to msg_key
                # (the textarea key) inside _do_regen is safe because the widget
                # hasn't been instantiated yet at that point.
                st.button("↺ Regenerate", key=f"regen_{msg_key}", on_click=_do_regen)
            with ccol:
                st.code(edited, language=None)
        else:
            st.code(edited, language=None)


# ── Message generation ─────────────────────────────────────────────────────────

if generate_btn:
    if not car_wash_name:
        st.warning("Enter a car wash name before generating.")
        st.stop()

    base_ctx = build_base_context()
    _meta: dict = {}  # msg_key → {type, context} — used by bulk regenerate callbacks

    with st.spinner("Generating messages…"):
        # Welcome
        st.session_state["msg_welcome"] = generate_message("welcome", base_ctx)
        _meta["msg_welcome"] = {"type": "welcome", "context": dict(base_ctx)}

        # Visit tracked
        if program_type == "visit-based":
            tiers = st.session_state.tiers
            first_tier = tiers[0] if tiers else {"visits": 5, "reward": "a free wash"}
            tracked_ctx = {
                **base_ctx,
                "status_detail": f"1 visit logged. {first_tier['visits'] - 1} more to earn {first_tier['reward']}.",
            }
        else:
            tracked_ctx = {**base_ctx, "status_detail": "Points added to your balance."}
        st.session_state["msg_tracked"] = generate_message("tracked", tracked_ctx)
        _meta["msg_tracked"] = {"type": "tracked", "context": dict(tracked_ctx)}

        # Progress
        for i in range(20):
            st.session_state.pop(f"msg_progress_tier_{i}", None)
        progress_ctx = {**base_ctx}
        st.session_state["msg_progress"] = generate_message("progress", progress_ctx)
        _meta["msg_progress"] = {"type": "progress", "context": dict(progress_ctx)}

        # Reward(s)
        if program_type == "visit-based":
            for i, tier in enumerate(st.session_state.tiers):
                reward_ctx = {**base_ctx, "reward_description": tier["reward"]}
                k = f"msg_reward_{i}"
                st.session_state[k] = generate_message("reward", reward_ctx)
                _meta[k] = {"type": "reward", "context": dict(reward_ctx)}
        else:
            for i, pkg in enumerate(st.session_state.get("wash_packages", [])):
                reward_ctx = {
                    **base_ctx,
                    "package_name": pkg["name"],
                    "earn_points": pkg["earn_points"],
                    "redeem_cost": pkg["redeem_cost"],
                    "reward_description": pkg["name"],
                }
                k = f"msg_reward_pkg_{i}"
                st.session_state[k] = generate_message("reward", reward_ctx)
                _meta[k] = {"type": "reward", "context": dict(reward_ctx)}

        # Auto-engage
        for i, ae in enumerate(st.session_state.auto_engage):
            ae_type = ae.get("type", "offer")
            ae_ctx = {
                **base_ctx,
                "days_since_visit": ae["days"],
                "offer": ae.get("offer", ""),
                "ae_type": ae_type,
            }
            k = f"msg_ae_{i}"
            st.session_state[k] = generate_message("autoengage", ae_ctx)
            _meta[k] = {"type": "autoengage", "context": dict(ae_ctx)}

        # Hot prospect — only when HPO is enabled
        if st.session_state.get("hpo_enabled", True):
            hp_ctx = {**base_ctx, "hpo_execution": st.session_state.get("hpo_execution", "redeem")}
            st.session_state["msg_hot_prospect"] = generate_message("hot_prospect", hp_ctx)
            _meta["msg_hot_prospect"] = {"type": "hot_prospect", "context": dict(hp_ctx)}
        else:
            st.session_state.pop("msg_hot_prospect", None)

    st.session_state["msg_meta"] = _meta

    # Initialize modes and clear images. msg_key is also the textarea widget key, so
    # DON'T re-init it here — Streamlit will read the value we just wrote above.
    default = st.session_state.get("default_mode", "SMS")
    for _k in _meta:
        st.session_state[f"mode_{_k}"] = default
        st.session_state[f"img_{_k}"] = None
        st.session_state[f"radio_{_k}"] = default

    st.session_state["generated"] = True


# ── Output area ────────────────────────────────────────────────────────────────

if st.session_state.get("generated"):
    base_ctx = build_base_context()

    # Count messages for display
    _vt_on = st.session_state.get("visit_tracked_enabled", True)
    _rewards_on = (
        program_type == "visit-based"
        or st.session_state.get("points_rewards_enabled", False)
    )
    msg_keys = ["msg_welcome"]
    if _vt_on:
        msg_keys.append("msg_tracked")
    msg_keys.append("msg_progress")
    if _rewards_on:
        if program_type == "visit-based":
            msg_keys += [f"msg_reward_{i}" for i in range(len(st.session_state.tiers))]
        else:
            msg_keys += [f"msg_reward_pkg_{i}" for i in range(len(st.session_state.get("wash_packages", [])))]
    msg_keys += [f"msg_ae_{i}" for i in range(len(st.session_state.auto_engage))]
    if st.session_state.get("msg_hot_prospect"):
        msg_keys.append("msg_hot_prospect")

    msg_count = sum(1 for k in msg_keys if k in st.session_state)

    # ── Output header + PDF download ───────────────────────────────────────────

    def _collect_pdf_messages() -> dict:
        msgs: dict = {"rewards": [], "auto_engage": []}
        if "msg_welcome" in st.session_state:
            msgs["welcome"] = {
                "label": "Welcome Message",
                "text": st.session_state["msg_welcome"],
                "strategy": "Confirms signup and sets expectations for the program.",
                "mode": st.session_state.get("mode_msg_welcome", "SMS"),
                "image_data": _resolve_image("msg_welcome")[0],
            }
        if "msg_tracked" in st.session_state and st.session_state.get("visit_tracked_enabled", True):
            msgs["tracked"] = {
                "label": "Visit Tracked",
                "text": st.session_state["msg_tracked"],
                "strategy": "Confirms activity and shows progress to keep momentum.",
                "mode": st.session_state.get("mode_msg_tracked", "SMS"),
                "image_data": _resolve_image("msg_tracked")[0],
            }
        if "msg_progress" in st.session_state:
            msgs["progress"] = {
                "label": "Progress Check",
                "text": st.session_state["msg_progress"],
                "strategy": "Sent after each wash — includes a link to check loyalty progress.",
                "mode": st.session_state.get("mode_msg_progress", "SMS"),
                "image_data": _resolve_image("msg_progress")[0],
            }
        if _rewards_on:
            if program_type == "visit-based":
                for i, tier in enumerate(st.session_state.get("tiers", [])):
                    key = f"msg_reward_{i}"
                    if key in st.session_state:
                        msgs["rewards"].append({
                            "label": f"Tier {i + 1} — {tier['reward']}",
                            "text": st.session_state[key],
                            "strategy": f"Celebrates earning {tier['reward']} and drives redemption.",
                            "mode": st.session_state.get(f"mode_{key}", "SMS"),
                            "image_data": _resolve_image(key)[0],
                        })
            else:
                for i, pkg in enumerate(st.session_state.get("wash_packages", [])):
                    key = f"msg_reward_pkg_{i}"
                    if key in st.session_state:
                        msgs["rewards"].append({
                            "label": f"{pkg['name']} Reward",
                            "text": st.session_state[key],
                            "strategy": f"Sent when customer reaches {pkg['redeem_cost']} points for a {pkg['name']} wash.",
                            "mode": st.session_state.get(f"mode_{key}", "SMS"),
                            "image_data": _resolve_image(key)[0],
                        })
        for i, ae in enumerate(st.session_state.get("auto_engage", [])):
            key = f"msg_ae_{i}"
            if key in st.session_state:
                _ae_type = ae.get("type", "offer")
                if _ae_type == "offer" and ae.get("offer"):
                    _ae_label = f"Day {ae['days']} — {ae['offer']}"
                    _ae_strategy = f"Win-back offer for customers inactive {ae['days']}+ days."
                else:
                    _ae_label = f"Day {ae['days']} — Reminder"
                    _ae_strategy = f"Friendly check-in for customers inactive {ae['days']}+ days."
                msgs["auto_engage"].append({
                    "label": _ae_label,
                    "text": st.session_state[key],
                    "strategy": _ae_strategy,
                    "days": ae["days"],
                    "ae_type": _ae_type,
                    "mode": st.session_state.get(f"mode_{key}", "SMS"),
                    "image_data": _resolve_image(key)[0],
                })
        if st.session_state.get("msg_hot_prospect") and st.session_state.get("hpo_enabled", True):
            msgs["hot_prospect"] = {
                "label": "Hot Prospect Offer",
                "text": st.session_state["msg_hot_prospect"],
                "strategy": "Converts frequent visitors who haven't redeemed yet.",
                "mode": st.session_state.get("mode_msg_hot_prospect", "SMS"),
                "image_data": _resolve_image("msg_hot_prospect")[0],
            }
        return msgs

    header_col, dl_col = st.columns([1, 3])
    with header_col:
        st.markdown(
            f"<p style='color:#E8EDF5;font-weight:700;font-size:1.2rem;margin:0 0 2px 0;'>"
            f"Generated Messages</p>"
            f"<p style='color:#7A99C4;font-size:0.85rem;margin:0 0 16px 0;'>"
            f"{msg_count} messages ready</p>",
            unsafe_allow_html=True,
        )
    with dl_col:
        safe = re.sub(r"[^\w\s-]", "", car_wash_name).strip().replace(" ", "_") or "car_wash"
        _export_context = {
            "car_wash_name": car_wash_name,
            "program_type": program_type,
            "generated_date": str(date.today()),
            "signup_reward_enabled": st.session_state.get("signup_reward_enabled", False),
            "signup_reward": st.session_state.get("signup_reward", ""),
            "signup_reward_expires_days": st.session_state.get("signup_reward_expires_days", 7),
            "tiers": st.session_state.get("tiers", []) if program_type == "visit-based" else [],
            "wash_packages": st.session_state.get("wash_packages", []) if program_type == "points-based" else [],
            "visit_tracked_enabled": st.session_state.get("visit_tracked_enabled", True),
            "points_rewards_enabled": st.session_state.get("points_rewards_enabled", False),
            "view_mode": st.session_state.get("view_mode", "Tabs"),
            "hpo_enabled": st.session_state.get("hpo_enabled", True),
            "hpo_membership_offer": st.session_state.get("hpo_membership_offer", ""),
            "hpo_timeframe_days": st.session_state.get("hpo_timeframe_days", 30),
            "hpo_min_visits": st.session_state.get("hpo_min_visits", 3),
            "hpo_max_checkins": st.session_state.get("hpo_max_checkins", 10),
            "hpo_execution": st.session_state.get("hpo_execution", "redeem"),
            "auto_engage": st.session_state.get("auto_engage", []),
            "uses_redemption_codes": st.session_state.get("uses_redemption_codes", False),
            "codes_location": st.session_state.get("codes_location", ""),
            "code_format_example": st.session_state.get("code_format_example", ""),
            "codes_provider": st.session_state.get("codes_provider", ""),
            "code_delivery_method": st.session_state.get("code_delivery_method", ""),
        }
        _export_messages = _collect_pdf_messages()
        pdf_bytes = build_pdf(_export_context, _export_messages)
        docx_bytes = build_loyalty_docx(_export_context, _export_messages)

        dl_pdf_col, dl_docx_col, dl_gdoc_col = st.columns(3)
        with dl_pdf_col:
            st.download_button(
                label="📄 Download PDF",
                data=pdf_bytes,
                file_name=f"{safe}_loyalty_messages_{date.today()}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        with dl_docx_col:
            st.download_button(
                label="📝 Download Word",
                data=docx_bytes,
                file_name=f"{safe}_loyalty_draft_{date.today()}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )
        with dl_gdoc_col:
            _draft_html = build_loyalty_html(_export_context, _export_messages)
            components.html(
                _gdocs_copy_button_html(
                    _draft_html,
                    st.session_state.get("user_optspot_email", ""),
                ),
                height=60,
            )
        st.caption(
            "Click to copy the draft. A new Google Doc opens in your OptSpot account "
            "if your email is set above."
        )

    # ── Default mode + bulk controls ──────────────────────────────────────────
    st.divider()

    # Callbacks run before the script re-executes, so writing to msg_key
    # (the textarea widget key) and radio_{k} is safe — widgets haven't rendered yet.
    def _set_all_sms():
        for k, m in st.session_state.get("msg_meta", {}).items():
            new_msg = generate_message(m["type"], m["context"], temperature=0.9, mode="SMS")
            st.session_state[k] = new_msg
            st.session_state[f"mode_{k}"] = "SMS"
            st.session_state[f"radio_{k}"] = "SMS"
            print(f"[bulk] msg_key={k}, mode=SMS, len={len(new_msg)}")

    def _set_all_mms():
        for k, m in st.session_state.get("msg_meta", {}).items():
            new_msg = generate_message(m["type"], m["context"], temperature=0.9, mode="MMS")
            st.session_state[k] = new_msg
            st.session_state[f"mode_{k}"] = "MMS"
            st.session_state[f"radio_{k}"] = "MMS"
            print(f"[bulk] msg_key={k}, mode=MMS, len={len(new_msg)}")

    bulk_col1, bulk_col2, bulk_col3 = st.columns([2, 1, 1])
    with bulk_col1:
        st.radio(
            "Default mode for new messages",
            options=["SMS", "MMS"],
            key="default_mode",
            horizontal=True,
            on_change=_save_to_storage,
        )
    with bulk_col2:
        st.button("Set all SMS", use_container_width=True, on_click=_set_all_sms)
    with bulk_col3:
        st.button("Set all MMS", use_container_width=True, on_click=_set_all_mms)

    st.divider()

    # ── Global MMS Image ──────────────────────────────────────────────────────
    with st.expander("Global MMS Image", expanded=False):
        st.caption("Upload once to attach the same image to all MMS messages. Per-message uploads override this.")

        def _on_global_upload():
            counter = st.session_state.get("global_upload_counter", 0)
            up_key = f"global_mms_uploader_{counter}"
            file = st.session_state.get(up_key)
            if file is not None:
                data = file.getvalue()
                if len(data) > 1_000_000:
                    st.session_state["_global_img_err"] = "too_large"
                else:
                    st.session_state["_global_img_err"] = "warn" if len(data) > 500_000 else None
                    st.session_state["global_mms_image"] = data
                st.session_state["global_upload_counter"] = counter + 1

        def _clear_global_image():
            st.session_state["global_mms_image"] = None
            st.session_state["global_upload_counter"] = st.session_state.get("global_upload_counter", 0) + 1
            st.session_state["_global_img_err"] = None

        global_img = st.session_state.get("global_mms_image")
        if global_img:
            gcol1, gcol2 = st.columns([3, 1])
            with gcol1:
                st.image(global_img, width=200)
                st.caption("Active global image")
            with gcol2:
                st.write("")
                st.write("")
                st.button("Remove global image", key="clear_global_img", on_click=_clear_global_image)
        else:
            g_counter = st.session_state.get("global_upload_counter", 0)
            st.file_uploader(
                "Upload global MMS image (JPG only, max 1 MB)",
                type=["jpg", "jpeg"],
                key=f"global_mms_uploader_{g_counter}",
                label_visibility="visible",
                on_change=_on_global_upload,
            )
            g_err = st.session_state.get("_global_img_err")
            if g_err == "too_large":
                st.error("Image too large. iVision Mobile blocks images over 1 MB.")
            elif g_err == "warn":
                st.warning("Over 500 KB — iVision Mobile recommends staying under 500 KB.")

    show_hp = bool(st.session_state.get("msg_hot_prospect")) and st.session_state.get("hpo_enabled", True)

    # Compute tracked_extra once — used in both Tabs and All-in-One views
    if program_type == "visit-based":
        tiers = st.session_state.tiers
        first_tier = tiers[0] if tiers else {"visits": 5, "reward": "a free wash"}
        tracked_extra = {
            "status_detail": f"1 visit logged. {first_tier['visits'] - 1} more to earn {first_tier['reward']}."
        }
    else:
        tracked_extra = {"status_detail": "Points added to your balance."}

    # ── View toggle ──────────────────────────────────────────────────────────
    st.radio(
        "View",
        options=["Tabs", "All-in-One"],
        horizontal=True,
        key="view_mode",
        label_visibility="collapsed",
    )
    view_mode = st.session_state.get("view_mode", "Tabs")

    # ── Tabs view ─────────────────────────────────────────────────────────────
    if view_mode == "Tabs":
        tab_labels = ["👋 Welcome"]
        if _vt_on:
            tab_labels.append("✅ Visit Tracked")
        tab_labels.append("📊 Progress")
        if _rewards_on:
            tab_labels.append("🎉 Rewards")
        tab_labels.append("🔁 Auto-Engage")
        if show_hp:
            tab_labels.append("🔥 Hot Prospect")
        tabs = st.tabs(tab_labels)

        _ti = 0
        with tabs[_ti]:
            render_message_card(
                "Welcome Message",
                "Confirms signup and sets expectations for the program.",
                "msg_welcome", base_ctx, "welcome",
            )
        _ti += 1

        if _vt_on:
            with tabs[_ti]:
                render_message_card(
                    "Visit Tracked",
                    "Confirms activity and shows progress to keep momentum.",
                    "msg_tracked", base_ctx, "tracked", tracked_extra,
                )
            _ti += 1

        with tabs[_ti]:
            render_message_card(
                "Progress Check",
                "Sent after each wash — includes a link to check loyalty progress.",
                "msg_progress", base_ctx, "progress",
            )
        _ti += 1

        if _rewards_on:
            with tabs[_ti]:
                if program_type == "visit-based":
                    for i, tier in enumerate(st.session_state.tiers):
                        render_message_card(
                            f"Tier {i + 1} — {tier['reward']}",
                            f"Celebrates earning {tier['reward']} and drives redemption.",
                            f"msg_reward_{i}", base_ctx, "reward",
                            {"reward_description": tier["reward"]},
                        )
                else:
                    for i, pkg in enumerate(st.session_state.get("wash_packages", [])):
                        render_message_card(
                            f"{pkg['name']} Reward Message",
                            f"Sent when customer reaches {pkg['redeem_cost']} points for a {pkg['name']} wash.",
                            f"msg_reward_pkg_{i}", base_ctx, "reward",
                            {"package_name": pkg["name"], "earn_points": pkg["earn_points"], "redeem_cost": pkg["redeem_cost"], "reward_description": pkg["name"]},
                        )
            _ti += 1

        with tabs[_ti]:
            for i, ae in enumerate(st.session_state.auto_engage):
                ae_type = ae.get("type", "offer")
                _ae_title = f"Day {ae['days']} — {ae['offer']}" if ae_type == "offer" and ae.get("offer") else f"Day {ae['days']} — Reminder"
                _ae_strategy = (
                    f"Win-back offer for customers inactive {ae['days']}+ days."
                    if ae_type == "offer"
                    else f"Friendly check-in for customers inactive {ae['days']}+ days."
                )
                render_message_card(
                    _ae_title, _ae_strategy,
                    f"msg_ae_{i}", base_ctx, "autoengage",
                    {"days_since_visit": ae["days"], "offer": ae.get("offer", ""), "ae_type": ae_type},
                )
        _ti += 1

        if show_hp:
            with tabs[_ti]:
                render_message_card(
                    "Hot Prospect Offer",
                    "Converts frequent visitors who haven't redeemed yet.",
                    "msg_hot_prospect", base_ctx, "hot_prospect",
                    {"hpo_execution": st.session_state.get("hpo_execution", "redeem")},
                )

    # ── All-in-One view ───────────────────────────────────────────────────────
    else:
        def _section_head(label: str):
            st.markdown(
                f"<div style='color:#23A3EA;font-weight:700;font-size:1.05rem;"
                f"margin:20px 0 6px 0;border-left:3px solid #264078;padding-left:10px;'>"
                f"{label}</div>",
                unsafe_allow_html=True,
            )

        _section_head("👋 Welcome")
        render_message_card(
            "Welcome Message",
            "Confirms signup and sets expectations for the program.",
            "msg_welcome", base_ctx, "welcome",
        )

        if _vt_on:
            st.divider()
            _section_head("✅ Visit Tracked")
            render_message_card(
                "Visit Tracked",
                "Confirms activity and shows progress to keep momentum.",
                "msg_tracked", base_ctx, "tracked", tracked_extra,
            )

        st.divider()
        _section_head("📊 Progress")
        render_message_card(
            "Progress Check",
            "Sent after each wash — includes a link to check loyalty progress.",
            "msg_progress", base_ctx, "progress",
        )

        if _rewards_on:
            st.divider()
            _section_head("🎉 Rewards")
            if program_type == "visit-based":
                for i, tier in enumerate(st.session_state.tiers):
                    render_message_card(
                        f"Tier {i + 1} — {tier['reward']}",
                        f"Celebrates earning {tier['reward']} and drives redemption.",
                        f"msg_reward_{i}", base_ctx, "reward",
                        {"reward_description": tier["reward"]},
                    )
            else:
                for i, pkg in enumerate(st.session_state.get("wash_packages", [])):
                    render_message_card(
                        f"{pkg['name']} Reward Message",
                        f"Sent when customer reaches {pkg['redeem_cost']} points for a {pkg['name']} wash.",
                        f"msg_reward_pkg_{i}", base_ctx, "reward",
                        {"package_name": pkg["name"], "earn_points": pkg["earn_points"], "redeem_cost": pkg["redeem_cost"], "reward_description": pkg["name"]},
                    )

        st.divider()
        _section_head("🔁 Auto-Engage")
        for i, ae in enumerate(st.session_state.auto_engage):
            ae_type = ae.get("type", "offer")
            _ae_title = f"Day {ae['days']} — {ae['offer']}" if ae_type == "offer" and ae.get("offer") else f"Day {ae['days']} — Reminder"
            _ae_strategy = (
                f"Win-back offer for customers inactive {ae['days']}+ days."
                if ae_type == "offer"
                else f"Friendly check-in for customers inactive {ae['days']}+ days."
            )
            render_message_card(
                _ae_title, _ae_strategy,
                f"msg_ae_{i}", base_ctx, "autoengage",
                {"days_since_visit": ae["days"], "offer": ae.get("offer", ""), "ae_type": ae_type},
            )

        if show_hp:
            st.divider()
            _section_head("🔥 Hot Prospect")
            render_message_card(
                "Hot Prospect Offer",
                "Converts frequent visitors who haven't redeemed yet.",
                "msg_hot_prospect", base_ctx, "hot_prospect",
                {"hpo_execution": st.session_state.get("hpo_execution", "redeem")},
            )

st.markdown(
    """<div class="optspot-footer">OptSpot Internal Prototype &bull; For team use only</div>""",
    unsafe_allow_html=True,
)
