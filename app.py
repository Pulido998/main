"""
╔══════════════════════════════════════════════════════════════════════════╗
║         GLASS MASTER INVENTARIO — (UI REDESIGN + DINÁMICO RACKS)         ║
║         Escrituras atómicas y serializadas mediante Apps Script          ║
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
import uuid
from pathlib import Path
from html import escape
from gac_client import InventoryClient, ServiceUnavailable
from datetime import datetime

import pandas as pd
import streamlit as st
from PIL import Image

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN GLOBAL Y BRANDING
# ═══════════════════════════════════════════════════════════════════════════

LOGO = Image.open(Path(__file__).with_name("logo.png")) if Path(__file__).with_name("logo.png").exists() else "📦"

try:
    with open(Path(__file__).with_name("logo.png"), "rb") as f:
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

# Las contraseñas se configuran en st.secrets["passwords"].
USUARIOS = {
    "admin": {"rol": "admin", "sucursal": None},
    **{f"sucursal{i}": {"rol": "user", "sucursal": f"Inventario_Suc{i}"} for i in range(1,5)},
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
    return " ".join(str(text or "").strip().upper().split())

def _normalize_rack(raw) -> str:
    t = _clean(raw)
    if t in ("", "RACK", "SIN RACK", "SIN ASIGNAR", "RACK SIN RACK", "RACK SIN ASIGNAR"):
        return "RACK SIN ASIGNAR"
    t = re.sub(r"^RACK\s*", "", t).strip()
    if re.fullmatch(r"[0-9]+", t): t = str(int(t))
    return "RACK " + t

INV_COLUMNS = ["CLAVE", "NOMBRE", "RACK", "CANTIDAD", "FECHA"]
PENDING_COLUMNS = ["FECHA", "CLAVE", "NOMBRE", "CANTIDAD", "ORIGEN", "DESTINO", "ID_TRASLADO", "RACK_ORIGEN"]
MOV_COLUMNS = ["FECHA", "CLAVE", "TIPO", "DETALLE", "CANTIDAD", "PRECIO", "USUARIO", "SUCURSAL", "ID_OPERACION", "ID_TRASLADO"]

def _client():
    return InventoryClient(st.secrets["inventory_api"]["url"], st.secrets["inventory_api"]["token"])

def _columns(name):
    return INV_COLUMNS if name in SUCURSALES else PENDING_COLUMNS if name == "Traslados_Pendientes" else MOV_COLUMNS

def _refresh_all():
    result = _client().snapshot(st.session_state["_user"])
    # Actualizar la vista solo cuando llegó la instantánea completa.
    frames = {f"df_{n}": pd.DataFrame(result.get(n, []), columns=_columns(n))
              for n in list(SUCURSALES) + ["Movimientos", "Traslados_Pendientes"]}
    st.session_state.update(frames)
    st.session_state["_data_loaded"] = True
    st.session_state["_loaded_at"] = time.monotonic()

def _init_session():
    if not st.session_state.get("_data_loaded") or time.monotonic() - st.session_state.get("_loaded_at", 0) > 30:
        try:
            with st.spinner("⏳ Sincronizando inventario…"): _refresh_all()
        except Exception as exc:
            st.error(f"No se pudo actualizar la vista: {exc}")
            st.stop()

def _refresh(sheet_name):
    _refresh_all()

def _get_df(name):
    return st.session_state.get(f"df_{name}", pd.DataFrame(columns=_columns(name))).copy()

def _get_df_stock(name):
    df = _get_df(name)
    return df[df["CANTIDAD"] > 0].copy()

def _search_keys(df, term):
    if df.empty or not term: return []
    pool = df[df["CANTIDAD"] > 0]
    return sorted(pool.loc[pool["CLAVE"].str.contains(_clean(term), case=False, na=False, regex=False), "CLAVE"].unique().tolist())

def _submit_command(command):
    # El mismo ID y contenido se conservan incluso si se pierde la respuesta.
    try:
        client = _client()
    except Exception:
        return False, "Revisa inventory_api.url e inventory_api.token en los secretos de Streamlit."
    st.session_state["_pending_operation"] = command
    try:
        result = client.execute(command)
    except ServiceUnavailable as exc:
        return False, f"No se confirmó el resultado: {exc}. ID: {command['id']}. Usa Reintentar operación pendiente."
    if result.get("ok"):
        st.session_state.pop("_pending_operation", None)
        st.session_state["_completed_operation"] = result
        st.session_state["_data_loaded"] = False
        return True, result["message"]
    if result.get("code") in {"VALIDACION", "PERMISO", "ID_REUTILIZADO", "AUTH", "CONFIGURACION", "FORMATO"}:
        st.session_state.pop("_pending_operation", None)
    return False, result.get("message", "No se pudo confirmar la operación.")

def _operate(action, branch, data, user):
    if not st.session_state.get("_logged") or user != st.session_state.get("_user"):
        return False, "La sesión no está autorizada."
    if st.session_state.get("_pending_operation"):
        return False, "Primero confirma la operación pendiente usando su mismo identificador."
    if st.session_state.get("_completed_operation"):
        return False, "La operación anterior ya está registrada. Pulsa Registrar otra operación."
    command = {"id": uuid.uuid4().hex, "action": action, "branch": branch, "user": user, "payload": data}
    return _submit_command(command)

def op_alta(sheet, clave, nombre, rack_raw, qty, usuario):
    return _operate("alta", sheet, {"key":clave,"name":nombre,"rack":rack_raw,"qty":qty}, usuario)

def op_venta(sheet, clave, rack, detalle, qty, precio, usuario):
    return _operate("venta", sheet, {"key":clave,"rack":rack,"detail":detalle,"qty":qty,"price":precio}, usuario)

def op_send_transfer(sheet_origin, clave, rack, qty, dest_sheet, usuario):
    return _operate("send", sheet_origin, {"key":clave,"rack":rack,"qty":qty,"destination":dest_sheet}, usuario)

def op_receive_transfer(dest_sheet, transfer_id, qty, rack_raw, usuario):
    return _operate("receive", dest_sheet, {"transfer_id":transfer_id,"qty":qty,"rack":rack_raw}, usuario)

def op_cancel_transfer(origin_sheet, item, rack_return_raw, usuario):
    return _operate("cancel", origin_sheet, {"transfer_id":item["ID_TRASLADO"],"rack":rack_return_raw}, usuario)

def op_relocate(sheet, clave, nombre, rack_origin_raw, rack_dest_raw, qty, usuario):
    return _operate("relocate", sheet, {"key":clave,"rack":rack_origin_raw,"destination_rack":rack_dest_raw,"qty":qty}, usuario)

def op_clean_duplicates(sheet):
    return _operate("clean", sheet, {}, st.session_state["_user"])

def op_direct_sale(sheet, transfer_id, qty, detail, price, usuario):
    return _operate("direct_sale", sheet, {"transfer_id":transfer_id,"qty":qty,"detail":detail,"price":price}, usuario)

def op_order(sheet, text, name, rack, usuario):
    return _operate("order", sheet, {"text":text,"name":name,"rack":rack}, usuario)

def _operation_status():
    pending = st.session_state.get("_pending_operation")
    completed = st.session_state.get("_completed_operation")
    if pending:
        st.warning(f"Operación pendiente de confirmar. ID: {pending['id']}. No vuelvas a capturarla como nueva.")
        if st.button("Reintentar operación pendiente", type="primary"):
            ok, msg = _submit_command(pending)
            if ok: st.rerun()
            else: st.error(msg)
        return True
    if completed:
        st.success(completed["message"])
        st.caption(f"Comprobante: {completed['id']}")
        if st.button("Registrar otra operación", type="primary"):
            st.session_state.pop("_completed_operation", None)
            st.rerun()
        return True
    return False

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

def _ok(msg): st.markdown(f'<div class="toast-success">✓ {escape(str(msg))}</div>', unsafe_allow_html=True)
def _err(msg): st.markdown(f'<div class="toast-error">✗ {escape(str(msg))}</div>', unsafe_allow_html=True)

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
                if data and password and st.secrets.get("passwords", {}).get(usuario) == password:
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

        st.markdown(f'<div class="sb-user-chip"><div><div class="sb-user-name">👤 {user}</div><div class="sb-user-rol" style="color:{C_BLUE_LT if rol == "admin" else C_GREEN}">{rol}</div></div></div>', unsafe_allow_html=True)
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
        if st.button("🔄 Actualizar datos", use_container_width=True):
            st.session_state["_data_loaded"] = False
            st.rerun()
        if st.button("🚪 Cerrar Sesión", use_container_width=True, disabled=bool(st.session_state.get("_pending_operation"))):
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
            st.warning(f"Suma cantidades de filas con la misma clave y rack en {nombre_suc}. Conserva el total registrado; no determina si el stock físico es correcto.")
            if st.button("▶️ Ejecutar Limpieza", type="primary", disabled=bool(st.session_state.get("_completed_operation") or st.session_state.get("_pending_operation"))):
                ok, msg = op_clean_duplicates(sheet)
                _ok(msg) if ok else _err(msg)
                if ok: st.rerun()

    if df_all.empty:
        st.info("No hay productos registrados en esta sucursal.")
        return

    _section("📋 Inventario Total (Con y Sin Existencia)")
    with st.container(border=True):
        filtro = st.text_input("Buscar en inventario:", placeholder="Ej: 75, FW, Rack...", key="wh_filter").strip().upper()
        df_view = df_all.copy()
        if filtro:
            mask = df_view.astype(str).apply(lambda col: col.str.contains(filtro, case=False, na=False, regex=False)).any(axis=1)
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
        
        # ═══════════════════════════════════════════════════════════════════════════
        # MEJORA: BUSCADOR PREDICTIVO EN TIEMPO REAL (RECOMENDACIONES)
        # ═══════════════════════════════════════════════════════════════════════════
        clave_sug = st.text_input("🔍 Escribe para ver recomendaciones de piezas similares / ubicaciones (Ej: 756):", key="alta_live_suggest").strip().upper()
        if clave_sug and len(clave_sug) >= 2:
            df_all_inv = _get_df(sheet)
            if not df_all_inv.empty and "CLAVE" in df_all_inv.columns:
                coincidencias = df_all_inv[df_all_inv["CLAVE"].str.contains(clave_sug, case=False, na=False, regex=False)]
                if not coincidencias.empty:
                    with st.expander(f"💡 Sugerencias y Racks encontrados en el sistema para '{clave_sug}':", expanded=True):
                        for _, r in coincidencias.head(6).iterrows():
                            st.markdown(f"• Pieza: **{r['CLAVE']}** ({r['NOMBRE']}) | Ubicación actual: `{r['RACK']}` | Stock: **{r['CANTIDAD']} pz**")
                else:
                    st.caption("No se encontraron piezas parecidas guardadas aún.")

        with st.form("form_alta", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns([1.5, 1, 1, 0.8])
            # Se pre-llena con lo escrito en el buscador para agilizar el proceso
            clave_in = c1.text_input("Clave del Cristal", value=clave_sug).upper().strip()
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
            opts_r = recv.apply(lambda r: f"{r['CLAVE']} ({r['CANTIDAD']} pz) de {SUCURSALES.get(r['ORIGEN'], r['ORIGEN'])} [{r['FECHA']}] · {r['ID_TRASLADO'][-8:]}", axis=1).tolist()
            ids_r = recv["ID_TRASLADO"].tolist()
            labels_r = dict(zip(ids_r, opts_r))
            sel_r = st.selectbox("Selecciona la pieza a procesar:", ids_r, format_func=labels_r.__getitem__)
            fila = recv.loc[recv["ID_TRASLADO"] == sel_r].iloc[0]

            clave_proc, nombre_proc, total_disp = fila["CLAVE"], fila["NOMBRE"], int(fila["CANTIDAD"])
            transfer_id, origen_proc = fila["ID_TRASLADO"], fila["ORIGEN"]

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
                        ok, msg = op_receive_transfer(sheet, transfer_id, qty_rec, rack_rec, usuario)

                        if ok: _ok(msg); st.rerun()
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
                        ok, msg = op_direct_sale(sheet, transfer_id, qty_baja, detalle, precio, usuario)
                        if ok: _ok(msg); st.rerun()
                        else: _err(msg)


    with tab_sent:
        sent = df_p[df_p["ORIGEN"] == sheet].reset_index(drop=False)
        if sent.empty:
            st.info("📭 No tienes envíos pendientes.")
        else:
            display_s = sent.copy()
            display_s["DESTINO"] = display_s["DESTINO"].map(SUCURSALES).fillna(display_s["DESTINO"])
            st.dataframe(display_s[["FECHA", "DESTINO", "CLAVE", "NOMBRE", "CANTIDAD"]], use_container_width=True, hide_index=True, column_config=_logistics_column_config("DESTINO"))
            
            opts_c = sent.apply(lambda r: f"{r['CLAVE']} ({r['CANTIDAD']} pz) → {SUCURSALES.get(r['DESTINO'], r['DESTINO'])} · {r['ID_TRASLADO'][-8:]}", axis=1).tolist()
            ids_c = sent["ID_TRASLADO"].tolist()
            labels_c = dict(zip(ids_c, opts_c))
            selected_id = st.selectbox("Envío a cancelar:", ids_c, format_func=labels_c.__getitem__)
            fila_c = sent.loc[sent["ID_TRASLADO"] == selected_id].iloc[0]

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
            
        ok, msg = op_order(sheet, texto_pedido, tipo_comun, rack_comun, usuario)
        if ok: _ok(msg); st.rerun()
        else: _err(msg)


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

    blocked = _operation_status()
    _init_session()
    active_sheet, section = ui_sidebar()
    if blocked and section in ("operaciones", "logistica", "pedidos"):
        return
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
    elif section == "auditoria" and rol == "admin":
        ui_history(active_sheet)


if __name__ == "__main__":
    main()
