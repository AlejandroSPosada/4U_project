package com.example.myapplication.ui.ubicacion

import android.app.Application
import android.os.SystemClock
import androidx.lifecycle.AndroidViewModel
import com.example.myapplication.data.local.GrafoDeLaApp
import com.example.myapplication.domain.model.LugarDestino
import com.example.myapplication.domain.model.SesionDeNavegacion
import com.example.myapplication.domain.model.UbicacionEstimada
import com.example.myapplication.domain.ruta.Planificador
import com.example.myapplication.domain.ruta.ResultadoRuta
import com.example.myapplication.domain.usecase.ConversionRumbo
import com.example.myapplication.domain.usecase.DescribirUbicacion
import com.example.myapplication.logs.AppLog
import com.example.myapplication.sensors.Declinacion
import com.example.myapplication.ui.inicio.VoiceController
import com.example.myapplication.ui.ubicacion.EscaneoConfig.INCLINACION_MAX
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlin.math.abs

private const val TAG = "ResultadoVM"

/**
 * Cerebro de la vista 6.3 (Resultado de ubicación, FE-3.2).
 *
 * Lee **una vez**, al crearse, la ubicación y el destino de `SesionDeNavegacion` (decisión abierta 15, ADR-FE-24) y los
 * describe con `DescribirUbicacion`. Lo dice en voz alta al abrir ([alAbrir], una sola vez) y cuando la persona pide
 * «Repetir en voz alta» ([repetir]), con el rumbo que tenga en ese momento: el de la brújula (pantalla →
 * [onOrientacion], convertido a norte verdadero con la declinación) o, sin lectura todavía, el del final del escaneo.
 * La dirección relativa de las referencias usa ese rumbo más la `correccion_rumbo_grados` del backend.
 *
 * FE-5.1: con un destino que está en el grafo (`GrafoDeLaApp`), dice la distancia **por el camino** y la primera
 * instrucción en lugar de la línea recta; deja una línea `Ruta` al abrir (sin posición ni nombres).
 *
 * Qué NO hace: no navega (las acciones van a `AppNav`), no escucha comandos de voz (FE-3.5, decisión del usuario del
 * 2026-10-26) y no muestra mapa ni alertas (FE-3.6).
 */
class ResultadoUbicacionViewModel(app: Application) : AndroidViewModel(app) {

    private val voz = VoiceController(app)
    private val ubicacion: UbicacionEstimada? = SesionDeNavegacion.ubicacion.value
    private val destino: LugarDestino? = SesionDeNavegacion.destino.value
    private val declinacion = Declinacion.paraLaUltimaPosicion()
    // FE-5.1: null si el grafo es inválido o no se pudo leer (rutas desactivadas; nunca lanza).
    private val planificador: Planificador? = runCatching { GrafoDeLaApp.planificador(app) }.getOrNull()

    private var rumboVivo: Double? = null     // rumbo verdadero de la brújula (sin corregir), o null sin lectura
    private var ultimaActualizacion = 0L      // para no recalcular los textos a 50 Hz
    private var abierto = false

    private val _estado = MutableStateFlow(calcular())
    val estado: StateFlow<ResultadoUiState> = _estado.asStateFlow()

    init {
        AppLog.i(
            TAG,
            "Resultado: ${ubicacion?.ubicado?.nivel?.etiqueta ?: if (ubicacion == null) "sin ubicación" else "sin_coincidencias"}" +
                ", destino ${if (destino != null) "sí" else "no"}",
        )
        if (destino != null) registrarRuta()
    }

    /** Línea `Ruta` (FE-5.1): si hay ruta por el grafo, sus metros e instrucciones; si no, por qué (sin posición ni nombres). */
    private fun registrarRuta() {
        val p = ubicacion?.ubicado?.posicion
        val d = destino ?: return
        val texto = when {
            planificador == null -> "sin ruta (grafo no disponible)"
            p == null -> "sin ruta (sin posición)"
            else -> when (val r = planificador.calcular(p.lat, p.lng, d, null)) {
                is ResultadoRuta.Encontrada ->
                    "ruta por el camino: ${Math.round(r.ruta.metros)} m, ${r.ruta.instrucciones.size} instrucciones" +
                        if (r.ruta.fueraDelCamino) ", fuera del camino" else ""
                ResultadoRuta.DestinoFueraDelGrafo -> "sin ruta (destino fuera del grafo)"
                ResultadoRuta.SinCamino -> "sin ruta (sin camino)"
            }
        }
        AppLog.i(TAG_RUTA, "Resultado: $texto")
    }

    /** Al entrar en composición: dice el resultado una sola vez (al volver de otra pantalla no lo repite). */
    fun alAbrir() {
        if (abierto) return
        abierto = true
        hablar()
    }

    /** «Repetir en voz alta»: recalcula las direcciones con el rumbo actual y lo vuelve a decir. */
    fun repetir() = hablar()

    /** Acimut magnético y cabeceo de `EscucharOrientacion` (~50 Hz): solo cuenta con el celular vertical. */
    fun onOrientacion(acimutGrados: Float, cabeceoGrados: Float) {
        if (abs(cabeceoGrados) > INCLINACION_MAX) return
        rumboVivo = ConversionRumbo.magneticoAVerdadero(acimutGrados.toDouble(), declinacion)
        val ahora = SystemClock.elapsedRealtime()
        if (ahora - ultimaActualizacion >= ACTUALIZAR_CADA_MS) {
            ultimaActualizacion = ahora
            _estado.value = calcular()
        }
    }

    /** `ON_STOP` de la pantalla o antes de navegar: calla la voz. */
    fun alPausar() = voz.stopAll()

    private fun hablar() {
        val e = calcular()
        _estado.value = e
        voz.speak(e.descripcion.hablado)
    }

    private fun calcular(): ResultadoUiState {
        val rumbo = rumboVivo ?: ubicacion?.rumboAlTerminar
        return ResultadoUiState(
            descripcion = DescribirUbicacion.describir(ubicacion, rumbo, destino, planificador),
            hayPosicion = ubicacion?.ubicado != null,
        )
    }

    override fun onCleared() {
        voz.release()
    }

    private companion object {
        const val ACTUALIZAR_CADA_MS = 1_000L
        const val TAG_RUTA = "Ruta"
    }
}
