package com.example.myapplication.ui.admin.mapa

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.example.myapplication.data.repository.AlertasRepository
import com.example.myapplication.domain.model.Alerta
import com.example.myapplication.domain.model.PrioridadAlerta
import com.example.myapplication.domain.model.TipoAlerta
import com.example.myapplication.ui.components.CapasMapa
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.util.UUID

class EditorMapaViewModel(private val repo: AlertasRepository) : ViewModel() {

    private val _ui = MutableStateFlow(EditorMapaUiState())
    val ui: StateFlow<EditorMapaUiState> = _ui.asStateFlow()

    init {
        viewModelScope.launch { repo.alertas.collect { l -> _ui.update { it.copy(alertas = l) } } }
        viewModelScope.launch { repo.pendientes.collect { n -> _ui.update { it.copy(pendientes = n) } } }
        viewModelScope.launch {
            repo.cargar().onFailure { avisar("No se pudieron cargar las alertas") }
        }
    }

    // ---------------------------------------------------------------- filtros y capas
    fun onFiltroTipo(v: TipoAlerta?) = _ui.update { it.copy(filtroTipo = v) }
    fun onFiltroPrioridad(v: PrioridadAlerta?) = _ui.update { it.copy(filtroPrioridad = v) }
    fun onFiltroActiva(v: Boolean?) = _ui.update { it.copy(filtroActiva = v) }
    fun onCapas(transformar: (CapasMapa) -> CapasMapa) = _ui.update { it.copy(capas = transformar(it.capas)) }

    // ---------------------------------------------------------------- toques en el mapa
    fun onAlertaToque(id: String) = _ui.update {
        if (it.colocando || it.moviendo || it.formularioVisible) it else it.copy(seleccionId = id)
    }

    fun onMapaToque(lat: Double, lng: Double) = _ui.update {
        when {
            it.moviendo || it.formularioVisible -> it
            it.colocando -> it.copy(
                colocando = false,
                seleccionId = null,
                borrador = Alerta(id = UUID.randomUUID().toString(), latitud = lat, longitud = lng, mensaje = ""),
                borradorEsNuevo = true,
                formularioVisible = true,
                errorMensaje = null,
            )
            else -> it.copy(seleccionId = null) // toque en vacío: deseleccionar
        }
    }

    fun onDeseleccionar() = _ui.update { it.copy(seleccionId = null) }

    // ---------------------------------------------------------------- nueva alerta
    fun onNuevaAlerta() = _ui.update {
        if (it.moviendo || it.formularioVisible) it
        else it.copy(colocando = !it.colocando, seleccionId = null)
    }

    // ---------------------------------------------------------------- editar / formulario
    fun onEditarSeleccionada() = _ui.update {
        val a = it.seleccionada ?: return@update it
        it.copy(borrador = a, borradorEsNuevo = false, formularioVisible = true, errorMensaje = null)
    }

    fun onBorradorCambio(transformar: (Alerta) -> Alerta) = _ui.update {
        val b = it.borrador ?: return@update it
        it.copy(borrador = transformar(b), errorMensaje = null)
    }

    fun onCancelarFormulario() = _ui.update {
        it.copy(borrador = null, formularioVisible = false, errorMensaje = null, borradorEsNuevo = false)
    }

    fun onGuardarFormulario() {
        val actual = _ui.value
        val b = actual.borrador ?: return
        val texto = b.mensaje.trim()
        if (texto.isEmpty()) {
            _ui.update { it.copy(errorMensaje = "Escribe el mensaje que se le leerá al usuario") }
            return
        }
        repo.guardar(b.copy(mensaje = texto))
        _ui.update {
            it.copy(
                borrador = null, formularioVisible = false, borradorEsNuevo = false,
                errorMensaje = null, seleccionId = b.id, mensaje = "Alerta guardada",
            )
        }
    }

    // ---------------------------------------------------------------- mover (arrastrar marcador)
    /** Botón "Mover" de la tarjeta. */
    fun onMoverSeleccionada() = _ui.update {
        val a = it.seleccionada ?: return@update it
        it.copy(
            borrador = a, borradorEsNuevo = false, formularioVisible = false,
            moviendo = true, moverOrigen = OrigenMover.TARJETA,
            moverOriginal = a.latitud to a.longitud,
        )
    }

    /** Botón "Ajustar en el mapa" del formulario. */
    fun onAjustarEnMapa() = _ui.update {
        val b = it.borrador ?: return@update it
        it.copy(
            formularioVisible = false, moviendo = true, moverOrigen = OrigenMover.FORMULARIO,
            moverOriginal = b.latitud to b.longitud,
        )
    }

    fun onAlertaMovida(id: String, lat: Double, lng: Double) = _ui.update {
        val b = it.borrador
        if (!it.moviendo || b == null || b.id != id) it
        else it.copy(borrador = b.copy(latitud = lat, longitud = lng))
    }

    fun onMoverListo() {
        val s = _ui.value
        val b = s.borrador ?: return
        if (s.moverOrigen == OrigenMover.TARJETA) {
            repo.guardar(b)
            _ui.update {
                it.copy(
                    borrador = null, moviendo = false, moverOrigen = null, moverOriginal = null,
                    mensaje = "Alerta movida",
                )
            }
        } else {
            _ui.update { it.copy(moviendo = false, moverOrigen = null, moverOriginal = null, formularioVisible = true) }
        }
    }

    fun onMoverCancelar() = _ui.update {
        val b = it.borrador
        val orig = it.moverOriginal
        if (it.moverOrigen == OrigenMover.TARJETA || b == null || orig == null) {
            it.copy(borrador = null, moviendo = false, moverOrigen = null, moverOriginal = null)
        } else {
            it.copy(
                borrador = b.copy(latitud = orig.first, longitud = orig.second),
                moviendo = false, moverOrigen = null, moverOriginal = null, formularioVisible = true,
            )
        }
    }

    // ---------------------------------------------------------------- eliminar
    fun onEliminarSolicitada(id: String) = _ui.update { it.copy(confirmarEliminarId = id) }
    fun onEliminarDescartada() = _ui.update { it.copy(confirmarEliminarId = null) }

    fun onEliminarConfirmada() {
        val id = _ui.value.confirmarEliminarId ?: return
        repo.eliminar(id)
        _ui.update {
            it.copy(
                confirmarEliminarId = null, seleccionId = null,
                borrador = null, formularioVisible = false, borradorEsNuevo = false,
                mensaje = "Alerta eliminada",
            )
        }
    }

    // ---------------------------------------------------------------- guardar / sincronizar
    fun onSincronizar() {
        if (_ui.value.sincronizando) return
        _ui.update { it.copy(sincronizando = true) }
        viewModelScope.launch {
            val r = repo.sincronizar()
            _ui.update {
                it.copy(
                    sincronizando = false,
                    mensaje = if (r.isSuccess) "Cambios sincronizados"
                    else "No se pudo sincronizar. Los cambios siguen pendientes",
                )
            }
        }
    }

    // ---------------------------------------------------------------- mensajes
    fun onMensajeMostrado() = _ui.update { it.copy(mensaje = null) }
    private fun avisar(texto: String) = _ui.update { it.copy(mensaje = texto) }

    companion object {
        fun factory(repo: AlertasRepository) = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T = EditorMapaViewModel(repo) as T
        }
    }
}