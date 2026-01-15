import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
import time

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Inventario Cristales", layout="wide")

# --- MAPEO DE NOMBRES ---
NOMBRES_SUCURSALES = {
    "Inventario_Suc1": "Arriaga",
    "Inventario_Suc2": "Libramiento",
    "Inventario_Suc3": "Zamora",
    "todas": "Todas las Sucursales"
}

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

# --- FUNCIONES DE LÓGICA ---

def obtener_fila_exacta(ws, clave, rack):
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    clave = str(clave).upper().strip()
    rack = str(rack).upper().strip()
    
    if not df.empty:
        # Aseguramos que existan las columnas y sean string
        if 'CLAVE' in df.columns:
            df['CLAVE'] = df['CLAVE'].astype(str).str.upper().str.strip()
        if 'RACK' in df.columns:
            df['RACK'] = df['RACK'].astype(str).str.upper().str.strip()
            
        filtro = df[(df['CLAVE'] == clave) & (df['RACK'] == rack)]
        
        if not filtro.empty:
            return filtro.index[0] + 2, int(filtro.iloc[0]['CANTIDAD'])
    return None, 0

def guardar_entrada(ws_destino, clave, nombre, rack, cantidad, usuario):
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        clave = str(clave).upper().strip()
        rack = str(rack).upper().strip()
        cantidad = int(cantidad) 
        
        fila, cant_actual = obtener_fila_exacta(ws_destino, clave, rack)

        if fila:
            nueva_cant = cant_actual + cantidad
            ws_destino.update_cell(fila, 4, nueva_cant)
            ws_destino.update_cell(fila, 5, fecha)
            return True, f"✅ Recibido en Rack {rack}. Total: {nueva_cant}"
        else:
            ws_destino.append_row([clave, nombre, rack, cantidad, fecha])
            return True, f"✅ Nuevo registro creado en Rack {rack}."
    except Exception as e:
        return False, f"Error técnico en guardar: {e}"

def iniciar_traslado(ws_origen, clave, rack, cantidad, suc_destino, usuario):
    try:
        clave = str(clave).upper().strip()
        rack = str(rack).upper().strip()
        cantidad = int(cantidad)
        
        fila, cant_actual = obtener_fila_exacta(ws_origen, clave, rack)
        
        if not fila:
            return False, f"❌ No se encontró la clave {clave} en el rack {rack}."

        if cant_actual < cantidad:
            return False, f"❌ Stock insuficiente en Rack {rack}. Tienes: {cant_actual}"

        nombre_prod = ws_origen.cell(fila, 2).value 
        nueva_cant = cant_actual - cantidad
        ws_origen.update_cell(fila, 4, nueva_cant)
        
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        hojas['Traslados_Pendientes'].append_row([fecha, clave, nombre_prod, cantidad, ws_origen.title, suc_destino])
        hojas['Movimientos'].append_row([fecha, clave, "Envío Traslado", f"Desde {rack} a {NOMBRES_SUCURSALES.get(suc_destino, suc_destino)}", cantidad, 0, usuario, ws_origen.title])

        return True, f"✅ Enviado a tránsito. Quedan {nueva_cant} en {rack}."
    except Exception as e:
        return False, f"Error: {e}"

def procesar_baja_venta(ws_origen, clave, rack, detalle, cantidad, precio, usuario):
    try:
        clave = str(clave).upper().strip()
        rack = str(rack).upper().strip()
        cantidad = int(cantidad)
        
        fila, cant_actual = obtener_fila_exacta(ws_origen, clave, rack)
        
        if not fila:
            return False, f"❌ No se encontró la clave {clave} en el rack {rack}."
        
        if cant_actual < cantidad:
            return False, f"❌ Stock insuficiente en {rack}. Tienes: {cant_actual}"
        
        nueva_cant = cant_actual - cantidad
        ws_origen.update_cell(fila, 4, nueva_cant)
        
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        hojas['Movimientos'].append_row([fecha, clave, "Venta/Instalación", f"{detalle} (Desde {rack})", cantidad, precio, usuario, ws_origen.title])
        
        return True, f"✅ Venta registrada desde {rack}. Quedan {nueva_cant}."
    except Exception as e:
        return False, f"Error: {e}"

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
        st.markdown("---")
        u = st.text_input("Usuario").strip() 
        p = st.text_input("Contraseña", type="password").strip()
        if st.button("ENTRAR", type="primary"):
            if u in credenciales and credenciales[u]["pass"] == p:
                st.session_state.logueado = True
                st.session_state.user_data = {"user": u, **credenciales[u]}
                st.rerun()
            else:
                st.error("Datos incorrectos.")
        st.markdown("---")
    st.stop()

# --- INTERFAZ PRINCIPAL ---

if "user_data" not in st.session_state:
    st.session_state.logueado = False
    st.rerun()

usuario = st.session_state.user_data["user"]
rol = st.session_state.user_data["rol"]
sucursal_asignada = st.session_state.user_data["sucursal"]

