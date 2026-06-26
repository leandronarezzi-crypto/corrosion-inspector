import ssl
ssl._create_default_https_context = ssl._create_unverified_context

import streamlit as st
import numpy as np
from PIL import Image, ImageDraw
import requests
from io import BytesIO

ROBOFLOW_API_KEY = "iUlu1ZIT04nqMXMjLtiz"
ROBOFLOW_PROJECT = "corrosiondetector"
ROBOFLOW_VERSION = 2

st.set_page_config(
    page_title="Corrosion Inspector",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── NORMAS ───────────────────────────────────────────────────────────────────

def classify_iso_4628(coverage):
    """ISO 4628-3: Degree of rusting on coated surfaces."""
    if coverage == 0:
        return "Ri 0", "No rusting", "#22C55E", "No deterioration detected."
    elif coverage <= 0.0005:
        return "Ri 1", "Very slight rusting", "#84CC16", "Up to 0.05% of surface affected."
    elif coverage <= 0.005:
        return "Ri 2", "Slight rusting", "#EAB308", "0.05%–0.5% of surface affected."
    elif coverage <= 0.01:
        return "Ri 3", "Moderate rusting", "#F97316", "0.5%–1% of surface affected."
    elif coverage <= 0.08:
        return "Ri 4", "Considerable rusting", "#EF4444", "1%–8% of surface affected."
    else:
        return "Ri 5", "Severe rusting", "#991B1B", "More than 8% of surface affected."

def classify_astm_d610(coverage):
    """ASTM D610: Evaluating degree of rusting on painted steel."""
    pct = coverage * 100
    if pct == 0:       return 10, "Perfect"
    elif pct < 0.03:   return 9,  "< 0.03%"
    elif pct < 0.1:    return 8,  "0.03–0.1%"
    elif pct < 0.3:    return 7,  "0.1–0.3%"
    elif pct < 1:      return 6,  "0.3–1%"
    elif pct < 3:      return 5,  "1–3%"
    elif pct < 10:     return 4,  "3–10%"
    elif pct < 16:     return 3,  "10–16%"
    elif pct < 33:     return 2,  "16–33%"
    elif pct < 50:     return 1,  "33–50%"
    else:              return 0,  "> 50%"

def recommended_action(ri_grade):
    actions = {
        "Ri 0": ("Routine Monitoring", "No treatment required. Schedule periodic visual inspection every 12 months.", "#22C55E"),
        "Ri 1": ("Preventive Monitoring", "Surface is in good condition. Inspect every 6 months and monitor for progression.", "#84CC16"),
        "Ri 2": ("Preventive Maintenance", "Schedule localized treatment. Apply spot primer and touch-up coating within 6 months.", "#EAB308"),
        "Ri 3": ("Corrective Maintenance", "Mechanical surface preparation (St 2 or Sa 2) and full recoating recommended within 3 months.", "#F97316"),
        "Ri 4": ("Urgent Intervention", "Immediate surface preparation to Sa 2½ per ISO 8501-1 and protective coating system required.", "#EF4444"),
        "Ri 5": ("Critical — Immediate Action", "Structural integrity may be compromised. Emergency intervention required. Evaluate load-bearing capacity.", "#991B1B"),
    }
    return actions.get(ri_grade, ("Unknown", "", "#6B7280"))

# ── CSS ──────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=DM+Sans:wght@400;500;600&family=DM+Mono:wght@400;500&display=swap');

.stApp { background: #F0F3F8 !important; }
#MainMenu, footer, header { visibility: hidden; }
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif !important; color: #0F172A; }

[data-testid="stSidebar"] { background: #FFFFFF !important; border-right: 1px solid #E2E8F0 !important; }

[data-testid="stFileUploader"] { background: #FFFFFF !important; border: 1px dashed #CBD5E1 !important;
    border-radius: 6px !important; padding: 4px 8px !important; margin: 0 !important; }
[data-testid="stFileUploader"] * { color: #94A3B8 !important; font-size: 0.78rem !important; }
[data-testid="stFileUploader"] section { background: transparent !important; }
[data-testid="stFileUploader"] label { display: none !important; }
[data-testid="stFileUploader"] section > div { padding: 4px 0 !important; }

[data-testid="stImage"] img { border-radius: 6px !important; border: 1px solid #E2E8F0 !important;
    max-height: 32vh !important; width: 100% !important; object-fit: contain !important;
    box-shadow: 0 1px 4px rgba(15,23,42,0.08) !important; }

[data-testid="stSlider"] { padding-top: 0 !important; margin-top: 0 !important; }
[data-testid="stSlider"] [class*="thumb"] { background: #EA580C !important; border: none !important; }
[data-testid="stSlider"] [class*="track"]:nth-child(1) { background: #EA580C !important; }

details { background: #FFFFFF !important; border: 1px solid #E2E8F0 !important;
    border-radius: 6px !important; padding: 2px 12px !important; }
details summary { color: #64748B !important; font-size: 0.78rem !important; }

::-webkit-scrollbar { width: 3px; }
::-webkit-scrollbar-track { background: #F0F3F8; }
::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 2px; }

[data-testid="column"] { padding: 0 5px !important; }
[data-testid="block-container"] { padding-top: 0.5rem !important; padding-bottom: 0.4rem !important;
    padding-left: 2rem !important; padding-right: 2rem !important; }
[data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"] { gap: 0.25rem !important; }
div[class*="element-container"] { margin-bottom: 0 !important; }
</style>
""", unsafe_allow_html=True)

# ── COMPONENTES HTML ──────────────────────────────────────────────────────────

def stat_card(label, value, sub="", accent="#EA580C"):
    return f"""
    <div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:8px;
                padding:12px 16px;box-shadow:0 1px 3px rgba(15,23,42,0.06)">
        <div style="font-family:'DM Mono',monospace;font-size:0.5rem;
                    color:#94A3B8;letter-spacing:0.18em;text-transform:uppercase;
                    margin-bottom:5px">{label}</div>
        <div style="font-family:'Syne',sans-serif;font-size:1.6rem;font-weight:800;
                    color:{accent};line-height:1;letter-spacing:-0.02em">{value}</div>
        <div style="font-size:0.62rem;color:#94A3B8;margin-top:3px">{sub}</div>
    </div>"""

def status_card(detected, n, coverage):
    if detected:
        color, bg, border = "#DC2626", "#FEF2F2", "#FECACA"
        icon = "!"
        title = "Corrosion Detected"
        desc  = f"{n} area{'s' if n>1 else ''} identified · {coverage:.2%} surface coverage"
    else:
        color, bg, border = "#16A34A", "#F0FDF4", "#BBF7D0"
        icon = "✓"
        title = "No Corrosion Detected"
        desc  = "Surface appears structurally sound"
    return f"""
    <div style="background:{bg};border:1px solid {border};border-left:3px solid {color};
                border-radius:8px;padding:10px 18px;display:flex;align-items:center;gap:14px">
        <div style="font-family:'Syne',sans-serif;font-size:1.3rem;font-weight:800;
                    color:{color};width:26px;text-align:center;flex-shrink:0">{icon}</div>
        <div>
            <div style="font-family:'Syne',sans-serif;font-size:0.9rem;font-weight:700;
                        color:{color}">{title}</div>
            <div style="font-size:0.72rem;color:#475569;margin-top:1px">{desc}</div>
        </div>
    </div>"""

def render_norm_section(ri_code, ri_label, ri_color, astm_rating, astm_range,
                        action_title, action_desc, action_color):
    severity_pct = int(ri_code[-1]) * 20
    astm_pct     = (10 - astm_rating) * 10
    h = action_color.lstrip('#')
    ar, ag, ab = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    # 3 colunas na mesma linha: ISO | ASTM | Ação
    nc1, nc2, nc3 = st.columns(3)

    with nc1:
        st.markdown(f"""<div style="background:#FFFFFF;border:1px solid #E2E8F0;
            border-radius:8px;padding:12px 14px;box-shadow:0 1px 3px rgba(15,23,42,0.05)">
            <div style="font-family:'DM Mono',monospace;font-size:0.48rem;color:#94A3B8;
                letter-spacing:0.2em;text-transform:uppercase;margin-bottom:6px">ISO 4628-3</div>
            <div style="display:flex;align-items:baseline;gap:8px">
                <span style="font-family:'Syne',sans-serif;font-size:1.5rem;font-weight:800;
                    color:{ri_color};line-height:1">{ri_code}</span>
                <span style="font-size:0.7rem;color:#334155;font-weight:500">{ri_label}</span>
            </div>
            <div style="margin-top:8px;height:3px;background:#E2E8F0;border-radius:2px">
                <div style="height:100%;width:{severity_pct}%;background:{ri_color};border-radius:2px"></div>
            </div>
            <div style="display:flex;justify-content:space-between;margin-top:3px">
                <span style="font-size:0.48rem;color:#94A3B8;font-family:'DM Mono',monospace">Ri 0</span>
                <span style="font-size:0.48rem;color:#94A3B8;font-family:'DM Mono',monospace">Ri 5</span>
            </div></div>""", unsafe_allow_html=True)

    with nc2:
        st.markdown(f"""<div style="background:#FFFFFF;border:1px solid #E2E8F0;
            border-radius:8px;padding:12px 14px;box-shadow:0 1px 3px rgba(15,23,42,0.05)">
            <div style="font-family:'DM Mono',monospace;font-size:0.48rem;color:#94A3B8;
                letter-spacing:0.2em;text-transform:uppercase;margin-bottom:6px">ASTM D610</div>
            <div style="display:flex;align-items:baseline;gap:8px">
                <span style="font-family:'Syne',sans-serif;font-size:1.5rem;font-weight:800;
                    color:{ri_color};line-height:1">Grade {astm_rating}</span>
                <span style="font-size:0.7rem;color:#64748B">{astm_range}</span>
            </div>
            <div style="margin-top:8px;height:3px;background:#E2E8F0;border-radius:2px">
                <div style="height:100%;width:{astm_pct}%;background:{ri_color};border-radius:2px"></div>
            </div>
            <div style="display:flex;justify-content:space-between;margin-top:3px">
                <span style="font-size:0.48rem;color:#94A3B8;font-family:'DM Mono',monospace">Grade 10</span>
                <span style="font-size:0.48rem;color:#94A3B8;font-family:'DM Mono',monospace">Grade 0</span>
            </div></div>""", unsafe_allow_html=True)

    with nc3:
        st.markdown(f"""<div style="background:rgba({ar},{ag},{ab},0.06);
            border:1px solid rgba({ar},{ag},{ab},0.18);
            border-radius:8px;padding:12px 14px">
            <div style="font-family:'DM Mono',monospace;font-size:0.48rem;color:#94A3B8;
                letter-spacing:0.2em;text-transform:uppercase;margin-bottom:6px">Recommended Action</div>
            <div style="font-family:'Syne',sans-serif;font-size:0.85rem;font-weight:700;
                color:{action_color};margin-bottom:4px">{action_title}</div>
            <div style="font-size:0.65rem;color:#475569;line-height:1.45">{action_desc}</div>
        </div>""", unsafe_allow_html=True)

def detection_row(i, score, area_pct):
    severity = "HIGH" if score > 0.7 else "MED" if score > 0.4 else "LOW"
    color = {"HIGH": "#DC2626", "MED": "#EA580C", "LOW": "#64748B"}[severity]
    h = color.lstrip('#')
    cr, cg, cb = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
    bar = int(score * 100)
    return f"""
    <div style="display:flex;align-items:center;gap:14px;padding:10px 14px;
                background:#FFFFFF;border:1px solid #E2E8F0;
                border-radius:6px;margin-bottom:5px">
        <div style="font-family:'DM Mono',monospace;font-size:0.65rem;
                    color:#94A3B8;min-width:22px">#{i:02d}</div>
        <div style="flex:1">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">
                <div style="height:3px;width:{bar}%;background:{color};border-radius:2px;max-width:100px"></div>
                <span style="font-size:0.72rem;color:#0F172A;font-weight:500">{score:.1%} confidence</span>
            </div>
            <div style="font-size:0.65rem;color:#64748B">Area: {area_pct:.2%} of surface</div>
        </div>
        <div style="font-family:'DM Mono',monospace;font-size:0.6rem;font-weight:500;
                    color:{color};background:rgba({cr},{cg},{cb},0.08);
                    padding:3px 9px;border-radius:10px">{severity}</div>
    </div>"""

# ── DETECÇÃO ─────────────────────────────────────────────────────────────────

def detect(image_pil, threshold):
    w, h = image_pil.size
    buf = BytesIO()
    image_pil.convert("RGB").save(buf, format="JPEG", quality=95)

    resp = requests.post(
        f"https://detect.roboflow.com/{ROBOFLOW_PROJECT}/{ROBOFLOW_VERSION}",
        params={"api_key": ROBOFLOW_API_KEY, "confidence": int(threshold * 100)},
        files={"file": ("image.jpg", buf.getvalue(), "image/jpeg")},
        timeout=30,
    )
    resp.raise_for_status()
    predictions = resp.json().get("predictions", [])

    valid, rust_mask = [], np.zeros((h, w), dtype=bool)
    for pred in predictions:
        s  = float(pred["confidence"])
        cx, cy, bw, bh = pred["x"], pred["y"], pred["width"], pred["height"]
        l  = max(int(cx - bw / 2), 0)
        t  = max(int(cy - bh / 2), 0)
        r  = min(int(cx + bw / 2), w)
        b  = min(int(cy + bh / 2), h)
        rust_mask[t:b, l:r] = True
        valid.append((s, l, t, r, b))

    base    = image_pil.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ov      = ImageDraw.Draw(overlay)
    for s, l, t, r, b in valid:
        ov.rectangle([l, t, r, b], fill=(232, 87, 10, 55))

    result = Image.alpha_composite(base, overlay).convert("RGB")
    draw   = ImageDraw.Draw(result)
    for s, l, t, r, b in valid:
        for px in range(2):
            draw.rectangle([l+px, t+px, r-px, b-px], outline=(232, 87, 10))
        lbl = f"{s:.0%}"
        draw.rectangle([l, max(t-18, 0), l + len(lbl)*8 + 6, max(t, 18)], fill=(232, 87, 10))
        draw.text((l+4, max(t-15, 2)), lbl, fill=(255, 255, 255))

    return result, valid, rust_mask.sum() / (h * w)

# ── LAYOUT ────────────────────────────────────────────────────────────────────

# ── Barra de controles: título | upload | slider+badge
t_title, t_upload, t_slider = st.columns([3, 5, 2])

with t_title:
    st.markdown("""<div style="padding:4px 0 8px;border-bottom:1px solid #E2E8F0">
        <div style="font-family:'DM Mono',monospace;font-size:0.48rem;color:#94A3B8;
                    letter-spacing:0.25em;text-transform:uppercase;margin-bottom:3px">Inspection System</div>
        <div style="font-family:'Syne',sans-serif;font-size:1.2rem;font-weight:800;
                    color:#0F172A;letter-spacing:-0.02em;line-height:1">Corrosion Inspector</div>
    </div>""", unsafe_allow_html=True)

with t_upload:
    uploaded = st.file_uploader("", type=["jpg","jpeg","png"], label_visibility="collapsed")

with t_slider:
    threshold = st.slider("", 0.05, 0.95, 0.30, 0.05, label_visibility="collapsed")
    st.markdown(
        f'<div style="font-family:\'DM Mono\',monospace;font-size:0.52rem;color:#64748B;'
        f'text-align:center;margin-top:-2px">sensitivity · <b style="color:#EA580C">{threshold:.0%}</b> '
        f'&nbsp;<span style="color:#16A34A">● ONLINE</span></div>',
        unsafe_allow_html=True
    )

if not uploaded:
    st.markdown("""<div style="border:1px dashed #CBD5E1;border-radius:10px;
                background:#FFFFFF;padding:60px 40px;text-align:center;margin-top:10px">
        <div style="font-family:'Syne',sans-serif;font-size:1rem;font-weight:700;
                    color:#334155">Upload an image to begin inspection</div>
        <div style="font-size:0.7rem;color:#94A3B8;margin-top:4px">JPG · JPEG · PNG</div>
    </div>""", unsafe_allow_html=True)

else:
    img = Image.open(uploaded)
    with st.spinner("Analyzing..."):
        try:
            result_img, detections, coverage = detect(img, threshold)
        except Exception as e:
            st.error(f"Detection error: {e}")
            st.stop()

    ri_code, ri_label, ri_color, ri_desc = classify_iso_4628(coverage)
    astm_rating, astm_range              = classify_astm_d610(coverage)
    action_title, action_desc, action_color = recommended_action(ri_code)
    avg_conf = sum(s for s,*_ in detections)/len(detections) if detections else 0
    max_conf = max(s for s,*_ in detections) if detections else 0

    # ── FOTOS lado a lado (altura limitada por CSS max-height:32vh)
    lbl = '<div style="font-family:\'DM Mono\',monospace;font-size:0.48rem;letter-spacing:0.18em;text-transform:uppercase;margin-bottom:3px;color:{c}">{t}</div>'
    i1, i2 = st.columns(2)
    with i1:
        st.markdown(lbl.format(c="#94A3B8", t="ORIGINAL"), unsafe_allow_html=True)
        st.image(img, use_container_width=True)
    with i2:
        st.markdown(lbl.format(c="#EA580C", t="DETECTION"), unsafe_allow_html=True)
        st.image(result_img, use_container_width=True)

    # ── STATUS (faixa fina, largura total)
    st.markdown(status_card(bool(detections), len(detections), coverage), unsafe_allow_html=True)

    # ── 4 MÉTRICAS
    m1, m2, m3, m4 = st.columns(4)
    m1.markdown(stat_card("Areas",     str(len(detections)), "regions",   "#E8570A"), unsafe_allow_html=True)
    m2.markdown(stat_card("Coverage",  f"{coverage:.1%}",   "surface",   "#EF4444"), unsafe_allow_html=True)
    m3.markdown(stat_card("Avg Conf",  f"{avg_conf:.0%}",   "certainty", "#C9A84C"), unsafe_allow_html=True)
    m4.markdown(stat_card("Peak Conf", f"{max_conf:.0%}",   "highest",   "#C9A84C"), unsafe_allow_html=True)

    # ── NORMAS (ISO | ASTM | Ação — 3 colunas na mesma linha)
    st.markdown('<div style="font-family:\'DM Mono\',monospace;font-size:0.48rem;color:#94A3B8;letter-spacing:0.18em;text-transform:uppercase;margin:8px 0 4px">Norm Classification · ISO 4628-3 · ASTM D610</div>', unsafe_allow_html=True)
    render_norm_section(
        ri_code, ri_label, ri_color,
        astm_rating, astm_range,
        action_title, action_desc, action_color
    )

    if detections:
        with st.expander(f"Detection log — {len(detections)} region{'s' if len(detections)>1 else ''}"):
            for i, (s, l, t, r, b) in enumerate(detections, 1):
                area_pct = ((r-l)*(b-t))/(img.width*img.height)
                st.markdown(detection_row(i, s, area_pct), unsafe_allow_html=True)
