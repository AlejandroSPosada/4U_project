package com.example.myapplication.data.repository

import android.content.Context
import android.util.Log
import com.example.myapplication.data.local.AlmacenRecorridos
import com.example.myapplication.data.local.ManifestRecorrido
import com.example.myapplication.data.local.Subidas
import com.example.myapplication.domain.model.Video
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.withContext

/** Contrato de acceso a videos y fotos. Las pantallas solo conocen esta interfaz. */
interface VideoRepository {
    suspend fun obtenerVideos(): List<Video>
    suspend fun renombrarVideo(videoId: String, nombre: String)
    suspend fun eliminarVideo(videoId: String)
    suspend fun eliminarFoto(videoId: String, fotoId: String)

    /** Emite cada vez que cambian los datos (renombrar, eliminar...) para que las pantallas abiertas se refresquen. */
    fun cambios(): Flow<Int>
}

/**
 * Ediciones en memoria sobre los assets (que son de solo lectura). Se pierden al cerrar la app.
 * Es un objeto único del proceso para que lista, detalle y galería vean lo mismo.
 *
 * **TODO:** desaparece cuando exista el backend (las ediciones serán llamadas a la API).
 */
internal object EdicionesLocales {
    private val nombres = mutableMapOf<String, String>()
    private val videosEliminados = mutableSetOf<String>()
    private val fotosEliminadas = mutableSetOf<String>()   // uid = "videoId/fotoId"
    private val _version = MutableStateFlow(0)
    val version: StateFlow<Int> = _version.asStateFlow()

    @Synchronized
    fun renombrar(videoId: String, nombre: String) {
        nombres[videoId] = nombre; _version.update { it + 1 }
    }

    @Synchronized
    fun eliminarVideo(videoId: String) {
        videosEliminados += videoId; _version.update { it + 1 }
    }

    @Synchronized
    fun eliminarFoto(videoId: String, fotoId: String) {
        fotosEliminadas += "$videoId/$fotoId"; _version.update { it + 1 }
    }

    @Synchronized
    fun aplicar(videos: List<Video>): List<Video> = videos
        .filterNot { it.id in videosEliminados }
        .map { v ->
            val nombre = nombres[v.id] ?: v.nombre
            v.copy(
                nombre = nombre,
                fotos = v.fotos.filterNot { it.uid in fotosEliminadas }.map { it.copy(videoNombre = nombre) },
            )
        }
}

/** Una fuente de videos de solo lectura para [VideoRepositoryCompuesto] (sin `EdicionesLocales` aplicadas). */
fun interface FuenteVideos {
    /** Los videos legibles; un video ilegible se omite (no lanza por él). */
    suspend fun videos(): List<Video>
}

/**
 * Lee los videos empaquetados en `app/src/main/assets/videos/<video_id>/manifest.json` con el parser compartido
 * (`ManifestRecorrido`, FE-2.1). Como [VideoRepository] aplica `EdicionesLocales`; como [FuenteVideos], no.
 *
 * **TODO (FE-4.1):** `RemoteVideoRepository` (`GET /v1/admin/videos…`). El modelo `Foto` no cambia: solo las URLs.
 */
class AssetsVideoRepository(private val context: Context) : VideoRepository, FuenteVideos {

    override suspend fun videos(): List<Video> = withContext(Dispatchers.IO) {
        context.assets.list(RAIZ).orEmpty().sorted().mapNotNull { videoId ->
            try {
                leerVideo(videoId)
            } catch (e: Exception) {
                Log.w(TAG, "No se pudo leer $RAIZ/$videoId", e)
                null
            }
        }
    }

    override suspend fun obtenerVideos(): List<Video> = EdicionesLocales.aplicar(videos())

    override suspend fun renombrarVideo(videoId: String, nombre: String) = EdicionesLocales.renombrar(videoId, nombre)
    override suspend fun eliminarVideo(videoId: String) = EdicionesLocales.eliminarVideo(videoId)
    override suspend fun eliminarFoto(videoId: String, fotoId: String) = EdicionesLocales.eliminarFoto(videoId, fotoId)
    override fun cambios(): Flow<Int> = EdicionesLocales.version

    private fun leerVideo(videoId: String): Video {
        val base = "$RAIZ/$videoId"
        val json = ManifestRecorrido.parsear(
            context.assets.open("$base/manifest.json").bufferedReader().use { it.readText() }
        )
        // Si una miniatura no existe todavía, se usa la foto original (Coil la reduce al cargar).
        val miniaturas = context.assets.list("$base/thumbs").orEmpty().toSet()
        return ManifestRecorrido.video(
            videoId = videoId,
            json = json,
            url = { ruta -> "$URI_ASSETS/$base/$ruta" },
            miniaturaExiste = { ruta -> ruta.substringAfterLast('/') in miniaturas },
        )
    }

    private companion object {
        const val TAG = "AssetsVideoRepository"
        const val RAIZ = "videos"
        const val URI_ASSETS = "file:///android_asset"
    }
}

/**
 * Los recorridos grabados en el teléfono (`files/recoleccion/`) con `estado = finalizado`, como [Video] (FE-2.1). Los
 * `en_curso` no salen: se retoman en 7.4. Estados de las fotos según `ManifestRecorrido.estadoFoto` (`PENDIENTE`
 * hasta que se suben; `procesada`/`error` cuando 7.5 consulta el backend).
 */
class FuenteRecorridos(private val almacen: AlmacenRecorridos) : FuenteVideos {
    override suspend fun videos(): List<Video> =
        almacen.listar().filter { it.finalizado }.map { ManifestRecorrido.video(it, almacen.carpeta(it.id)) }
}

/**
 * `VideoRepository` **compuesto** (FE-2.1): los videos de [fuentes] en orden (en la app, `assets/videos/` y después
 * `files/recoleccion/`), con `EdicionesLocales` encima. Renombrar y eliminar siguen en memoria también para los
 * recorridos locales (persistirlos contra el backend es FE-4.1; el borrado real de un recorrido local es «Descartar
 * video» en 7.5). [cambios] emite con `EdicionesLocales` y con [cambiosExtra] (en la app, cada vez que la cola de
 * subida termina un intento: así la Lista ve «Pendiente de subir» → «Pendiente de proceso»).
 */
class VideoRepositoryCompuesto(
    private val fuentes: List<FuenteVideos>,
    private val cambiosExtra: Flow<Int> = flowOf(0),
) : VideoRepository {

    override suspend fun obtenerVideos(): List<Video> = EdicionesLocales.aplicar(fuentes.flatMap { it.videos() })
    override suspend fun renombrarVideo(videoId: String, nombre: String) = EdicionesLocales.renombrar(videoId, nombre)
    override suspend fun eliminarVideo(videoId: String) = EdicionesLocales.eliminarVideo(videoId)
    override suspend fun eliminarFoto(videoId: String, fotoId: String) = EdicionesLocales.eliminarFoto(videoId, fotoId)
    override fun cambios(): Flow<Int> = combine(EdicionesLocales.version, cambiosExtra) { a, b -> a * 100_003 + b }

    companion object {
        /** El de la app: `assets/videos/` + `files/recoleccion/` (de `Subidas`). Espera el contexto de la aplicación. */
        fun deLaApp(appContext: Context): VideoRepository = VideoRepositoryCompuesto(
            fuentes = listOf(AssetsVideoRepository(appContext), FuenteRecorridos(Subidas.almacen)),
            cambiosExtra = Subidas.cola.cambiosVideos,
        )
    }
}