package com.example.myapplication.ui.admin.mapa

import com.example.myapplication.domain.model.Alerta
import com.example.myapplication.domain.model.PrioridadAlerta
import com.example.myapplication.domain.model.TipoAlerta
import com.example.myapplication.ui.components.CapasMapa

/** Desde dónde se inició el modo "arrastrar marcador". */
enum class OrigenMover { TARJETA, FORMULARIO }

data class EditorMapaUiState(
    val alertas: List<Alerta> = emptyList(),
    val pendientes: Int = 0,
    val sincronizando: Boolean = false,

    // Filtros (null = Todos / Todas)
    val filtroTipo: TipoAlerta? = null,
    val filtroPrioridad: PrioridadAlerta? = null,
    /** true = solo activas, false = solo inactivas, null = todas. */
    val filtroActiva: Boolean? = null,
    val capas: CapasMapa = CapasMapa(),

    val seleccionId: String? = null,
    /** Modo "Nueva alerta": el siguiente toque en el mapa fija el punto. */
    val colocando: Boolean = false,

    /** Alerta en edición (nueva o existente). El mapa la dibuja en vivo, aún sin guardar. */
    val borrador: Alerta? = null,
    val borradorEsNuevo: Boolean = false,
    val formularioVisible: Boolean = false,
    val errorMensaje: String? = null,

    /** Modo arrastrar: el marcador del borrador se puede mover en el mapa. */
    val moviendo: Boolean = false,
    val moverOrigen: OrigenMover? = null,
    val moverOriginal: Pair<Double, Double>? = null,

    val confirmarEliminarId: String? = null,
    /** Mensaje de una sola vez para el Snackbar. */
    val mensaje: String? = null,
) {
    val seleccionada: Alerta?
        get() = alertas.firstOrNull { it.id == seleccionId }

    /** Alertas que se dibujan: las filtradas + la seleccionada + el borrador (que sustituye a su original). */
    val alertasParaMapa: List<Alerta>
        get() {
            val base = alertas.filter { a ->
                a.id == seleccionId || a.id == borrador?.id || (
                    (filtroTipo == null || a.tipo == filtroTipo) &&
                        (filtroPrioridad == null || a.prioridad == filtroPrioridad) &&
                        (filtroActiva == null || a.activa == filtroActiva)
                    )
            }
            val b = borrador ?: return base
            return if (base.any { it.id == b.id }) base.map { if (it.id == b.id) b else it } else base + b
        }

    /** Id que el mapa resalta y alrededor del cual dibuja el radio. */
    val idResaltado: String?
        get() = borrador?.id ?: seleccionId
}