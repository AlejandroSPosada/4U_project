package com.example.myapplication.ui.components

import android.annotation.SuppressLint
import android.os.Handler
import android.util.Log
import android.os.Looper
import android.webkit.ConsoleMessage
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import com.example.myapplication.domain.model.Alerta
import com.example.myapplication.map.MbtilesReader
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayInputStream

/** Capas que el admin puede mostrar/ocultar. */
data class CapasMapa(
    val alertas: Boolean = true,
    val lugares: Boolean = true,
    val cobertura: Boolean = false,
    val rutas: Boolean = false,
)

/** Acciones imperativas sobre el mapa (zoom, centrar). */
class MapaCampusController {
    internal var webView: WebView? = null

    fun zoomIn() = js("EditorMapa.zoom(1)")
    fun zoomOut() = js("EditorMapa.zoom(-1)")
    fun centrarEn(lat: Double, lng: Double, zoom: Double? = null) =
        js("EditorMapa.centrar($lat,$lng,${zoom ?: "null"})")

    internal fun js(codigo: String) {
        webView?.evaluateJavascript(codigo, null)
    }
}

private const val HOST = "campus.local"

/**
 * Mapa base del campus (`eafit.mbtiles`, vectorial) dibujado con MapLibre GL JS dentro de
 * un WebView, igual que el visor de script2.py. Funciona sin conexión: el WebView nunca
 * sale a internet; todas sus peticiones (HTML, JS, tiles) se atienden aquí.
 */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun MapaCampus(
    controller: MapaCampusController,
    alertas: List<Alerta>,
    seleccionId: String?,
    moverId: String?,
    modoColocar: Boolean,
    capas: CapasMapa,
    posicionAdmin: Pair<Double, Double>?,
    onAlertaToque: (String) -> Unit,
    onMapaToque: (lat: Double, lng: Double) -> Unit,
    onAlertaMovida: (id: String, lat: Double, lng: Double) -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current

    val lector by produceState<Result<MbtilesReader>?>(initialValue = null) {
        value = runCatching { MbtilesReader.abrir(context) }
    }
    DisposableEffect(lector) {
        // Se captura AHORA: dentro de onDispose, `lector` ya valdría el lector nuevo
        val abierto = lector?.getOrNull()
        onDispose { abierto?.close() }
    }

    val alToque by rememberUpdatedState(onAlertaToque)
    val mapaToque by rememberUpdatedState(onMapaToque)
    val alMovida by rememberUpdatedState(onAlertaMovida)
    var listo by remember { mutableStateOf(false) }

    Box(modifier.fillMaxSize()) {
        val resultado = lector
        when {
            resultado == null -> CircularProgressIndicator(Modifier.align(Alignment.Center))
            resultado.isFailure -> Text(
                "No se pudo abrir el mapa del campus (${resultado.exceptionOrNull()?.message})",
                color = Color.White,
                modifier = Modifier.align(Alignment.Center),
            )
            else -> {
                val mbtiles = resultado.getOrThrow()
                AndroidView(
                    modifier = Modifier.fillMaxSize(),
                    factory = { ctx ->
                        val main = Handler(Looper.getMainLooper())
                        WebView(ctx).apply {
                            setBackgroundColor(0xFF0D0B14.toInt())
                            settings.javaScriptEnabled = true
                            settings.allowFileAccess = false
                            settings.allowContentAccess = false
                            settings.domStorageEnabled = false
                            settings.setSupportZoom(false)

                            addJavascriptInterface(
                                PuenteJs(
                                    main = main,
                                    onListo = { listo = true },
                                    onAlertaToque = { alToque(it) },
                                    onMapaToque = { la, lo -> mapaToque(la, lo) },
                                    onAlertaMovida = { id, la, lo -> alMovida(id, la, lo) },
                                    onError = { Log.e("MapaCampus", "JS: $it") },
                                ),
                                "CampusBridge",
                            )
                            // Depuración: consola JS -> Logcat (filtro "MapaCampusJS");
                            // además permite chrome://inspect. Quitar en producción.
                            WebView.setWebContentsDebuggingEnabled(true)
                            webChromeClient = object : WebChromeClient() {
                                override fun onConsoleMessage(m: ConsoleMessage): Boolean {
                                    Log.d("MapaCampusJS", "${m.message()} (${m.sourceId()}:${m.lineNumber()})")
                                    return true
                                }
                            }
                            webViewClient = ClienteLocal({ ctx.assets.open(it) }, mbtiles)
                            controller.webView = this
                            loadUrl("https://$HOST/index.html")
                        }
                    },
                    onRelease = { wv ->
                        controller.webView = null
                        wv.destroy()
                    },
                )

                // ---- Estado de Compose -> mapa (solo cuando el mapa terminó de cargar) ----
                LaunchedEffect(listo, alertas) {
                    if (listo) controller.js("EditorMapa.setAlertas(${alertasJson(alertas)})")
                }
                LaunchedEffect(listo, seleccionId) {
                    if (listo) controller.js("EditorMapa.setSeleccion(${jsString(seleccionId)})")
                }
                LaunchedEffect(listo, moverId) {
                    if (listo) controller.js("EditorMapa.setMover(${jsString(moverId)})")
                }
                LaunchedEffect(listo, modoColocar) {
                    if (listo) controller.js("EditorMapa.setModoColocar($modoColocar)")
                }
                LaunchedEffect(listo, capas) {
                    if (listo) controller.js(
                        "EditorMapa.setCapas({alertas:${capas.alertas},lugares:${capas.lugares}," +
                                "cobertura:${capas.cobertura},rutas:${capas.rutas}})",
                    )
                }
                LaunchedEffect(listo, posicionAdmin) {
                    if (listo) {
                        val p = posicionAdmin
                        controller.js(
                            if (p == null) "EditorMapa.setUsuario(null,null)"
                            else "EditorMapa.setUsuario(${p.first},${p.second})",
                        )
                    }
                }
            }
        }
    }
}

