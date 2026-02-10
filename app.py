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
    "admin":       {"pass": "Xk9#mZ21!",     "rol": "admin", "sucursal": "todas"},
    "sucursal1":   {"pass": "Suc1_Ax7$",     "rol": "user",  "sucursal": "Inventario_Suc1"},
    "sucursal2":   {"pass": "Br4nch_Two!",   "rol": "user",  "sucursal": "Inventario_Suc2"},
    "sucursal3":   {"pass": "T3rcera_P0s#",  "rol": "user",  "sucursal": "Inventario_Suc3"}
}

# --- FUNCIONES DE LÓGICA ---

def limpiar_texto(texto):
    """Normaliza el texto: MAYÚSCULAS y quita espacios extra."""
    if not texto:
        return ""
    return " ".join(str(texto).strip().upper().split())

def obtener_fila_exacta(ws, clave, rack):
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    
    clave_buscada = limpiar_texto(clave)
    rack_buscado = limpiar_texto(rack)
    
    if df.empty: return None, 0

    if 'CLAVE' in df.columns: df['CLAVE_CLEAN'] = df['CLAVE'].apply(limpiar_texto)
    else: return None, 0

    if 'RACK' in df.columns: df['RACK_CLEAN'] = df['RACK'].apply(limpiar_texto)
    else: return None, 0
        
    if 'CANTIDAD' in df.columns:
        df['CANTIDAD'] = pd.to_numeric(df['CANTIDAD'], errors='coerce').fillna(0)
    
    filtro = df[(df['CLAVE_CLEAN'] == clave_buscada) & (df['RACK_CLEAN'] == rack_buscado)]
    
    if not filtro.empty:
        filtro = filtro.sort_values(by='CANTIDAD', ascending=False)
        indice_pandas = filtro.index[0]
        # Convertimos a int nativo de Python para evitar error int64
        cantidad_actual = int(filtro.iloc[0]['CANTIDAD'])
        return indice_pandas + 2, cantidad_actual
            
    return None, 0

def guardar_entrada(ws_destino, clave, nombre, rack, cantidad, usuario):
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        clave_clean = limpiar_texto(clave)
        rack_clean = limpiar_texto(rack)
        cantidad = int(cantidad) 
        
        fila, cant_actual = obtener_fila_exacta(ws_destino, clave_clean, rack_clean)

        if fila:
            nueva_cant = int(cant_actual + cantidad)
            ws_destino.update_cell(fila, 4, nueva_cant)
            ws_destino.update_cell(fila, 5, fecha)
            return True, f"✅ Stock actualizado en {rack_clean}. ({cant_actual} -> {nueva_cant})"
        else:
            ws_destino.append_row([clave_clean, nombre, rack_clean, cantidad, fecha])
            return True, f"✅ Nuevo registro creado en {rack_clean}."
    except Exception as e:
        return False, f"Error técnico: {e}"

def iniciar_traslado(ws_origen, clave, rack, cantidad, suc_destino, usuario):
    try:
        clave_clean = limpiar_texto(clave)
        rack_clean = limpiar_texto(rack)
        cantidad = int(cantidad)
        
        fila, cant_actual = obtener_fila_exacta(ws_origen, clave_clean, rack_clean)
        
        if not fila:
            return False, f"❌ No se encontró la clave {clave_clean} en {rack_clean}."
        if cant_actual < cantidad:
            return False, f"❌ Stock insuficiente en {rack_clean}. Tienes: {cant_actual}"

        nombre_prod = ws_origen.cell(fila, 2).value 
        nueva_cant = int(cant_actual - cantidad)
        ws_origen.update_cell(fila, 4, nueva_cant)
        
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        hojas['Traslados_Pendientes'].append_row([fecha, clave_clean, nombre_prod, cantidad, ws_origen.title, suc_destino])
        hojas['Movimientos'].append_row([fecha, clave_clean, "Envío Traslado", f"Desde {rack_clean} a {NOMBRES_SUCURSALES.get(suc_destino, suc_destino)}", cantidad, 0, usuario, ws_origen.title])

        return True, f"✅ Enviado a tránsito. Quedan {nueva_cant} en {rack_clean}."
    except Exception as e:
        return False, f"Error: {e}"

