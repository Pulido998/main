import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
import time

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Inventario Cristales", layout="wide")

# --- CONEXIÓN A GOOGLE SHEETS ---
try:
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    credentials_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open('Inventario_Cristales') 
    
    hojas = {
        "Inventario_Suc1": sh.worksheet('Inventario_Suc1'),
        "Inventario_Suc2": sh.worksheet('Inventario_Suc2'),
        "Inventario_Suc3": sh.worksheet('Inventario_Suc3'),
        "Movimientos": sh.worksheet('Movimientos'),
        "Traslados_Pendientes": sh.worksheet('Traslados_Pendientes')
    }
except Exception as e:
    st.error(f"⚠️ Error de conexión: {e}")
    st.stop()

# --- USUARIOS ---
credenciales = {
    "admin":      {"pass": "Xk9#mZ21!",     "rol": "admin", "sucursal": "todas"},
    "sucursal1":  {"pass": "Suc1_Ax7$",     "rol": "user",  "sucursal": "Inventario_Suc1"},
    "sucursal2":  {"pass": "Br4nch_Two!",   "rol": "user",  "sucursal": "Inventario_Suc2"},
    "sucursal3":  {"pass": "T3rcera_P0s#",  "rol": "user",  "sucursal": "Inventario_Suc3"}
}

# --- FUNCIONES DE LÓGICA CON REINTENTOS Y CORRECCIÓN DE DUPLICADOS ---

def ejecutar_con_reintentos(func, *args):
    """
    Intenta ejecutar una función de Google Sheets hasta 3 veces
    si falla por tráfico o bloqueo.
    """
    intentos = 3
    for i in range(intentos):
        try:
            return func(*args)
        except Exception as e:
            if i < intentos - 1:
                time.sleep(2) # Espera 2 segundos antes de reintentar
                continue
            else:
                raise e

def obtener_fila_exacta(ws, clave, rack):
    """
    Busca la fila exacta.
    MEJORA: Si hay duplicados, prioriza la fila que tenga MAYOR cantidad (stock positivo).
    """
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    clave = str(clave).upper().strip()
    rack = str(rack).upper().strip()
    
    # Manejo seguro de columnas vacías
    if df.empty or 'CLAVE' not in df.columns or 'RACK' not in df.columns:
        return None, 0

    df['CLAVE'] = df['CLAVE'].astype(str).str.upper().str.strip()
    df['RACK'] = df['RACK'].astype(str).str.upper().str.strip()
    
    # Aseguramos que CANTIDAD sea número para poder ordenar
    if 'CANTIDAD' in df.columns:
        df['CANTIDAD'] = pd.to_numeric(df['CANTIDAD'], errors='coerce').fillna(0)
    
    filtro = df[(df['CLAVE'] == clave) & (df['RACK'] == rack)]
    
    if not filtro.empty:
        # AQUÍ ESTÁ EL TRUCO: Ordenamos descendente por cantidad.
        # Si hay una fila con 0 y otra con 1, la del 1 queda primero (index 0).
        filtro = filtro.sort_values(by='CANTIDAD', ascending=False)
        
        # Retornamos el índice original de esa fila prioritaria
        return filtro.index[0] + 2, int(filtro.iloc[0]['CANTIDAD'])
        
    return None, 0

def guardar_entrada(ws_destino, clave, nombre, rack, cantidad, usuario):
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def _accion():
        clave_str = str(clave).upper().strip()
        rack_str = str(rack).upper().strip()
        cant_int = int(cantidad)
        
        fila, cant_actual = obtener_fila_exacta(ws_destino, clave_str, rack_str)

        if fila:
            nueva_cant = cant_actual + cant_int
            ws_destino.update_cell(fila, 4, nueva_cant)
            ws_destino.update_cell(fila, 5, fecha)
            return True, f"✅ Recibido en Rack {rack_str}. Total: {nueva_cant}"
        else:
            ws_destino.append_row([clave_str, nombre, rack_str, cant_int, fecha])
            return True, f"✅ Nuevo registro creado en Rack {rack_str}."

    try:
        return ejecutar_con_reintentos(_accion)
    except Exception as e:
        return False, f"Error (Red saturada): {e}"

def iniciar_traslado(ws_origen, clave, rack, cantidad, suc_destino, usuario):
    def _accion():
        clave_str = str(clave).upper().strip()
        rack_str = str(rack).upper().strip()
        cant_int = int(cantidad)
        
        fila, cant_actual = obtener_fila_exacta(ws_origen, clave_str, rack_str)
        
        if not fila:
            return False, f"❌ No se encontró la clave {clave_str} en el rack {rack_str}."

        if cant_actual < cant_int:
            return False, f"❌ Stock insuficiente en Rack {rack_str}. Tienes: {cant_actual}"

        nombre_prod = ws_origen.cell(fila, 2).value 
        nueva_cant = cant_actual - cant_int
        ws_origen.update_cell(fila, 4, nueva_cant)
        
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        hojas['Traslados_Pendientes'].append_row([fecha, clave_str, nombre_prod, cant_int, ws_origen.title, suc_destino])
        hojas['Movimientos'].append_row([fecha, clave_str, "Envío Traslado", f"Desde {rack_str} a {suc_destino}", cant_int, 0, usuario, ws_origen.title])

        return True, f"✅ Enviado a tránsito. Quedan {nueva_cant} en {rack_str}."

    try:
        return ejecutar_con_reintentos(_accion)
    except Exception as e:
        return False, f"Error (Red saturada): {e}"

