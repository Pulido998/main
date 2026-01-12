import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
import time

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Inventario Cristales", layout="wide")

# --- CONEXIÓN A GOOGLE SHEETS (MODO STREAMLIT CLOUD) ---
try:
    # Definimos los permisos necesarios
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # Recuperamos las credenciales desde los "Secrets" de Streamlit
    # Esto busca una sección llamada [gcp_service_account] en la configuración de la nube
    credentials_dict = st.secrets["gcp_service_account"]
    
    # Creamos la credencial
    creds = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
    gc = gspread.authorize(creds)
    
    # Abrimos el archivo de Google Sheets
    sh = gc.open('Inventario_Cristales') 
    
    # Cargamos las hojas
    hojas = {
        "Inventario_Suc1": sh.worksheet('Inventario_Suc1'),
        "Inventario_Suc2": sh.worksheet('Inventario_Suc2'),
        "Inventario_Suc3": sh.worksheet('Inventario_Suc3'),
        "Movimientos": sh.worksheet('Movimientos'),
        "Traslados_Pendientes": sh.worksheet('Traslados_Pendientes')
    }
except Exception as e:
    st.error(f"⚠️ Error de conexión: {e}")
    st.info("Nota: Si estás viendo esto en Streamlit Cloud, verifica que hayas configurado los 'Secrets' correctamente.")
    st.stop()

# --- USUARIOS (Igual que antes) ---
credenciales = {
    "admin":      {"pass": "1234",      "rol": "admin", "sucursal": "todas"},
    "sucursal1":  {"pass": "suc1",      "rol": "user",  "sucursal": "Inventario_Suc1"},
    "sucursal2":  {"pass": "suc2",      "rol": "user",  "sucursal": "Inventario_Suc2"},
    "sucursal3":  {"pass": "suc3",      "rol": "user",  "sucursal": "Inventario_Suc3"}
}

# --- FUNCIONES DE LÓGICA (Con corrección de números) ---

def guardar_entrada(ws_destino, clave, nombre, rack, cantidad, usuario):
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        clave = str(clave).upper().strip()
        rack = str(rack).upper().strip()
        cantidad = int(cantidad) # Forzar entero de Python
        
        try:
            data = ws_destino.get_all_records()
            df = pd.DataFrame(data)
        except:
            return False, "Error al leer la hoja destino. ¿Tiene encabezados?"

        if not df.empty and clave in df['CLAVE'].astype(str).values:
            cell = ws_destino.find(clave)
            valor_actual = ws_destino.cell(cell.row, 4).value
            # Limpieza del valor actual
            if valor_actual and str(valor_actual).replace('.', '', 1).isdigit():
                cant_actual = int(float(valor_actual))
            else:
                cant_actual = 0
            
            nueva_cant = cant_actual + cantidad
            ws_destino.update_cell(cell.row, 4, nueva_cant)
            ws_destino.update_cell(cell.row, 5, fecha)
            return True, f"✅ Recibido y sumado. Total: {nueva_cant}"
        else:
            ws_destino.append_row([clave, nombre, rack, cantidad, fecha])
            return True, f"✅ Nuevo registro creado en inventario."
            
    except Exception as e:
        return False, f"Error técnico en guardar: {e}"

def iniciar_traslado(ws_origen, clave, cantidad, suc_destino, usuario):
    try:
        clave = str(clave).upper().strip()
        cantidad = int(cantidad)
        
        try:
            cell = ws_origen.find(clave)
            cant_actual = int(ws_origen.cell(cell.row, 4).value)
        except:
            return False, "❌ La clave no existe en tu inventario."

        if cant_actual < cantidad:
            return False, f"❌ Stock insuficiente. Tienes: {cant_actual}"

        row_values = ws_origen.row_values(cell.row)
        nombre_prod = row_values[1] 

        nueva_cant = cant_actual - cantidad
        ws_origen.update_cell(cell.row, 4, nueva_cant)
        
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        hojas['Traslados_Pendientes'].append_row([fecha, clave, nombre_prod, cantidad, ws_origen.title, suc_destino])
        hojas['Movimientos'].append_row([fecha, clave, "Envío Traslado", f"Enviado a {suc_destino}", cantidad, 0, usuario, ws_origen.title])

        return True, f"✅ Enviado a tránsito. Quedan {nueva_cant}."
    except Exception as e:
        return False, f"Error: {e}"

