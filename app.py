"""
╔══════════════════════════════════════════════════════════════════════════╗
║         GLASS MASTER INVENTARIO — (UI REDESIGN + DINÁMICO RACKS)         ║
║         Arquitectura: Session State SSOT + Write-Through Cache          ║
╠══════════════════════════════════════════════════════════════════════════╣
║  ESTE PASE: VISUALIZACIÓN COMPLETA + FILTRADO PARCIAL EN PANEL.          ║
║  · Muestra todos los cristales en Panel de Control (con o sin stock)     ║
║  · Auditoría restringida solo para admin                                 ║
║  · Sección Pedidos multilinea con Rack dinámico (CLAVE,CANTIDAD,RACK)    ║
║  · Baja inmediata desde Tránsitos integrada                              ║
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

LOGO = Image.open("logo.png")

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

C_NAVY       = "#138A27"
C_BLUE       = "#1E3A8A"
C_BLUE_LT    = "#2563EB"
C_BG         = "#F8F9FA"
C_SURFACE    = "#FFFFFF"
C_BORDER     = "#E2E8F0"
C_TEXT       = "#0F172A"
C_TEXT_MED   = "#475569"
C_TEXT_LIGHT = "#94A3B8"
C_GREEN      = "#059669"
C_AMBER      = "#D97706"
C_RED        = "#DC2626"

CORPORATE_CSS = f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
  html, body, [class*="css"], .stApp {{ font-family: 'Inter', sans-serif; }}
  .stApp {{ background-color: {C_BG}; }}
  .main .block-container {{ background-color: {C_BG}; padding-top: 1rem; padding-bottom: 2rem; }}
  [data-testid="stVerticalBlockBorderWrapper"] > div > [data-testid="stVerticalBlock"] {{ gap: 0.6rem; }}
  div[data-testid="stForm"] {{ border-color: {C_BORDER} !important; }}
  [data-testid="stSidebar"] {{ background: linear-gradient(180deg, {C_NAVY} 0%, #050d18 100%); border-right: none; }}
  [data-testid="stSidebar"] * {{ color: #CBD5E1 !important; }}
  [data-testid="stSidebar"] .stRadio label {{ font-size: 0.875rem; font-weight: 500; padding: 6px 0; }}
  [data-testid="stSidebar"] .stRadio label:hover {{ color: #FFFFFF !important; }}
  [data-testid="stSidebar"] [data-baseweb="radio"] [aria-checked="true"] + div {{ color: #FFFFFF !important; font-weight: 600; }}
  [data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,0.12) !important; margin: 12px 0 !important; }}
  [data-testid="stSidebar"] .stButton button {{ background: rgba(255,255,255,0.08) !important; border: 1px solid rgba(255,255,255,0.15) !important; font-weight: 500; border-radius: 8px; transition: all 0.2s; }}
  [data-testid="stSidebar"] .stButton button:hover {{ background: rgba(255,255,255,0.14) !important; color: #FFFFFF !important; }}
  h1, h2, h3 {{ color: {C_NAVY} !important; font-weight: 700; letter-spacing: -0.02em; }}
  .kpi-card {{ background: {C_SURFACE}; border: 1px solid {C_BORDER}; border-radius: 12px; padding: 20px 22px; box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 4px 16px rgba(10,25,47,0.07); position: relative; overflow: hidden; transition: box-shadow 0.2s; }}
  .kpi-card:hover {{ box-shadow: 0 4px 20px rgba(10,25,47,0.12); }}
  .kpi-card::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: {C_BLUE}; border-radius: 12px 12px 0 0; }}
  .kpi-card.green::before {{ background: {C_GREEN}; }}
  .kpi-card.amber::before {{ background: {C_AMBER}; }}
  .kpi-card.red::before   {{ background: {C_RED}; }}
  .kpi-icon {{ font-size: 1.4rem; margin-bottom: 10px; display: block; }}
  .kpi-label {{ color: {C_TEXT_LIGHT}; font-size: 0.7rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 6px; }}
  .kpi-value {{ color: {C_TEXT}; font-size: 2.1rem; font-weight: 800; line-height: 1; margin-bottom: 4px; letter-spacing: -0.03em; }}
  .kpi-sub {{ color: {C_TEXT_LIGHT}; font-size: 0.72rem; font-weight: 400; }}
  .section-title {{ color: {C_NAVY}; font-size: 1.05rem; font-weight: 700; margin: 18px 0 10px; padding-bottom: 8px; border-bottom: 2px solid {C_BORDER}; letter-spacing: -0.01em; }}
  .page-header {{ background: {C_SURFACE}; border: 1px solid {C_BORDER}; border-radius: 12px; padding: 16px 22px; margin-bottom: 20px; display: flex; align-items: center; gap: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }}
  .page-header-icon {{ font-size: 1.5rem; background: {C_BG}; width: 44px; height: 44px; border-radius: 10px; display: flex; align-items: center; justify-content: center; border: 1px solid {C_BORDER}; }}
  .page-header-title {{ color: {C_NAVY}; font-size: 1.15rem; font-weight: 700; margin: 0; letter-spacing: -0.02em; }}
  .page-header-sub {{ color: {C_TEXT_LIGHT}; font-size: 0.78rem; margin: 0; }}
  .rack-preview {{ background: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 6px; padding: 4px 10px; color: {C_BLUE}; font-size: 0.78rem; font-weight: 700; font-family: 'Courier New', monospace; display: inline-block; margin-top: 6px; }}
  .toast-success {{ background: #F0FDF4; border: 1px solid #BBF7D0; border-left: 4px solid {C_GREEN}; border-radius: 8px; padding: 12px 16px; color: #166534; font-size: 0.85rem; font-weight: 500; margin: 8px 0; }}
  .toast-error {{ background: #FEF2F2; border: 1px solid #FECACA; border-left: 4px solid {C_RED}; border-radius: 8px; padding: 12px 16px; color: #991B1B; font-size: 0.85rem; font-weight: 500; margin: 8px 0; }}
  [data-testid="stTabs"] [data-baseweb="tab-list"] {{ background: {C_SURFACE}; border-radius: 10px; padding: 4px; border: 1px solid {C_BORDER}; gap: 2px; }}
  [data-testid="stTabs"] [data-baseweb="tab"] {{ border-radius: 7px; font-weight: 500; font-size: 0.83rem; color: {C_TEXT_MED}; padding: 8px 16px; }}
  [data-testid="stTabs"] [aria-selected="true"] {{ background: {C_NAVY} !important; color: white !important; font-weight: 600; }}
  [data-testid="stTabs"] [data-baseweb="tab-border"] {{ display: none; }}
  .stButton [data-testid="baseButton-primary"] {{ background: {C_BLUE} !important; border: none !important; border-radius: 8px !important; font-weight: 600 !important; letter-spacing: 0.01em; box-shadow: 0 1px 4px rgba(30,58,138,0.25); transition: all 0.18s; }}
  .stButton [data-testid="baseButton-primary"]:hover {{ background: {C_BLUE_LT} !important; box-shadow: 0 4px 12px rgba(30,58,138,0.35); transform: translateY(-1px); }}
  [data-testid="stFormSubmitButton"] button[kind="primary"] {{ background: {C_BLUE} !important; border: none !important; border-radius: 8px !important; font-weight: 600 !important; box-shadow: 0 1px 4px rgba(30,58,138,0.25); }}
  [data-testid="stFormSubmitButton"] button[kind="primary"]:hover {{ background: {C_BLUE_LT} !important; }}
  .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] {{ border-color: {C_BORDER} !important; border-radius: 8px !important; font-size: 0.875rem; color: {C_TEXT} !important; background: {C_SURFACE} !important; }}
  .stTextInput input:focus, .stNumberInput input:focus {{ border-color: {C_BLUE} !important; box-shadow: 0 0 0 3px rgba(30,58,138,0.12) !important; }}
  .stTextInput label, .stNumberInput label, .stSelectbox label, .stRadio label {{ color: {C_TEXT_MED} !important; font-size: 0.8rem !important; font-weight: 600 !important; text-transform: uppercase; letter-spacing: 0.06em; }}
  [data-testid="stDataFrame"] {{ border-radius: 10px; overflow: hidden; border: 1px solid {C_BORDER}; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }}
  [data-testid="stExpander"] {{ border: 1px solid {C_BORDER} !important; border-radius: 10px !important; background: {C_SURFACE}; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }}
  [data-testid="stExpander"] summary {{ font-weight: 600; color: {C_NAVY} !important; font-size: 0.88rem; }}
  [data-testid="stAlert"] {{ border-radius: 8px !important; font-size: 0.85rem; }}
  .stCaption, [data-testid="stCaptionContainer"] {{ color: {C_TEXT_LIGHT} !important; font-size: 0.75rem; }}
  hr {{ border-color: {C_BORDER} !important; margin: 14px 0 !important; }}
  .login-card {{ background: {C_SURFACE}; border: 1px solid {C_BORDER}; border-radius: 16px; padding: 44px 40px; box-shadow: 0 8px 32px rgba(10,25,47,0.10); margin-top: 48px; }}
  .login-logo {{ text-align: center; margin-bottom: 6px; }}
  .login-brand {{ text-align: center; color: {C_NAVY}; font-size: 1.5rem; font-weight: 800; letter-spacing: -0.03em; margin-bottom: 2px; }}
  .login-sub {{ text-align: center; color: {C_TEXT_LIGHT}; font-size: 0.78rem; margin-bottom: 32px; }}
  .login-divider {{ border: none; border-top: 1px solid {C_BORDER}; margin: 20px 0; }}
  .sb-brand {{ text-align: center; padding: 16px 0 8px; }}
  .sb-brand-name {{ color: #FFFFFF; font-size: 1.1rem; font-weight: 800; letter-spacing: -0.02em; }}
  .sb-user-chip {{ background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.12); border-radius: 8px; padding: 8px 12px; margin: 8px 0; display: flex; align-items: center; gap: 8px; }}
  .sb-user-name {{ color: #E2E8F0; font-size: 0.82rem; font-weight: 600; }}
  .sb-user-rol {{ color: rgba(255,255,255,0.45); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em; }}
  .sb-suc-label {{ color: rgba(255,255,255,0.4); font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 2px; }}
  .sb-suc-name {{ color: #FFFFFF; font-size: 0.92rem; font-weight: 600; }}
  .prod-info {{ background: {C_SURFACE}; border: 1px solid {C_BORDER}; border-radius: 8px; padding: 10px 16px; margin: 6px 0 10px; display: flex; align-items: center; gap: 10px; font-size: 0.88rem; }}
  .prod-clave {{ background: {C_BG}; border: 1px solid {C_BORDER}; border-radius: 6px; padding: 3px 10px; font-family: 'Courier New', monospace; font-weight: 700; color: {C_NAVY}; font-size: 0.92rem; }}
  .prod-nombre {{ color: {C_TEXT_MED}; font-size: 0.83rem; }}
</style>
"""

