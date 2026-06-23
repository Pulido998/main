"""
╔══════════════════════════════════════════════════════════════════════════╗
║         GLASS MASTER INVENTARIO — (UI REDESIGN)                          ║
║         Arquitectura: Session State SSOT + Write-Through Cache          ║
╠══════════════════════════════════════════════════════════════════════════╣
║  ESTE PASE: VISUALIZACIÓN COMPLETA + FILTRADO PARCIAL EN PANEL.          ║
║  · Muestra todos los cristales en Panel de Control (con o sin stock)     ║
║  · Filtro de búsqueda por coincidencias parciales con Enter              ║
║  · Paleta corporativa actualizada (#0A192F / #1E3A8A)                   ║
║  · Sidebar de navegación con etiquetas y claves internas separadas      ║
║  · Tablas con st.column_config (alineación numérica, anchos, formato)  ║
║  CERO cambios en: conexión a Sheets, caché, normalización de racks,    ║
║  búsqueda parcial, llave compuesta CLAVE+RACK, roles y credenciales.    ║
╠══════════════════════════════════════════════════════════════════════════╣
║  BACK-END (invariante — NO TOCADO en este pase):                        ║
║  1. Cero lecturas API en caliente — todo desde SSOT                    ║
║  2. _find_row() re-lee Sheets solo en el momento exacto de escritura   ║
║  3. Llave compuesta CLAVE+RACK única por sucursal                      ║
║  4. Normalización canónica de racks en toda la pila                    ║
║  5. Búsqueda parcial .str.contains()                                   ║
║  6. Stock cero invisible solo en selectores de operaciones de venta    ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import re
import time
import base64
from datetime import datetime

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials
from PIL import Image

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN GLOBAL Y BRANDING
# ═══════════════════════════════════════════════════════════════════════════

# Carga del logo corporativo solicitado
LOGO = Image.open("logo.png")

# Conversión a Base64 para incrustar limpiamente en contenedores HTML nativos sin romper el diseño premium
try:
    with open("logo.png", "rb") as f:
        LOGO_B64 = base64.b64encode(f.read()).decode()
    LOGO_HTML = f'<img src="data:image/png;base64,{LOGO_B64}" style="max-height: 55px; width: auto; display: block; margin: 0 auto;">'
except Exception:
    LOGO_HTML = ""

st.set_page_config(
    page_title="Glass Master Inventario — Inventario",
    page_icon=LOGO,
    layout="wide",
    initial_sidebar_state="expanded",
)

SUCURSALES: dict[str, str] = {
    "Inventario_Suc1": "Arriaga",
    "Inventario_Suc2": "Libramiento",
    "Inventario_Suc3": "Zamora",
    "Inventario_Suc4": "Moroleon",
}

USUARIOS: dict[str, dict] = {
    "admin":     {"pass": "Xk9#mZ21!",    "rol": "admin", "sucursal": None},
    "sucursal1": {"pass": "Suc1_Ax7$",    "rol": "user",  "sucursal": "Inventario_Suc1"},
    "sucursal2": {"pass": "Br4nch_Two!",  "rol": "user",  "sucursal": "Inventario_Suc2"},
    "sucursal3": {"pass": "T3rcera_P0s#", "rol": "user",  "sucursal": "Inventario_Suc3"},
    "sucursal4": {"pass": "Moro_L3on$",   "rol": "user",  "sucursal": "Inventario_Suc4"},
}

TIPOS_PIEZA = ["Parabrisas", "Medallón", "Puerta", "Aleta", "Costado"]

# ─── Paleta corporativa ──────────────────────────────────────────────────
C_NAVY       = "#138A27"   # azul corporativo profundo — sidebar, headings
C_BLUE       = "#1E3A8A"   # azul corporativo — acentos, botones primarios
C_BLUE_LT    = "#2563EB"   # botones hover
C_BG         = "#F8F9FA"   # fondo principal gris perla
C_SURFACE    = "#FFFFFF"   # tarjetas / contenedores
C_BORDER     = "#E2E8F0"   # bordes suaves
C_TEXT       = "#0F172A"   # texto principal carbón
C_TEXT_MED   = "#475569"   # texto secundario
C_TEXT_LIGHT = "#94A3B8"   # etiquetas / captions
C_GREEN      = "#059669"   # éxito
C_AMBER      = "#D97706"   # advertencia
C_RED        = "#DC2626"   # error


# ═══════════════════════════════════════════════════════════════════════════
# CSS CORPORATIVO — MODO CLARO PREMIUM
# ═══════════════════════════════════════════════════════════════════════════

CORPORATE_CSS = f"""
<style>
  /* ── Google Font: Inter ─────────────────────────────────────────── */
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

  html, body, [class*="css"], .stApp {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  }}

  /* ── Fondo principal ────────────────────────────────────────────── */
  .stApp {{
    background-color: {C_BG};
  }}

  /* ── Densidad ERP: paddings nativos reducidos ─────────────────────── */
  .main .block-container {{
    background-color: {C_BG};
    padding-top: 1rem;
    padding-bottom: 2rem;
  }}
  [data-testid="stVerticalBlockBorderWrapper"] > div > [data-testid="stVerticalBlock"] {{
    gap: 0.6rem;
  }}
  div[data-testid="stForm"] {{
    border-color: {C_BORDER} !important;
  }}

  /* ── SIDEBAR — azul corporativo profundo ───────────────────────── */
  [data-testid="stSidebar"] {{
    background: linear-gradient(180deg, {C_NAVY} 0%, #050d18 100%);
    border-right: none;
  }}
  [data-testid="stSidebar"] * {{
    color: #CBD5E1 !important;
  }}
  [data-testid="stSidebar"] .stRadio label {{
    color: #CBD5E1 !important;
    font-size: 0.875rem;
    font-weight: 500;
    padding: 6px 0;
  }}
  [data-testid="stSidebar"] .stRadio label:hover {{
    color: #FFFFFF !important;
  }}
  /* Radio seleccionado */
  [data-testid="stSidebar"] [data-baseweb="radio"] [aria-checked="true"] + div {{
    color: #FFFFFF !important;
    font-weight: 600;
  }}
  [data-testid="stSidebar"] hr {{
    border-color: rgba(255,255,255,0.12) !important;
    margin: 12px 0 !important;
  }}
  [data-testid="stSidebar"] .stSelectbox label,
  [data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] {{
    color: #CBD5E1 !important;
  }}
  /* Botones en sidebar */
  [data-testid="stSidebar"] .stButton button {{
    background: rgba(255,255,255,0.08) !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    color: #CBD5E1 !important;
    font-weight: 500;
    border-radius: 8px;
    transition: all 0.2s;
  }}
  [data-testid="stSidebar"] .stButton button:hover {{
    background: rgba(255,255,255,0.14) !important;
    color: #FFFFFF !important;
  }}

  /* ── Encabezados principales ────────────────────────────────────── */
  h1, h2, h3 {{
    color: {C_NAVY} !important;
    font-weight: 700;
    letter-spacing: -0.02em;
  }}

  /* ── TARJETAS KPI — efecto flotante con sombra ──────────────────── */
  .kpi-card {{
    background: {C_SURFACE};
    border: 1px solid {C_BORDER};
    border-radius: 12px;
    padding: 20px 22px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 4px 16px rgba(10,25,47,0.07);
    position: relative;
    overflow: hidden;
    transition: box-shadow 0.2s;
  }}
  .kpi-card:hover {{
    box-shadow: 0 4px 20px rgba(10,25,47,0.12);
  }}
  .kpi-card::before {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: {C_BLUE};
    border-radius: 12px 12px 0 0;
  }}
  .kpi-card.green::before {{ background: {C_GREEN}; }}
  .kpi-card.amber::before {{ background: {C_AMBER}; }}
  .kpi-card.red::before   {{ background: {C_RED}; }}

  .kpi-icon {{
    font-size: 1.4rem;
    margin-bottom: 10px;
    display: block;
  }}
  .kpi-label {{
    color: {C_TEXT_LIGHT};
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 6px;
  }}
  .kpi-value {{
    color: {C_TEXT};
    font-size: 2.1rem;
    font-weight: 800;
    line-height: 1;
    margin-bottom: 4px;
    letter-spacing: -0.03em;
  }}
  .kpi-sub {{
    color: {C_TEXT_LIGHT};
    font-size: 0.72rem;
    font-weight: 400;
  }}

  /* ── Section headings ─────────────────────────────────────────────── */
  .section-title {{
    color: {C_NAVY};
    font-size: 1.05rem;
    font-weight: 700;
    margin: 18px 0 10px;
    padding-bottom: 8px;
    border-bottom: 2px solid {C_BORDER};
    letter-spacing: -0.01em;
  }}

  /* ── Page header strip ───────────────────────────────────────────── */
  .page-header {{
    background: {C_SURFACE};
    border: 1px solid {C_BORDER};
    border-radius: 12px;
    padding: 16px 22px;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 12px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04);
  }}
  .page-header-icon {{
    font-size: 1.5rem;
    background: {C_BG};
    width: 44px; height: 44px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px solid {C_BORDER};
  }}
  .page-header-title {{
    color: {C_NAVY};
    font-size: 1.15rem;
    font-weight: 700;
    margin: 0;
    letter-spacing: -0.02em;
  }}
  .page-header-sub {{
    color: {C_TEXT_LIGHT};
    font-size: 0.78rem;
    margin: 0;
  }}

  /* ── Rack preview tag ─────────────────────────────────────────────── */
  .rack-preview {{
    background: #EFF6FF;
    border: 1px solid #BFDBFE;
    border-radius: 6px;
    padding: 4px 10px;
    color: {C_BLUE};
    font-size: 0.78rem;
    font-weight: 700;
    font-family: 'Courier New', monospace;
    display: inline-block;
    margin-top: 6px;
  }}

  /* ── Toast notifications ─────────────────────────────────────────── */
  .toast-success {{
    background: #F0FDF4;
    border: 1px solid #BBF7D0;
    border-left: 4px solid {C_GREEN};
    border-radius: 8px;
    padding: 12px 16px;
    color: #166534;
    font-size: 0.85rem;
    font-weight: 500;
    margin: 8px 0;
  }}
  .toast-error {{
    background: #FEF2F2;
    border: 1px solid #FECACA;
    border-left: 4px solid {C_RED};
    border-radius: 8px;
    padding: 12px 16px;
    color: #991B1B;
    font-size: 0.85rem;
    font-weight: 500;
    margin: 8px 0;
  }}

  /* ── Tabs override ───────────────────────────────────────────────── */
  [data-testid="stTabs"] [data-baseweb="tab-list"] {{
    background: {C_SURFACE};
    border-radius: 10px;
    padding: 4px;
    border: 1px solid {C_BORDER};
    gap: 2px;
  }}
  [data-testid="stTabs"] [data-baseweb="tab"] {{
    border-radius: 7px;
    font-weight: 500;
    font-size: 0.83rem;
    color: {C_TEXT_MED};
    padding: 8px 16px;
  }}
  [data-testid="stTabs"] [aria-selected="true"] {{
    background: {C_NAVY} !important;
    color: white !important;
    font-weight: 600;
  }}
  [data-testid="stTabs"] [data-baseweb="tab-border"] {{
    display: none;
  }}

  /* ── Primary buttons ─────────────────────────────────────────────── */
  .stButton [data-testid="baseButton-primary"] {{
    background: {C_BLUE} !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    letter-spacing: 0.01em;
    box-shadow: 0 1px 4px rgba(30,58,138,0.25);
    transition: all 0.18s;
  }}
  .stButton [data-testid="baseButton-primary"]:hover {{
    background: {C_BLUE_LT} !important;
    box-shadow: 0 4px 12px rgba(30,58,138,0.35);
    transform: translateY(-1px);
  }}
  [data-testid="stFormSubmitButton"] button[kind="primary"] {{
    background: {C_BLUE} !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    box-shadow: 0 1px 4px rgba(30,58,138,0.25);
  }}
  [data-testid="stFormSubmitButton"] button[kind="primary"]:hover {{
    background: {C_BLUE_LT} !important;
  }}

  /* ── Form inputs ─────────────────────────────────────────────────── */
  .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] {{
    border-color: {C_BORDER} !important;
    border-radius: 8px !important;
    font-size: 0.875rem;
    color: {C_TEXT} !important;
    background: {C_SURFACE} !important;
  }}
  .stTextInput input:focus, .stNumberInput input:focus {{
    border-color: {C_BLUE} !important;
    box-shadow: 0 0 0 3px rgba(30,58,138,0.12) !important;
  }}
  .stTextInput label, .stNumberInput label,
  .stSelectbox label, .stRadio label {{
    color: {C_TEXT_MED} !important;
    font-size: 0.8rem !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }}

  /* ── Dataframe ───────────────────────────────────────────────────── */
  [data-testid="stDataFrame"] {{
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid {C_BORDER};
    box-shadow: 0 1px 4px rgba(0,0,0,0.04);
  }}

  /* ── Expander ────────────────────────────────────────────────────── */
  [data-testid="stExpander"] {{
    border: 1px solid {C_BORDER} !important;
    border-radius: 10px !important;
    background: {C_SURFACE};
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }}
  [data-testid="stExpander"] summary {{
    font-weight: 600;
    color: {C_NAVY} !important;
    font-size: 0.88rem;
  }}

  /* ── st.info / warning / success ─────────────────────────────────── */
  [data-testid="stAlert"] {{
    border-radius: 8px !important;
    font-size: 0.85rem;
  }}

  /* ── Caption / small text ─────────────────────────────────────────── */
  .stCaption, [data-testid="stCaptionContainer"] {{
    color: {C_TEXT_LIGHT} !important;
    font-size: 0.75rem;
  }}

  /* ── Divider ─────────────────────────────────────────────────────── */
  hr {{
    border-color: {C_BORDER} !important;
    margin: 14px 0 !important;
  }}

  /* ── Login card ──────────────────────────────────────────────────── */
  .login-card {{
    background: {C_SURFACE};
    border: 1px solid {C_BORDER};
    border-radius: 16px;
    padding: 44px 40px;
    box-shadow: 0 8px 32px rgba(10,25,47,0.10);
    margin-top: 48px;
  }}
  .login-logo {{
    text-align: center;
    margin-bottom: 6px;
  }}
  .login-brand {{
    text-align: center;
    color: {C_NAVY};
    font-size: 1.5rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    margin-bottom: 2px;
  }}
  .login-sub {{
    text-align: center;
    color: {C_TEXT_LIGHT};
    font-size: 0.78rem;
    margin-bottom: 32px;
  }}
  .login-divider {{
    border: none;
    border-top: 1px solid {C_BORDER};
    margin: 20px 0;
  }}

  /* ── Badge inline ─────────────────────────────────────────────────── */
  .badge {{
    display: inline-block;
    padding: 2px 9px;
    border-radius: 20px;
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }}
  .badge-blue  {{ background: #DBEAFE; color: {C_NAVY}; }}
  .badge-green {{ background: #D1FAE5; color: #065F46; }}
  .badge-amber {{ background: #FEF3C7; color: #92400E; }}
  .badge-red   {{ background: #FEE2E2; color: #991B1B; }}

  /* ── Sidebar brand block ──────────────────────────────────────────── */
  .sb-brand {{
    text-align: center;
    padding: 16px 0 8px;
  }}
  .sb-brand-name {{
    color: #FFFFFF;
    font-size: 1.1rem;
    font-weight: 800;
    letter-spacing: -0.02em;
  }}
  .sb-user-chip {{
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 8px;
    padding: 8px 12px;
    margin: 8px 0;
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .sb-user-name {{
    color: #E2E8F0;
    font-size: 0.82rem;
    font-weight: 600;
  }}
  .sb-user-rol {{
    color: rgba(255,255,255,0.45);
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }}
  .sb-suc-label {{
    color: rgba(255,255,255,0.4);
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 2px;
  }}
  .sb-suc-name {{
    color: #FFFFFF;
    font-size: 0.92rem;
    font-weight: 600;
  }}

  /* ── Product info pill ────────────────────────────────────────────── */
  .prod-info {{
    background: {C_SURFACE};
    border: 1px solid {C_BORDER};
    border-radius: 8px;
    padding: 10px 16px;
    margin: 6px 0 10px;
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 0.88rem;
  }}
  .prod-clave {{
    background: {C_BG};
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    padding: 3px 10px;
    font-family: 'Courier New', monospace;
    font-weight: 700;
    color: {C_NAVY};
    font-size: 0.92rem;
  }}
  .prod-nombre {{
    color: {C_TEXT_MED};
    font-size: 0.83rem;
  }}

  /* ── Badge de disponibilidad (Centro de Operaciones) ─────────────── */
  .avail-wrap {{
    margin-top: 1.55rem;
  }}
</style>
"""


def _inject_css():
    st.markdown(CORPORATE_CSS, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# CAPA DE NORMALIZACIÓN (invariante)
# ═══════════════════════════════════════════════════════════════════════════

def _clean(text) -> str:
    if text is None:
        return ""
    return " ".join(str(text).strip().upper().split())


def _normalize_rack(raw) -> str:
    t = _clean(raw)
    if not t:
        return "RACK SIN ASIGNAR"
    if re.fullmatch(r"\d+", t):
        return f"RACK {t}"
    if "SIN PEINE" in t:
        return "RACK SIN PEINE"
    if "PEINE" in t:
        return "RACK PEINE"
    if t.startswith("RACK "):
        parts = t.split(None, 1)
        suffix = parts[1].strip() if len(parts) > 1 else ""
        return f"RACK {suffix}" if suffix else "RACK SIN ASIGNAR"
    return f"RACK {t}"


# ═══════════════════════════════════════════════════════════════════════════
# CONEXIÓN — Singleton por worker (invariante)
# ═══════════════════════════════════════════════════════════════════════════

@st.cache_resource
def _connect_gsheets():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=scopes
    )
    return gspread.authorize(creds).open("Inventario_Cristales")


def _sheet(name: str):
    return _connect_gsheets().worksheet(name)


# ═══════════════════════════════════════════════════════════════════════════
# CAPA DE DATOS — Session State SSOT (invariante)
# ═══════════════════════════════════════════════════════════════════════════

def _load_df(sheet_name: str) -> pd.DataFrame:
    ws = _sheet(sheet_name)
    records = ws.get_all_records()
    df = pd.DataFrame(records)
    if df.empty:
        return df
    if "CLAVE" in df.columns:
        df["CLAVE"] = df["CLAVE"].apply(_clean)
    if "RACK" in df.columns:
        df["RACK"] = df["RACK"].apply(_normalize_rack)
    if "NOMBRE" in df.columns:
        df["NOMBRE"] = df["NOMBRE"].astype(str)
    if "CANTIDAD" in df.columns:
        df["CANTIDAD"] = pd.to_numeric(df["CANTIDAD"], errors="coerce").fillna(0).astype(int)
    return df


def _init_session():
    if not st.session_state.get("_data_loaded", False):
        with st.spinner("⏳ Sincronizando inventario…"):
            try:
                sheets = list(SUCURSALES.keys()) + ["Movimientos", "Traslados_Pendientes"]
                for name in sheets:
                    st.session_state[f"df_{name}"] = _load_df(name)
                st.session_state["_data_loaded"] = True
            except Exception as e:
                st.error(f"⚠️ Error de conexión con Google Sheets: {e}")
                st.stop()


def _refresh(sheet_name: str):
    st.session_state[f"df_{sheet_name}"] = _load_df(sheet_name)


def _get_df(sheet_name: str) -> pd.DataFrame:
    key = f"df_{sheet_name}"
    if key not in st.session_state:
        _refresh(sheet_name)
    return st.session_state.get(key, pd.DataFrame())


def _get_df_stock(sheet_name: str) -> pd.DataFrame:
    df = _get_df(sheet_name)
    if df.empty or "CANTIDAD" not in df.columns:
        return df
    return df[df["CANTIDAD"] > 0].copy()


# ═══════════════════════════════════════════════════════════════════════════
# MOTOR DE BÚSQUEDA PARCIAL (invariante)
# ═══════════════════════════════════════════════════════════════════════════

def _search_keys(df: pd.DataFrame, term: str) -> list[str]:
    if df.empty or "CLAVE" not in df.columns or not term:
        return []
    t = _clean(term)
    pool = df[df["CANTIDAD"] > 0] if "CANTIDAD" in df.columns else df
    mask = pool["CLAVE"].str.contains(t, case=False, na=False)
    return sorted(pool.loc[mask, "CLAVE"].unique().tolist())


# ═══════════════════════════════════════════════════════════════════════════
# CAPA DE ESCRITURA — Operaciones atómicas (invariante)
# ═══════════════════════════════════════════════════════════════════════════

def _find_row(ws, clave: str, rack: str) -> tuple[int | None, int]:
    records = ws.get_all_records()
    for i, row in enumerate(records):
        if _clean(row.get("CLAVE", "")) == clave and \
           _normalize_rack(row.get("RACK", "")) == rack:
            qty = int(pd.to_numeric(row.get("CANTIDAD", 0), errors="coerce") or 0)
            return i + 2, qty
    return None, 0


def _log_movement(clave, tipo, detalle, cantidad, precio, usuario, sucursal):
    try:
        ws = _sheet("Movimientos")
        ws.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            clave, tipo, detalle, cantidad, precio, usuario, sucursal,
        ])
    except Exception:
        pass


def op_alta(sheet, clave, nombre, rack_raw, qty, usuario):
    try:
        ws    = _sheet(sheet)
        clave = _clean(clave)
        rack  = _normalize_rack(rack_raw)
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row, current = _find_row(ws, clave, rack)
        if row:
            new_qty = current + qty
            ws.update_cell(row, 4, new_qty)
            ws.update_cell(row, 5, fecha)
            msg = f"Stock actualizado en {rack}: {current} → {new_qty} pz."
        else:
            ws.append_row([clave, nombre, rack, qty, fecha])
            msg = f"Nuevo registro: {clave} en {rack} ({qty} pz)."
        _log_movement(clave, "Alta/Compra", f"Entrada en {rack}", qty, 0, usuario, sheet)
        _refresh(sheet); _refresh("Movimientos")
        return True, msg
    except Exception as e:
        return False, f"Error en Alta: {e}"


def op_venta(sheet, clave, rack, detalle, qty, precio, usuario):
    try:
        ws    = _sheet(sheet)
        clave = _clean(clave)
        rack  = _normalize_rack(rack)
        row, current = _find_row(ws, clave, rack)
        if not row:
            return False, f"No se encontró {clave} en {rack}."
        if current < qty:
            return False, f"Stock insuficiente al confirmar. Disponible: {current} pz."
        new_qty = current - qty
        ws.update_cell(row, 4, new_qty)
        ws.update_cell(row, 5, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        _log_movement(clave, "Venta/Instalación", f"{detalle} (desde {rack})", qty, precio, usuario, sheet)
        _refresh(sheet); _refresh("Movimientos")
        return True, f"Venta confirmada. Quedan {new_qty} pz en {rack}."
    except Exception as e:
        return False, f"Error en Venta: {e}"


def op_send_transfer(sheet_origin, clave, rack, qty, dest_sheet, usuario):
    try:
        ws    = _sheet(sheet_origin)
        clave = _clean(clave)
        rack  = _normalize_rack(rack)
        row, current = _find_row(ws, clave, rack)
        if not row:
            return False, f"No se encontró {clave} en {rack}."
        if current < qty:
            return False, f"Stock insuficiente. Disponible: {current} pz."
        nombre = ws.cell(row, 2).value or "Sin Nombre"
        ws.update_cell(row, 4, current - qty)
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _sheet("Traslados_Pendientes").append_row(
            [fecha, clave, nombre, qty, sheet_origin, dest_sheet])
        _log_movement(clave, "Envío Traslado",
            f"De {sheet_origin}/{rack} → {SUCURSALES.get(dest_sheet, dest_sheet)}",
            qty, 0, usuario, sheet_origin)
        _refresh(sheet_origin); _refresh("Traslados_Pendientes"); _refresh("Movimientos")
        return True, f"Traslado enviado. Quedan {current - qty} pz en {rack}."
    except Exception as e:
        return False, f"Error en traslado: {e}"


def op_receive_transfer(dest_sheet, clave, nombre, qty, rack_raw, pending_row, usuario):
    try:
        ok, msg = op_alta(dest_sheet, clave, nombre, rack_raw, qty, usuario)
        if not ok:
            return False, msg
        _sheet("Traslados_Pendientes").delete_rows(pending_row)
        _log_movement(clave, "Recepción Traslado",
            f"Guardado en {_normalize_rack(rack_raw)}", qty, 0, usuario, dest_sheet)
        _refresh("Traslados_Pendientes"); _refresh("Movimientos")
        return True, f"{qty} pz de {clave} recibidas en {_normalize_rack(rack_raw)}."
    except Exception as e:
        return False, f"Error al recibir traslado: {e}"


def op_cancel_transfer(origin_sheet, item, rack_return_raw, usuario):
    try:
        ws_p = _sheet("Traslados_Pendientes")
        records = ws_p.get_all_records()
        real_row = None
        for i, row in enumerate(records):
            if (str(row.get("FECHA", "")) == str(item["FECHA"]) and
                    _clean(row.get("CLAVE", "")) == _clean(item["CLAVE"])):
                real_row = i + 2
                break
        if not real_row:
            return False, "El traslado ya fue aceptado por el destino. No se puede cancelar."
        qty = int(item["CANTIDAD"])
        ok, msg = op_alta(origin_sheet, item["CLAVE"], item["NOMBRE"], rack_return_raw, qty, usuario)
        if not ok:
            return False, f"Error al restaurar inventario: {msg}"
        ws_p.delete_rows(real_row)
        _log_movement(item["CLAVE"], "Cancelación Traslado",
            f"Regresado a {_normalize_rack(rack_return_raw)}", qty, 0, usuario, origin_sheet)
        _refresh("Traslados_Pendientes"); _refresh("Movimientos")
        return True, "Traslado cancelado. Material restaurado al inventario."
    except Exception as e:
        return False, f"Error al cancelar: {e}"


def op_relocate(sheet, clave, nombre, rack_origin_raw, rack_dest_raw, qty, usuario):
    try:
        clave       = _clean(clave)
        rack_origin = _normalize_rack(rack_origin_raw)
        rack_dest   = _normalize_rack(rack_dest_raw)
        if rack_origin == rack_dest:
            return False, "El rack de destino es igual al de origen."
        ws = _sheet(sheet)
        row_o, qty_o = _find_row(ws, clave, rack_origin)
        if not row_o:
            return False, f"No se encontró {clave} en {rack_origin}."
        if qty_o < qty:
            return False, f"Stock insuficiente en {rack_origin}. Disponible: {qty_o} pz."
        ws.update_cell(row_o, 4, qty_o - qty)
        row_d, qty_d = _find_row(ws, clave, rack_dest)
        if row_d:
            ws.update_cell(row_d, 4, qty_d + qty)
        else:
            fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ws.append_row([clave, nombre, rack_dest, qty, fecha])
        _log_movement(clave, "Reubicación Interna", f"De {rack_origin} → {rack_dest}",
            qty, 0, usuario, sheet)
        _refresh(sheet); _refresh("Movimientos")
        return True, f"{qty} pz de {clave} movidas de {rack_origin} a {rack_dest}."
    except Exception as e:
        return False, f"Error en reubicación: {e}"


def op_clean_duplicates(sheet):
    try:
        ws = _sheet(sheet)
        records = ws.get_all_records()
        df = pd.DataFrame(records)
        if df.empty:
            return True, "La hoja está vacía."
        df["CLAVE"]    = df["CLAVE"].apply(_clean)
        df["RACK"]     = df["RACK"].apply(_normalize_rack)
        df["CANTIDAD"] = pd.to_numeric(df["CANTIDAD"], errors="coerce").fillna(0).astype(int)
        before = len(df)
        df_c = (df.groupby(["CLAVE", "RACK"], as_index=False)
                  .agg({"NOMBRE": "last", "CANTIDAD": "sum", "FECHA": "last"})
               )[["CLAVE", "NOMBRE", "RACK", "CANTIDAD", "FECHA"]]
        removed = before - len(df_c)
        if removed <= 0:
            return True, "Sin duplicados. La hoja ya está limpia."
        ws.clear()
        ws.update([df_c.columns.tolist()] + df_c.values.tolist())
        _refresh(sheet)
        return True, f"{removed} filas duplicadas consolidadas. Racks normalizados."
    except Exception as e:
        return False, f"Error en limpieza: {e}"


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS DE UI — presentación pura
# ═══════════════════════════════════════════════════════════════════════════

def _kpi(icon: str, label: str, value, sub: str = "", color: str = "blue"):
    st.markdown(
        f"""<div class="kpi-card {color}">
              <span class="kpi-icon">{icon}</span>
              <div class="kpi-label">{label}</div>
              <div class="kpi-value">{value}</div>
              <div class="kpi-sub">{sub}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def _page_header(icon: str, title: str, sub: str = ""):
    st.markdown(
        f"""<div class="page-header">
              <div class="page-header-icon">{icon}</div>
              <div>
                <div class="page-header-title">{title}</div>
                <div class="page-header-sub">{sub}</div>
              </div>
            </div>""",
        unsafe_allow_html=True,
    )


def _section(text: str):
    st.markdown(f'<div class="section-title">{text}</div>', unsafe_allow_html=True)


def _rack_tag(raw: str):
    if raw:
        st.markdown(
            f'<div style="margin-top:4px">'
            f'<span class="rack-preview">→ {_normalize_rack(raw)}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )


def _ok(msg: str):
    st.markdown(f'<div class="toast-success">✓ {msg}</div>', unsafe_allow_html=True)


def _err(msg: str):
    st.markdown(f'<div class="toast-error">✗ {msg}</div>', unsafe_allow_html=True)


def _badge(text: str, color: str = "blue"):
    st.markdown(
        f'<span class="badge badge-{color}">{text}</span>',
        unsafe_allow_html=True,
    )


def _avail_badge(qty: int):
    color = "green" if qty > 5 else ("amber" if qty > 0 else "red")
    st.markdown(
        f'<div class="avail-wrap">'
        f'<span class="badge badge-{color}">📦 {qty} pz disponibles</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── st.column_config — tablas de alta gama ─────────────────────────────────

def _stock_column_config() -> dict:
    return {
        "CLAVE":    st.column_config.TextColumn("Clave", width="small"),
        "NOMBRE":   st.column_config.TextColumn("Descripción", width="medium"),
        "RACK":     st.column_config.TextColumn("Ubicación", width="small"),
        "CANTIDAD": st.column_config.NumberColumn("Stock", format="%d pz", width="small"),
    }


def _logistics_column_config(loc_col: str) -> dict:
    return {
        "FECHA":    st.column_config.TextColumn("Fecha", width="small"),
        loc_col:    st.column_config.TextColumn(loc_col.title(), width="medium"),
        "CLAVE":    st.column_config.TextColumn("Clave", width="small"),
        "NOMBRE":   st.column_config.TextColumn("Descripción", width="medium"),
        "CANTIDAD": st.column_config.NumberColumn("Cantidad", format="%d pz", width="small"),
    }


def _history_column_config() -> dict:
    return {
        "FECHA":    st.column_config.TextColumn("Fecha", width="small"),
        "CLAVE":    st.column_config.TextColumn("Clave", width="small"),
        "TIPO":     st.column_config.TextColumn("Tipo de Movimiento", width="medium"),
        "DETALLE":  st.column_config.TextColumn("Detalle", width="large"),
        "CANTIDAD": st.column_config.NumberColumn("Cantidad", format="%d pz", width="small"),
        "PRECIO":   st.column_config.NumberColumn("Precio", format="$%.2f", width="small"),
        "USUARIO":  st.column_config.TextColumn("Usuario", width="small"),
        "SUCURSAL": st.column_config.TextColumn("Sucursal", width="medium"),
    }


# ═══════════════════════════════════════════════════════════════════════════
# UI — LOGIN
# ═══════════════════════════════════════════════════════════════════════════

def ui_login():
    _inject_css()
    _, col, _ = st.columns([1, 1.1, 1])
    with col:
        st.markdown(
            f"""<div class="login-card">
                 <div class="login-logo">{LOGO_HTML}</div>
                 <div class="login-brand">Glass Master Inventario</div>
                 <div class="login-sub">Sistema de Gestión de Inventario</div>
                 <hr class="login-divider">
               </div>""",
            unsafe_allow_html=True,
        )
        with st.container(border=True):
            usuario  = st.text_input("Usuario", placeholder="Ingresa tu usuario").strip()
            password = st.text_input("Contraseña", type="password",
                                     placeholder="••••••••••").strip()
            if st.button("INICIAR SESIÓN →", type="primary", use_container_width=True):
                data = USUARIOS.get(usuario)
                if data and data["pass"] == password:
                    st.session_state.update({
                        "_logged":    True,
                        "_user":      usuario,
                        "_rol":       data["rol"],
                        "_own_sheet": data["sucursal"] or "Inventario_Suc1",
                    })
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
        st.markdown(
            "<div style='text-align:center;margin-top:16px'>"
            "<span style='font-size:0.72rem;color:#94A3B8'>"
            "Acceso restringido — uso corporativo exclusivo"
            "</span></div>",
            unsafe_allow_html=True,
        )


# ═══════════════════════════════════════════════════════════════════════════
# UI — SIDEBAR (Navegación corporativa)
# ═══════════════════════════════════════════════════════════════════════════

SECTION_LABELS: dict[str, str] = {
    "dashboard":   "📊 Panel de Control",
    "operaciones": "🔄 Centro de Operaciones",
    "logistica":   "🚚 Tránsitos",
    "auditoria":   "📜 Auditoría",
}


def ui_sidebar() -> tuple[str, str]:
    rol       = st.session_state["_rol"]
    own_sheet = st.session_state["_own_sheet"]
    user      = st.session_state["_user"]

    with st.sidebar:
        st.markdown(
            f"""<div class="sb-brand">
                  <div style="margin-bottom: 12px;">{LOGO_HTML}</div>
                  <div class="sb-brand-name">Glass Master Inventario</div>
                </div>""",
            unsafe_allow_html=True,
        )
        st.markdown("---")

        if rol == "admin":
            active_sheet = st.selectbox(
                "🏢 Sucursal activa",
                list(SUCURSALES.keys()),
                format_func=lambda x: SUCURSALES[x],
            )
        else:
            active_sheet = own_sheet
            st.markdown(
                f'<div class="sb-suc-label">🏢 Sucursal asignada</div>'
                f'<div class="sb-suc-name">{SUCURSALES.get(active_sheet, active_sheet)}</div>',
                unsafe_allow_html=True,
            )

        rol_color = "#818CF8" if rol == "admin" else "#34D399"
        st.markdown(
            f"""<div class="sb-user-chip">
                  <div>
                    <div class="sb-user-name">👤 {user.upper()}</div>
                    <div class="sb-user-rol" style="color:{rol_color}">{rol.upper()}</div>
                  </div>
                </div>""",
            unsafe_allow_html=True,
        )
        st.markdown("---")

        keys = ["dashboard", "operaciones", "logistica"]
        if rol == "admin":
            keys.append("auditoria")

        section = st.radio(
            "Navegación",
            keys,
            format_func=lambda k: SECTION_LABELS[k],
            label_visibility="collapsed",
        )

        st.markdown("---")
        if st.button("🔄 Sincronizar Datos", use_container_width=True):
            for k in [k for k in st.session_state if k.startswith("df_")]:
                del st.session_state[k]
            st.session_state["_data_loaded"] = False
            st.rerun()

        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()

    return active_sheet, section


# ═══════════════════════════════════════════════════════════════════════════
# UI — SECCIÓN 1: PANEL DE CONTROL (DASHBOARD COMPLETO MODIFICADO)
# ═══════════════════════════════════════════════════════════════════════════

def ui_warehouse(sheet: str, rol: str):
    nombre_suc = SUCURSALES.get(sheet, sheet)
    _page_header("📊", f"Panel de Control — {nombre_suc}",
                 "Métricas e Inventario Completo del almacén activo")

    # MODIFICADO: Se utiliza _get_df() para traer la tabla entera incluyendo registros en 0
    df_all_crystals = _get_df(sheet)
    df_pending      = _get_df("Traslados_Pendientes")

    total_qty   = int(df_all_crystals["CANTIDAD"].sum())   if not df_all_crystals.empty else 0
    unique_keys = int(df_all_crystals["CLAVE"].nunique())  if not df_all_crystals.empty else 0
    pending_in  = (
        len(df_pending[df_pending["DESTINO"] == sheet])
        if not df_pending.empty and "DESTINO" in df_pending.columns else 0
    )

    # KPI Cards
    c1, c2, c3 = st.columns(3)
    with c1:
        _kpi("📦", "Total de Cristales en Stock", f"{total_qty:,}",
             "unidades con existencias reales")
    with c2:
        _kpi("🔑", "Catálogo Registrado", unique_keys,
             "modelos guardados en este almacén", "green")
    with c3:
        _kpi("🚚", "Traslados por Recibir", pending_in,
             "envíos en tránsito hacia esta sucursal",
             "amber" if pending_in > 0 else "green")

    st.markdown("---")

    if rol == "admin":
        with st.expander("🧹 Mantenimiento — Consolidar Duplicados y Normalizar Racks"):
            st.warning(
                f"Consolida filas con la misma CLAVE+RACK sumando sus cantidades "
                f"y normaliza todos los nombres de rack en **{nombre_suc}**. "
                f"No se pierde stock."
            )
            if st.button("▶ Ejecutar Limpieza", type="primary"):
                ok, msg = op_clean_duplicates(sheet)
                _ok(msg) if ok else _err(msg)

    if df_all_crystals.empty:
        st.info("No hay productos registrados en esta sucursal.")
        return

    _section("📋 Inventario Total (Con y Sin Existencia)")

    with st.container(border=True):
        # Filtro interactivo en tiempo real al ingresar texto y pulsar Enter
        filtro = st.text_input(
            "Buscar en inventario:",
            placeholder="Escribe un parecido (Ej: 75, FW, Rack) y presiona Enter...",
            key="wh_filter",
        ).strip().upper()

        df_view = df_all_crystals.copy()
        if filtro:
            mask = df_view.astype(str).apply(
                lambda col: col.str.contains(filtro, case=False, na=False)
            ).any(axis=1)
            df_view = df_view[mask]
            if df_view.empty:
                st.warning(f"Sin resultados para la búsqueda: '{filtro}'")
                return
            st.caption(f"{len(df_view)} registro(s) encontrados con '{filtro}'.")

        cfg = _stock_column_config()
        tab_pb, tab_med, tab_otros = st.tabs(["🚘 Parabrisas", "🔙 Medallones", "🚪 Otros"])
        
        with tab_pb:
            d = df_view[df_view["NOMBRE"].str.contains("Parabrisas", case=False, na=False)]
            st.caption(f"{len(d)} registros encontrados · Total en Stock: {int(d['CANTIDAD'].sum()) if not d.empty else 0} pz")
            st.dataframe(d[["CLAVE", "NOMBRE", "RACK", "CANTIDAD"]],
                         use_container_width=True, hide_index=True, column_config=cfg)
        with tab_med:
            d = df_view[df_view["NOMBRE"].str.contains("Medallón|Medallon", case=False, na=False)]
            st.caption(f"{len(d)} registros encontrados · Total en Stock: {int(d['CANTIDAD'].sum()) if not d.empty else 0} pz")
            st.dataframe(d[["CLAVE", "NOMBRE", "RACK", "CANTIDAD"]],
                         use_container_width=True, hide_index=True, column_config=cfg)
        with tab_otros:
            d = df_view[~df_view["NOMBRE"].str.contains(
                "Parabrisas|Medallón|Medallon", case=False, na=False)]
            st.caption(f"{len(d)} registros encontrados · Total en Stock: {int(d['CANTIDAD'].sum()) if not d.empty else 0} pz")
            st.dataframe(d[["CLAVE", "NOMBRE", "RACK", "CANTIDAD"]],
                         use_container_width=True, hide_index=True, column_config=cfg)


# ═══════════════════════════════════════════════════════════════════════════
# UI — SECCIÓN 2: CENTRO DE OPERACIONES
# ═══════════════════════════════════════════════════════════════════════════

def ui_operations(sheet: str, usuario: str, rol: str):
    nombre_suc = SUCURSALES.get(sheet, sheet)
    _page_header("🔄", f"Centro de Operaciones — {nombre_suc}",
                 "Buscar · seleccionar rack · ejecutar — todo en una sola vista")

    df_stock = _get_df_stock(sheet)

    with st.expander("➕ Registrar Entrada de Material Nuevo"):
        with st.form("form_alta", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns([1.3, 1, 1, 0.8])
            clave_in = c1.text_input("Clave del Cristal").upper().strip()
            tipo_in  = c2.selectbox("Tipo de Pieza", TIPOS_PIEZA)
            rack_in  = c3.text_input("Rack / Ubicación", value="PISO").strip()
            qty_in = c4.number_input("Cantidad", min_value=1, max_value=999, value=1)
            _rack_tag(rack_in)

            submitted = st.form_submit_button("💾 Confirmar Entrada", type="primary")
            if submitted:
                if not clave_in:
                    st.warning("⚠️ La clave es obligatoria.")
                else:
                    ok, msg = op_alta(sheet, clave_in, tipo_in, rack_in, qty_in, usuario)
                    if ok:
                        _ok(msg); time.sleep(0.4); st.rerun()
                    else:
                        _err(msg)

    with st.container(border=True):
        col_search, col_match = st.columns([1.4, 1])
        with col_search:
            term = st.text_input(
                "🔍 Buscar pieza para Operación (clave con stock activo)",
                placeholder="Ej: 756 · FW75 · JEEP · FORD",
                key="ops_search",
            ).strip()

        if not term:
            with col_match:
                st.caption("💡 Escribe al menos 2 caracteres para transaccionar sobre existencias.")
            return

        found = _search_keys(df_stock, term)

        if not found:
            with col_match:
                st.warning(f"Sin stock para operar **'{term.upper()}'**.")
            df_all = _get_df(sheet)
            if not df_all.empty and "CLAVE" in df_all.columns:
                ghosts = df_all[df_all["CLAVE"].str.contains(_clean(term), case=False, na=False)]
                if not ghosts.empty:
                    st.caption(f"Existen {len(ghosts)} registro(s) con esa clave pero stock = 0. Consúltalo en el Panel de Control.")
            return

        with col_match:
            if len(found) == 1:
                clave_sel = found[0]
                st.success(f"✅ Coincidencia: **{clave_sel}**")
            else:
                clave_sel = st.selectbox(f"{len(found)} coincidencias:", found, key="ops_key")

        nombre_disp = ""
        if not df_stock.empty and "NOMBRE" in df_stock.columns:
            info_row = df_stock[df_stock["CLAVE"] == clave_sel]
            if not info_row.empty:
                nombre_disp = info_row.iloc[0]["NOMBRE"]

        st.markdown(
            f'<div class="prod-info">'
            f'  <span class="prod-clave">{clave_sel}</span>'
            f'  <span class="prod-nombre">{nombre_disp or "Sin descripción"}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        stock_rows = df_stock[df_stock["CLAVE"] == clave_sel].copy()
        rack_summary = (
            stock_rows.groupby("RACK")["CANTIDAD"].sum()
            .reset_index().sort_values("CANTIDAD", ascending=False)
        )

        if rack_summary.empty:
            st.warning("Sin stock disponible en ningún rack.")
            return

        col_rack, col_avail, col_action = st.columns([1.2, 0.8, 1.3])
        with col_rack:
            rack_opts = [
                f"{r['RACK']}  —  {int(r['CANTIDAD'])} pz"
                for _, r in rack_summary.iterrows()
            ]
            rack_label = st.selectbox("📍 Rack de origen", rack_opts, key="ops_rack")
            rack_sel   = rack_label.split("  —  ")[0].strip()
            stock_rack = int(rack_summary[rack_summary["RACK"] == rack_sel]["CANTIDAD"].values[0])
        with col_avail:
            _avail_badge(stock_rack)
        with col_action:
            accion = st.selectbox(
                "⚙️ Acción",
                ["💰 Venta / Instalación", "🚚 Traslado a Sucursal", "📦 Reubicar Rack"],
                key="ops_action",
            )

        nombre_prod = nombre_disp or (
            stock_rows[stock_rows["RACK"] == rack_sel]["NOMBRE"].iloc[0]
            if not stock_rows[stock_rows["RACK"] == rack_sel].empty else "Sin descripción"
        )

        st.markdown('<hr style="margin:6px 0 14px">', unsafe_allow_html=True)

        if accion.startswith("💰"):
            with st.form("form_venta"):
                c_a, c_b, c_c, c_d = st.columns([0.8, 1, 1, 1.2], vertical_alignment="bottom")
                qty_v   = c_a.number_input("Cantidad", min_value=1, max_value=stock_rack, value=1)
                precio  = c_b.number_input("Precio $", min_value=0.0, value=0.0, step=50.0)
                tipo_cl = c_c.selectbox("Cliente", ["Público General", "Asegurado"])
                aseg    = c_d.text_input("Aseguradora") if tipo_cl == "Asegurado" else ""
                nota    = st.text_input("Nota / Observaciones (opcional)")

                detalle = f"Asegurado: {aseg}" if aseg else "Público General"
                if nota:
                    detalle += f" — {nota}"

                btn_col = st.columns([3, 1])[1]
                if btn_col.form_submit_button("💰 Confirmar Venta", type="primary", use_container_width=True):
                    ok, msg = op_venta(sheet, clave_sel, rack_sel, detalle, qty_v, precio, usuario)
                    if ok:
                        _ok(msg); time.sleep(0.4); st.rerun()
                    else:
                        _err(msg)

        elif accion.startswith("🚚"):
            with st.form("form_traslado"):
                c_a, c_b, c_c = st.columns([1, 1.4, 1], vertical_alignment="bottom")
                qty_t    = c_a.number_input("Cantidad", min_value=1, max_value=stock_rack, value=1)
                dest_ops = {k: v for k, v in SUCURSALES.items() if k != sheet}
                dest     = c_b.selectbox("Sucursal destino", list(dest_ops.keys()), format_func=lambda x: SUCURSALES[x])
                enviar   = c_c.form_submit_button("🚚 Confirmar Traslado", type="primary", use_container_width=True)
                st.caption(f"{qty_t} pz de **{clave_sel}** · {rack_sel} → {SUCURSALES[dest]}")
                if enviar:
                    ok, msg = op_send_transfer(sheet, clave_sel, rack_sel, qty_t, dest, usuario)
                    if ok:
                        _ok(msg); time.sleep(0.4); st.rerun()
                    else:
                        _err(msg)

        elif accion.startswith("📦"):
            with st.form("form_reubicacion"):
                c_a, c_b, c_c = st.columns([1, 1.4, 1], vertical_alignment="bottom")
                qty_r       = c_a.number_input("Cantidad", min_value=1, max_value=stock_rack, value=1)
                rack_dest_r = c_b.text_input("Rack de destino", placeholder="Ej: 3 · PEINE · A-2").strip()
                confirmar_r = c_c.form_submit_button("📦 Confirmar", type="primary", use_container_width=True)
                _rack_tag(rack_dest_r)
                if confirmar_r:
                    if not rack_dest_r:
                        st.warning("⚠️ Indica el rack de destino.")
                    else:
                        ok, msg = op_relocate(sheet, clave_sel, nombre_prod, rack_sel, rack_dest_r, qty_r, usuario)
                        if ok:
                            _ok(msg); time.sleep(0.4); st.rerun()
                        else:
                            _err(msg)


# ═══════════════════════════════════════════════════════════════════════════
# UI — SECCIÓN 3: TRÁNSITOS (LOGÍSTICA INTER-SUCURSAL)
# ═══════════════════════════════════════════════════════════════════════════

def ui_logistics(sheet: str, usuario: str):
    nombre_suc = SUCURSALES.get(sheet, sheet)
    _page_header("🚚", f"Tránsitos — {nombre_suc}",
                 "Gestión de traslados en tránsito entre sucursales")

    df_p = _get_df("Traslados_Pendientes")

    if df_p.empty or "DESTINO" not in df_p.columns:
        st.info("📭 No hay traslados en tránsito actualmente.")
        return

    tab_recv, tab_sent = st.tabs(["📥 Por Recibir", "📤 Enviados — Cancelar"])

    with tab_recv:
        arrivals = df_p[df_p["DESTINO"] == sheet].reset_index(drop=False)
        if arrivals.empty:
            st.success("✅ No tienes material pendiente de recibir.")
        else:
            _section("Envíos que llegarán a esta sucursal")
            display = arrivals.copy()
            display["ORIGEN"] = display["ORIGEN"].map(SUCURSALES).fillna(display["ORIGEN"])
            with st.container(border=True):
                st.dataframe(
                    display[["FECHA", "ORIGEN", "CLAVE", "NOMBRE", "CANTIDAD"]],
                    use_container_width=True, hide_index=True,
                    column_config=_logistics_column_config("ORIGEN"),
                )

            _section("Confirmar Recepción")
            opts = arrivals.apply(
                lambda r: f"{r['CLAVE']} · {r['CANTIDAD']} pz · de {SUCURSALES.get(r['ORIGEN'], r['ORIGEN'])} [{r['FECHA']}]",
                axis=1,
            ).tolist()
            sel = st.selectbox("Envío a recibir:", opts)
            idx  = opts.index(sel)
            fila = arrivals.iloc[idx]

            with st.container(border=True):
                with st.form("form_recv"):
                    c_a, c_b = st.columns([1.5, 1], vertical_alignment="bottom")
                    c_a.markdown(f"**Clave:** `{fila['CLAVE']}` &nbsp;·&nbsp; **Cantidad:** {int(fila['CANTIDAD'])} pz")
                    rack_recv = c_b.text_input("📍 Rack donde se guardará", placeholder="Ej: 3 · PEINE · PISO").strip()
                    _rack_tag(rack_recv)

                    if st.form_submit_button("✅ Confirmar Recepción", type="primary"):
                        if not rack_recv:
                            st.warning("⚠️ Indica el rack de destino.")
                        else:
                            pending_row = int(fila["index"]) + 2
                            ok, msg = op_receive_transfer(
                                sheet, fila["CLAVE"], fila["NOMBRE"],
                                int(fila["CANTIDAD"]), rack_recv, pending_row, usuario,
                            )
                            if ok:
                                _ok(msg); time.sleep(0.4); st.rerun()
                            else:
                                _err(msg)

    with tab_sent:
        sent = df_p[df_p["ORIGEN"] == sheet].reset_index(drop=False)
        if sent.empty:
            st.info("📭 No tienes envíos pendientes activos.")
        else:
            st.info("Solo puedes cancelar envíos que aún no hayan sido confirmados por la sucursal destino.")
            display_s = sent.copy()
            display_s["DESTINO"] = display_s["DESTINO"].map(SUCURSALES).fillna(display_s["DESTINO"])
            with st.container(border=True):
                st.dataframe(
                    display_s[["FECHA", "DESTINO", "CLAVE", "NOMBRE", "CANTIDAD"]],
                    use_container_width=True, hide_index=True,
                    column_config=_logistics_column_config("DESTINO"),
                )

            _section("Cancelar Envío y Recuperar Material")
            opts_c = sent.apply(
                lambda r: f"{r['CLAVE']} · {r['CANTIDAD']} pz → {SUCURSALES.get(r['DESTINO'], r['DESTINO'])} [{r['FECHA']}]",
                axis=1,
            ).tolist()
            sel_c  = st.selectbox("Envío a cancelar:", opts_c)
            idx_c  = opts_c.index(sel_c)
            fila_c = sent.iloc[idx_c]

            with st.container(border=True):
                with st.form("form_cancel"):
                    c_a, c_b = st.columns([1.5, 1], vertical_alignment="bottom")
                    c_a.markdown(f"**Recuperarás:** `{fila_c['CLAVE']}` · {int(fila_c['CANTIDAD'])} pz")
                    rack_ret = c_b.text_input("📍 Rack de retorno", placeholder="Ej: PISO · 3 · PEINE").strip()
                    _rack_tag(rack_ret)

                    if st.form_submit_button("🚨 Cancelar Envío y Recuperar", type="primary"):
                        if not rack_ret:
                            st.warning("⚠️ Indica el rack de retorno.")
                        else:
                            ok, msg = op_cancel_transfer(sheet, fila_c.to_dict(), rack_ret, usuario)
                            if ok:
                                _ok(msg); time.sleep(0.4); st.rerun()
                            else:
                                _err(msg)


# ═══════════════════════════════════════════════════════════════════════════
# UI — SECCIÓN 4: AUDITORÍA (solo admin)
# ═══════════════════════════════════════════════════════════════════════════

def ui_history():
    _page_header("📜", "Auditoría e Historial de Movimientos",
                 "Registro cronológico completo de todas las operaciones")

    df = _get_df("Movimientos")

    if df.empty:
        st.info("No hay movimientos registrados.")
        return

    with st.container(border=True):
        c1, c2 = st.columns(2)
        tipos = ["Todos"] + (sorted(df["TIPO"].unique().tolist()) if "TIPO" in df.columns else [])
        sucs  = ["Todas"] + (sorted(df["SUCURSAL"].unique().tolist()) if "SUCURSAL" in df.columns else [])
        ft = c1.selectbox("Tipo de movimiento:", tipos)
        fs = c2.selectbox("Sucursal:", sucs)

    df_v = df.copy()
    if "TIPO" in df.columns and ft != "Todos":
        df_v = df_v[df_v["TIPO"] == ft]
    if "SUCURSAL" in df.columns and fs != "Todas":
        df_v = df_v[df_v["SUCURSAL"] == fs]

    st.caption(f"{len(df_v)} registros · orden más reciente primero.")
    st.dataframe(df_v.iloc[::-1], use_container_width=True, hide_index=True, column_config=_history_column_config())

    csv = df_v.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Exportar CSV",
        data=csv,
        file_name=f"historial_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )


# ═══════════════════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA
# ═══════════════════════════════════════════════════════════════════════════

def main():
    _inject_css()

    if not st.session_state.get("_logged", False):
        ui_login()
        return

    _init_session()
    active_sheet, section = ui_sidebar()
    user = st.session_state["_user"]
    rol  = st.session_state["_rol"]

    if section == "dashboard":
        ui_warehouse(active_sheet, rol)
    elif section == "operaciones":
        ui_operations(active_sheet, user, rol)
    elif section == "logistica":
        ui_logistics(active_sheet, user)
    elif section == "auditoria" and rol == "admin":
        ui_history()


if __name__ == "__main__":
    main()