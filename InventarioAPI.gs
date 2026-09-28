/* Glass Master: único punto de escritura para TODAS las sucursales.
 * Activar servicio avanzado Google Sheets v4. Ver README.md.
 * Propiedades: GAC_SHEET_ID y GAC_API_TOKEN (secreto de al menos 32 caracteres).
 * No editar datos manualmente ni mantener versiones antiguas escribiendo.
 */
const BRANCHES = ['Inventario_Suc1','Inventario_Suc2','Inventario_Suc3','Inventario_Suc4'];
const INV = ['CLAVE','NOMBRE','RACK','CANTIDAD','FECHA'];
const PEN = ['FECHA','CLAVE','NOMBRE','CANTIDAD','ORIGEN','DESTINO','ID_TRASLADO','RACK_ORIGEN'];
const MOV = ['FECHA','CLAVE','TIPO','DETALLE','CANTIDAD','PRECIO','USUARIO','SUCURSAL','ID_OPERACION','ID_TRASLADO'];
const OPS = ['FECHA','ID_OPERACION','HUELLA','RESPUESTA'];
const USERS = {admin:null, sucursal1:BRANCHES[0], sucursal2:BRANCHES[1], sucursal3:BRANCHES[2], sucursal4:BRANCHES[3]};
const MAX_QTY = 1000000000;