def cancelar_traslado_seguro(ws_origen, item_data, rack_retorno, usuario):
    try:
        data_pendientes = hojas['Traslados_Pendientes'].get_all_records()
        df_p = pd.DataFrame(data_pendientes)
        
        if df_p.empty:
            return False, "❌ La lista de pendientes está vacía. Seguramente ya fue aceptado."

        df_p['FECHA'] = df_p['FECHA'].astype(str)
        df_p['CLAVE'] = df_p['CLAVE'].astype(str)
        
        fecha_buscada = str(item_data['FECHA'])
        clave_buscada = str(item_data['CLAVE'])
        
        match = df_p[
            (df_p['FECHA'] == fecha_buscada) & 
            (df_p['CLAVE'] == clave_buscada)
        ]
        
        if match.empty:
            return False, "❌ ERROR: Esta pieza ya no está en pendientes. Es probable que la otra sucursal la acabara de aceptar."
            
        fila_real_borrar = match.index[0] + 2
        # Aseguramos conversión a int de Python
        cantidad = int(item_data['CANTIDAD'])

        ok, msg = guardar_entrada(ws_origen, item_data['CLAVE'], item_data['NOMBRE'], rack_retorno, cantidad, usuario)
        
        if ok:
            hojas['Traslados_Pendientes'].delete_rows(fila_real_borrar)
            fecha_log = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            hojas['Movimientos'].append_row([fecha_log, item_data['CLAVE'], "Cancelación Traslado", f"Regresado a {rack_retorno}", cantidad, 0, usuario, ws_origen.title])
            return True, "✅ Traslado cancelado correctamente y material recuperado."
        else:
            return False, f"Error al restaurar inventario: {msg}"

    except Exception as e:
        return False, f"Error técnico al cancelar: {e}"

def mover_interno_rack(ws, clave, nombre, rack_origen, rack_destino, cantidad, usuario):
    try:
        clave_clean = limpiar_texto(clave)
        rack_origen_clean = limpiar_texto(rack_origen)
        rack_destino_clean = limpiar_texto(rack_destino)
        cantidad = int(cantidad)

        if rack_origen_clean == rack_destino_clean: return False, "❌ El rack de destino es igual al de origen."

        fila_origen, cant_origen = obtener_fila_exacta(ws, clave_clean, rack_origen_clean)
        if not fila_origen or cant_origen < cantidad: return False, "❌ Stock insuficiente en origen."

        ws.update_cell(fila_origen, 4, int(cant_origen - cantidad))

        fila_destino, cant_destino = obtener_fila_exacta(ws, clave_clean, rack_destino_clean)
        if fila_destino:
            ws.update_cell(fila_destino, 4, int(cant_destino + cantidad))
        else:
            fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ws.append_row([clave_clean, nombre, rack_destino_clean, cantidad, fecha])
        
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        hojas['Movimientos'].append_row([fecha, clave_clean, "Reubicación Interna", f"De {rack_origen_clean} a {rack_destino_clean}", cantidad, 0, usuario, ws.title])
        return True, f"✅ Reubicado: {cantidad} pz de {rack_origen_clean} a {rack_destino_clean}."

    except Exception as e: return False, f"Error moviendo: {e}"

def procesar_baja_venta(ws_origen, clave, rack, detalle, cantidad, precio, usuario):
    try:
        clave_clean = limpiar_texto(clave)
        rack_clean = limpiar_texto(rack)
        cantidad = int(cantidad)
        
        fila, cant_actual = obtener_fila_exacta(ws_origen, clave_clean, rack_clean)
        
        if not fila: return False, f"❌ No se encontró la clave {clave_clean} en {rack_clean}."
        if cant_actual < cantidad: return False, f"❌ Stock insuficiente en {rack_clean}. Tienes: {cant_actual}"
        
        # --- AQUÍ ESTABA EL ERROR (CORREGIDO) ---
        # Antes decía 'ws', ahora dice 'ws_origen'
        nueva_cantidad = int(cant_actual - cantidad)
        ws_origen.update_cell(fila, 4, nueva_cantidad)
        
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        hojas['Movimientos'].append_row([fecha, clave_clean, "Venta/Instalación", f"{detalle} (Desde {rack_clean})", cantidad, precio, usuario, ws_origen.title])
        return True, f"✅ Venta registrada. Quedan {nueva_cantidad}."
    except Exception as e: return False, f"Error: {e}"

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
        else: return False, f"Fallo al guardar: {msg}"
    except Exception as e: return False, f"Error crítico: {e}"

