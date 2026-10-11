package com.example.myapplication.sensors

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.hardware.GeomagneticField
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Build
import android.os.SystemClock
import androidx.core.content.ContextCompat
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlin.math.abs
import kotlin.math.atan2

enum class FuentePasos { NINGUNA, HARDWARE, ACELEROMETRO_SIN_PERMISO, ACELEROMETRO_SIN_SENSOR }

data class PdrEstado(
    val lat: Double? = null,
    val lng: Double? = null,
    /** Grados, 0 = norte real, sentido horario. */
    val rumboGrados: Float = 0f,
    val pasos: Int = 0,
    val distanciaMetros: Double = 0.0,
    val velocidadMps: Double = 0.0,
    val activo: Boolean = false,
    val fuentePasos: FuentePasos = FuentePasos.NINGUNA,
)

/** Avisos de una sola vez (no son estado). */
sealed interface PdrEvento {
    /** Se evalúa en cada [PdrTracker.iniciar]: ¿hay sensor de rotación para el rumbo? */
    data class Brujula(val disponible: Boolean) : PdrEvento

    /** Los pasos se detectan con el acelerómetro. [motivo]: `permission_denied` o `no_sensor`. */
    data class PasosPorAcelerometro(val motivo: String) : PdrEvento
}

/**
 * Conecta los sensores de Android con [PdrEngine]. No depende de ninguna pantalla ni del WebView:
 * cualquier vista que necesite la posición (mapa público, recolección, navegación guiada) crea uno,
 * llama a [fijarPosicion] + [iniciar] y lee [estado].
 *
 * Hilo: todo ocurre en el hilo principal (los sensores se registran sin `Handler`, así que sus
 * callbacks llegan al principal). Quien lo llame desde otro hilo debe pasar al principal antes.
 *
 * Pasos: `TYPE_STEP_DETECTOR` si existe y hay permiso `ACTIVITY_RECOGNITION` (Android 10+);
 * si no, detección por acelerómetro ([StepDetector]).
 * Rumbo: `TYPE_ROTATION_VECTOR`, corregido a norte real con la declinación magnética de la
 * posición actual.
 */
class PdrTracker(context: Context) {

    private val app = context.applicationContext
    private val sm = app.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    private val engine = PdrEngine()
    private val detector = StepDetector()

    private val _estado = MutableStateFlow(PdrEstado())
    val estado: StateFlow<PdrEstado> = _estado.asStateFlow()

    private val _eventos = MutableSharedFlow<PdrEvento>(extraBufferCapacity = 8)
    val eventos: SharedFlow<PdrEvento> = _eventos.asSharedFlow()

    /** Desviación de la aceleración (m/s²), ~20 Hz, para dibujar gráficas. Hilo principal. */
    var onAceleracion: ((Float) -> Unit)? = null

    private var activo = false
    private var fuente = FuentePasos.NINGUNA
    private var declinacion = 0f
    private var ultimoRumboPublicadoMs = 0L
    private var ultimaAceleracionMs = 0L

    // ── API ────────────────────────────────────

    /** Fija el punto de partida. Úsalo antes de [iniciar] (o al tocar otro punto del mapa). */
    fun fijarPosicion(lat: Double, lng: Double) {
        engine.fijarPosicion(lat, lng)
        actualizarDeclinacion()
        publicar()
    }

    fun fijarRumboManual(grados: Float) {
        engine.fijarRumboManual(grados)
        publicar()
    }

    fun reiniciar() {
        engine.reiniciar()
        detector.reiniciar()
        publicar()
    }

    fun iniciar() {
        if (activo) return
        activo = true
        detector.reiniciar()
        actualizarDeclinacion()

        val rotacion = sm.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)
        if (rotacion != null) {
            sm.registerListener(listenerRumbo, rotacion, SensorManager.SENSOR_DELAY_GAME)
        }
        _eventos.tryEmit(PdrEvento.Brujula(rotacion != null))

