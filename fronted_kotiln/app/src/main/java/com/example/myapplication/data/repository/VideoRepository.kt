package com.example.myapplication.data.repository

import android.content.Context
import android.util.Log
import com.example.myapplication.domain.model.CalidadFoto
import com.example.myapplication.domain.model.EstadoFoto
import com.example.myapplication.domain.model.Foto
import com.example.myapplication.domain.model.Video
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject

/** Contrato de acceso a videos y fotos. Las pantallas solo conocen esta interfaz. */
interface VideoRepository {
    suspend fun obtenerVideos(): List<Video>
}

/**
 * Lee los videos empaquetados en `app/src/main/assets/videos/<video_id>/manifest.json`.
 *
 * **TODO:** reemplazar por `RemoteVideoRepository` (`GET /admin/videos/{id}/images`) cuando
 * exista el backend. El modelo `Foto` no cambia: solo cambian las URLs.
 */
class AssetsVideoRepository(private val context: Context) : VideoRepository {

    override suspend fun obtenerVideos(): List<Video> = withContext(Dispatchers.IO) {
        context.assets.list(RAIZ).orEmpty().sorted().mapNotNull { videoId ->
            try {
                leerVideo(videoId)
            } catch (e: Exception) {
                Log.w(TAG, "No se pudo leer $RAIZ/$videoId", e)
                null
            }
        }
    }

    private fun leerVideo(videoId: String): Video {
        val base = "$RAIZ/$videoId"
        val json = JSONObject(
            context.assets.open("$base/manifest.json").bufferedReader().use { it.readText() }
        )
        val nombre = json.optString("name", videoId)

        // Si una miniatura no existe todavía, se usa la foto original (Coil la reduce al cargar).
        val miniaturas = context.assets.list("$base/thumbs").orEmpty().toSet()

        val arreglo = json.getJSONArray("photos")
        val fotos = (0 until arreglo.length()).map { i ->
            val p = arreglo.getJSONObject(i)
            val archivo = p.getString("file")
            val miniatura = p.optString("thumb")
                .takeIf { it.isNotEmpty() && it.substringAfterLast('/') in miniaturas }
                ?: archivo

            Foto(
                id = p.getString("id"),
                videoId = videoId,
                videoNombre = nombre,
                urlFoto = "$URI_ASSETS/$base/$archivo",
                urlMiniatura = "$URI_ASSETS/$base/$miniatura",
                lat = p.getDouble("lat"),
                lng = p.getDouble("lng"),
                rumbo = if (p.has("heading") && !p.isNull("heading")) {
                    p.getDouble("heading").toFloat()
                } else null,
                capturadaEn = p.optString("captured_at").ifBlank { null },
                lugar = p.optString("lugar").ifBlank { null },
                estado = p.enumOpcional("estado", EstadoFoto.PROCESADA),
                calidad = p.enumOpcional("calidad", CalidadFoto.NORMAL),
            )
        }.sortedBy { it.id }

        return Video(
            id = videoId,
            nombre = nombre,
            creadoEn = json.optString("created_at").ifBlank { null },
            fotos = fotos,
        )
    }

    private inline fun <reified T : Enum<T>> JSONObject.enumOpcional(clave: String, porDefecto: T): T {
        val texto = optString(clave, "")
        return enumValues<T>().firstOrNull { it.name.equals(texto, ignoreCase = true) } ?: porDefecto
    }

    private companion object {
        const val TAG = "AssetsVideoRepository"
        const val RAIZ = "videos"
        const val URI_ASSETS = "file:///android_asset"
    }
}