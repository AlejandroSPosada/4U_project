package com.example.myapplication.ui.inicio

import android.app.Application
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.myapplication.ApiConfig
import com.google.gson.Gson
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

// ─── Result from the API ──────────────────────────────────────────────────────
data class PredictionResult(
    val location: String,
    val point_id: Int,
    val similarity: Float,
    val matched_ref_image: String
)

// ─── UI State ─────────────────────────────────────────────────────────────────
sealed class PredictionState {
    object Idle    : PredictionState()
    object Loading : PredictionState()
    data class Success(val result: PredictionResult) : PredictionState()
    data class Error(val message: String)            : PredictionState()
}

data class InicioUiState(
    val imagenSeleccionada: Uri?           = null,
    val predictionState: PredictionState  = PredictionState.Idle
)

// ─── ViewModel ────────────────────────────────────────────────────────────────
class InicioViewModel(application: Application) : AndroidViewModel(application) {

    private val _uiState = MutableStateFlow(InicioUiState())
    val uiState: StateFlow<InicioUiState> = _uiState.asStateFlow()

    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .build()

    private val gson = Gson()

    /** Called when the user picks one image from the gallery. */
    fun onImagenSeleccionada(uri: Uri) {
        _uiState.value = InicioUiState(
            imagenSeleccionada = uri,
            predictionState    = PredictionState.Loading
        )
        viewModelScope.launch {
            val state = withContext(Dispatchers.IO) { predict(uri) }
            _uiState.value = _uiState.value.copy(predictionState = state)
        }
    }

    /** Clear result so the user can pick a new image. */
    fun reset() {
        _uiState.value = InicioUiState()
    }

    // ── Private ────────────────────────────────────────────────────────────────

    private fun predict(uri: Uri): PredictionState {
        return try {
            val bytes = getApplication<Application>()
                .contentResolver
                .openInputStream(uri)
                ?.readBytes()
                ?: return PredictionState.Error("No se pudo leer la imagen")

            val body = MultipartBody.Builder()
                .setType(MultipartBody.FORM)
                .addFormDataPart(
                    name     = "image",
                    filename = "photo.png",
                    body     = bytes.toRequestBody("image/*".toMediaType())
                )
                .build()

            val request = Request.Builder()
                .url(ApiConfig.PREDICT_URL)
                .post(body)
                .build()

            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    return PredictionState.Error("Error del servidor: ${response.code}")
                }
                val json = response.body?.string()
                    ?: return PredictionState.Error("Respuesta vacía del servidor")
                val result = gson.fromJson(json, PredictionResult::class.java)
                PredictionState.Success(result)
            }
        } catch (e: Exception) {
            PredictionState.Error("No se pudo conectar: ${e.message}")
        }
    }
}