def procesar_baja_venta(ws_origen, clave, rack, detalle, cantidad, precio, usuario):
    def _accion():
        clave_str = str(clave).upper().strip()
        rack_str = str(rack).upper().strip()
        cant_int = int(cantidad)
        
        fila, cant_actual = obtener_fila_exacta(ws_origen, clave_str, rack_str)
        
        if not fila:
            return False, f"❌ No se encontró la clave {clave_str} en el rack {rack_str}."
        
        if cant_actual < cant_int:
            return False, f"❌ Stock insuficiente en {rack_str}. Tienes: {cant_actual}"
        
        nueva_cant = cant_actual - cant_int
        ws_origen.update_cell(fila, 4, nueva_cant)
        
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        hojas['Movimientos'].append_row([fecha, clave_str, "Venta/Instalación", f"{detalle} (Desde {rack_str})", cant_int, precio, usuario, ws_origen.title])
        
        return True, f"✅ Venta registrada desde {rack_str}. Quedan {nueva_cant}."

    try:
        return ejecutar_con_reintentos(_accion)
    except Exception as e:
        return False, f"Error (Red saturada): {e}"

def finalizar_recepcion(suc_destino_nombre, clave, nombre, cantidad, rack, usuario, fila_traslado):
    def _accion():
        cant_int = int(cantidad)
        fila_t_int = int(fila_traslado)
        
        ws_local = hojas[suc_destino_nombre]
        
        # Guardamos usando la lógica interna
        ok, msg = guardar_entrada(ws_local, clave, nombre, rack, cant_int, usuario)
        
        if ok:
            hojas['Traslados_Pendientes'].delete_rows(fila_t_int)
            fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            hojas['Movimientos'].append_row([fecha, clave, "Recepción Traslado", "Recibido en sucursal", cant_int, 0, usuario, suc_destino_nombre])
            return True, msg
        else:
            return False, f"Fallo al guardar: {msg}"

    try:
        return ejecutar_con_reintentos(_accion)
    except Exception as e:
        return False, f"Error (Red saturada): {e}"

# --- LOGIN ---
if 'logueado' not in st.session_state:
    st.session_state.logueado = False

if not st.session_state.logueado:
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.title("🔐 SISTEMA CRISTALES")
        st.markdown("---")
        u = st.text_input("Usuario").strip() 
        p = st.text_input("Contraseña", type="password").strip()
        if st.button("ENTRAR", type="primary"):
            if u in credenciales and credenciales[u]["pass"] == p:
                st.session_state.logueado = True
                st.session_state.user_data = {"user": u, **credenciales[u]}
                st.rerun()
            else:
                st.error("Datos incorrectos")
        st.markdown("---")
    st.stop()

# --- INTERFAZ PRINCIPAL ---

# Bloque de seguridad para sesión
if "user_data" not in st.session_state:
    st.session_state.logueado = False
    st.rerun()

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

# Obtener Dataframe Global
try:
    df_inventario = pd.DataFrame(ws_activo.get_all_records())
except:
    st.error("⚠️ La hoja está ocupada. Espera unos segundos y refresca.")
    df_inventario = pd.DataFrame()

if not df_inventario.empty:
    if 'CLAVE' in df_inventario.columns:
        df_inventario['CLAVE'] = df_inventario['CLAVE'].astype(str).str.upper().str.strip()
    if 'RACK' in df_inventario.columns:
        df_inventario['RACK'] = df_inventario['RACK'].astype(str).str.upper().str.strip()
    if 'CANTIDAD' in df_inventario.columns:
        # Asegurar que cantidad sea numérica para evitar errores visuales
        df_inventario['CANTIDAD'] = pd.to_numeric(df_inventario['CANTIDAD'], errors='coerce').fillna(0)