def _inject_css():
    st.markdown(CORPORATE_CSS, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════
# CAPA DE NORMALIZACIÓN
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
# CONEXIÓN Y DATOS
# ═══════════════════════════════════════════════════════════════════════════

@st.cache_resource
def _connect_gsheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(creds).open("Inventario_Cristales")

def _sheet(name: str):
    return _connect_gsheets().worksheet(name)

def _load_df(sheet_name: str) -> pd.DataFrame:
    ws = _sheet(sheet_name)
    records = ws.get_all_records()
    df = pd.DataFrame(records)
    if df.empty:
        return df
    if "CLAVE" in df.columns: df["CLAVE"] = df["CLAVE"].apply(_clean)
    if "RACK" in df.columns: df["RACK"] = df["RACK"].apply(_normalize_rack)
    if "NOMBRE" in df.columns: df["NOMBRE"] = df["NOMBRE"].astype(str)
    if "CANTIDAD" in df.columns: df["CANTIDAD"] = pd.to_numeric(df["CANTIDAD"], errors="coerce").fillna(0).astype(int)
    return df

def _init_session():
    if not st.session_state.get("_data_loaded", False):
        with st.spinner("⏳ Sincronizando inventario…"):
            try:
                sheets = list(SUCURSALES.keys()) + ["Movimientos", "Traslados_Pendientes"]
                for name in sheets: st.session_state[f"df_{name}"] = _load_df(name)
                st.session_state["_data_loaded"] = True
            except Exception as e:
                st.error(f"⚠️ Error de conexión con Google Sheets: {e}")
                st.stop()

def _refresh(sheet_name: str):
    st.session_state[f"df_{sheet_name}"] = _load_df(sheet_name)

def _get_df(sheet_name: str) -> pd.DataFrame:
    key = f"df_{sheet_name}"
    if key not in st.session_state: _refresh(sheet_name)
    return st.session_state.get(key, pd.DataFrame())

def _get_df_stock(sheet_name: str) -> pd.DataFrame:
    df = _get_df(sheet_name)
    if df.empty or "CANTIDAD" not in df.columns: return df
    return df[df["CANTIDAD"] > 0].copy()

def _search_keys(df: pd.DataFrame, term: str) -> list[str]:
    if df.empty or "CLAVE" not in df.columns or not term: return []
    t = _clean(term)
    pool = df[df["CANTIDAD"] > 0] if "CANTIDAD" in df.columns else df
    mask = pool["CLAVE"].str.contains(t, case=False, na=False)
    return sorted(pool.loc[mask, "CLAVE"].unique().tolist())

# ═══════════════════════════════════════════════════════════════════════════
# CAPA DE ESCRITURA
# ═══════════════════════════════════════════════════════════════════════════

def _find_row(ws, clave: str, rack: str) -> tuple[int | None, int]:
    records = ws.get_all_records()
    for i, row in enumerate(records):
        if _clean(row.get("CLAVE", "")) == clave and _normalize_rack(row.get("RACK", "")) == rack:
            qty = int(pd.to_numeric(row.get("CANTIDAD", 0), errors="coerce") or 0)
            return i + 2, qty
    return None, 0

def _log_movement(clave, tipo, detalle, cantidad, precio, usuario, sucursal):
    try:
        ws = _sheet("Movimientos")
        ws.append_row([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), clave, tipo, detalle, cantidad, precio, usuario, sucursal])
    except Exception:
        pass