# --- BARRA LATERAL ---
with st.sidebar:
    nombre_visual_sucursal = NOMBRES_SUCURSALES.get(sucursal_asignada, sucursal_asignada)
    st.header(f"🏢 {nombre_visual_sucursal}")
    st.caption(f"Usuario: {usuario}")
    if st.button("Cerrar Sesión"):
        st.session_state.logueado = False
        st.rerun()
    
    opciones_menu = ["📦 Operaciones", "🚚 Traslados en Camino", "👀 Rack Visual"]
    if rol == "admin":
        opciones_menu.append("📜 Historial de Movimientos")
        
    menu = st.radio("Menú", opciones_menu)

# Selección de hoja
if rol == "admin":
    opciones_suc = ["Inventario_Suc1", "Inventario_Suc2", "Inventario_Suc3"]
    sucursal_visualizada = st.selectbox(
        "Vista Admin - Inventario:", opciones_suc, 
        format_func=lambda x: NOMBRES_SUCURSALES.get(x, x)
    )
    ws_activo = hojas[sucursal_visualizada]
else:
    sucursal_visualizada = sucursal_asignada
    ws_activo = hojas[sucursal_asignada]

# Pre-carga de inventario
df_inventario = pd.DataFrame(ws_activo.get_all_records())
if not df_inventario.empty:
    df_inventario['CLAVE'] = df_inventario['CLAVE'].astype(str).str.upper().str.strip()
    df_inventario['RACK'] = df_inventario['RACK'].astype(str).str.upper().str.strip()
    if 'NOMBRE' in df_inventario.columns:
        df_inventario['NOMBRE'] = df_inventario['NOMBRE'].astype(str)

# ==========================================
# PESTAÑA 1: OPERACIONES
# ==========================================
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
                    ok, txt = guardar_entrada(ws_activo, c_clave, c_pieza, c_rack, c_cant, usuario)
                    if ok: st.success(txt)
                    else: st.error(txt)
                else: st.warning("Falta clave.")

    # --- SECCIÓN BAJA/TRASLADO ---
    with st.expander("➖ BAJA (Venta) o ENVÍO (Traslado)", expanded=True):
        st.write("**Paso 1: Buscar Producto**")
        b_clave_input = st.text_input("🔍 Ingresa Clave del producto:", placeholder="Ej. DW01234").upper().strip()
        
        racks_disponibles = []
        if b_clave_input and not df_inventario.empty:
            filtro_prod = df_inventario[df_inventario['CLAVE'] == b_clave_input]
            if not filtro_prod.empty:
                racks_disponibles = [f"{row['RACK']} (Disp: {row['CANTIDAD']})" for i, row in filtro_prod.iterrows()]
            else:
                st.warning("⚠️ Producto no encontrado en esta sucursal.")

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
                    tipo_cliente = col_c.radio("¿Tipo de Cliente?", ["Público General", "Asegurado"], horizontal=True)
                    nombre_aseguradora = col_c.text_input("Nombre Aseguradora (Si aplica):", placeholder="Ej: Qualitas, GNP...")
                    nota = st.text_input("Nota / Observaciones:")
                    prec = col_d.number_input("Precio Venta $", 0.0)

                    if tipo_cliente == "Asegurado":
                         aseg_txt = nombre_aseguradora if nombre_aseguradora else "Asegurado"
                         detalle = f"Aseg: {aseg_txt} - {nota}"
                    else:
                         detalle = f"Público Gral - {nota}"
                    
                    if st.form_submit_button("💰 Confirmar Venta", type="primary"):
                        ok, msg = procesar_baja_venta(ws_activo, b_clave_input, rack_real, detalle, cant_baja, prec, usuario)
                        
                else: # Traslado
                    st.divider()
                    st.info(f"El producto saldrá del rack: {rack_real}")
                    todas = ["Inventario_Suc1", "Inventario_Suc2", "Inventario_Suc3"]
                    otras = [s for s in todas if s != sucursal_visualizada]
                    destino = st.selectbox("Enviar a:", otras, format_func=lambda x: NOMBRES_SUCURSALES.get(x, x))
                    
                    if st.form_submit_button("🚚 Enviar Traslado", type="primary"):
                        ok, msg = iniciar_traslado(ws_activo, b_clave_input, rack_real, cant_baja, destino, usuario)

                if ok: 
                    st.success(msg)
                    time.sleep(2)
                    st.rerun()
                elif msg: 
                    st.error(msg)
        elif b_clave_input:
            st.info("Escribe una clave válida para ver los Racks disponibles.")

    st.divider()
    # --- SECCIÓN DE INVENTARIO DIVIDIDO ---
    st.markdown("### 📋 Inventario Actual")
    
    # 1. BUSCADOR GRANDE
    st.markdown("#### 🔎 BUSCADOR DE PIEZAS")
    busqueda = st.text_input("", placeholder="Escribe Clave, Nombre, Rack...", label_visibility="collapsed").upper()

    if not df_inventario.empty:
        # 2. Filtrado general por buscador
        df_final = df_inventario.copy()
        if busqueda:
            df_final = df_final[
                df_final.astype(str).apply(lambda x: x.str.contains(busqueda, case=False)).any(axis=1)
            ]

        # 3. Pestañas separadas
        tab1, tab2, tab3 = st.tabs(["🚘 PARABRISAS", "🔙 MEDALLONES", "🚪 PUERTAS / OTROS"])
        
        # Filtro por tipo de pieza (Columna 'NOMBRE')
        # Asumiendo que 'NOMBRE' contiene 'Parabrisas', 'Medallón', 'Puerta', etc.
        
        with tab1:
            df_p = df_final[df_final['NOMBRE'].str.contains("Parabrisas", case=False, na=False)]
            st.dataframe(df_p, use_container_width=True, height=400)
            st.caption(f"Total registros: {len(df_p)}")

        with tab2:
            df_m = df_final[df_final['NOMBRE'].str.contains("Medallón", case=False, na=False)]
            st.dataframe(df_m, use_container_width=True, height=400)
            st.caption(f"Total registros: {len(df_m)}")

        with tab3:
            # Aquí metemos Puertas, Aletas, Costados y cualquier otra cosa
            # Filtramos lo que NO sea Parabrisas NI Medallón
            mask_otros = (
                ~df_final['NOMBRE'].str.contains("Parabrisas", case=False, na=False) & 
                ~df_final['NOMBRE'].str.contains("Medallón", case=False, na=False)
            )
            df_o = df_final[mask_otros]
            st.dataframe(df_o, use_container_width=True, height=400)
            st.caption(f"Total registros: {len(df_o)}")

    else:
        st.info("El inventario está vacío.")