def procesar_baja_venta(ws_origen, clave, detalle, cantidad, precio, usuario):
    try:
        clave = str(clave).upper().strip()
        cantidad = int(cantidad)
        
        cell = ws_origen.find(clave)
        cant_actual = int(ws_origen.cell(cell.row, 4).value)
        
        if cant_actual < cantidad:
            return False, f"❌ Stock insuficiente."
        
        nueva_cant = cant_actual - cantidad
        ws_origen.update_cell(cell.row, 4, nueva_cant)
        
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        hojas['Movimientos'].append_row([fecha, clave, "Venta/Instalación", detalle, cantidad, precio, usuario, ws_origen.title])
        
        return True, f"✅ Venta registrada. Quedan {nueva_cant}."
    except:
        return False, "❌ Clave no encontrada."

def finalizar_recepcion(suc_destino_nombre, clave, nombre, cantidad, rack, usuario, fila_traslado):
    try:
        cantidad = int(cantidad)
        fila_traslado = int(fila_traslado)
        
        ws_local = hojas[suc_destino_nombre]
        ok, msg = guardar_entrada(ws_local, clave, nombre, rack, cantidad, usuario)
        
        if ok:
            hojas['Traslados_Pendientes'].delete_rows(fila_traslado)
            fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            hojas['Movimientos'].append_row([fecha, clave, "Recepción Traslado", "Recibido en sucursal", cantidad, 0, usuario, suc_destino_nombre])
            return True, msg
        else:
            return False, f"Fallo al guardar: {msg}"
    except Exception as e:
        return False, f"Error crítico: {e}"

# --- LOGIN ---
if 'logueado' not in st.session_state:
    st.session_state.logueado = False

if not st.session_state.logueado:
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.title("🔐 SISTEMA CRISTALES")
        u = st.text_input("Usuario")
        p = st.text_input("Contraseña", type="password")
        if st.button("ENTRAR", type="primary"):
            if u in credenciales and credenciales[u]["pass"] == p:
                st.session_state.logueado = True
                st.session_state.user_data = {"user": u, **credenciales[u]}
                st.rerun()
            else:
                st.error("Datos incorrectos")
    st.stop()

# --- INTERFAZ PRINCIPAL ---
usuario = st.session_state.user_data["user"]
rol = st.session_state.user_data["rol"]
sucursal_asignada = st.session_state.user_data["sucursal"]

with st.sidebar:
    st.header(f"🏢 {sucursal_asignada.replace('Inventario_','').upper()}")
    st.caption(f"Usuario: {usuario}")
    if st.button("Cerrar Sesión"):
        st.session_state.logueado = False
        st.rerun()
    menu = st.radio("Menú", ["📦 Operaciones", "🚚 Traslados en Camino", "👀 Rack Visual"])

# Definir hoja activa
if rol == "admin":
    opciones_suc = ["Inventario_Suc1", "Inventario_Suc2", "Inventario_Suc3"]
    sucursal_visualizada = st.selectbox("Vista Admin - Inventario:", opciones_suc)
    ws_activo = hojas[sucursal_visualizada]
else:
    sucursal_visualizada = sucursal_asignada
    ws_activo = hojas[sucursal_asignada]