# --- LOGIN ---
if 'logueado' not in st.session_state: st.session_state.logueado = False

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
            else: st.error("Datos incorrectos.")
        st.markdown("---")
    st.stop()

# --- INTERFAZ PRINCIPAL ---
if "user_data" not in st.session_state:
    st.session_state.logueado = False
    st.rerun()

usuario = st.session_state.user_data["user"]
rol = st.session_state.user_data["rol"]
sucursal_asignada = st.session_state.user_data["sucursal"]

with st.sidebar:
    nombre_visual_sucursal = NOMBRES_SUCURSALES.get(sucursal_asignada, sucursal_asignada)
    st.header(f"🏢 {nombre_visual_sucursal}")
    st.caption(f"Usuario: {usuario}")
    if st.button("🚪 Cerrar Sesión"):
        st.session_state.logueado = False
        st.rerun()
    st.markdown("---")
    opciones_menu = ["📦 Operaciones", "🚚 Traslados en Camino", "👀 Rack Visual"]
    if rol == "admin": opciones_menu.append("📜 Historial de Movimientos")
    menu = st.radio("Menú", opciones_menu)

# Selección de hoja
if rol == "admin":
    opciones_suc = ["Inventario_Suc1", "Inventario_Suc2", "Inventario_Suc3"]
    sucursal_visualizada = st.selectbox("Vista Admin - Inventario:", opciones_suc, format_func=lambda x: NOMBRES_SUCURSALES.get(x, x))
    ws_activo = hojas[sucursal_visualizada]
else:
    sucursal_visualizada = sucursal_asignada
    ws_activo = hojas[sucursal_asignada]

# Pre-carga de inventario
try:
    data_inv = ws_activo.get_all_records()
    df_inventario = pd.DataFrame(data_inv)
except Exception as e:
    st.error("Error leyendo inventario (Posible límite de API). Espera unos segundos y recarga.")
    df_inventario = pd.DataFrame()

if not df_inventario.empty:
    if 'CLAVE' in df_inventario.columns: df_inventario['CLAVE'] = df_inventario['CLAVE'].apply(limpiar_texto)
    if 'RACK' in df_inventario.columns: df_inventario['RACK'] = df_inventario['RACK'].apply(limpiar_texto)
    if 'NOMBRE' in df_inventario.columns: df_inventario['NOMBRE'] = df_inventario['NOMBRE'].astype(str)
    if 'CANTIDAD' in df_inventario.columns: df_inventario['CANTIDAD'] = pd.to_numeric(df_inventario['CANTIDAD'], errors='coerce').fillna(0)

