package com.example.myapplication.data.repository

import com.example.myapplication.domain.model.Alerta
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.update

/**
 * Contrato de alertas. Es "local primero": guardar/eliminar se reflejan al instante
 * y quedan como cambios pendientes hasta [sincronizar] (ARCHITECTURE.md, 7.8).
 */
interface AlertasRepository {
    val alertas: StateFlow<List<Alerta>>

    /** Cantidad de cambios locales aún no enviados al backend. */
    val pendientes: Flow<Int>

    suspend fun cargar(): Result<Unit>
    fun guardar(alerta: Alerta)
    fun eliminar(id: String)
    suspend fun sincronizar(): Result<Unit>
}

/**
 * Stub temporal, igual que el de AuthRepository.
 * TODO: reemplazar por Retrofit/Ktor + Room usando ApiConfig.kt
 *  (GET/POST/PUT/DELETE /admin/alerts).
 */
class AlertasRepositoryEnMemoria : AlertasRepository {

    private val _alertas = MutableStateFlow<List<Alerta>>(emptyList())
    override val alertas: StateFlow<List<Alerta>> = _alertas.asStateFlow()

    /** id -> true si el cambio pendiente es una eliminación. */
    private val cambios = MutableStateFlow<Map<String, Boolean>>(emptyMap())
    override val pendientes: Flow<Int> = cambios.map { it.size }

    override suspend fun cargar(): Result<Unit> = Result.success(Unit)

    override fun guardar(alerta: Alerta) {
        _alertas.update { lista ->
            if (lista.any { it.id == alerta.id }) {
                lista.map { if (it.id == alerta.id) alerta else it }
            } else {
                lista + alerta
            }
        }
        cambios.update { it + (alerta.id to false) }
    }

    override fun eliminar(id: String) {
        _alertas.update { lista -> lista.filterNot { it.id == id } }
        cambios.update { it + (id to true) }
    }

    override suspend fun sincronizar(): Result<Unit> {
        delay(600) // simula la red
        cambios.value = emptyMap()
        return Result.success(Unit)
    }
}

/** Instancia única mientras el repositorio sea un stub (el ViewModel se recrea). */
object AlertasRepositoryProvider {
    val instancia: AlertasRepository by lazy { AlertasRepositoryEnMemoria() }
}