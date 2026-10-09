package com.example.myapplication.ui.admin.mapa

import android.annotation.SuppressLint
import android.content.pm.ApplicationInfo
import android.graphics.Color
import android.util.Log
import android.view.ViewGroup
import android.webkit.ConsoleMessage
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.os.Handler
import android.os.Looper
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.systemBars
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import org.json.JSONObject

/** Eventos que el mapa web (editor_mapa.js) envía a la app. */
interface EditorMapaEventos {
    fun abrirFormulario(id: String?, lat: Double, lng: Double)
    fun cancelarFormulario()
    fun moverAlerta(id: String, lat: Double, lng: Double)
    fun eliminarAlerta(id: String)
    fun sincronizar()
    fun verLista()
    fun pedirMiPosicion()
    fun salir()
}

/** Vista 7.8 — Editor de mapa y alertas. Es la que se usa en el NavHost. */
@Composable
fun EditorMapaScreen(
    onVolver: () -> Unit,
    onVerLista: () -> Unit,
    posicionAdmin: () -> Pair<Double, Double>?,
    modifier: Modifier = Modifier.fillMaxSize(),
    vm: EditorMapaViewModel = viewModel(),
) {
    val ui by vm.ui.collectAsStateWithLifecycle()
    var miPos by remember { mutableStateOf<Pair<Double, Double>?>(null) }

    EditorMapaContent(
        alertasJson = ui.alertasJson,
        lugaresJson = ui.lugaresJson,
        pendientes = ui.pendientes.size,
        borradorJson = ui.borradorJson,
        miPosicion = miPos,
        modifier = modifier,
        eventos = object : EditorMapaEventos {
            override fun abrirFormulario(id: String?, lat: Double, lng: Double) = vm.abrirFormulario(id, lat, lng)
            override fun cancelarFormulario() = vm.cancelarFormulario()
            override fun moverAlerta(id: String, lat: Double, lng: Double) = vm.mover(id, lat, lng)
            override fun eliminarAlerta(id: String) = vm.eliminar(id)
            override fun sincronizar() = vm.sincronizar()
            override fun verLista() = onVerLista()
            override fun pedirMiPosicion() { miPos = posicionAdmin() }
            override fun salir() = onVolver()
        },
    )

    ui.formulario?.let { alerta ->
        AlertaFormSheet(
            alerta = alerta,
            esNueva = ui.formularioEsNuevo,
            error = ui.error,
            onCambio = vm::actualizarFormulario,
            onGuardar = vm::guardarFormulario,
            onCancelar = vm::cancelarFormulario,
            onEliminar = { vm.eliminar(alerta.id); vm.cancelarFormulario() },
        )
    }
}

/**
 * Solo dibuja el WebView (`assets/editor_mapa.html`: Leaflet + OpenStreetMap en línea).
 * Recibe todo como JSON; no conoce el ViewModel.
 */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun EditorMapaContent(
    alertasJson: String,
    lugaresJson: String,
    pendientes: Int,
    borradorJson: String?,
    eventos: EditorMapaEventos,
    modifier: Modifier = Modifier.fillMaxSize(),
    miPosicion: Pair<Double, Double>? = null,
) {
    var webView by remember { mutableStateOf<WebView?>(null) }
    var listo by remember { mutableStateOf(false) }
    val eventosActuales by rememberUpdatedState(eventos)

    // Barra de estado y de navegación en dp. Con edge-to-edge el WebView ocupa toda la pantalla y
    // `env(safe-area-inset-*)` no funciona en WebView, así que el alto se lo pasamos a la página.
    val density = LocalDensity.current
    val barras = WindowInsets.systemBars
    val topDp = barras.getTop(density) / density.density
    val bottomDp = barras.getBottom(density) / density.density

    fun js(code: String) { webView?.evaluateJavascript(code, null) }   // siempre en el hilo principal
    fun lit(s: String) = JSONObject.quote(s)                           // JSON → literal de JavaScript

    // El JS sale de los modos temporales (mover, colocar, formulario) y al final llama a salir().
    BackHandler { js("window.onAtras()") }

    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            WebView(ctx).apply {
                // Sin tamaño explícito el WebView puede quedar en 0×0 y la pantalla se ve en blanco.
                layoutParams = ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
                setBackgroundColor(Color.parseColor("#0A0E1A"))   // mismo fondo oscuro que la página
                settings.javaScriptEnabled = true
                settings.domStorageEnabled = true   // caché de teselas
                if (ctx.applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0) {
                    WebView.setWebContentsDebuggingEnabled(true)   // chrome://inspect en la PC
                }
                // Diagnóstico: errores de carga y mensajes de consola en Logcat (tag "EditorMapa").
                webChromeClient = object : WebChromeClient() {
                    override fun onConsoleMessage(m: ConsoleMessage): Boolean {
                        Log.d("EditorMapa", "JS ${m.messageLevel()}: ${m.message()} (${m.sourceId()}:${m.lineNumber()})")
                        return true
                    }
                }
                webViewClient = object : WebViewClient() {
                    override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                        Log.e("EditorMapa", "Error cargando ${request.url}: ${error.description}")
                    }
                }
                val main = Handler(Looper.getMainLooper())
                // Estas funciones corren en un hilo del WebView: todo se pasa al hilo principal.
                addJavascriptInterface(object {
                    @JavascriptInterface fun listo() { main.post { listo = true } }
                    @JavascriptInterface fun abrirFormulario(json: String) {
                        main.post {
                            val o = JSONObject(json)
                            val id = if (o.isNull("id")) null else o.getString("id")
                            eventosActuales.abrirFormulario(id, o.getDouble("lat"), o.getDouble("lng"))
                        }
                    }
                    @JavascriptInterface fun cancelarFormulario() { main.post { eventosActuales.cancelarFormulario() } }
                    @JavascriptInterface fun moverAlerta(id: String, lat: Double, lng: Double) { main.post { eventosActuales.moverAlerta(id, lat, lng) } }
                    @JavascriptInterface fun eliminarAlerta(id: String) { main.post { eventosActuales.eliminarAlerta(id) } }
                    @JavascriptInterface fun sincronizar() { main.post { eventosActuales.sincronizar() } }
                    @JavascriptInterface fun verLista() { main.post { eventosActuales.verLista() } }
                    @JavascriptInterface fun pedirMiPosicion() { main.post { eventosActuales.pedirMiPosicion() } }
                    @JavascriptInterface fun salir() { main.post { eventosActuales.salir() } }
                }, "EditorBridge")
                loadUrl("file:///android_asset/editor_mapa.html")
                webView = this
            }
        },
        onRelease = { it.destroy(); webView = null },
    )

    // Empuja el estado al mapa cuando la página avisa que está lista y cada vez que cambia.
    LaunchedEffect(listo, topDp, bottomDp) { if (listo) js("setInsets($topDp, $bottomDp)") }
    LaunchedEffect(listo, alertasJson) { if (listo) js("cargarAlertas(${lit(alertasJson)})") }
    LaunchedEffect(listo, lugaresJson) { if (listo) js("cargarLugares(${lit(lugaresJson)})") }
    LaunchedEffect(listo, pendientes) { if (listo) js("setPendientes($pendientes)") }
    LaunchedEffect(listo, borradorJson) { if (listo) js("setBorrador(${borradorJson?.let(::lit) ?: "null"})") }
    LaunchedEffect(listo, miPosicion) { if (listo && miPosicion != null) js("setMiPosicion(${miPosicion.first}, ${miPosicion.second})") }
}