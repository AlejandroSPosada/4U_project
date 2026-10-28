package com.example.myapplication.map

import android.annotation.SuppressLint
import android.content.pm.ApplicationInfo
import android.view.ViewGroup
import android.webkit.ConsoleMessage
import android.webkit.WebChromeClient
import android.webkit.WebView
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.example.myapplication.data.local.GrafoDeLaApp
import com.example.myapplication.domain.model.SesionDeNavegacion
import com.example.myapplication.domain.ruta.ResultadoRuta
import com.example.myapplication.logs.AppLog
import com.example.myapplication.sensors.PdrEvento
import com.example.myapplication.sensors.PdrTracker
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.filter
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.mapNotNull
import kotlinx.coroutines.launch

private const val TAG = "MapaPublico"

private data class Posicion(
    val lat: Double,
    val lng: Double,
    val pasos: Int,
    val distanciaM: Double,
    val velocidadMps: Double,
)

/** Llama a `window.<codigo>` en la página; si la función no existe, no pasa nada. */
private fun WebView.js(codigo: String) {
    evaluateJavascript("try{window.$codigo}catch(e){}", null)
}

/**
 * Mapa público (Leaflet + OSM en un WebView) con seguimiento por pasos.
 * El cálculo de la posición NO está en la página: lo hace [PdrTracker] (sensors/) y aquí solo se
 * empuja el resultado a `app.js`.
 *
 * Kotlin → Web: `onNativePosition(lat, lng, pasos, distanciaM, velocidadMps)`,
 * `onNativeHeading(grados)`, `onNativeAccel(desviacion)`, `onNativeBrujula(disponible)`,
 * `onNativeStepUnavailable(motivo)`.
 * Web → Kotlin: ver [PuentePdr].
 *
 * Ruta `mapa` (FE-3.1: desde Inicio por la voz «mapa» o la acción de TalkBack «Ver mapa»; Atrás vuelve a Inicio). Los
 * sensores siguen el ciclo de vida de la entrada de la pila de esta pantalla (ADR-FE-22): se quitan en su `ON_STOP`
 * (app en segundo plano, o el mapa tapado por otra pantalla) y se liberan al salir de la composición.
 *
 * FE-5.1: con un destino (el de `SesionDeNavegacion`, elegido en 6.4, o el de prueba de [PruebaMapa]) y una posición
 * (toque, GPS o la de prueba), calcula la ruta por el grafo (`GrafoDeLaApp`) en cada cambio de posición, la dibuja
 * (`onNativeRuta(json|null)`) y muestra arriba un aviso en Compose con la distancia por el camino y la primera
 * instrucción ([TextosRutaMapa]). La página avisa que está lista con `AndroidBridge.listo()`; en el APK de depuración,
 * la posición de prueba se envía con `onNativeInicio(lat, lng)` (como un toque).
 */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun MapaPublicoScreen(modifier: Modifier = Modifier) {
    val ctx = LocalContext.current
    // FE-3.1 (ADR-FE-22): el tracker sigue el ciclo de vida de esta pantalla (la entrada de la pila), no el del
    // proceso: si el mapa queda en la pila sin ser lo visible (o en otra tarea), sus sensores no vuelven al primer plano.
    val cicloPantalla = LocalLifecycleOwner.current.lifecycle
    val tracker = remember { PdrTracker(ctx, cicloDeVida = cicloPantalla) }
    var webView by remember { mutableStateOf<WebView?>(null) }

    // FE-5.1: ruta por el grafo. `null` = rutas desactivadas (grafo inválido o ilegible; nunca lanza).
    val planificador = remember { runCatching { GrafoDeLaApp.planificador(ctx) }.getOrNull() }
    val destinoSesion by SesionDeNavegacion.destino.collectAsState()
    val destinoPrueba = remember { PruebaMapa.destino }
    var paginaLista by remember { mutableStateOf(false) }
    var posicionActual by remember { mutableStateOf<Pair<Double, Double>?>(null) }
    var aviso by remember { mutableStateOf<AvisoRuta?>(null) }

    DisposableEffect(Unit) {
        onDispose {
            tracker.liberar()
            webView?.destroy()
            PruebaMapa.limpiar()
        }
    }

    // FE-5.1: posición actual (solo cambia con la posición, no con el rumbo).
    LaunchedEffect(tracker) {
        tracker.estado
            .mapNotNull { e ->
                val la = e.lat
                val ln = e.lng
                if (la != null && ln != null) la to ln else null
            }
            .distinctUntilChanged()
            .collect { posicionActual = it }
    }

    // FE-5.1: posición de prueba (solo APK de depuración, PruebaMapa), una vez, cuando la página está lista.
    LaunchedEffect(paginaLista, webView) {
        val w = webView ?: return@LaunchedEffect
        if (!paginaLista) return@LaunchedEffect
        val p = PruebaMapa.posicion ?: return@LaunchedEffect
        PruebaMapa.posicion = null
        w.js("onNativeInicio(${p.first},${p.second})")
    }

    // FE-5.1: ruta en cada cambio de posición o de destino.
    LaunchedEffect(paginaLista, webView, posicionActual, destinoSesion) {
        val nombres: List<String>?
        val mostrar: String?
        if (destinoPrueba != null) {
            nombres = listOf(destinoPrueba)
            mostrar = TextosRutaMapa.nombrePrueba(planificador, destinoPrueba)
        } else {
            val d = destinoSesion
            nombres = d?.let { listOf(it.nombre) + it.alias }
            mostrar = d?.nombre
        }
        val pos = posicionActual
        val resultado = if (planificador != null && nombres != null && mostrar != null && pos != null) {
            val e = tracker.estado.value
            val rumbo = if (e.activo) e.rumboGrados.toDouble() else null
            runCatching { planificador.calcular(pos.first, pos.second, nombres, mostrar, rumbo) }.getOrNull()
        } else {
            null
        }
        aviso = TextosRutaMapa.aviso(mostrar, planificador != null, pos != null, resultado)
        val w = webView
        if (w != null && paginaLista) {
            val ruta = (resultado as? ResultadoRuta.Encontrada)?.ruta
            w.js("onNativeRuta(${ruta?.json() ?: "null"})")
        }
    }

    // Kotlin → Web
    LaunchedEffect(webView) {
        val w = webView ?: return@LaunchedEffect
        tracker.onAceleracion = { d -> w.js("onNativeAccel($d)") }
        try {
            coroutineScope {
                launch {
                    tracker.estado
                        .mapNotNull { e ->
                            val la = e.lat
                            val ln = e.lng
                            if (la != null && ln != null) {
                                Posicion(la, ln, e.pasos, e.distanciaMetros, e.velocidadMps)
                            } else null
                        }
                        .distinctUntilChanged()
                        .collect { p ->
                            w.js("onNativePosition(${p.lat},${p.lng},${p.pasos},${p.distanciaM},${p.velocidadMps})")
                        }
                }
                launch {
                    tracker.estado
                        .filter { it.activo }
                        .map { it.rumboGrados }
                        .distinctUntilChanged()
                        .collect { w.js("onNativeHeading($it)") }
                }
                launch {
                    tracker.eventos.collect { ev ->
                        when (ev) {
                            is PdrEvento.Brujula -> w.js("onNativeBrujula(${ev.disponible})")
                            is PdrEvento.PasosPorAcelerometro ->
                                w.js("onNativeStepUnavailable('${ev.motivo}')")
                        }
                    }
                }
            }
        } finally {
            tracker.onAceleracion = null
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .systemBarsPadding(),
    ) {
        aviso?.let { AvisoRutaMapa(it) }
        AndroidView(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f),
            factory = { c ->
                if (c.applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0) {
                    WebView.setWebContentsDebuggingEnabled(true)
                }
                WebView(c).apply {
                    layoutParams = ViewGroup.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT,
                        ViewGroup.LayoutParams.MATCH_PARENT,
                    )
                    setBackgroundColor(Color(0xFF0A0E1A).toArgb()) // = --bg-dark de index.html
                    settings.javaScriptEnabled = true
                    settings.domStorageEnabled = true
                    webChromeClient = object : WebChromeClient() {
                        override fun onConsoleMessage(m: ConsoleMessage): Boolean {
                            AppLog.d(TAG, "JS: ${m.message()} (línea ${m.lineNumber()})")
                            return true
                        }
                        // Geolocalización: sin sobrescribir onGeolocationPermissionsShowPrompt el
                        // botón GPS falla con un aviso (decisión abierta 14 de ARCHITECTURE.md).
                    }
                    addJavascriptInterface(PuentePdr(tracker) { paginaLista = true }, "AndroidBridge")
                    loadUrl("file:///android_asset/index.html")
                    webView = this
                }
            },
        )
    }
}

/** FE-5.1: aviso de ruta sobre el mapa (lo lee TalkBack al cambiar y `uiautomator` en la validación). */
@Composable
private fun AvisoRutaMapa(aviso: AvisoRuta) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(Color(0xFF0A0E1A))
            .padding(horizontal = 16.dp, vertical = 10.dp)
            .semantics { liveRegion = LiveRegionMode.Polite },
    ) {
        Text(aviso.titulo, color = Color.White, fontSize = 18.sp, fontWeight = FontWeight.Bold)
        aviso.detalle?.let { Text(it, color = Color(0xFFB9F6CA), fontSize = 16.sp) }
    }
}