private fun jsString(valor: String?): String =
    if (valor == null) "null" else JSONObject.quote(valor)

private fun alertasJson(alertas: List<Alerta>): String =
    JSONArray().apply {
        alertas.forEach { a ->
            put(
                JSONObject()
                    .put("id", a.id)
                    .put("lat", a.latitud)
                    .put("lng", a.longitud)
                    .put("mensaje", a.mensaje)
                    .put("tipo", a.tipo.name)
                    .put("prioridad", a.prioridad.name)
                    .put("activa", a.activa)
                    .put("radio", a.radioM),
            )
        }
    }.toString()

/** Puente JS -> Kotlin. Los métodos llegan en un hilo del WebView: se reenvían al principal. */
private class PuenteJs(
    private val main: Handler,
    private val onListo: () -> Unit,
    private val onAlertaToque: (String) -> Unit,
    private val onMapaToque: (Double, Double) -> Unit,
    private val onAlertaMovida: (String, Double, Double) -> Unit,
    private val onError: (String) -> Unit,
) {
    @JavascriptInterface fun listo() { main.post { onListo() } }
    @JavascriptInterface fun alertaToque(id: String) { main.post { onAlertaToque(id) } }
    @JavascriptInterface fun mapaToque(lat: Double, lng: Double) { main.post { onMapaToque(lat, lng) } }
    @JavascriptInterface fun alertaMovida(id: String, lat: Double, lng: Double) {
        main.post { onAlertaMovida(id, lat, lng) }
    }
    @JavascriptInterface fun error(mensaje: String) { main.post { onError(mensaje) } }
}

/**
 * Atiende todo lo que pide el WebView sin tocar la red:
 *   /index.html, /maplibre-gl.js, /maplibre-gl.css  -> assets/map/
 *   /meta.json                                      -> metadata del MBTiles
 *   /tiles/{z}/{x}/{y}.pbf                          -> tabla `tiles` de eafit.mbtiles
 */
private class ClienteLocal(
    private val abrirAsset: (String) -> java.io.InputStream,
    private val mbtiles: MbtilesReader,
) : WebViewClient() {

    override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse {
        val url = request.url
        if (url.host != HOST) return respuesta(404, "text/plain", ByteArray(0))
        val ruta = url.path ?: "/"

        // Una excepción aquí llegaría sin captura al hilo del WebView y mataría la app
        return try {
            atender(ruta)
        } catch (e: Exception) {
            Log.e("MapaCampus", "Error sirviendo $ruta", e)
            respuesta(500, "text/plain", ByteArray(0))
        }
    }

    private fun atender(ruta: String): WebResourceResponse {
        return when {
            ruta == "/" || ruta == "/index.html" -> asset("map/editor_mapa.html", "text/html")
            ruta == "/maplibre-gl.js" -> asset("map/maplibre-gl.js", "application/javascript")
            ruta == "/maplibre-gl.css" -> asset("map/maplibre-gl.css", "text/css")
            ruta == "/meta.json" ->
                respuesta(200, "application/json", mbtiles.metaJson().toByteArray(), "utf-8")
            ruta.startsWith("/tiles/") -> tile(ruta)
            else -> respuesta(404, "text/plain", ByteArray(0))
        }
    }

    private fun tile(ruta: String): WebResourceResponse {
        val partes = ruta.removePrefix("/tiles/").removeSuffix(".pbf").split("/")
        val z = partes.getOrNull(0)?.toIntOrNull()
        val x = partes.getOrNull(1)?.toIntOrNull()
        val y = partes.getOrNull(2)?.toIntOrNull()
        if (z == null || x == null || y == null) return respuesta(400, "text/plain", ByteArray(0))
        val datos = mbtiles.tile(z, x, y) ?: return respuesta(204, "application/x-protobuf", ByteArray(0))
        return respuesta(200, "application/x-protobuf", datos)
    }

    private fun asset(nombre: String, mime: String): WebResourceResponse =
        try {
            respuesta(200, mime, abrirAsset(nombre).use { it.readBytes() }, "utf-8")
        } catch (e: Exception) {
            respuesta(404, "text/plain", ByteArray(0))
        }

    private fun respuesta(codigo: Int, mime: String, cuerpo: ByteArray, codificacion: String? = null) =
        WebResourceResponse(
            mime, codificacion, codigo,
            if (codigo == 200) "OK" else "Error",
            mapOf("Access-Control-Allow-Origin" to "*"),
            ByteArrayInputStream(cuerpo),
        )
}