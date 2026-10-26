package com.example.myapplication.ui.admin.panel

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.example.myapplication.data.local.AlmacenRecorridos
import com.example.myapplication.data.local.ColaSubida
import com.example.myapplication.data.local.EstadoCola
import com.example.myapplication.data.local.EstadoSubida
import com.example.myapplication.data.local.FaseCola
import com.example.myapplication.data.local.RecorridoLocal
import com.example.myapplication.data.local.Subidas
import com.example.myapplication.data.repository.AdminRepository
import com.example.myapplication.data.repository.AdminRepositoryStub
import com.example.myapplication.domain.model.ResumenAdmin
import com.example.myapplication.domain.model.Rol
import com.example.myapplication.session.SessionManager
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class PanelUiState(
    val nombre: String = "",
    val rolTexto: String = "",
    val resumen: ResumenAdmin? = null,
    val cargandoResumen: Boolean = true,
    val errorResumen: Boolean = false,
    /** FE-2.1: aviso de la cola de subida (subiendo, esperando, recorridos sin subir); `null` = nada pendiente. */
    val avisoSubidas: AvisoSubidas? = null,
)

/**
 * Tarjeta de subidas del Panel (FE-2.1). Tocarla abre la vista 7.5 de [videoId] (así se retoma una subida tras volver
 * a entrar, y se suben los recorridos de «Guardar y subir después»).
 */
data class AvisoSubidas(val videoId: String, val titulo: String, val detalle: String, val accion: String)

/** Arma [AvisoSubidas] a partir de la cola y de los recorridos locales (lógica pura). */
internal fun avisoSubidas(estado: EstadoCola, recorridos: List<RecorridoLocal>): AvisoSubidas? {
    val sinTerminar = recorridos.filter { it.finalizado && it.subida != EstadoSubida.COMPLETADA }
    val nombreDe = { id: String -> recorridos.firstOrNull { it.id == id }?.nombre ?: id }
    estado.videoId?.let { id ->
        val nombre = nombreDe(id)
        when (estado.fase) {
            FaseCola.PREPARANDO -> return AvisoSubidas(id, "Preparando «$nombre»", "${estado.hechas} de ${estado.total} fotos", "Ver")
            FaseCola.SUBIENDO, FaseCola.COMPLETANDO ->
                return AvisoSubidas(id, "Subiendo «$nombre»", "${estado.hechas} de ${estado.total} fotos", "Ver")
            FaseCola.SIN_CONEXION ->
                return AvisoSubidas(id, "Subida de «$nombre» en pausa", "Sin conexión: reintento en ${estado.reintentoEnS ?: 0} s", "Ver")
            FaseCola.ERROR, FaseCola.FOTOS_ILEGIBLES ->
                return AvisoSubidas(id, "La subida de «$nombre» se detuvo", estado.mensaje ?: "Revisa el recorrido", "Revisar")
            else -> Unit
        }
    }
    val aMedias = sinTerminar.filter { it.subida == EstadoSubida.SUBIENDO }.maxByOrNull { it.id }
    if (aMedias != null) {
        return AvisoSubidas(aMedias.id, "Subida pendiente de «${aMedias.nombre}»", "${aMedias.fotosPendientes} fotos por subir", "Ver")
    }
    val ultimo = sinTerminar.maxByOrNull { it.id } ?: return null
    val detalle = if (sinTerminar.size == 1) "«${ultimo.nombre}», ${ultimo.fotos.size} fotos"
    else "${sinTerminar.size} recorridos; el más reciente, «${ultimo.nombre}»"
    return AvisoSubidas(ultimo.id, "Recorridos sin subir", detalle, "Revisar y subir")
}

sealed interface PanelEvento {
    /** El admin cerró sesión: volver al flujo público. */
    data object SesionCerrada : PanelEvento
    /** No hay sesión ADMIN válida: redirigir a Login. */
    data object SinSesion : PanelEvento
}

class PanelAdminViewModel(
    private val repo: AdminRepository,
    private val session: SessionManager,
    // FE-2.1: cola de subida del proceso (`Subidas`); `null` en previews o pruebas sin subida.
    private val almacen: AlmacenRecorridos? = null,
    private val cola: ColaSubida? = null,
) : ViewModel() {

    private val _state = MutableStateFlow(PanelUiState())
    val state: StateFlow<PanelUiState> = _state.asStateFlow()

    private val _eventos = Channel<PanelEvento>(Channel.BUFFERED)
    val eventos = _eventos.receiveAsFlow()

    init {
        val sesion = session.obtener()
        if (sesion == null || sesion.usuario.rol != Rol.ADMIN) {
            // Guarda de rol: sin sesión ADMIN no se muestra el panel.
            _eventos.trySend(PanelEvento.SinSesion)
        } else {
            _state.update {
                it.copy(
                    nombre = sesion.usuario.nombre.trim().substringBefore(' '),
                    rolTexto = "Administrador del sistema",
                )
            }
            cargarResumen()
            vigilarSubidas()
        }
    }

    /**
     * FE-2.1: con sesión ADMIN, retoma la cola (lo que quedó `subiendo`; ARCHITECTURE §5.8: tras volver a Login se cae
     * aquí) y mantiene [PanelUiState.avisoSubidas] al día.
     */
    private fun vigilarSubidas() {
        val c = cola ?: return
        val a = almacen ?: return
        c.reanudar()
        viewModelScope.launch {
            combine(c.estado, c.cambiosVideos) { estado, _ -> estado }.collect { estado ->
                val recorridos = runCatching { a.listar() }.getOrDefault(emptyList())
                _state.update { it.copy(avisoSubidas = avisoSubidas(estado, recorridos)) }
                // La cola se paró por falta de sesión y el Panel (vivo en la pila) ya no la tiene (p. ej. venció a las
                // 12 h): a Login, como haría su guarda de `init`. Con sesión vigente (recién entró) no pasa nada.
                if (estado.fase == FaseCola.ESPERANDO_SESION && runCatching { session.obtener() }.getOrNull() == null) {
                    _eventos.trySend(PanelEvento.SinSesion)
                }
            }
        }
    }

    fun cargarResumen() {
        _state.update { it.copy(cargandoResumen = true, errorResumen = false) }
        viewModelScope.launch {
            try {
                val resumen = repo.obtenerResumen()
                _state.update { it.copy(resumen = resumen, cargandoResumen = false) }
            } catch (e: Exception) {
                _state.update { it.copy(cargandoResumen = false, errorResumen = true) }
            }
        }
    }

    fun cerrarSesion() {
        session.cerrarSesion()
        _eventos.trySend(PanelEvento.SesionCerrada)
    }

    class Factory(private val context: Context) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T =
            PanelAdminViewModel(
                AdminRepositoryStub(),
                SessionManager(context.applicationContext),
                Subidas.almacen,
                Subidas.cola,
            ) as T
    }
}