function fail(message, code) { const e = new Error(message); e.code = code || 'VALIDACION'; throw e; }
function clean(v) { return v == null ? '' : String(v).trim().replace(/\s+/g,' ').toUpperCase(); }
function rack(v) {
  let s = clean(v);
  if (['','SIN RACK','SIN ASIGNAR','RACK SIN RACK','RACK SIN ASIGNAR','RACK'].includes(s)) return 'RACK SIN ASIGNAR';
  s = s.replace(/^RACK\s*/, '').trim();
  if (/^\d+$/.test(s)) s = String(Number(s));
  // Conservar PEINE 1, PEINE 2, SIN PEINE 1, etc.: son ubicaciones diferentes.
  return 'RACK ' + s;
}
function integer(v, zero) {
  if (typeof v === 'boolean' || v === null || v === undefined || !/^\d+(\.0+)?$/.test(String(v).trim())) fail('La cantidad debe ser un entero ' + (zero?'no negativo.':'mayor que cero.'));
  const n = Number(v);
  if (!Number.isSafeInteger(n) || n < (zero?0:1) || n > MAX_QTY) fail('Cantidad fuera del intervalo permitido.');
  return n;
}
function key(v) { const s = clean(v); if (!s || s.length > 150) fail('La clave es obligatoria y admite hasta 150 caracteres.'); return s; }
function money(v) {
  if (v === '' || v === null || typeof v === 'boolean' || v === undefined) fail('Precio inválido.');
  const n = Number(v); if (!Number.isFinite(n) || n < 0 || n > 1e12) fail('Precio inválido.'); return n;
}
function now() { return Utilities.formatDate(new Date(), 'America/Mexico_City', 'yyyy-MM-dd HH:mm:ss'); }
function stable(v) {
  if (Array.isArray(v)) return '[' + v.map(stable).join(',') + ']';
  if (v && typeof v === 'object') return '{' + Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+stable(v[k])).join(',') + '}';
  return JSON.stringify(v);
}
function hash(v) { return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, stable(v)).map(b=>('0'+((b+256)%256).toString(16)).slice(-2)).join(''); }
function config() {
  const p = PropertiesService.getScriptProperties();
  const id = p.getProperty('GAC_SHEET_ID'), token = p.getProperty('GAC_API_TOKEN');
  if (!id || !token || token.length < 32) fail('Configura GAC_SHEET_ID y GAC_API_TOKEN en Apps Script.', 'CONFIGURACION');
  return {id, token, props:p};
}
function authorize(user, branch, adminOnly) {
  if (!Object.prototype.hasOwnProperty.call(USERS,user)) fail('Usuario no autorizado.', 'PERMISO');
  if (adminOnly && user !== 'admin') fail('Esta operación requiere administrador.', 'PERMISO');
  if (branch !== undefined && !BRANCHES.includes(branch)) fail('Sucursal inválida.');
  if (branch && user !== 'admin' && USERS[user] !== branch) fail('No puedes modificar otra sucursal.', 'PERMISO');
}
function schema(name) { return BRANCHES.includes(name)?INV:name==='Traslados_Pendientes'?PEN:name==='Movimientos'?MOV:OPS; }
function load(id, setup) {
  const meta = Sheets.Spreadsheets.get(id, {fields:'sheets.properties'}).sheets.map(s=>s.properties);
  const names = BRANCHES.concat(['Traslados_Pendientes','Movimientos','Operaciones']);
  const existing = names.filter(n=>meta.some(m=>m.title===n));
  for (const n of names) if (!existing.includes(n) && !(setup && n==='Operaciones')) fail('Falta la pestaña '+n+'.');
  const result = Sheets.Spreadsheets.Values.batchGet(id, {ranges:existing.map(n=>"'"+n+"'"), valueRenderOption:'UNFORMATTED_VALUE'});
  const tables = {};
  existing.forEach((n,i)=>{
    const grid = (result.valueRanges[i].values || []).map(r=>r.slice());
    const expected = schema(n);
    const base = n==='Traslados_Pendientes'?6:n==='Movimientos'?8:expected.length;
    let header = grid.length ? grid[0].map(clean) : [];
    while (header.length && header[header.length-1]==='') header.pop();
    const valid = header.length===expected.length || (setup && header.length===base);
    if (!valid || header.some((v,j)=>v!==expected[j])) fail('Encabezados inesperados en '+n+'. Revisa README; no se modificaron datos.');
    if (grid.some(r=>r.slice(expected.length).some(v=>v!=='' && v!=null))) fail('Hay datos fuera del esquema en '+n+'.');
    const rows = grid.slice(1).filter(r=>r.some(v=>v!=='' && v!=null)).map(r=>expected.map((_,j)=>r[j] == null?'':r[j]));
    tables[n] = {name:n, meta:meta.find(m=>m.title===n), grid, rows};
  });
  return {tables, meta};
}
function inventory(rows) {
  const map = new Map();
  rows.forEach(r=>{
    const k = key(r[0]), loc = rack(r[2]), qty = integer(r[3],true), id = JSON.stringify([k,loc]);
    if (map.has(id)) { const a=map.get(id); a[3]=integer(a[3]+qty,true); if(r[1]) a[1]=String(r[1]); if(r[4]) a[4]=r[4]; }
    else map.set(id,[k,String(r[1]||'Sin Nombre'),loc,qty,r[4]]);
  });
  return Array.from(map.values());
}
function pending(rows) {
  const ids = new Set();
  return rows.map(r=>{
    const a = r.slice(); a[1]=key(a[1]); a[3]=integer(a[3],false);
    if (!BRANCHES.includes(a[4]) || !BRANCHES.includes(a[5]) || a[4]===a[5]) fail('Traslado con sucursales inválidas.');
    if (!a[6] || ids.has(String(a[6]))) fail('ID de traslado vacío o repetido; ejecuta prepararSistema y revisa los datos.');
    ids.add(String(a[6])); a[6]=String(a[6]); return a;
  });
}
function cell(v) { return {userEnteredValue:typeof v==='number'?{numberValue:v}:{stringValue:String(v == null?'':v)}}; }
function cells(rows) { return rows.map(r=>({values:r.map(cell)})); }
function capacity(t, rows, cols, requests) {
  const g=t.meta.gridProperties;
  if (rows>g.rowCount || cols>g.columnCount) requests.push({updateSheetProperties:{properties:{sheetId:t.meta.sheetId,gridProperties:{rowCount:Math.max(rows,g.rowCount),columnCount:Math.max(cols,g.columnCount)}},fields:'gridProperties.rowCount,gridProperties.columnCount'}});
}
function replace(t, rows, requests) {
  const grid=[schema(t.name)].concat(rows), end=Math.max(t.grid.length,grid.length);
  capacity(t,end,schema(t.name).length,requests);
  requests.push({updateCells:{range:{sheetId:t.meta.sheetId,startRowIndex:0,endRowIndex:end,startColumnIndex:0,endColumnIndex:schema(t.name).length},rows:cells(grid),fields:'userEnteredValue'}});
}
function append(t, rows, requests) {
  if (!rows.length) return;
  capacity(t,t.grid.length+rows.length,schema(t.name).length,requests);
  requests.push({appendCells:{sheetId:t.meta.sheetId,rows:cells(rows),fields:'userEnteredValue'}});
}
function receipt(tables,id) {
  const rows=tables.Operaciones.rows.filter(r=>String(r[1])===id);
  if (rows.length>1) fail('Identificador repetido en Operaciones. Revisión administrativa requerida.');
  return rows[0] || null;
}
function checkUncertain(cfg,tables) {
  const raw=cfg.props.getProperty('GAC_ESCRITURA_INCIERTA');
  if (!raw) return;
  const marker=JSON.parse(raw), saved=receipt(tables,marker.id);
  if (saved && saved[2]===marker.hash) { cfg.props.deleteProperty('GAC_ESCRITURA_INCIERTA'); return; }
  fail('La operación '+marker.id+' aún no se ha podido confirmar. Escrituras bloqueadas para evitar duplicados. Revisa Operaciones; no generes otro pedido.', 'INCIERTO');
}
function snapshot(tables,user) {
  const data={};
  BRANCHES.forEach(n=>{if(user==='admin'||USERS[user]===n) data[n]=inventory(tables[n].rows).map(r=>Object.fromEntries(INV.map((h,i)=>[h,r[i]])));});
  data.Traslados_Pendientes=pending(tables.Traslados_Pendientes.rows).filter(r=>user==='admin'||r[4]===USERS[user]||r[5]===USERS[user]).map(r=>Object.fromEntries(PEN.map((h,i)=>[h,r[i]])));
  data.Movimientos=user==='admin'?tables.Movimientos.rows.map(r=>Object.fromEntries(MOV.map((h,i)=>[h,r[i]]))):[];
  return {ok:true,data};
}
function add(rows,k,name,loc,qty,date) {
  const r=rows.find(r=>r[0]===k&&r[2]===loc);
  if(r) {r[3]=integer(r[3]+qty,true); r[4]=date;}
  else rows.push([k,String(name||'Sin Nombre'),loc,integer(qty,false),date]);
}
function take(rows,k,loc,qty,date) {
  const i=rows.findIndex(r=>r[0]===k&&r[2]===loc);
  if(i<0) fail('No se encontró '+k+' en '+loc+'.');
  const r=rows[i],name=r[1];
  if(r[3]<qty) fail('Stock insuficiente. Disponible: '+r[3]+' pz.');
  r[3]-=qty; r[4]=date;
  // Mantener en cero racks numerados; eliminar ubicación genérica vacía.
  if(r[3]===0&&!/\d/.test(loc)) rows.splice(i,1);
  return name;
}
function parseOrder(text, defaultRack) {
  if(typeof text!=='string'||!text.trim()) fail('El pedido está vacío.');
  const lines=text.split(/\r?\n/).map((s,i)=>[s.trim(),i+1]).filter(a=>a[0]);
  if(lines.length>1000) fail('Máximo 1,000 líneas por pedido.');
  const result=new Map();
  for(const [line,num] of lines) {
    try {
      const p=line.split(',').map(s=>s.trim());
      if(p.length<1||p.length>3) fail('Usa CLAVE,CANTIDAD,RACK.');
      const k=key(p[0]),q=p.length>=2?integer(p[1],false):1,loc=rack(p.length===3?p[2]:defaultRack),id=JSON.stringify([k,loc]);
      if(result.has(id)) result.get(id).qty=integer(result.get(id).qty+q,false);
      else result.set(id,{key:k,rack:loc,qty:q});
    } catch(e) {fail('Línea '+num+': '+e.message);}
  }
  return Array.from(result.values());
}
function execute(p,cfg) {
  authorize(p.user,p.action==='snapshot'?undefined:p.branch,p.action==='clean');
  const {tables}=load(cfg.id,false);
  if(p.action==='snapshot') return snapshot(tables,p.user);
  if(typeof p.id!=='string'||!/^[A-Za-z0-9_-]{16,100}$/.test(p.id)) fail('Falta un identificador de operación válido.');
  const signature=hash({action:p.action,user:p.user,branch:p.branch,payload:p.payload||{}});
  checkUncertain(cfg,tables);
  const saved=receipt(tables,p.id);
  if(saved) {
    if(saved[2]!==signature) fail('El ID ya fue usado con datos diferentes.','ID_REUTILIZADO');
    return Object.assign(JSON.parse(saved[3]),{replayed:true});
  }
  const allowed=['alta','venta','send','receive','cancel','relocate','direct_sale','order','clean'];
  if(!allowed.includes(p.action)) fail('Acción desconocida.');
  const d=p.payload||{}, date=now(), changed=new Set(), logs=[];
  let trans=null, message='', tid='';
  const stock=inventory(tables[p.branch].rows);
  const log=(k,type,detail,q,price,transfer)=>logs.push([date,k,type,detail,q,price,p.user,p.branch,p.id,transfer||'']);
  const persistStock=()=>{tables[p.branch].rows=stock;changed.add(p.branch);};
  if(['alta','venta','send','relocate'].includes(p.action)) {
    const k=key(d.key),loc=rack(d.rack),q=integer(d.qty,false);
    if(p.action==='alta') {add(stock,k,d.name,loc,q,date);log(k,'Alta/Compra','Entrada en '+loc,q,0);message=q+' pz registradas en '+loc+'.';}
    if(p.action==='venta') {const price=money(d.price);take(stock,k,loc,q,date);log(k,'Venta/Instalación',String(d.detail||'')+' (desde '+loc+')',q,price);message='Venta confirmada: '+q+' pz.';}
    if(p.action==='send') {
      if(!BRANCHES.includes(d.destination)||d.destination===p.branch) fail('El destino debe ser otra sucursal válida.');
      const name=take(stock,k,loc,q,date); trans=pending(tables.Traslados_Pendientes.rows);
      tid='TR-'+p.id;trans.push([date,k,name,q,p.branch,d.destination,tid,loc]);
      log(k,'Envío Traslado','De '+p.branch+'/'+loc+' a '+d.destination,q,0,tid);message='Traslado enviado: '+q+' pz.';
    }
    if(p.action==='relocate') {
      const dest=rack(d.destination_rack);if(dest===loc) fail('El rack de destino es igual al de origen.');
      const name=take(stock,k,loc,q,date);add(stock,k,name,dest,q,date);
      log(k,'Reubicación Interna','De '+loc+' a '+dest,q,0);message=q+' pz reubicadas.';
    }
    persistStock();
  }
  if(['receive','cancel','direct_sale'].includes(p.action)) {
    trans=pending(tables.Traslados_Pendientes.rows);
    const i=trans.findIndex(r=>r[6]===d.transfer_id);
    if(i<0) fail('El traslado ya fue procesado o no existe. Actualiza la vista.');
    const r=trans[i];tid=r[6];
    if(p.branch!==(p.action==='cancel'?r[4]:r[5])) fail('El traslado no corresponde a esta sucursal.','PERMISO');
    const q=p.action==='cancel'?r[3]:integer(d.qty,false);
    if(q>r[3]) fail('Solo quedan '+r[3]+' pz pendientes. Actualiza la vista.');
    if(p.action==='direct_sale') {log(r[1],'Venta/Instalación','Baja inmediata desde '+r[4]+': '+String(d.detail||''),q,money(d.price),tid);message='Baja inmediata confirmada: '+q+' pz.';}
    else {
      const loc=rack(d.rack);add(stock,r[1],r[2],loc,q,date);persistStock();
      log(r[1],p.action==='cancel'?'Cancelación Traslado':'Recepción Traslado',(p.action==='cancel'?'Regresado a ':'Guardado en ')+loc,q,0,tid);
      message=q+' pz '+(p.action==='cancel'?'restauradas':'recibidas')+' en '+loc+'.';
    }
    r[3]-=q;if(r[3]===0) trans.splice(i,1);
  }
  if(p.action==='order') {
    const items=parseOrder(d.text,d.rack);
    items.forEach(it=>{add(stock,it.key,d.name,it.rack,it.qty,date);log(it.key,'Alta/Compra','Pedido en '+it.rack,it.qty,0);});
    persistStock();message='Pedido completo: '+items.reduce((a,b)=>a+b.qty,0)+' pz en '+items.length+' combinaciones de clave y rack.';
  }
  if(p.action==='clean') {
    const removed=tables[p.branch].rows.length-stock.length;
    persistStock();log('','Consolidación','Filas consolidadas: '+removed+'; cantidades sumadas, sin ajuste físico.',0,0);
    message=removed+' filas consolidadas. Se conserva el total registrado.';
  }
  if(trans!==null) {tables.Traslados_Pendientes.rows=trans;changed.add('Traslados_Pendientes');}
  const result={ok:true,message,id:p.id,transfer_id:tid}, requests=[];
  changed.forEach(n=>replace(tables[n],tables[n].rows,requests));
  append(tables.Movimientos,logs,requests);
  append(tables.Operaciones,[[date,p.id,signature,JSON.stringify(result)]],requests);
  // El marcador permanece si Google devuelve un resultado indeterminado.
  cfg.props.setProperty('GAC_ESCRITURA_INCIERTA',JSON.stringify({id:p.id,hash:signature}));
  Sheets.Spreadsheets.batchUpdate({requests},cfg.id);
  cfg.props.deleteProperty('GAC_ESCRITURA_INCIERTA');
  return result;
}
function handle(p) {
  let lock=null, acquired=false, cfg=null;
  try {
    cfg=config();if(!p || p.token!==cfg.token) fail('Credencial del servicio inválida.','AUTH');
    lock=LockService.getScriptLock();acquired=lock.tryLock(20000);
    if(!acquired) fail('Otra operación está en curso. Reintenta con el mismo ID.','OCUPADO');
    return execute(p,cfg);
  } catch(e) {
    let uncertain=false;
    try {uncertain=!!(acquired&&cfg&&cfg.props.getProperty('GAC_ESCRITURA_INCIERTA'));}
    catch(_) {uncertain=true;}
    return {ok:false,message:uncertain?'Resultado pendiente de confirmar. Conserva el ID y reintenta; las escrituras están protegidas.':String(e.message||e),code:uncertain?'INCIERTO':(e.code||'SERVICIO'),uncertain};
  } finally {
    // No convertir una escritura confirmada en un error de formato si falla la liberación.
    if(acquired) {try {lock.releaseLock();} catch(_) { /* Google libera al terminar la ejecución. */ }}
  }
}
function doPost(e) {
  let response;
  try {response=handle(JSON.parse(e.postData.contents));}
  catch(err) {response={ok:false,message:'Solicitud JSON inválida.',code:'FORMATO'};}
  return ContentService.createTextOutput(JSON.stringify(response)).setMimeType(ContentService.MimeType.JSON);
}
function prepararSistema() {
  const cfg=config(), lock=LockService.getScriptLock();lock.waitLock(20000);
  try {
    if(cfg.props.getProperty('GAC_ESCRITURA_INCIERTA')) fail('Resuelve primero la escritura incierta.');
    const {tables,meta}=load(cfg.id,true),requests=[];
    // Validar antes de cualquier escritura. No modificar cantidades en migración.
    BRANCHES.forEach(n=>inventory(tables[n].rows));
    tables.Traslados_Pendientes.rows.forEach(r=>{if(!r[6]) r[6]='LEGACY-'+Utilities.getUuid();if(!r[7]) r[7]='';});
    pending(tables.Traslados_Pendientes.rows);
    replace(tables.Traslados_Pendientes,tables.Traslados_Pendientes.rows,requests);
    // Escribir solo encabezado extra; preservar celdas y fórmulas del historial.
    const mt=tables.Movimientos;capacity(mt,Math.max(1,mt.grid.length),MOV.length,requests);
    requests.push({updateCells:{range:{sheetId:mt.meta.sheetId,startRowIndex:0,endRowIndex:1,startColumnIndex:0,endColumnIndex:MOV.length},rows:cells([MOV]),fields:'userEnteredValue'}});
    if(!tables.Operaciones) {
      const id=Math.max(...meta.map(m=>m.sheetId))+1;
      requests.push({addSheet:{properties:{sheetId:id,title:'Operaciones',gridProperties:{rowCount:1000,columnCount:OPS.length}}}});
      requests.push({updateCells:{start:{sheetId:id,rowIndex:0,columnIndex:0},rows:cells([OPS]),fields:'userEnteredValue'}});
    }
    Sheets.Spreadsheets.batchUpdate({requests},cfg.id);
    return 'Sistema preparado. Encabezados e IDs listos; inventario físico sin cambios.';
  } finally {lock.releaseLock();}
}
