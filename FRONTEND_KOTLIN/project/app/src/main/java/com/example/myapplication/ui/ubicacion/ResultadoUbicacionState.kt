package com.example.myapplication.ui.ubicacion

import com.example.myapplication.domain.usecase.DescripcionUbicacion

/**
 * Estado de la vista 6.3 (Resultado de ubicación, FE-3.2). La UI solo lo lee; lo escribe `ResultadoUbicacionViewModel`.
 *
 * [descripcion]: textos de `DescribirUbicacion` (título, distancia, referencias, confianza, avisos y lo hablado).
 * [hayPosicion]: hay una ubicación con posición (cambia el botón a «Ir a un lugar desde aquí»).
 */
data class ResultadoUiState(
    val descripcion: DescripcionUbicacion,
    val hayPosicion: Boolean,
)

/**
 * Acciones de la vista 6.3 (todas con valor por defecto para las vistas previas). La pantalla no conoce el
 * `NavController`: `AppNav` conecta [onVolverAUbicarme], [onIrALugar] e [onInicio] (ARCHITECTURE §5.8).
 */
data class ResultadoAcciones(
    val onRepetir: () -> Unit = {},
    val onVolverAUbicarme: () -> Unit = {},
    val onIrALugar: () -> Unit = {},
    val onInicio: () -> Unit = {},
)