def op_alta(sheet, clave, nombre, rack_raw, qty, usuario):
    try:
        ws = _sheet(sheet)
        clave = _clean(clave)
        rack = _normalize_rack(rack_raw)
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
        ws = _sheet(sheet)
        clave = _clean(clave)
        rack = _normalize_rack(rack)
        row, current = _find_row(ws, clave, rack)
        if not row: return False, f"No se encontró {clave} en {rack}."
        if current < qty: return False, f"Stock insuficiente. Disponible: {current} pz."
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
        ws = _sheet(sheet_origin)
        clave = _clean(clave)
        rack = _normalize_rack(rack)
        row, current = _find_row(ws, clave, rack)
        if not row: return False, f"No se encontró {clave} en {rack}."
        if current < qty: return False, f"Stock insuficiente. Disponible: {current} pz."
        nombre = ws.cell(row, 2).value or "Sin Nombre"
        ws.update_cell(row, 4, current - qty)
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _sheet("Traslados_Pendientes").append_row([fecha, clave, nombre, qty, sheet_origin, dest_sheet])
        _log_movement(clave, "Envío Traslado", f"De {sheet_origin}/{rack} → {SUCURSALES.get(dest_sheet, dest_sheet)}", qty, 0, usuario, sheet_origin)
        _refresh(sheet_origin); _refresh("Traslados_Pendientes"); _refresh("Movimientos")
        return True, f"Traslado enviado. Quedan {current - qty} pz en {rack}."
    except Exception as e:
        return False, f"Error en traslado: {e}"

def op_receive_transfer(dest_sheet, clave, nombre, qty, rack_raw, pending_row, usuario):
    try:
        ok, msg = op_alta(dest_sheet, clave, nombre, rack_raw, qty, usuario)
        if not ok: return False, msg
        _sheet("Traslados_Pendientes").delete_rows(pending_row)
        _log_movement(clave, "Recepción Traslado", f"Guardado en {_normalize_rack(rack_raw)}", qty, 0, usuario, dest_sheet)
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
            if str(row.get("FECHA", "")) == str(item["FECHA"]) and _clean(row.get("CLAVE", "")) == _clean(item["CLAVE"]):
                real_row = i + 2
                break
        if not real_row: return False, "El traslado ya fue aceptado por el destino."
        qty = int(item["CANTIDAD"])
        ok, msg = op_alta(origin_sheet, item["CLAVE"], item["NOMBRE"], rack_return_raw, qty, usuario)
        if not ok: return False, f"Error al restaurar inventario: {msg}"
        ws_p.delete_rows(real_row)
        _log_movement(item["CLAVE"], "Cancelación Traslado", f"Regresado a {_normalize_rack(rack_return_raw)}", qty, 0, usuario, origin_sheet)
        _refresh("Traslados_Pendientes"); _refresh("Movimientos")
        return True, "Traslado cancelado. Material restaurado al inventario."
    except Exception as e:
        return False, f"Error al cancelar: {e}"

def op_relocate(sheet, clave, nombre, rack_origin_raw, rack_dest_raw, qty, usuario):
    try:
        clave = _clean(clave)
        rack_origin = _normalize_rack(rack_origin_raw)
        rack_dest = _normalize_rack(rack_dest_raw)
        if rack_origin == rack_dest: return False, "El rack de destino es igual al de origen."
        ws = _sheet(sheet)
        row_o, qty_o = _find_row(ws, clave, rack_origin)
        if not row_o: return False, "No se encontró el artículo origen."
        if qty_o < qty: return False, f"Cantidad insuficiente en origen ({qty_o} pz)."
        ws.update_cell(row_o, 4, qty_o - qty)
        row_d, qty_d = _find_row(ws, clave, rack_dest)
        if row_d:
            ws.update_cell(row_d, 4, qty_d + qty)
        else:
            fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ws.append_row([clave, nombre, rack_dest, qty, fecha])
        _log_movement(clave, "Reubicación Interna", f"De {rack_origin} → {rack_dest}", qty, 0, usuario, sheet)
        _refresh(sheet); _refresh("Movimientos")
        return True, f"{qty} pz de {clave} movidas a {rack_dest}."
    except Exception as e:
        return False, f"Error en reubicación: {e}"

def op_clean_duplicates(sheet):
    try:
        ws = _sheet(sheet)
        records = ws.get_all_records()
        df = pd.DataFrame(records)
        if df.empty: return True, "La hoja está vacía."
        df["CLAVE"] = df["CLAVE"].apply(_clean)
        df["RACK"] = df["RACK"].apply(_normalize_rack)
        df["CANTIDAD"] = pd.to_numeric(df["CANTIDAD"], errors="coerce").fillna(0).astype(int)
        before = len(df)
        df_c = (df.groupby(["CLAVE", "RACK"], as_index=False).agg({"NOMBRE": "last", "CANTIDAD": "sum", "FECHA": "last"}))[["CLAVE", "NOMBRE", "RACK", "CANTIDAD", "FECHA"]]
        removed = before - len(df_c)
        if removed <= 0: return True, "Sin duplicados. La hoja ya está limpia."
        ws.clear()
        ws.update([df_c.columns.tolist()] + df_c.values.tolist())
        _refresh(sheet)
        return True, f"{removed} filas duplicadas consolidadas. Racks normalizados."
    except Exception as e:
        return False, f"Error en limpieza: {e}"


# ═══════════════════════════════════════════════════════════════════════════
# MEJORA 1b: LIMPIEZA DE DUPLICADOS CON 0 PIEZAS
# ═══════════════════════════════════════════════════════════════════════════