        val permiso = Build.VERSION.SDK_INT < Build.VERSION_CODES.Q ||
            ContextCompat.checkSelfPermission(app, Manifest.permission.ACTIVITY_RECOGNITION) ==
            PackageManager.PERMISSION_GRANTED
        val sensorPasos = if (permiso) sm.getDefaultSensor(Sensor.TYPE_STEP_DETECTOR) else null
        if (sensorPasos != null) {
            fuente = FuentePasos.HARDWARE
            sm.registerListener(listenerPasos, sensorPasos, SensorManager.SENSOR_DELAY_FASTEST)
        } else {
            fuente = if (!permiso) FuentePasos.ACELEROMETRO_SIN_PERMISO
            else FuentePasos.ACELEROMETRO_SIN_SENSOR
            _eventos.tryEmit(
                PdrEvento.PasosPorAcelerometro(if (!permiso) "permission_denied" else "no_sensor")
            )
        }

        // El acelerómetro siempre corre (gráfica); solo cuenta pasos si no hay sensor de hardware.
        sm.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)?.let {
            sm.registerListener(listenerAcel, it, SensorManager.SENSOR_DELAY_GAME)
        }
        publicar()
    }

    fun detener() {
        if (!activo) return
        activo = false
        sm.unregisterListener(listenerRumbo)
        sm.unregisterListener(listenerPasos)
        sm.unregisterListener(listenerAcel)
        publicar()
    }

    /** Llamar al destruir la pantalla que lo creó. */
    fun liberar() {
        detener()
        onAceleracion = null
    }

    // ── Sensores ───────────────────────────────

    private val matriz = FloatArray(9)

    private val listenerRumbo = object : SensorEventListener {
        override fun onSensorChanged(e: SensorEvent) {
            SensorManager.getRotationMatrixFromVector(matriz, e.values)
            engine.onRumboSensor(rumboDesdeMatriz(matriz) + declinacion)
            val ahora = SystemClock.elapsedRealtime()
            if (ahora - ultimoRumboPublicadoMs >= 50) { // ~20 Hz basta para la UI
                ultimoRumboPublicadoMs = ahora
                publicar()
            }
        }

        override fun onAccuracyChanged(s: Sensor?, accuracy: Int) = Unit
    }

    private val listenerPasos = object : SensorEventListener {
        override fun onSensorChanged(e: SensorEvent) {
            registrarPaso(SystemClock.elapsedRealtime())
        }

        override fun onAccuracyChanged(s: Sensor?, accuracy: Int) = Unit
    }

    private val listenerAcel = object : SensorEventListener {
        override fun onSensorChanged(e: SensorEvent) {
            val t = SystemClock.elapsedRealtime()
            val paso = detector.procesar(
                e.values[0], e.values[1], e.values[2], t,
                detectar = fuente != FuentePasos.HARDWARE,
            )
            if (paso) registrarPaso(t)
            if (t - ultimaAceleracionMs >= 50) {
                ultimaAceleracionMs = t
                onAceleracion?.invoke(detector.ultimaDesviacion)
            }
        }

        override fun onAccuracyChanged(s: Sensor?, accuracy: Int) = Unit
    }

    private fun registrarPaso(tMs: Long) {
        if (engine.onPaso(tMs)) publicar()
    }

    private fun actualizarDeclinacion() {
        val la = engine.lat ?: return
        val ln = engine.lng ?: return
        declinacion = GeomagneticField(
            la.toFloat(), ln.toFloat(), 0f, System.currentTimeMillis(),
        ).declination
    }

    private fun publicar() {
        _estado.value = PdrEstado(
            lat = engine.lat,
            lng = engine.lng,
            rumboGrados = engine.rumbo,
            pasos = engine.pasos,
            distanciaMetros = engine.distanciaMetros,
            velocidadMps = engine.velocidadMps,
            activo = activo,
            fuentePasos = fuente,
        )
    }
}

/**
 * Rumbo (grados, 0–360, norte magnético) hacia donde "avanza" el celular, según cómo lo lleve:
 *  - plano (la pantalla mira al cielo): hacia donde apunta la parte superior del celular;
 *  - en vertical: hacia donde apunta la cámara trasera.
 * Así el PDR sirve con el celular en la mano en cualquiera de las dos posturas.
 *
 * `r` es la matriz de `getRotationMatrixFromVector` (dispositivo → mundo: Este, Norte, Arriba).
 */
internal fun rumboDesdeMatriz(r: FloatArray): Float {
    val plano = abs(r[8]) > 0.7f
    val este = if (plano) r[1] else -r[2]
    val norte = if (plano) r[4] else -r[5]
    val grados = Math.toDegrees(atan2(este.toDouble(), norte.toDouble()))
    return ((grados + 360.0) % 360.0).toFloat()
}