# ==========================================
# PESTAÑA 1: OPERACIONES
# ==========================================
if menu == "📦 Operaciones":
    col_t1, col_t2 = st.columns([3,1])
    with col_t1: st.title("Operaciones de Inventario")
    with col_t2: 
        if st.button("🔄 ACTUALIZAR DATOS", type="primary"): st.rerun()

    # --- HERRAMIENTA DE LIMPIEZA ---
    if usuario == "admin":
        with st.expander("🧹 HERRAMIENTA DE LIMPIEZA DE DUPLICADOS", expanded=False):
            st.warning(f"⚠️ Esto eliminará las filas duplicadas en '{NOMBRES_SUCURSALES.get(sucursal_visualizada)}'.")
            if st.button("🔴 EJECUTAR LIMPIEZA AHORA"):
                try:
                    data = ws_activo.get_all_records()
                    df_clean = pd.DataFrame(data)
                    if not df_clean.empty:
                        rows_antes = len(df_clean)
                        df_clean['CLAVE_TEMP'] = df_clean['CLAVE'].astype(str).str.strip().str.upper()
                        df_clean['RACK_TEMP'] = df_clean['RACK'].astype(str).str.strip().str.upper()
                        df_clean['CANTIDAD'] = pd.to_numeric(df_clean['CANTIDAD'], errors='coerce').fillna(0)
                        df_clean = df_clean.sort_values(by='CANTIDAD', ascending=False)
                        df_clean = df_clean.drop_duplicates(subset=['CLAVE_TEMP', 'RACK_TEMP'], keep='first')
                        df_clean = df_clean.drop(columns=['CLAVE_TEMP', 'RACK_TEMP'])
                        eliminados = rows_antes - len(df_clean)
                        if eliminados > 0:
                            ws_activo.clear()
                            ws_activo.update([df_clean.columns.values.tolist()] + df_clean.values.tolist())
                            st.success(f"✅ Se eliminaron {eliminados} duplicados.")
                            time.sleep(2)
                            st.rerun()
                        else: st.info("Hoja limpia.")
                except Exception as e: st.error(f"Error: {e}")

    # --- SECCIÓN ALTA ---
    with st.expander("➕ ALTA (Compra/Material Nuevo)", expanded=False):
        with st.form("form_alta", clear_on_submit=True):
            col1, col2 = st.columns(2)
            c_clave = col1.text_input("Clave").upper()
            c_pieza = col2.selectbox("Pieza", ["Parabrisas", "Medallón", "Puerta", "Aleta", "Costado"])
            c_rack = col1.text_input("Ubicación / Rack", "PISO").upper()
            c_cant = col2.number_input("Cantidad", 1, 100, 1)
            
            if st.form_submit_button("💾 Guardar Entrada"):
                if c_clave:
                    ok, txt = guardar_entrada(ws_activo, c_clave, c_pieza, c_rack, c_cant, usuario)
                    if ok: 
                        st.success(txt)
                        time.sleep(1)
                        st.rerun()
                    else: st.error(txt)
                else: st.warning("Falta clave.")

    # --- SECCIÓN BAJA/TRASLADO ---
    with st.expander("➖ BAJA (Venta) o ENVÍO (Traslado)", expanded=True):
        st.write("**Paso 1: Buscar Producto**")
        b_clave_input = st.text_input("🔍 Ingresa Clave del producto:", placeholder="Ej. DW01234").upper()
        b_clave_clean = limpiar_texto(b_clave_input)
        
        racks_disponibles = []
        if b_clave_clean and not df_inventario.empty:
            filtro_prod = df_inventario[df_inventario['CLAVE'] == b_clave_clean]
            if not filtro_prod.empty:
                resumen = filtro_prod.groupby('RACK')['CANTIDAD'].sum().reset_index()
                racks_disponibles = [f"{row['RACK']} (Disp: {int(row['CANTIDAD'])})" for i, row in resumen.iterrows() if row['CANTIDAD'] > 0]
                if not racks_disponibles: st.warning("⚠️ Producto existe, pero Stock es 0.")
            else: st.warning("⚠️ Producto no encontrado.")

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
                    nombre_aseguradora = col_c.text_input("Nombre Aseguradora:", placeholder="Ej: Qualitas")
                    nota = st.text_input("Nota / Observaciones:")
                    prec = col_d.number_input("Precio Venta $", 0.0)
                    detalle = f"{nombre_aseguradora if tipo_cliente == 'Asegurado' else 'Público'} - {nota}"
                    
                    if st.form_submit_button("💰 Confirmar Venta", type="primary"):
                        ok, msg = procesar_baja_venta(ws_activo, b_clave_clean, rack_real, detalle, cant_baja, prec, usuario)
                        
                else: 
                    st.divider()
                    st.info(f"El producto saldrá del rack: {rack_real}")
                    todas = ["Inventario_Suc1", "Inventario_Suc2", "Inventario_Suc3"]
                    otras = [s for s in todas if s != sucursal_visualizada]
                    destino = st.selectbox("Enviar a:", otras, format_func=lambda x: NOMBRES_SUCURSALES.get(x, x))
                    
                    if st.form_submit_button("🚚 Enviar Traslado", type="primary"):
                        ok, msg = iniciar_traslado(ws_activo, b_clave_clean, rack_real, cant_baja, destino, usuario)

                if ok: 
                    st.success(msg)
                    time.sleep(2)
                    st.rerun()
                elif msg: st.error(msg)

    st.divider()
    # --- BUSCADOR ---
    st.markdown("### 📋 Inventario Actual")
    busqueda_raw = st.text_input("", placeholder="Escribe Clave, Nombre, Rack...", label_visibility="collapsed").upper()
    busqueda = limpiar_texto(busqueda_raw)

    if not df_inventario.empty:
        df_final = df_inventario.copy()
        if busqueda:
            df_final = df_final[df_final.astype(str).apply(lambda x: x.str.contains(busqueda, case=False)).any(axis=1)]
            st.info(f"Resultados: {len(df_final)}")
            
            for idx, row in df_final.head(10).iterrows():
                with st.container():
                    col_info, col_move = st.columns([2, 2])
                    with col_info:
                        st.markdown(f"**{row['CLAVE']}** - {row['NOMBRE']}")
                        st.markdown(f"📍 {row['RACK']} | Stock: **{int(row['CANTIDAD'])}**")
                    with col_move:
                        if int(row['CANTIDAD']) > 0:
                            with st.expander(f"🛠️ Mover"):
                                with st.form(f"move_{idx}"):
                                    nuevo_rack = st.text_input("Nuevo Rack:").upper()
                                    cant_mover = st.number_input("Cantidad:", 1, int(row['CANTIDAD']), 1, key=f"n_{idx}")
                                    if st.form_submit_button("Mover"):
                                        if nuevo_rack and limpiar_texto(nuevo_rack) != row['RACK']:
                                            ok, txt = mover_interno_rack(ws_activo, row['CLAVE'], row['NOMBRE'], row['RACK'], nuevo_rack, cant_mover, usuario)
                                            if ok:
                                                st.success(txt)
                                                time.sleep(1)
                                                st.rerun()
                                            else: st.error(txt)
                                        else: st.warning("Rack inválido")
                        else: st.caption("Sin stock.")
                    st.divider()

        tab1, tab2, tab3 = st.tabs(["🚘 PARABRISAS", "🔙 MEDALLONES", "🚪 OTROS"])
        with tab1: st.dataframe(df_final[df_final['NOMBRE'].str.contains("Parabrisas", case=False, na=False)], use_container_width=True)
        with tab2: st.dataframe(df_final[df_final['NOMBRE'].str.contains("Medallón", case=False, na=False)], use_container_width=True)
        with tab3: st.dataframe(df_final[~df_final['NOMBRE'].str.contains("Parabrisas|Medallón", case=False, na=False)], use_container_width=True)