# ==========================================
# PESTAÑA 2: TRASLADOS
# ==========================================
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
            df_mostrar = mis_llegadas.copy()
            if not df_mostrar.empty:
                df_mostrar['ORIGEN'] = df_mostrar['ORIGEN'].map(NOMBRES_SUCURSALES).fillna(df_mostrar['ORIGEN'])

            if mis_llegadas.empty:
                st.success("✅ No tienes envíos pendientes.")
            else:
                st.warning(f"Tienes {len(mis_llegadas)} envíos esperando recepción.")
                st.dataframe(df_mostrar[['FECHA','ORIGEN','CLAVE','NOMBRE','CANTIDAD']], use_container_width=True)
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
                                ok, m = finalizar_recepcion(sucursal_visualizada, fila['CLAVE'], fila['NOMBRE'], fila['CANTIDAD'], rack_in, usuario, int(fila['index'])+2)
                                if ok: 
                                    st.success(m)
                                    time.sleep(2)
                                    st.rerun()
                                else: st.error(m)
                            else: st.warning("Escribe el Rack.")
        with tab_enviados:
            mis_envios = df_p[df_p['ORIGEN'] == sucursal_visualizada]
            df_enviados_mostrar = mis_envios.copy()
            if not df_enviados_mostrar.empty:
                df_enviados_mostrar['DESTINO'] = df_enviados_mostrar['DESTINO'].map(NOMBRES_SUCURSALES).fillna(df_enviados_mostrar['DESTINO'])
            st.dataframe(df_enviados_mostrar[['FECHA','DESTINO','CLAVE','CANTIDAD']], use_container_width=True)

# ==========================================
# PESTAÑA 3: RACK
# ==========================================
elif menu == "👀 Rack Visual":
    nombre_visual = NOMBRES_SUCURSALES.get(sucursal_visualizada, sucursal_visualizada)
    st.title(f"Visor - {nombre_visual}")
    if st.button("🔄 Refrescar"): st.rerun()
    
    df = pd.DataFrame(ws_activo.get_all_records())
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

# ==========================================
# PESTAÑA 4: HISTORIAL (SOLO ADMIN)
# ==========================================
elif menu == "📜 Historial de Movimientos":
    st.title("📜 Historial Global de Movimientos")
    if st.button("🔄 Actualizar Historial"): st.rerun()

    try:
        data_movs = hojas['Movimientos'].get_all_records()
        df_movs = pd.DataFrame(data_movs)

        if df_movs.empty:
            st.info("No hay movimientos registrados todavía.")
        else:
            if 'FECHA' in df_movs.columns:
                try:
                    df_movs['FECHA_DT'] = pd.to_datetime(df_movs['FECHA'])
                    df_movs = df_movs.sort_values(by='FECHA_DT', ascending=False)
                    df_movs = df_movs.drop(columns=['FECHA_DT'])
                except: pass

            st.dataframe(df_movs, use_container_width=True)
            csv = df_movs.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="💾 Descargar Historial como CSV",
                data=csv,
                file_name='historial_movimientos.csv',
                mime='text/csv',
            )
    except Exception as e:
        st.error(f"Error al cargar el historial: {e}")