# PESTAÑA 1: OPERACIONES
if menu == "📦 Operaciones":
    st.title("Operaciones de Inventario")

    # --- SECCIÓN ALTA ---
    with st.expander("➕ ALTA (Compra/Material Nuevo)", expanded=False):
        with st.form("form_alta", clear_on_submit=True):
            col1, col2 = st.columns(2)
            c_clave = col1.text_input("Clave")
            c_pieza = col2.selectbox("Pieza", ["Parabrisas", "Medallón", "Puerta", "Aleta", "Costado"])
            c_rack = col1.text_input("Ubicación / Rack", "PISO")
            c_cant = col2.number_input("Cantidad", 1, 100, 1)
            if st.form_submit_button("💾 Guardar"):
                if c_clave:
                    with st.spinner("Guardando en la nube..."):
                        ok, txt = guardar_entrada(ws_activo, c_clave, c_pieza, c_rack, c_cant, usuario)
                        if ok: st.success(txt)
                        else: st.error(txt)
                else: st.warning("Falta clave.")

    # --- SECCIÓN BAJA/TRASLADO ---
    with st.expander("➖ BAJA (Venta) o ENVÍO (Traslado)", expanded=True):
        st.write("**Paso 1: Buscar Producto**")
        b_clave_input = st.text_input("🔍 Ingresa Clave del producto:", placeholder="Ej. DW01234").upper().strip()
        
        racks_disponibles = []
        if b_clave_input and not df_inventario.empty and 'CLAVE' in df_inventario.columns:
            # Filtro mejorado: Agrupa por Rack y suma cantidades para visualización
            filtro_prod = df_inventario[df_inventario['CLAVE'] == b_clave_input]
            
            if not filtro_prod.empty:
                # Mostrar todas las ubicaciones, incluso si hay duplicados, sumamos para visualización
                resumen_racks = filtro_prod.groupby('RACK')['CANTIDAD'].sum()
                racks_disponibles = [f"{rack} (Disp: {int(cant)})" for rack, cant in resumen_racks.items() if cant > 0]
                
                # Si todo está en cero pero existe la clave
                if not racks_disponibles and not filtro_prod.empty:
                    st.warning("⚠️ Producto existe pero sin stock (Cantidad 0).")
            else:
                st.warning("⚠️ Producto no encontrado.")

        if racks_disponibles:
            st.write("**Paso 2: Detalles de la Operación**")
            tipo_op = st.radio("Tipo:", ["Venta / Instalación", "Enviar a otra Sucursal"], horizontal=True)
            
            with st.form("form_baja_dinamica"):
                col_rack, col_cant = st.columns(2)
                rack_seleccionado_texto = col_rack.selectbox("📍 Selecciona Rack de origen:", racks_disponibles)
                rack_real = rack_seleccionado_texto.split(" (Disp:")[0]
                cant_baja = col_cant.number_input("Cantidad", 1, 50, 1)
                
                ok = False
                msg = ""
                
                if tipo_op == "Venta / Instalación":
                    st.divider()
                    col_c, col_d = st.columns(2)
                    aseg = col_c.selectbox("Cliente:", ["Público General", "ANA", "GNP", "Zurich", "Qualitas", "CHUBB"])
                    nota = st.text_input("Nota adicional:")
                    prec = col_d.number_input("Precio $", 0.0)
                    detalle = f"{aseg} - {nota}" if nota else aseg
                    
                    if st.form_submit_button("💰 Confirmar Venta", type="primary"):
                        with st.spinner("Procesando venta..."):
                            ok, msg = procesar_baja_venta(ws_activo, b_clave_input, rack_real, detalle, cant_baja, prec, usuario)
                        
                else: 
                    st.divider()
                    st.info(f"El producto saldrá del rack: {rack_real}")
                    todas = ["Inventario_Suc1", "Inventario_Suc2", "Inventario_Suc3"]
                    otras = [s for s in todas if s != sucursal_visualizada]
                    destino = st.selectbox("Enviar a:", otras)
                    
                    if st.form_submit_button("🚚 Enviar Traslado", type="primary"):
                        with st.spinner("Generando envío..."):
                            ok, msg = iniciar_traslado(ws_activo, b_clave_input, rack_real, cant_baja, destino, usuario)

                if ok: 
                    st.success(msg)
                    time.sleep(2)
                    st.rerun()
                elif msg: 
                    st.error(msg)
        elif b_clave_input and not racks_disponibles:
            pass # Ya mostró warning arriba

    st.divider()
    st.subheader("📋 Inventario Actual")
    if not df_inventario.empty:
        st.dataframe(df_inventario, use_container_width=True, height=300)

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
                        rack_in = st.text_input("📍 Ubicación / Rack donde se guardará")
                        if st.form_submit_button("✅ CONFIRMAR RECEPCIÓN"):
                            if rack_in:
                                with st.spinner("Recibiendo..."):
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
    
    try:
        df = pd.DataFrame(ws_activo.get_all_records())
    except:
        df = pd.DataFrame()
        st.error("Error al leer datos. Intenta de nuevo.")

    if not df.empty and 'RACK' in df.columns:
        df['RACK'] = df['RACK'].astype(str).str.upper().str.strip()
        racks = sorted(df['RACK'].unique().tolist())
        
        col_r1, col_r2 = st.columns([1, 3])
        with col_r1:
            sel = st.radio("Selecciona Rack:", racks)
        with col_r2:
            st.subheader(f"Contenido Rack: {sel}")
            filtro_rack = df[df['RACK'] == sel]
            st.dataframe(filtro_rack[['CLAVE','NOMBRE','CANTIDAD']], use_container_width=True)
            st.metric("Total Piezas en Rack", int(filtro_rack['CANTIDAD'].sum()))
    else:
        st.warning("Sin datos de Rack.")