# ==========================================
# PESTAÑA 2: TRASLADOS
# ==========================================
elif menu == "🚚 Traslados en Camino":
    st.title("Gestión de Traslados")
    if st.button("🔄 Actualizar"): st.rerun()
    
    try:
        data_p = hojas['Traslados_Pendientes'].get_all_records()
        df_p = pd.DataFrame(data_p)
    except:
        df_p = pd.DataFrame()

    if df_p.empty or 'DESTINO' not in df_p.columns:
        st.info("No hay traslados.")
    else:
        tab_recibir, tab_enviados = st.tabs(["📥 POR RECIBIR", "📤 ENVIADOS (CANCELAR)"])
        
        with tab_recibir:
            mis_llegadas = df_p[df_p['DESTINO'] == sucursal_visualizada].reset_index()
            if mis_llegadas.empty:
                st.success("Nada pendiente por recibir.")
            else:
                st.dataframe(mis_llegadas[['FECHA','ORIGEN','CLAVE','NOMBRE','CANTIDAD']], use_container_width=True)
                st.divider()
                st.subheader("📦 Recibir Material")
                opciones = mis_llegadas.apply(lambda x: f"{x['CLAVE']} ({x['CANTIDAD']}pz) - De: {NOMBRES_SUCURSALES.get(x['ORIGEN'],x['ORIGEN'])}", axis=1).tolist()
                seleccion = st.selectbox("Selecciona envío:", opciones)
                
                if seleccion:
                    idx = opciones.index(seleccion)
                    fila = mis_llegadas.iloc[idx]
                    with st.form("form_recibir"):
                        st.write(f"Recibiendo: **{fila['CLAVE']}**")
                        rack_in = st.text_input("📍 Guardar en Rack:")
                        if st.form_submit_button("✅ CONFIRMAR"):
                            if rack_in:
                                ok, m = finalizar_recepcion(sucursal_visualizada, fila['CLAVE'], fila['NOMBRE'], fila['CANTIDAD'], rack_in, usuario, int(fila['index'])+2)
                                if ok: 
                                    st.success(m)
                                    time.sleep(2)
                                    st.rerun()
                                else: st.error(m)
                            else: st.warning("Falta Rack.")

        with tab_enviados:
            mis_envios = df_p[df_p['ORIGEN'] == sucursal_visualizada].reset_index()
            
            if mis_envios.empty:
                st.info("No tienes envíos pendientes.")
            else:
                st.write("Estos envíos **aún no han sido aceptados** y pueden cancelarse.")
                df_mostrar = mis_envios.copy()
                df_mostrar['DESTINO'] = df_mostrar['DESTINO'].map(NOMBRES_SUCURSALES).fillna(df_mostrar['DESTINO'])
                st.dataframe(df_mostrar[['FECHA','DESTINO','CLAVE','CANTIDAD']], use_container_width=True)
                
                st.divider()
                st.subheader("🛑 Cancelar Traslado (Regresar a Inventario)")
                st.warning("Solo puedes cancelar envíos que NO han sido aceptados todavía.")
                
                opciones_cancelar = mis_envios.apply(lambda x: f"{x['CLAVE']} ({x['CANTIDAD']}pz) -> {NOMBRES_SUCURSALES.get(x['DESTINO'],x['DESTINO'])}", axis=1).tolist()
                seleccion_cancelar = st.selectbox("Selecciona envío a cancelar:", opciones_cancelar)
                
                if seleccion_cancelar:
                    idx_c = opciones_cancelar.index(seleccion_cancelar)
                    fila_c = mis_envios.iloc[idx_c]
                    
                    with st.form("form_cancelar"):
                        st.write(f"Vas a recuperar: **{fila_c['CLAVE']}** ({fila_c['CANTIDAD']} pz)")
                        rack_retorno = st.text_input("📍 ¿En qué Rack la guardarás de nuevo?", placeholder="Ej. PISO")
                        
                        if st.form_submit_button("🚨 CANCELAR ENVÍO"):
                            if rack_retorno:
                                # Usamos la nueva función segura
                                ok, m = cancelar_traslado_seguro(ws_activo, fila_c, rack_retorno, usuario)
                                if ok:
                                    st.success(m)
                                    time.sleep(2)
                                    st.rerun()
                                else:
                                    st.error(m)
                            else:
                                st.warning("Debes indicar en qué Rack guardarás la pieza recuperada.")

