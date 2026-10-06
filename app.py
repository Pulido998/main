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
    "Inventario_Suc5": "Sucursal 5",
}

# Las contraseñas se configuran en st.secrets["passwords"].
USUARIOS = {
    "admin": {"rol": "admin", "sucursal": None},
    **{f"sucursal{i}": {"rol": "user", "sucursal": f"Inventario_Suc{i}"} for i in range(1,6)},
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