# PESTAÑA 1: OPERACIONES
if menu == "📦 Operaciones":
    st.title("Operaciones de Inventario")

    with st.expander("➕ ALTA (Compra/Material Nuevo)", expanded=False):
        with st.form("form_alta", clear_on_submit=True):
            col1, col2 = st.columns(2)
            c_clave = col1.text_input("Clave")
            c_pieza = col2.selectbox("Pieza", ["Parabrisas", "Medallón", "Puerta", "Aleta", "Costado"])
            c_rack = col1.text_input("Ubicación / Rack", "PISO")
            c_cant = col2.number_input("Cantidad", 1, 100, 1)
            if st.form_submit_button("💾 Guardar"):
                if c_clave:
                    ok, txt = guardar_entrada(ws_activo, c_clave, c_pieza, c_rack, c_cant, usuario)
                    if ok: st.success(txt)
                    else: st.error(txt)
                else: st.warning("Falta clave.")

    with st.expander("➖ BAJA (Venta) o ENVÍO (Traslado)", expanded=True):
        st.write("**¿Qué deseas hacer?**")
        tipo_op = st.radio("Tipo:", ["Venta / Instalación", "Enviar a otra Sucursal"], horizontal=True, label_visibility="collapsed")
        st.divider()
        with st.form("form_baja", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            b_clave = col_a.text_input("Clave")
            b_cant = col_b.number_input("Cantidad", 1, 50, 1)
            ok = False
            msg = ""
            if tipo_op == "Venta / Instalación":
                col_c, col_d = st.columns(2)
                aseg = col_c.selectbox("Cliente:", ["Público General", "ANA", "GNP", "Zurich", "Qualitas", "CHUBB"])
                nota = st.text_input("Nota adicional:")
                prec = col_d.number_input("Precio $", 0.0)
                detalle = f"{aseg} - {nota}" if nota else aseg
                if st.form_submit_button("💰 Confirmar Venta", type="primary"):
                    if b_clave:
                        ok, msg = procesar_baja_venta(ws_activo, b_clave, detalle, b_cant, prec, usuario)
                    else: st.warning("Falta clave.")
            else: 
                st.info("⚠️ La pieza saldrá de tu inventario y quedará 'En Camino'.")
                todas = ["Inventario_Suc1", "Inventario_Suc2", "Inventario_Suc3"]
                otras = [s for s in todas if s != sucursal_visualizada]
                destino = st.selectbox("Enviar a:", otras)
                if st.form_submit_button("🚚 Enviar Traslado", type="primary"):
                    if b_clave:
                        ok, msg = iniciar_traslado(ws_activo, b_clave, b_cant, destino, usuario)
                    else: st.warning("Falta clave.")
            if ok: st.success(msg)
            elif msg: st.error(msg)

    st.divider()
    df = pd.DataFrame(ws_activo.get_all_records())
    if not df.empty:
        st.dataframe(df, use_container_width=True, height=300)

# PESTAÑA 2: TRASLADOS
elif menu == "🚚 Traslados en Camino":
    st.title("Gestión de Traslados")
    if st.button("🔄 Actualizar Lista"): st.rerun()
    
    try:
        data_pend = hojas['Traslados_Pendientes'].get_all_records()
        df_p = pd.DataFrame(data_pend)
    except:
        df_p = pd.DataFrame()

    if df_p.empty or 'DESTINO' not in df_p.columns:
        df_p = pd.DataFrame(columns=['FECHA', 'CLAVE', 'NOMBRE', 'CANTIDAD', 'ORIGEN', 'DESTINO'])

    if df_p.empty:
        st.info("No hay traslados en curso.")
    else:
        tab_recibir, tab_enviados = st.tabs(["📥 POR RECIBIR", "📤 ENVIADOS"])
        with tab_recibir:
            mis_llegadas = df_p[df_p['DESTINO'] == sucursal_visualizada].reset_index()
            if mis_llegadas.empty:
                st.success("✅ No tienes envíos pendientes.")
            else:
                st.warning(f"Tienes {len(mis_llegadas)} envíos esperando recepción.")
                st.dataframe(mis_llegadas[['FECHA','ORIGEN','CLAVE','NOMBRE','CANTIDAD']], use_container_width=True)
                st.divider()
                st.subheader("📦 Procesar Recepción")
                opciones = mis_llegadas.apply(lambda x: f"{x['CLAVE']} - {x['NOMBRE']} (Cant: {x['CANTIDAD']})", axis=1).tolist()
                seleccion = st.selectbox("Selecciona:", opciones)
                if seleccion:
                    idx = opciones.index(seleccion)
                    fila = mis_llegadas.iloc[idx]
                    with st.form("form_recibir"):
                        st.write(f"Ingresando: **{fila['CLAVE']}**")
                        rack_in = st.text_input("📍 Ubicación / Rack")
                        if st.form_submit_button("✅ CONFIRMAR"):
                            if rack_in:
                                ok, m = finalizar_recepcion(sucursal_visualizada, fila['CLAVE'], fila['NOMBRE'], fila['CANTIDAD'], rack_in, usuario, int(fila['index'])+2)
                                if ok: 
                                    st.success(m)
                                    time.sleep(2)
                                    st.rerun()
                                else: st.error(m)
                            else: st.warning("Escribe el Rack.")
        with tab_enviados:
            mis_envios = df_p[df_p['ORIGEN'] == sucursal_visualizada]
            st.dataframe(mis_envios[['FECHA','DESTINO','CLAVE','CANTIDAD']], use_container_width=True)

# PESTAÑA 3: RACK
elif menu == "👀 Rack Visual":
    st.title(f"Visor - {sucursal_visualizada}")
    if st.button("🔄 Refrescar"): st.rerun()
    df = pd.DataFrame(ws_activo.get_all_records())
    if not df.empty and 'RACK' in df.columns:
        df['RACK'] = df['RACK'].astype(str).str.upper().str.strip()
        racks = sorted(df['RACK'].unique().tolist())
        sel = st.radio("Rack:", racks, horizontal=True)
        st.dataframe(df[df['RACK'] == sel][['CLAVE','NOMBRE','CANTIDAD']], use_container_width=True)
    else:
        st.warning("Sin datos de Rack.")