def limpiar_duplicados_cero(ws_inventario):
    """
    Busca filas duplicadas (misma CLAVE + RACK + SUCURSAL) cuya CANTIDAD
    sea 0 y las elimina de Google Sheets borrando de abajo hacia arriba
    para no desplazar índices durante la eliminación.
    Retorna (bool, str) con el resultado de la operación.
    """
    try:
        records = ws_inventario.get_all_records()
        if not records:
            return True, "La hoja está vacía. No hay nada que limpiar."

        df = pd.DataFrame(records)
        df["_row"] = range(2, len(df) + 2)  # índice de fila real en Google Sheets (1-based + encabezado)
        df["CLAVE"] = df["CLAVE"].apply(_clean)
        df["RACK"] = df["RACK"].apply(_normalize_rack)
        df["CANTIDAD"] = pd.to_numeric(df["CANTIDAD"], errors="coerce").fillna(0).astype(int)

        # Identificar grupos duplicados (misma CLAVE + RACK)
        # Dentro de cada grupo, marcar como "candidata a borrar" la fila con CANTIDAD == 0
        # si en ese grupo existe al menos una fila con CANTIDAD > 0
        filas_a_borrar = []
        grupos = df.groupby(["CLAVE", "RACK"])
        for _, grupo in grupos:
            if len(grupo) > 1:
                # Hay duplicados en este par CLAVE-RACK
                con_stock = grupo[grupo["CANTIDAD"] > 0]
                sin_stock = grupo[grupo["CANTIDAD"] == 0]
                if not con_stock.empty and not sin_stock.empty:
                    # Sólo eliminamos las de 0 si hay al menos una con stock
                    filas_a_borrar.extend(sin_stock["_row"].tolist())

        if not filas_a_borrar:
            return True, "No se encontraron duplicados con 0 piezas eliminables."

        # Borrar de abajo hacia arriba para no correr los índices
        for row_idx in sorted(filas_a_borrar, reverse=True):
            ws_inventario.delete_rows(row_idx)

        return True, f"{len(filas_a_borrar)} fila(s) duplicada(s) con 0 piezas eliminada(s) correctamente."
    except Exception as e:
        return False, f"Error en limpiar_duplicados_cero: {e}"


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS DE UI
# ═══════════════════════════════════════════════════════════════════════════

def _kpi(icon, label, value, sub="", color="blue"):
    st.markdown(f'<div class="kpi-card {color}"><span class="kpi-icon">{icon}</span><div class="kpi-label">{label}</div><div class="kpi-value">{value}</div><div class="kpi-sub">{sub}</div></div>', unsafe_allow_html=True)

def _page_header(icon, title, sub=""):
    st.markdown(f'<div class="page-header"><div class="page-header-icon">{icon}</div><div><div class="page-header-title">{title}</div><div class="page-header-sub">{sub}</div></div></div>', unsafe_allow_html=True)

def _section(text):
    st.markdown(f'<div class="section-title">{text}</div>', unsafe_allow_html=True)

def _rack_tag(raw):
    if raw: st.markdown(f'<div style="margin-top:4px"><span class="rack-preview">→ {_normalize_rack(raw)}</span></div>', unsafe_allow_html=True)

def _ok(msg): st.markdown(f'<div class="toast-success">✓ {msg}</div>', unsafe_allow_html=True)
def _err(msg): st.markdown(f'<div class="toast-error">✗ {msg}</div>', unsafe_allow_html=True)

def _stock_column_config():
    return {"CLAVE": st.column_config.TextColumn("Clave Única", width="medium"), "NOMBRE": st.column_config.TextColumn("Descripción / Tipo", width="large"), "RACK": st.column_config.TextColumn("📍 Ubicación Rack", width="medium"), "CANTIDAD": st.column_config.NumberColumn("Existencia", format="%d pz", width="small")}

def _logistics_column_config(label_or_dest):
    return {"FECHA": st.column_config.TextColumn("Enviado El", width="medium"), label_or_dest: st.column_config.TextColumn(label_or_dest.title(), width="medium"), "CLAVE": st.column_config.TextColumn("Clave", width="small"), "NOMBRE": st.column_config.TextColumn("Descripción", width="large"), "CANTIDAD": st.column_config.NumberColumn("Pz", format="%d", width="small")}

def _history_column_config():
    return {"FECHA": st.column_config.TextColumn("Fecha/Hora", width="medium"), "CLAVE": st.column_config.TextColumn("Clave", width="small"), "TIPO": st.column_config.TextColumn("Transacción", width="medium"), "DETALLE": st.column_config.TextColumn("Detalle / Destino u Origen", width="large"), "CANTIDAD": st.column_config.NumberColumn("Cant", format="%d pz", width="small"), "PRECIO": st.column_config.NumberColumn("Precio", format="$%.2f", width="small"), "USUARIO": st.column_config.TextColumn("Usuario", width="small"), "SUCURSAL": st.column_config.TextColumn("Sucursal", width="medium")}

# ═══════════════════════════════════════════════════════════════════════════
# UI — LOGIN
# ═══════════════════════════════════════════════════════════════════════════