# ==========================================
# PESTAÑA 3: RACK
# ==========================================
elif menu == "👀 Rack Visual":
    st.title(f"Visor - {NOMBRES_SUCURSALES.get(sucursal_visualizada, sucursal_visualizada)}")
    if st.button("🔄 Refrescar"): st.rerun()
    
    if not df_inventario.empty and 'RACK' in df_inventario.columns:
        # Normalizamos racks para evitar errores si la columna no existe
        df_inventario['RACK'] = df_inventario['RACK'].astype(str)
        racks = sorted(df_inventario['RACK'].unique().tolist())
        col_r1, col_r2 = st.columns([1, 3])
        with col_r1:
            sel = st.radio("Rack:", racks) if racks else None
        with col_r2:
            if sel:
                st.subheader(f"Contenido Rack: {sel}")
                filtro_rack = df_inventario[df_inventario['RACK'] == sel]
                resumen = filtro_rack.groupby(['CLAVE', 'NOMBRE'])['CANTIDAD'].sum().reset_index()
                st.dataframe(resumen, use_container_width=True)
                st.metric("Piezas Totales", int(resumen['CANTIDAD'].sum()))
    else: st.warning("Sin datos para mostrar.")

# ==========================================
# PESTAÑA 4: HISTORIAL
# ==========================================
elif menu == "📜 Historial de Movimientos" and rol == "admin":
    st.title("Historial")
    if st.button("🔄 Actualizar"): st.rerun()
    try:
        data_movs = hojas['Movimientos'].get_all_records()
        df_movs = pd.DataFrame(data_movs)
        if not df_movs.empty:
            st.dataframe(df_movs.sort_index(ascending=False), use_container_width=True)
            st.download_button("Descargar CSV", df_movs.to_csv(index=False).encode('utf-8'), "historial.csv")
    except: st.error("Error cargando historial.")