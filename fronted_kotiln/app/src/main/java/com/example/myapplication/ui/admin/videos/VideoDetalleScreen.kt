package com.example.myapplication.ui.admin.videos

import android.annotation.SuppressLint
import android.content.pm.ApplicationInfo
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.ViewGroup
import android.webkit.ConsoleMessage
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBars
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import org.json.JSONObject

/** Eventos que el mapa web (video_detalle.js) envía a la app. */
interface VideoDetalleEventos {
    fun abrirFoto(fotoId: String)
    fun renombrar(nombre: String)
    fun eliminarFoto(fotoId: String)
    fun eliminarVideo()
    fun salir()
}

/** Vista 7.14 — Detalle de video. Es la que se usa en el NavHost. */
@Composable
fun VideoDetalleScreen(
    videoId: String,
    onVolver: () -> Unit,
    onAbrirImagen: (videoId: String, fotoId: String) -> Unit,
    modifier: Modifier = Modifier.fillMaxSize(),
    vm: VideoDetalleViewModel = viewModel(
        key = "video-$videoId",
        factory = VideoDetalleViewModel.Factory(LocalContext.current.applicationContext, videoId),
    ),
) {
    val ui by vm.ui.collectAsStateWithLifecycle()

    Box(modifier) {
        VideoDetalleContent(
            videoJson = ui.videoJson,
            otrosJson = ui.otrosJson,
            eventos = object : VideoDetalleEventos {
                override fun abrirFoto(fotoId: String) = onAbrirImagen(videoId, fotoId)
                override fun renombrar(nombre: String) = vm.renombrar(nombre)
                override fun eliminarFoto(fotoId: String) = vm.eliminarFoto(fotoId)
                override fun eliminarVideo() = vm.eliminarVideo()
                override fun salir() = onVolver()
            },
        )
        if (ui.noEncontrado) NoEncontrado(onVolver)
    }
}

/**
 * Solo dibuja el WebView (`assets/video_detalle.html`: Leaflet + OpenStreetMap en línea).
 * Recibe todo como JSON; no conoce el ViewModel.
 */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun VideoDetalleContent(
    videoJson: String?,
    otrosJson: String,
    eventos: VideoDetalleEventos,
    modifier: Modifier = Modifier.fillMaxSize(),
) {
    var webView by remember { mutableStateOf<WebView?>(null) }
    var listo by remember { mutableStateOf(false) }
    val eventosActuales by rememberUpdatedState(eventos)

    // Con edge-to-edge el WebView ocupa toda la pantalla y `env(safe-area-inset-*)` no funciona en
    // WebView, así que el alto de las barras del sistema se lo pasamos a la página.
    val density = LocalDensity.current
    val barras = WindowInsets.systemBars
    val topDp = barras.getTop(density) / density.density
    val bottomDp = barras.getBottom(density) / density.density

    fun js(code: String) { webView?.evaluateJavascript(code, null) }   // siempre en el hilo principal
    fun lit(s: String) = JSONObject.quote(s)                           // JSON → literal de JavaScript

    // El JS cierra primero el diálogo o la foto seleccionada y al final llama a salir().
    BackHandler { js("window.onAtras()") }

    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            WebView(ctx).apply {
                layoutParams = ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
                setBackgroundColor(android.graphics.Color.parseColor("#0A0E1A"))   // mismo fondo oscuro que la página
                settings.javaScriptEnabled = true
                settings.domStorageEnabled = true   // caché de teselas
                if (ctx.applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0) {
                    WebView.setWebContentsDebuggingEnabled(true)   // chrome://inspect en la PC
                }
                webChromeClient = object : WebChromeClient() {
                    override fun onConsoleMessage(m: ConsoleMessage): Boolean {
                        Log.d(TAG, "JS ${m.messageLevel()}: ${m.message()} (${m.sourceId()}:${m.lineNumber()})")
                        return true
                    }
                }
                webViewClient = object : WebViewClient() {
                    override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                        Log.e(TAG, "Error cargando ${request.url}: ${error.description}")
                    }
                }
                val main = Handler(Looper.getMainLooper())
                // Estas funciones corren en un hilo del WebView: todo se pasa al hilo principal.
                addJavascriptInterface(object {
                    @JavascriptInterface fun listo() { main.post { listo = true } }
                    @JavascriptInterface fun abrirFoto(id: String) { main.post { eventosActuales.abrirFoto(id) } }
                    @JavascriptInterface fun renombrar(nombre: String) { main.post { eventosActuales.renombrar(nombre) } }
                    @JavascriptInterface fun eliminarFoto(id: String) { main.post { eventosActuales.eliminarFoto(id) } }
                    @JavascriptInterface fun eliminarVideo() { main.post { eventosActuales.eliminarVideo() } }
                    @JavascriptInterface fun salir() { main.post { eventosActuales.salir() } }
                }, "VideoBridge")
                loadUrl("file:///android_asset/video_detalle.html")
                webView = this
            }
        },
        onRelease = { it.destroy(); webView = null },
    )

    // Empuja el estado al mapa cuando la página avisa que está lista y cada vez que cambia.
    LaunchedEffect(listo, topDp, bottomDp) { if (listo) js("setInsets($topDp, $bottomDp)") }
    LaunchedEffect(listo, otrosJson) { if (listo) js("cargarOtros(${lit(otrosJson)})") }
    LaunchedEffect(listo, videoJson) { if (listo && videoJson != null) js("cargarVideo(${lit(videoJson)})") }
}

@Composable
private fun NoEncontrado(onVolver: () -> Unit) {
    Column(
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xFF0A0E1A))
            .padding(24.dp),
    ) {
        Text("No se encontró este video.", color = Color.White, fontSize = 16.sp)
        Button(onClick = onVolver, modifier = Modifier.padding(top = 16.dp)) { Text("Volver") }
    }
}

private const val TAG = "VideoDetalle"