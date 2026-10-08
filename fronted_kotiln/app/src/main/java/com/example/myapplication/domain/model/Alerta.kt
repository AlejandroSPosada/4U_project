package com.example.myapplication.domain.model

enum class TipoAlerta(val etiqueta: String) {
    AGUA("Agua"),
    MOBILIARIO("Mobiliario"),
    ESCALONES("Escalones"),
    OBRA("Obra"),
    VEHICULOS("Vehículos"),
    OTRO("Otro"),
}

enum class PrioridadAlerta(val etiqueta: String) {
    NORMAL("Normal"),
    ALTA("Alta"),
}

/**
 * Punto de alerta de obstáculo colocado por el admin (ARCHITECTURE.md, 2.5).
 * Es una capa propia: NO se escribe dentro de eafit.mbtiles.
 */
data class Alerta(
    val id: String,
    val latitud: Double,
    val longitud: Double,
    val mensaje: String,
    val tipo: TipoAlerta = TipoAlerta.OTRO,
    val prioridad: PrioridadAlerta = PrioridadAlerta.NORMAL,
    val radioM: Int = RADIO_POR_DEFECTO_M,
    val activa: Boolean = true,
    val vigenciaInicioMs: Long? = null,
    val vigenciaFinMs: Long? = null,
) {
    companion object {
        /** Decisión abierta 3: radio por defecto (el brief sugiere 15 m). */
        const val RADIO_POR_DEFECTO_M = 15
        const val RADIO_MIN_M = 5
        const val RADIO_MAX_M = 100
        const val MENSAJE_MAX = 200
    }
}