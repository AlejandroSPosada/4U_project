package com.example.myapplication.data.repository

import com.example.myapplication.data.local.AlmacenRecorridos
import com.example.myapplication.data.local.ManifestPrueba
import com.example.myapplication.domain.model.EstadoFoto
import com.example.myapplication.domain.model.Foto
import com.example.myapplication.domain.model.Video
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.take
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.util.concurrent.CopyOnWriteArrayList

/**
 * FE-2.1: Galería, Lista y Detalle de video ven lo recolectado. `VideoRepositoryCompuesto` une las fuentes
 * (assets y `files/recoleccion/` con `FuenteRecorridos`) y aplica `EdicionesLocales`.
 */
class VideoRepositoryCompuestoTest {

    @get:Rule
    val tmp = TemporaryFolder()

    private val raiz: File by lazy { tmp.newFolder("recoleccion") }

    private val deAssets = FuenteVideos {
        listOf(
            Video(
                "vid_0001", "Video 1", "2026-10-09T10:00:00Z",
                listOf(Foto("0001", "vid_0001", "Video 1", "file:///android_asset/videos/vid_0001/photos/0001.png", "x", 6.2, -75.5)),
            ),
        )
    }

    @Test
    fun une_assets_y_recorridosFinalizados_conEstadosYUrlsLocales() = runBlocking {
        ManifestPrueba.crear(raiz, id = "rec_0001", fotos = 2, subidas = setOf(1))
        ManifestPrueba.crear(raiz, id = "rec_0002", fotos = 3, estado = "en_curso") // se retoma en 7.4: no sale
        val repo = VideoRepositoryCompuesto(listOf(deAssets, FuenteRecorridos(AlmacenRecorridos(raiz))))

        val videos = repo.obtenerVideos()
        assertEquals(listOf("vid_0001", "rec_0001"), videos.map { it.id })
        val rec = videos[1]
        assertEquals("Entrada norte", rec.nombre)
        assertEquals("2026-10-25T15:00:00-05:00", rec.creadoEn)
        assertEquals(listOf(EstadoFoto.SUBIDA, EstadoFoto.PENDIENTE), rec.fotos.map { it.estado })
        val url = rec.fotos[0].urlFoto
        assertTrue(url, url.startsWith("file://") && url.replace('\\', '/').endsWith("rec_0001/photos/0001.jpg"))
        assertEquals(url, rec.fotos[0].urlMiniatura)
        assertEquals("rec_0001/0001", rec.fotos[0].uid)
        assertEquals(37.5f, rec.fotos[0].rumbo)
        assertTrue(rec.distanciaMetros > 0)
    }

    @Test
    fun renombrarYEliminar_vanAEdicionesLocales_sinTocarElDisco() = runBlocking {
        ManifestPrueba.crear(raiz, id = "rec_9101", fotos = 2)
        val almacen = AlmacenRecorridos(raiz)
        val repo = VideoRepositoryCompuesto(listOf(FuenteRecorridos(almacen)))
        repo.renombrarVideo("rec_9101", "Otro nombre")
        repo.eliminarFoto("rec_9101", "0002")
        val video = repo.obtenerVideos().single { it.id == "rec_9101" }
        assertEquals("Otro nombre", video.nombre)
        assertEquals(listOf("0001"), video.fotos.map { it.id })
        val enDisco = almacen.leer("rec_9101")
        assertEquals("Entrada norte", enDisco.nombre) // solo en memoria (persistir es FE-4.1)
        assertEquals(2, enDisco.fotos.size)
    }

    @Test
    fun cambios_emiteConLasEdicionesYConLaCola() = runBlocking {
        val extra = MutableStateFlow(0)
        val repo = VideoRepositoryCompuesto(emptyList(), cambiosExtra = extra)
        val recibidos = CopyOnWriteArrayList<Int>()
        val primero = CompletableDeferred<Unit>()
        val trabajo = launch {
            repo.cambios().take(2).collect {
                recibidos += it
                primero.complete(Unit)
            }
        }
        withTimeout(5_000) { primero.await() }
        extra.value = 1
        withTimeout(5_000) { trabajo.join() }
        assertEquals(2, recibidos.size)
        assertTrue(recibidos[0] != recibidos[1])
    }
}
