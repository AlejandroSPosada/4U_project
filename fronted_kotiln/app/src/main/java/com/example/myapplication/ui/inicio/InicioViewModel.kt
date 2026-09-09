package com.example.myapplication.ui.inicio

import android.net.Uri
import androidx.lifecycle.ViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

// ── UI State ──────────────────────────────────────────────────────────────────
data class InicioUiState(
    val imagenesSeleccionadas: List<Uri> = emptyList()
)

// ── ViewModel ─────────────────────────────────────────────────────────────────
class InicioViewModel : ViewModel() {

    private val _uiState = MutableStateFlow(InicioUiState())
    val uiState: StateFlow<InicioUiState> = _uiState.asStateFlow()

    /** Almacena las URIs devueltas por el selector de galería. */
    fun onImagenesSeleccionadas(uris: List<Uri>) {
        // Tomar solo las primeras 3 por si el sistema devuelve más
        _uiState.value = _uiState.value.copy(imagenesSeleccionadas = uris.take(3))
    }
}
