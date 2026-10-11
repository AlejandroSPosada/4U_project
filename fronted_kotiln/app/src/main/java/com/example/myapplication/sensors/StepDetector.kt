package com.example.myapplication.sensors

import kotlin.math.abs
import kotlin.math.sqrt

/**
 * Detector de pasos por acelerómetro. Es el respaldo para cuando el teléfono no tiene
 * `TYPE_STEP_DETECTOR` o no se concedió `ACTIVITY_RECOGNITION`. Lógica pura (sin Android).
 *
 * Es la misma lógica que antes vivía en `app.js` (umbral 2,2 m/s², pausa de 280 ms entre pasos).
 */
class StepDetector(
    private val umbral: Float = UMBRAL,
    private val pausaMs: Long = PAUSA_MS,
) {
    companion object {
        const val GRAVEDAD = 9.81f
        const val UMBRAL = 2.2f
        const val PAUSA_MS = 280L
    }

    /** Desviación de la última muestra respecto a la gravedad (m/s²). Sirve para la gráfica. */
    var ultimaDesviacion: Float = 0f
        private set

    private var subiendo = false
    private var ultimoPasoMs = 0L

    /**
     * Procesa una muestra del acelerómetro (con gravedad incluida).
     * Devuelve `true` si esta muestra cierra un paso. Con [detectar] en `false` solo actualiza
     * [ultimaDesviacion] (cuando los pasos los da el sensor de hardware).
     */
    fun procesar(x: Float, y: Float, z: Float, tMs: Long, detectar: Boolean = true): Boolean {
        val desviacion = abs(sqrt(x * x + y * y + z * z) - GRAVEDAD)
        ultimaDesviacion = desviacion
        if (!detectar) return false

        if (desviacion > umbral) {
            subiendo = true
        } else if (subiendo && desviacion < umbral * 0.6f) {
            subiendo = false
            if (tMs - ultimoPasoMs > pausaMs) {
                ultimoPasoMs = tMs
                return true
            }
        }
        return false
    }

    fun reiniciar() {
        subiendo = false
        ultimoPasoMs = 0L
        ultimaDesviacion = 0f
    }
}