def ui_login():
    _inject_css()
    _, col, _ = st.columns([1, 1.1, 1])
    with col:
        st.markdown(f'<div class="login-card"><div class="login-logo">{LOGO_HTML}</div><div class="login-brand">Glass Master Inventario</div><div class="login-sub">Sistema de Gestión de Inventario</div><hr class="login-divider"></div>', unsafe_allow_html=True)
        with st.container(border=True):
            usuario = st.text_input("Usuario", placeholder="Ingresa tu usuario").strip()
            password = st.text_input("Contraseña", type="password", placeholder="••••••••••").strip()
            if st.button("INICIAR SESIÓN →", type="primary", use_container_width=True):
                data = USUARIOS.get(usuario)
                if data and data["pass"] == password:
                    st.session_state.update({"_logged": True, "_user": usuario, "_rol": data["rol"], "_own_sheet": data["sucursal"] or "Inventario_Suc1"})
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")
        st.markdown("<div style='text-align:center;margin-top:16px'><span style='font-size:0.72rem;color:#94A3B8'>Acceso restringido — uso corporativo exclusivo</span></div>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════
# UI — SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════

SECTION_LABELS: dict[str, str] = {
    "dashboard": "📊 Panel de Control",
    "operaciones": "🔄 Centro de Operaciones",
    "logistica": "🚚 Tránsitos",
    "pedidos": "📋 Pedidos",
    "express": "⚡ Operación Express",    # MEJORA 2: nueva sección
    "auditoria": "📜 Auditoría",
}

def ui_sidebar() -> tuple[str, str]:
    rol = st.session_state["_rol"]
    own_sheet = st.session_state["_own_sheet"]
    user = st.session_state["_user"]

    with st.sidebar:
        st.markdown(f'<div class="sb-brand"><div style="margin-bottom: 12px;">{LOGO_HTML}</div><div class="sb-brand-name">Glass Master Inventario</div></div>', unsafe_allow_html=True)
        st.markdown("---")

        if rol == "admin":
            active_sheet = st.selectbox("🏢 Sucursal activa", list(SUCURSALES.keys()), format_func=lambda x: SUCURSALES[x])
        else:
            active_sheet = own_sheet
            st.markdown(f'<div class="sb-suc-label">🏢 Sucursal asignada</div><div class="sb-suc-name">{SUCURSALES.get(active_sheet, active_sheet)}</div>', unsafe_allow_html=True)

        st.markdown(f'<div class="sb-user-chip"><div><div class="sb-user-name">👤 {user}</div><div class="sb-user-rol" style="color:{"#818CF8" if rol == "admin" else "#A7F3D0"}">{rol}</div></div></div>', unsafe_allow_html=True)
        st.markdown("---")

        # 🚨 CANDADO DE SEGURIDAD CORREGIDO: Ocultar Auditoría a usuarios regulares
        visible_sections = list(SECTION_LABELS.keys())
        if rol != "admin":
            if "auditoria" in visible_sections:
                visible_sections.remove("auditoria")

        seccion = st.radio(
            "Navegación Modular",
            visible_sections,
            format_func=lambda x: SECTION_LABELS[x],
        )

        st.markdown("<br><br><br>", unsafe_allow_html=True)
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    return active_sheet, seccion

# ═══════════════════════════════════════════════════════════════════════════
# MODULO 1: DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════

def ui_dashboard(sheet: str, rol: str):
    nombre_suc = SUCURSALES.get(sheet, sheet)
    _page_header("📊", f"Panel de Control — {nombre_suc}", "Visualización analítica integral y catálogo en tiempo real.")

    df_all = _get_df(sheet)
    df_pending = _get_df("Traslados_Pendientes")

    total_qty = int(df_all["CANTIDAD"].sum()) if not df_all.empty else 0
    unique_keys = int(df_all["CLAVE"].nunique()) if not df_all.empty else 0
    pending_in = len(df_pending[df_pending["DESTINO"] == sheet]) if not df_pending.empty and "DESTINO" in df_pending.columns else 0

    c1, c2, c3 = st.columns(3)
    with c1: _kpi("📦", "Total de Cristales en Stock", f"{total_qty:,}", "unidades con existencias reales")
    with c2: _kpi("🔑", "Catálogo Registrado", unique_keys, "modelos guardados en este almacén", "green")
    with c3: _kpi("🚚", "Traslados por Recibir", pending_in, "envíos en tránsito hacia esta sucursal", "amber" if pending_in > 0 else "green")

    st.markdown("---")
    if rol == "admin":
        with st.expander("🧹 Mantenimiento — Consolidar Duplicados y Normalizar Racks"):
            st.warning(f"Consolida filas duplicadas en {nombre_suc}. No se pierde stock.")
            col_clean1, col_clean2 = st.columns(2)
            with col_clean1:
                if st.button("▶ Ejecutar Limpieza", type="primary"):
                    ok, msg = op_clean_duplicates(sheet)
                    _ok(msg) if ok else _err(msg)
            with col_clean2:
                if st.button("🗑️ Eliminar Duplicados con 0 Piezas", type="primary"):
                    # MEJORA 1b: limpiar filas con 0 piezas que son duplicados de otra con stock
                    ws_inv = _sheet(sheet)
                    ok, msg = limpiar_duplicados_cero(ws_inv)
                    if ok:
                        _ok(msg)
                        _refresh(sheet)
                    else:
                        _err(msg)

    if df_all.empty:
        st.info("No hay productos registrados en esta sucursal.")
        return

    _section("📋 Inventario Total (Con y Sin Existencia)")
    with st.container(border=True):
        filtro = st.text_input("Buscar en inventario:", placeholder="Ej: 75, FW, Rack...", key="wh_filter").strip().upper()
        df_view = df_all.copy()
        if filtro:
            mask = df_view.astype(str).apply(lambda col: col.str.contains(filtro, case=False, na=False)).any(axis=1)
            df_view = df_view[mask]
        
        if df_view.empty:
            st.warning(f"Sin resultados para la búsqueda: '{filtro}'")
            return
            
        cfg = _stock_column_config()
        tab_pb, tab_med, tab_otros = st.tabs(["🚘 Parabrisas", "🔙 Medallones", "🚪 Otros"])

        with tab_pb:
            d = df_view[df_view["NOMBRE"].str.contains("Parabrisas", case=False, na=False)]
            st.dataframe(d[["CLAVE", "NOMBRE", "RACK", "CANTIDAD"]], use_container_width=True, hide_index=True, column_config=cfg)
        with tab_med:
            d = df_view[df_view["NOMBRE"].str.contains("Medallón", case=False, na=False)]
            st.dataframe(d[["CLAVE", "NOMBRE", "RACK", "CANTIDAD"]], use_container_width=True, hide_index=True, column_config=cfg)
        with tab_otros:
            d = df_view[~df_view["NOMBRE"].str.contains("Parabrisas|Medallón", case=False, na=False)]
            st.dataframe(d[["CLAVE", "NOMBRE", "RACK", "CANTIDAD"]], use_container_width=True, hide_index=True, column_config=cfg)

# ═══════════════════════════════════════════════════════════════════════════
# MODULO 2: CENTRO DE OPERACIONES
# ═══════════════════════════════════════════════════════════════════════════

def ui_operations(sheet: str, usuario: str):
    nombre_suc = SUCURSALES.get(sheet, sheet)
    _page_header("🔄", f"Centro de Operaciones — {nombre_suc}", "Módulo de transacciones inmediatas: Compras, Ventas e Intercambios.")

    df_stock = _get_df_stock(sheet)
    tab_alta, tab_baja = st.tabs(["📥 Registrar Entrada (Alta/Compra)", "📤 Transaccionar Existencias (Ventas / Traslados / Ajustes)"])

    with tab_alta:
        _section("Nueva Entrada de Mercancía a Almacén")
        with st.form("form_alta", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns([1.5, 1, 1, 0.8])
            clave_in = c1.text_input("Clave del Cristal").upper().strip()
            tipo_in = c2.selectbox("Tipo de Pieza", TIPOS_PIEZA)
            rack_in = c3.text_input("Rack / Ubicación", value="PISO").strip()
            qty_in = c4.number_input("Cantidad", min_value=1, max_value=999, value=1)
            _rack_tag(rack_in)
            if st.form_submit_button("💾 Confirmar Entrada", type="primary"):
                if not clave_in: st.warning("⚠️ La clave es obligatoria.")
                else:
                    ok, msg = op_alta(sheet, clave_in, tipo_in, rack_in, qty_in, usuario)
                    if ok: _ok(msg); time.sleep(0.4); st.rerun()
                    else: _err(msg)

    with tab_baja:
        _section("Buscador de Existencias para Salida")
        with st.container(border=True):
            col_search, col_match = st.columns([1.4, 1])
            with col_search:
                term = st.text_input("🔍 Buscar pieza para Operación (clave con stock activo)", placeholder="Ej: 756 · FW75 · JEEP", key="ops_search").strip()
                if not term:
                    with col_match: st.caption("💡 Escribe al menos 2 caracteres.")
                    return

            found = _search_keys(df_stock, term)
            if not found:
                with col_match: st.warning(f"Sin stock para **'{term.upper()}'**.")
                return

            with col_match:
                if len(found) == 1: clave_sel = found[0]; st.success(f"✅ {clave_sel}")
                else: clave_sel = st.selectbox(f"{len(found)} coincidencias:", found, key="ops_key")

            nombre_disp = ""
            info_row = df_stock[df_stock["CLAVE"] == clave_sel]
            if not info_row.empty: nombre_disp = info_row.iloc[0]["NOMBRE"]

            st.markdown(f'<div class="prod-info"><span class="prod-clave">{clave_sel}</span><span class="prod-nombre">{nombre_disp or "Sin descripción"}</span></div>', unsafe_allow_html=True)

            stock_rows = df_stock[df_stock["CLAVE"] == clave_sel].copy()
            # ── MEJORA 1a: ordenar de mayor a menor stock para priorizar filas con existencia ──
            stock_rows = stock_rows.sort_values(by="CANTIDAD", ascending=False)
            rack_opts = stock_rows.apply(lambda r: f"{r['RACK']} ({r['CANTIDAD']} pz disponible)", axis=1).tolist()

            c_rk, c_ac = st.columns([1.2, 1.4])
            rack_sel_raw = c_rk.selectbox("Selecciona ubicación de origen:", rack_opts)
            fila_stock = stock_rows.iloc[rack_opts.index(rack_sel_raw)]
            rack_sel, stock_rack = fila_stock["RACK"], int(fila_stock["CANTIDAD"])

            accion = c_ac.radio("Acción a Ejecutar:", ["💰 Venta / Instalación", "🚚 Traslado Inter-Sucursal", "📦 Reubicación (Mover Rack)"], horizontal=True)

            st.markdown("---")

            if accion.startswith("💰"):
                with st.form("form_venta"):
                    c1, c2, c3 = st.columns([1, 1.2, 1.2])
                    qty_v = c1.number_input("Cantidad", min_value=1, max_value=stock_rack, value=1)
                    precio = c2.number_input("Precio Cobrado ($)", min_value=0.0, value=0.0, step=100.0)
                    costo = c3.number_input("Costo de Pieza ($)", min_value=0.0, value=0.0, step=100.0)
                    c4, c5 = st.columns(2)
                    aseg = c4.text_input("Aseguradora (Vacío si es Público)")
                    deducible = c5.number_input("Deducible ($)", min_value=0.0, value=0.0, step=50.0)
                    nota = st.text_input("Nota / Observaciones (opcional)")

                    detalle = f"Asegurado: {aseg}" if aseg else "Público General"
                    if deducible > 0: detalle += f" | Deducible: ${deducible:.2f}"
                    if costo > 0: detalle += f" | Costo: ${costo:.2f}"
                    if nota: detalle += f" — {nota}"

                    if st.columns([3, 1])[1].form_submit_button("💰 Confirmar Venta", type="primary", use_container_width=True):
                        ok, msg = op_venta(sheet, clave_sel, rack_sel, detalle, qty_v, precio, usuario)
                        if ok: _ok(msg); time.sleep(0.4); st.rerun()
                        else: _err(msg)

            elif accion.startswith("🚚"):
                with st.form("form_traslado"):
                    c_a, c_b, c_c = st.columns([1, 1.4, 1], vertical_alignment="bottom")
                    qty_t = c_a.number_input("Cantidad", min_value=1, max_value=stock_rack, value=1)
                    dest_ops = {k: v for k, v in SUCURSALES.items() if k != sheet}
                    dest = c_b.selectbox("Sucursal destino", list(dest_ops.keys()), format_func=lambda x: SUCURSALES[x])
                    if c_c.form_submit_button("🚚 Confirmar Traslado", type="primary", use_container_width=True):
                        ok, msg = op_send_transfer(sheet, clave_sel, rack_sel, qty_t, dest, usuario)
                        if ok: _ok(msg); time.sleep(0.4); st.rerun()
                        else: _err(msg)

            elif accion.startswith("📦"):
                with st.form("form_reubicacion"):
                    c_a, c_b, c_c = st.columns([1, 1.4, 1], vertical_alignment="bottom")
                    qty_r = c_a.number_input("Cantidad", min_value=1, max_value=stock_rack, value=1)
                    rack_dest_r = c_b.text_input("Rack destino", placeholder="Ej: PISO").strip()
                    if c_c.form_submit_button("📦 Confirmar", type="primary", use_container_width=True):
                        if not rack_dest_r: st.warning("⚠️ Indica el rack destino.")
                        else:
                            ok, msg = op_relocate(sheet, clave_sel, fila_stock["NOMBRE"], rack_sel, rack_dest_r, qty_r, usuario)
                            if ok: _ok(msg); time.sleep(0.4); st.rerun()
                            else: _err(msg)

# ═══════════════════════════════════════════════════════════════════════════
# MODULO 3: TRÁNSITOS
# ═══════════════════════════════════════════════════════════════════════════

def ui_logistics(sheet: str, usuario: str):
    nombre_suc = SUCURSALES.get(sheet, sheet)
    _page_header("🚚", f"Módulo de Logística y Tránsitos — {nombre_suc}", "Administración de mercancía inter-sucursal.")

    df_p = _get_df("Traslados_Pendientes")
    tab_recv, tab_sent = st.tabs(["📥 Recibir Pedidos / Traslados", "📤 Envíos Realizados Pendientes"])

    with tab_recv:
        recv = df_p[df_p["DESTINO"] == sheet].reset_index(drop=False)
        if recv.empty:
            st.info("📥 No tienes traslados pendientes por recibir.")
        else:
            display_r = recv.copy()
            display_r["ORIGEN"] = display_r["ORIGEN"].map(SUCURSALES).fillna(display_r["ORIGEN"])
            st.dataframe(display_r[["FECHA", "ORIGEN", "CLAVE", "NOMBRE", "CANTIDAD"]], use_container_width=True, hide_index=True, column_config=_logistics_column_config("ORIGEN"))

            _section("📥 Procesamiento Individual por Pieza / Rack")
            opts_r = recv.apply(lambda r: f"{r['CLAVE']} ({r['CANTIDAD']} pz) de {SUCURSALES.get(r['ORIGEN'], r['ORIGEN'])} [{r['FECHA']}]", axis=1).tolist()
            sel_r = st.selectbox("Selecciona la pieza a procesar:", opts_r)
            fila = recv.iloc[opts_r.index(sel_r)]

            clave_proc, nombre_proc, total_disp = fila["CLAVE"], fila["NOMBRE"], int(fila["CANTIDAD"])
            pending_row, origen_proc = int(fila["index"]) + 2, fila["ORIGEN"]

            tipo_proc = st.radio("Acción:", ["📥 Ingresar al Almacén (Asignar Racks)", "💥 Dar de baja inmediatamente (Siniestro/Venta)"], horizontal=True)

            if "Ingresar" in tipo_proc:
                st.caption("Procesa la cantidad deseada para cada rack (Ingresos parciales o totales).")
                c1, c2 = st.columns([1, 2])
                qty_rec = c1.number_input("Cantidad", min_value=1, max_value=total_disp, value=total_disp)
                rack_rec = c2.text_input("Rack destino", placeholder="Ej: RACK 3").strip()
                _rack_tag(rack_rec)

                if st.button("📥 Confirmar Ingreso", type="primary"):
                    if not rack_rec: st.warning("⚠️ Debes especificar un rack.")
                    else:
                        if qty_rec == total_disp:
                            ok, msg = op_receive_transfer(sheet, clave_proc, nombre_proc, qty_rec, rack_rec, pending_row, usuario)
                        else:
                            try:
                                ok, msg_alta = op_alta(sheet, clave_proc, nombre_proc, rack_rec, qty_rec, usuario)
                                if ok:
                                    _sheet("Traslados_Pendientes").update_cell(pending_row, 4, total_disp - qty_rec)
                                    msg = f"Ingreso parcial de {qty_rec} pz al {rack_rec}. Restan {total_disp - qty_rec}."
                                else: msg = msg_alta
                            except Exception as e: ok, msg = False, f"Error: {e}"

                        if ok: _ok(msg); _refresh("Traslados_Pendientes"); time.sleep(0.5); st.rerun()
                        else: _err(msg)

            else:
                st.caption("La pieza se dará de baja directamente sin tocar inventario físico.")
                with st.form("form_baja_inmediata"):
                    c1, c2, c3 = st.columns(3)
                    qty_baja = c1.number_input("Cantidad", min_value=1, max_value=total_disp, value=total_disp)
                    precio = c2.number_input("Precio Venta ($)", min_value=0.0, step=100.0)
                    costo = c3.number_input("Costo Pieza ($)", min_value=0.0, step=100.0)

                    c4, c5 = st.columns(2)
                    aseg = c4.text_input("Aseguradora")
                    deducible = c5.number_input("Deducible ($)", min_value=0.0, step=50.0)
                    nota = st.text_input("Observaciones (siniestro)")

                    detalle = f"Baja Inmediata ({SUCURSALES.get(origen_proc, origen_proc)}) — "
                    detalle += f"Asegurado: {aseg}" if aseg else "Público General"
                    if deducible > 0: detalle += f" | Deducible: ${deducible:.2f}"
                    if costo > 0: detalle += f" | Costo: ${costo:.2f}"
                    if nota: detalle += f" — {nota}"

                    if st.form_submit_button("💥 Confirmar Baja", type="primary", use_container_width=True):
                        try:
                            _log_movement(clave_proc, "Venta/Instalación", detalle, qty_baja, precio, usuario, sheet)
                            ws_p = _sheet("Traslados_Pendientes")
                            if qty_baja == total_disp:
                                ws_p.delete_rows(pending_row)
                                msg = f"Baja total confirmada."
                            else:
                                ws_p.update_cell(pending_row, 4, total_disp - qty_baja)
                                msg = f"Baja parcial de {qty_baja} pz."
                            _ok(msg); _refresh("Traslados_Pendientes"); _refresh("Movimientos"); time.sleep(0.5); st.rerun()
                        except Exception as e: _err(f"Error: {e}")

    with tab_sent:
        sent = df_p[df_p["ORIGEN"] == sheet].reset_index(drop=False)
        if sent.empty:
            st.info("📭 No tienes envíos pendientes.")
        else:
            display_s = sent.copy()
            display_s["DESTINO"] = display_s["DESTINO"].map(SUCURSALES).fillna(display_s["DESTINO"])
            st.dataframe(display_s[["FECHA", "DESTINO", "CLAVE", "NOMBRE", "CANTIDAD"]], use_container_width=True, hide_index=True, column_config=_logistics_column_config("DESTINO"))
            
            opts_c = sent.apply(lambda r: f"{r['CLAVE']} ({r['CANTIDAD']} pz) → {SUCURSALES.get(r['DESTINO'], r['DESTINO'])}", axis=1).tolist()
            fila_c = sent.iloc[opts_c.index(st.selectbox("Envío a cancelar:", opts_c))]

            with st.form("form_cancel"):
                rack_ret = st.text_input("Rack para regresar el material:", value="PISO").strip()
                if st.form_submit_button("❌ Ejecutar Cancelación", type="primary"):
                    ok, msg = op_cancel_transfer(sheet, fila_c, rack_ret, usuario)
                    if ok: _ok(msg); time.sleep(0.4); st.rerun()
                    else: _err(msg)

# ═══════════════════════════════════════════════════════════════════════════
# NUEVO MODULO: PEDIDOS (ALTA MASIVA)
# ═══════════════════════════════════════════════════════════════════════════

def ui_pedidos(sheet: str):
    usuario = st.session_state["_user"]
    nombre_suc = SUCURSALES.get(sheet, sheet)
    
    _page_header("📋", "Carga de Pedidos Múltiples", f"Alta masiva de cristales para {nombre_suc}")
    
    _section("Pega la lista de piezas")
    with st.container(border=True):
        st.markdown("**Formatos permitidos por línea:**")
        st.code("CLAVE\nCLAVE,CANTIDAD\nCLAVE,CANTIDAD,RACK_DESTINO")
        texto_pedido = st.text_area(
            "Lista de pedido:",
            placeholder="756\nFW2034,1\nDW1190,3,RACK 2\n1234,2,PEINE 1",
            height=250
        )
        
        c1, c2 = st.columns(2)
        tipo_comun = c1.selectbox("Tipo de pieza (por defecto)", TIPOS_PIEZA)
        rack_comun = c2.text_input("Rack común / Ubicación por defecto", value="PISO").strip()
        _rack_tag(rack_comun)
        
        procesar = st.button("🚀 Procesar Pedido Masivo", type="primary", use_container_width=True)
        
    if procesar:
        if not texto_pedido.strip():
            st.warning("⚠️ El cuadro de texto está vacío.")
            return
            
        lineas = [linea.strip() for linea in texto_pedido.split("\n") if linea.strip()]
        exitos = 0
        errores = 0
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for idx, linea in enumerate(lineas):
            try:
                status_text.caption(f"Procesando línea {idx+1}/{len(lineas)}: {linea}")
                
                # Extracción dinámica de 1, 2 o 3 parámetros (Clave, Cantidad, Rack)
                partes = [p.strip() for p in linea.split(",")]
                clave_raw = partes[0]
                cantidad = 1
                rack_item = rack_comun
                
                if len(partes) >= 2:
                    try: cantidad = int(partes[1])
                    except ValueError: cantidad = 1
                        
                if len(partes) >= 3:
                    rack_item = partes[2]
                
                if not clave_raw:
                    continue
                    
                ok, msg = op_alta(sheet, clave_raw, tipo_comun, rack_item, cantidad, usuario)
                if ok: exitos += 1
                else: errores += 1
            except Exception:
                errores += 1
            progress_bar.progress((idx + 1) / len(lineas))
            
        status_text.empty()
        if exitos > 0: _ok(f"✅ ¡Pedido procesado con éxito! {exitos} líneas registradas.")
        if errores > 0: _err(f"❌ Hubo problemas al procesar {errores} líneas.")
            
        time.sleep(1.0)
        st.rerun()

# ═══════════════════════════════════════════════════════════════════════════
# MEJORA 2: MÓDULO DE OPERACIÓN EXPRESS (COMPRA + INSTALACIÓN INMEDIATA)
# ═══════════════════════════════════════════════════════════════════════════

def ui_operacion_express(sheet: str, usuario: str):
    """
    Módulo de Operación Express: registra simultáneamente una ENTRADA y una
    SALIDA en la pestaña 'Historial' (Movimientos) sin tocar el Inventario.
    Se usa cuando se compra a un proveedor externo y se instala al cliente
    de inmediato, de modo que la pieza nunca toca el stock físico.
    """
    nombre_suc = SUCURSALES.get(sheet, sheet)
    _page_header(
        "⚡",
        "Operación Express",
        f"Compra inmediata a proveedor + instalación al cliente — {nombre_suc} · Sin alterar inventario físico",
    )

    st.info(
        "⚡ **¿Qué hace este módulo?** Registra DOS movimientos en la bitácora: "
        "una **ENTRADA** (compra al proveedor externo) y una **SALIDA** (instalación a la aseguradora/cliente). "
        "El stock de Inventario **no se modifica**.",
        icon="ℹ️",
    )

    _section("Datos de la Operación Express")

    with st.form("form_express", clear_on_submit=True):
        c1, c2, c3 = st.columns([1.5, 1, 1])
        clave_exp   = c1.text_input("Clave del Cristal *").upper().strip()
        cantidad_exp = c2.number_input("Cantidad *", min_value=1, max_value=999, value=1)
        sucursal_exp = c3.selectbox(
            "Sucursal *",
            list(SUCURSALES.keys()),
            index=list(SUCURSALES.keys()).index(sheet),
            format_func=lambda x: SUCURSALES[x],
        )

        c4, c5 = st.columns(2)
        proveedor_exp  = c4.text_input("Proveedor Externo *", placeholder="Ej: Cristales del Norte SA")
        aseguradora_exp = c5.text_input("Aseguradora / Cliente *", placeholder="Ej: GNP, AXA, Público General")

        notas_exp = st.text_input("Notas u observaciones (opcional)", placeholder="Ej: Vehículo siniestrado, urgente")

        st.markdown("---")
        submitted = st.form_submit_button("⚡ Registrar Operación Express", type="primary", use_container_width=True)

    if submitted:
        # Validaciones básicas
        if not clave_exp:
            _err("La clave del cristal es obligatoria.")
            return
        if not proveedor_exp.strip():
            _err("El nombre del Proveedor Externo es obligatorio.")
            return
        if not aseguradora_exp.strip():
            _err("La Aseguradora / Cliente es obligatoria.")
            return

        rack_virtual = "EXPRESS"
        fecha_op = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        suc_nombre = SUCURSALES.get(sucursal_exp, sucursal_exp)

        detalle_entrada = f"Compra Express — Proveedor: {proveedor_exp.strip()}"
        if notas_exp.strip():
            detalle_entrada += f" — Nota: {notas_exp.strip()}"

        detalle_salida = f"Instalación Express — Aseguradora/Cliente: {aseguradora_exp.strip()}"
        if notas_exp.strip():
            detalle_salida += f" — Nota: {notas_exp.strip()}"

        try:
            ws_historial = _sheet("Movimientos")

            # Fila 1 — ENTRADA (Compra al proveedor externo)
            ws_historial.append_row([
                fecha_op,
                _clean(clave_exp),
                "ENTRADA Express",
                detalle_entrada,
                cantidad_exp,
                0,           # Precio (se puede agregar en notas si es necesario)
                usuario,
                suc_nombre,
            ])

            # Fila 2 — SALIDA (Instalación a aseguradora/cliente)
            ws_historial.append_row([
                fecha_op,
                _clean(clave_exp),
                "SALIDA Express",
                detalle_salida,
                cantidad_exp,
                0,
                usuario,
                suc_nombre,
            ])

            _refresh("Movimientos")

            _ok(
                f"✅ Operación Express registrada: "
                f"**{cantidad_exp} pz** de **{_clean(clave_exp)}** — "
                f"Proveedor: {proveedor_exp.strip()} → "
                f"Cliente: {aseguradora_exp.strip()} · "
                f"El inventario físico no fue modificado."
            )
            time.sleep(0.5)
            st.rerun()

        except Exception as e:
            _err(f"Error al registrar la Operación Express: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# MODULO 4: AUDITORÍA 
# ═══════════════════════════════════════════════════════════════════════════

def ui_history(sheet: str):
    _page_header("📜", "Auditoría de Movimientos", "Historial estricto write-through indexado cronológicamente.")

    df = _get_df("Movimientos")
    if df.empty:
        st.info("No hay registros históricos en la bitácora global.")
        return

    _section("Filtros Avanzados de Auditoría")
    with st.container(border=True):
        c1, c2 = st.columns(2)
        tipos = ["Todos"] + sorted(df["TIPO"].unique().tolist() if "TIPO" in df.columns else [])
        sucs = ["Todas"] + sorted(df["SUCURSAL"].unique().tolist() if "SUCURSAL" in df.columns else [])
        ft = c1.selectbox("Tipo de movimiento:", tipos)
        fs = c2.selectbox("Sucursal:", sucs)

    df_v = df.copy()
    if "TIPO" in df.columns and ft != "Todos": df_v = df_v[df_v["TIPO"] == ft]
    if "SUCURSAL" in df.columns and fs != "Todas": df_v = df_v[df_v["SUCURSAL"] == fs]

    st.dataframe(df_v.iloc[::-1], use_container_width=True, hide_index=True, column_config=_history_column_config())

# ═══════════════════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA (ENRUTAMIENTO PRINCIPAL)
# ═══════════════════════════════════════════════════════════════════════════

def main():
    _inject_css()

    if not st.session_state.get("_logged", False):
        ui_login()
        return

    _init_session()
    active_sheet, section = ui_sidebar()
    user = st.session_state["_user"]
    rol = st.session_state["_rol"]

    # 🚨 CANDADO EN EL ENRUTADOR: Las vistas se muestran según los permisos del menú lateral
    if section == "dashboard":
        ui_dashboard(active_sheet, rol)
    elif section == "operaciones":
        ui_operations(active_sheet, user)
    elif section == "logistica":
        ui_logistics(active_sheet, user)
    elif section == "pedidos":       
        ui_pedidos(active_sheet)
    elif section == "express":                          # MEJORA 2: nueva ruta Express
        ui_operacion_express(active_sheet, user)
    elif section == "auditoria" and rol == "admin":
        ui_history(active_sheet)


if __name__ == "__main__":
    main()