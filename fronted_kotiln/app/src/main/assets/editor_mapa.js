// Editor de mapa y alertas (vista 7.8) — Leaflet + OpenStreetMap en línea.
// Kotlin ⇄ Web: ver `EditorMapaScreen.kt`. Sin puente (navegador) usa datos de demo.
(function () {
'use strict';
// Si Leaflet no cargó (sin internet o sin permiso INTERNET) se avisa en pantalla en vez de dejarla vacía.
if (typeof L === 'undefined') {
  document.body.insertAdjacentHTML('beforeend', '<div class="toast" style="bottom:50%;white-space:normal;text-align:center;max-width:80%">No se pudo cargar el mapa. Revisa tu conexión a internet.</div>');
  return;
}
const B = window.EditorBridge || null;
const $ = (id) => document.getElementById(id);
const ic = (n) => `<svg class="ic"><use href="#i-${n}"/></svg>`;   // icono del sprite del HTML
const TIPOS = { agua: '💧', mobiliario: '🪑', escalones: '🪜', obra: '🚧', vehiculos: '🚗', otro: '⚠️' };
const TIPO_NOMBRE = { agua: 'Agua', mobiliario: 'Mobiliario', escalones: 'Escalones', obra: 'Obra', vehiculos: 'Vehículos', otro: 'Otro' };
const COLOR = { alta: '#ef4444', normal: '#f59e0b' };

const S = {
  alertas: new Map(), lugares: [], sel: null, borrador: null,
  modo: null,                // null | 'colocar' | 'mover'
  moverOrig: null, pend: 0, filtros: { tipo: '', prio: '', estado: '' },
};

// ── Mapa ───────────────────────────────────────
const map = L.map('map', { center: [6.2002, -75.5783], zoom: 17, zoomControl: false, attributionControl: false });
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);
L.control.attribution({ position: 'bottomleft', prefix: false }).addAttribution('© <a href="https://openstreetmap.org">OSM</a>').addTo(map);
L.control.zoom({ position: 'bottomleft' }).addTo(map);
const capas = { alertas: L.layerGroup().addTo(map), lugares: L.layerGroup().addTo(map), cobertura: L.layerGroup(), rutas: L.layerGroup() };
const circulo = L.circle([0, 0], { radius: 15, color: '#ef4444', weight: 2, dashArray: '6 6', fillOpacity: .18 });
let marcaBorrador = null, marcaPos = null;
const marcas = new Map();

// ── Medidas de la interfaz ─────────────────────
// La cabecera y el dock cambian de alto (panel de capas, tarjeta, aviso de mover). Se publican como
// variables CSS para que los botones laterales y los controles del mapa se acomoden sin taparse.
function medir() {
  const r = document.documentElement.style;
  r.setProperty('--toph', $('top').offsetHeight + 'px');
  r.setProperty('--dockh', $('dock').offsetHeight + 'px');
}
if (window.ResizeObserver) { const ro = new ResizeObserver(medir); ro.observe($('top')); ro.observe($('dock')); }
window.addEventListener('resize', medir);

// ── Utilidades ─────────────────────────────────
const call = (fn, ...a) => { if (B && B[fn]) { try { B[fn](...a); } catch (e) { console.warn(fn, e); } return true; } return false; };
function toast(t) { const e = document.createElement('div'); e.className = 'toast'; e.textContent = t; document.body.appendChild(e); setTimeout(() => e.remove(), 2200); }
function confirmar(texto, ok, label = 'Eliminar') {
  const m = document.createElement('div'); m.className = 'modal';
  m.innerHTML = '<div role="alertdialog"><p></p><div class="acts"><button class="no">Cancelar</button><button class="del si"></button></div></div>';
  m.querySelector('p').textContent = texto; m.querySelector('.si').textContent = label;
  m.querySelector('.no').onclick = () => m.remove();
  m.querySelector('.si').onclick = () => { m.remove(); ok(); };
  document.body.appendChild(m); m.querySelector('.no').focus();
}
function visible(a) {
  if (a.id === S.sel) return true;   // los filtros nunca ocultan la alerta seleccionada
  const f = S.filtros;
  return (!f.tipo || a.tipo === f.tipo) && (!f.prio || a.prioridad === f.prio) &&
         (!f.estado || (f.estado === 'activa') === !!a.activa);
}
const icono = (a, sel) => L.divIcon({
  className: '', iconSize: [34, 34], iconAnchor: [17, 34],
  html: `<div class="al${a.activa ? '' : ' off'}${sel ? ' sel' : ''}" style="border-color:${COLOR[a.prioridad] || COLOR.normal}"><span>${TIPOS[a.tipo] || TIPOS.otro}</span></div>`,
});

// ── Pintar ─────────────────────────────────────
function pintar() {
  capas.alertas.clearLayers(); marcas.clear();
  S.alertas.forEach((a) => {
    if (!visible(a)) return;
    const m = L.marker([a.lat, a.lng], { icon: icono(a, a.id === S.sel), draggable: false, keyboard: true, title: a.mensaje })
      .on('click', (e) => { L.DomEvent.stopPropagation(e); if (!S.modo) seleccionar(a.id); })
      .on('dragend', (e) => { const p = e.target.getLatLng(); if (S.sel === a.id) { circulo.setLatLng(p); renderCard(); } });
    m.addTo(capas.alertas); marcas.set(a.id, m);
  });
  if (S.sel && S.alertas.has(S.sel)) {
    const a = S.alertas.get(S.sel);
    circulo.setLatLng([a.lat, a.lng]).setRadius(a.radio).setStyle({ color: COLOR[a.prioridad] || COLOR.normal });
    circulo.addTo(map);
  } else if (!S.borrador) circulo.remove();
  actualizarPend();
}
function actualizarPend() {
  const n = S.pend;
  $('chip').innerHTML = ic(n ? 'cloud' : 'ok') + '<span>' + (n ? `Cambios pendientes (${n})` : 'Todo sincronizado') + '</span>';
  $('chip').classList.toggle('ok', !n);
  $('dot').classList.toggle('pend', !!n);
}

// ── Selección y tarjeta ────────────────────────
function seleccionar(id) { S.sel = id; renderCard(); pintar(); }
function deseleccionar() { S.sel = null; renderCard(); pintar(); }
function renderCard() {
  const c = $('card'), a = S.alertas.get(S.sel);
  c.classList.toggle('hidden', !a || S.modo === 'mover');
  if (!a) { medir(); return; }
  const col = COLOR[a.prioridad] || COLOR.normal;
  c.innerHTML = `<button class="x" aria-label="Cerrar">${ic('x')}</button>
    <div class="c-head"><div class="c-ico"></div>
      <div class="c-ttl"><h2></h2><span class="badge"></span><p class="msg"></p></div></div>
    <div class="c-foot">
      <div class="meta"><div>${ic('pin')}<span class="pos"></span></div><div>${ic('clock')}<span class="rad"></span></div></div>
      <div class="acts">
        <button id="a-mover">${ic('move')}<span>Mover</span></button>
        <button id="a-edit">${ic('edit')}<span>Editar</span></button>
        <button class="del" id="a-del">${ic('trash')}<span>Eliminar</span></button>
      </div>
    </div>`;
  const ci = c.querySelector('.c-ico'); ci.textContent = TIPOS[a.tipo] || TIPOS.otro; ci.style.borderColor = col;
  c.querySelector('h2').textContent = TIPO_NOMBRE[a.tipo] || 'Alerta';
  const bd = c.querySelector('.badge'); bd.textContent = a.prioridad === 'alta' ? 'Alta' : 'Normal'; bd.style.color = col;
  c.querySelector('.msg').textContent = a.mensaje;
  c.querySelector('.pos').textContent = 'Posición: ' + a.lat.toFixed(5) + ', ' + a.lng.toFixed(5);
  c.querySelector('.rad').textContent = 'Radio de activación: ' + a.radio + ' m' + (a.activa ? '' : ' · Inactiva');
  c.querySelector('.x').onclick = deseleccionar;
  $('a-mover').onclick = iniciarMover;
  $('a-edit').onclick = () => abrirForm(a);
  $('a-del').onclick = () => confirmar('¿Eliminar esta alerta? Dejará de avisarse a los usuarios.', () => eliminar(a.id));
  medir();
}

// ── Formulario (7.9 es nativo en Android) ──────
function abrirForm(a, lat, lng) {
  const datos = a ? { id: a.id, lat: a.lat, lng: a.lng } : { id: null, lat, lng };
  if (!call('abrirFormulario', JSON.stringify(datos))) {            // demo en navegador
    const msg = window.prompt('Mensaje de la alerta', a ? a.mensaje : '');
    if (!msg) { cancelarBorrador(); return; }
    upsert({ id: a ? a.id : 'a' + Date.now(), lat: datos.lat, lng: datos.lng, mensaje: msg.slice(0, 200),
             tipo: a ? a.tipo : 'otro', prioridad: a ? a.prioridad : 'normal', radio: a ? a.radio : 15, activa: true }, true);
  }
}
function upsert(a, local) {
  S.alertas.set(a.id, a); cancelarBorrador(true);
  if (local) S.pend++;
  seleccionar(a.id);
}
function eliminar(id) {
  call('eliminarAlerta', id); S.alertas.delete(id); if (!B) S.pend++;
  S.sel = null; renderCard(); pintar(); toast('Alerta eliminada');
}

// ── Colocar nueva alerta ───────────────────────
function entrarColocar() { S.modo = 'colocar'; deseleccionar(); const b = $('btn-new'); b.innerHTML = ic('x') + 'Cancelar'; b.classList.add('cancel'); toast('Toca el mapa para fijar el punto'); }
function salirModo() { S.modo = null; const b = $('btn-new'); b.innerHTML = ic('plus') + 'Nueva alerta'; b.classList.remove('cancel'); }
map.on('click', (e) => {
  if (S.modo === 'colocar') { salirModo(); abrirForm(null, e.latlng.lat, e.latlng.lng); setBorrador({ lat: e.latlng.lat, lng: e.latlng.lng, radio: 15, prioridad: 'normal', tipo: 'otro' }); }
  else if (!S.modo) deseleccionar();                                  // tocar vacío deselecciona
});
$('btn-new').onclick = () => (S.modo === 'colocar' ? salirModo() : S.modo ? null : entrarColocar());

// ── Borrador en vivo (cambios del formulario antes de guardar) ──
function setBorrador(d) {
  if (!d) { cancelarBorrador(); return; }
  S.borrador = d;
  const a = d.id && S.alertas.get(d.id);
  const col = COLOR[d.prioridad] || COLOR.normal;
  circulo.setLatLng([d.lat, d.lng]).setRadius(d.radio || 15).setStyle({ color: col }).addTo(map);
  if (marcaBorrador) marcaBorrador.remove();
  if (!a) marcaBorrador = L.marker([d.lat, d.lng], { icon: icono({ tipo: d.tipo, prioridad: d.prioridad, activa: true }, true), interactive: false }).addTo(map);
  else { const m = marcas.get(d.id); if (m) m.setIcon(icono({ ...a, ...d }, true)); }
}
function cancelarBorrador(keep) {
  S.borrador = null; if (marcaBorrador) { marcaBorrador.remove(); marcaBorrador = null; }
  if (!keep && !S.sel) circulo.remove();
}

// ── Mover (solo ese marcador) ──────────────────
function iniciarMover() {
  const a = S.alertas.get(S.sel), m = marcas.get(S.sel); if (!a || !m) return;
  S.modo = 'mover'; S.moverOrig = { lat: a.lat, lng: a.lng };
  m.dragging.enable(); $('move-bar').classList.remove('hidden'); renderCard();
}
function terminarMover(ok) {
  const a = S.alertas.get(S.sel), m = marcas.get(S.sel);
  if (a && m) {
    if (ok) { const p = m.getLatLng(); a.lat = p.lat; a.lng = p.lng; call('moverAlerta', a.id, p.lat, p.lng); if (!B) S.pend++; toast('Alerta movida'); }
    else { m.setLatLng([S.moverOrig.lat, S.moverOrig.lng]); }   // cancelar restituye la posición
    m.dragging.disable();
  }
  S.modo = null; $('move-bar').classList.add('hidden'); renderCard(); pintar();
}
$('move-ok').onclick = () => terminarMover(true);
$('move-cancel').onclick = () => terminarMover(false);

// ── Filtros, capas y botones ───────────────────
// El select real es invisible y cubre la caja; el valor que se ve se copia en #v-<filtro>.
[['f-tipo', 'tipo'], ['f-prio', 'prio'], ['f-estado', 'estado']].forEach(([id, k]) =>
  $(id).addEventListener('change', (e) => {
    S.filtros[k] = e.target.value; pintar();
    $('v-' + k).textContent = e.target.selectedOptions[0].text;
    $('w-' + k).classList.toggle('on', !!e.target.value);
  }));
document.querySelectorAll('[data-layer]').forEach((c) => c.addEventListener('change', () => {
  const g = capas[c.dataset.layer]; c.checked ? g.addTo(map) : g.remove();
}));
$('btn-pos').onclick = () => { if (!call('pedirMiPosicion')) { if (marcaPos) map.setView(marcaPos.getLatLng(), 18); else toast('Posición no disponible'); } };
const verLista = () => { if (!call('verLista')) toast('Lista de alertas (vista 7.10)'); };
$('btn-list').onclick = verLista; $('btn-lista-top').onclick = verLista;
$('btn-sync').onclick = () => { if (!S.pend) { toast('No hay cambios pendientes'); return; } if (!call('sincronizar')) { S.pend = 0; actualizarPend(); toast('Sincronizado'); } };
$('btn-back').onclick = () => window.onAtras();

// ── API para Kotlin ────────────────────────────
window.cargarAlertas = (json) => { S.alertas.clear(); JSON.parse(json).forEach((a) => S.alertas.set(a.id, a)); if (S.sel && !S.alertas.has(S.sel)) S.sel = null; pintar(); renderCard(); };
window.upsertAlerta = (json) => { const a = JSON.parse(json); upsert(a, false); };
window.quitarAlerta = (id) => { S.alertas.delete(id); if (S.sel === id) S.sel = null; pintar(); renderCard(); };
window.setBorrador = (json) => setBorrador(json ? JSON.parse(json) : null);
window.cargarLugares = (json) => {
  S.lugares = JSON.parse(json); capas.lugares.clearLayers();
  S.lugares.forEach((l) => L.marker([l.lat, l.lng], { icon: L.divIcon({ className: '', iconSize: [26, 26], html: '<div class="pl">📍</div>' }), interactive: false })
    .bindTooltip(l.nombre, { permanent: true, direction: 'bottom', className: 'tip', offset: [0, 8] }).addTo(capas.lugares));
};
window.setMiPosicion = (lat, lng) => {
  if (!marcaPos) marcaPos = L.circleMarker([lat, lng], { radius: 8, color: '#fff', weight: 3, fillColor: '#6366f1', fillOpacity: 1 }).addTo(map);
  marcaPos.setLatLng([lat, lng]); map.setView([lat, lng], Math.max(map.getZoom(), 18));
};
window.setPendientes = (n) => { S.pend = n; actualizarPend(); };
// Alto de la barra de estado y de la barra de navegación (en dp = px CSS). Lo envía Kotlin al cargar y al cambiar.
window.setInsets = (top, bottom) => {
  const r = document.documentElement.style;
  r.setProperty('--sat', top + 'px'); r.setProperty('--sab', bottom + 'px'); medir();
};
// Botón Atrás: sale primero de los modos temporales; devuelve true si lo consumió.
window.onAtras = () => {
  if (S.modo === 'mover') { terminarMover(false); return true; }
  if (S.modo === 'colocar') { salirModo(); return true; }
  if (S.borrador) { cancelarBorrador(); call('cancelarFormulario'); return true; }
  if (S.sel) { deseleccionar(); return true; }
  if (S.pend > 0) { confirmar('Tienes cambios sin sincronizar. ¿Salir de todas formas?', () => { if (!call('salir')) toast('Saliste del editor'); }, 'Salir'); return true; }
  if (!call('salir')) toast('Saliste del editor');
  return true;
};

// ── Arranque ───────────────────────────────────
if (B) call('listo');   // Kotlin responde con cargarAlertas / cargarLugares / setPendientes / setInsets
else {
  cargarDemo();
}
function cargarDemo() {
  window.cargarAlertas(JSON.stringify([
    { id: 'a1', lat: 6.2004, lng: -75.5785, mensaje: 'Ten cuidado, hay bancas cerca, no te vayas a estrellar', tipo: 'mobiliario', prioridad: 'normal', radio: 15, activa: true },
    { id: 'a2', lat: 6.2010, lng: -75.5777, mensaje: 'Rampa de acceso bloqueada por obras de mantenimiento.', tipo: 'obra', prioridad: 'alta', radio: 50, activa: true },
    { id: 'a3', lat: 6.1997, lng: -75.5779, mensaje: 'Escalones al frente.', tipo: 'escalones', prioridad: 'normal', radio: 10, activa: false },
  ]));
  window.cargarLugares(JSON.stringify([{ nombre: 'Biblioteca', lat: 6.2007, lng: -75.5781 }]));
}
actualizarPend(); medir();
})();