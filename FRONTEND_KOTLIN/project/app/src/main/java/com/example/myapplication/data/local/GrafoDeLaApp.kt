package com.example.myapplication.data.local

import android.content.Context
import com.example.myapplication.domain.model.LugarDestino
import com.example.myapplication.domain.ruta.CargaGrafo
import com.example.myapplication.domain.ruta.EmparejarLugares
import com.example.myapplication.domain.ruta.LectorGrafo
import com.example.myapplication.domain.ruta.Planificador
import com.example.myapplication.logs.AppLog

/**
 * El grafo de caminos de la app (FE-5.1; ARCHITECTURE §5.6 y §5.7, «Grafo y rutas»): `assets/grafo.json`, de solo
 * lectura, leído **una vez por proceso** con [LectorGrafo]. Si el archivo falta o es inválido, la app no se cae: las
 * rutas quedan desactivadas ([planificador] da `null`) y se registra una línea `Grafo` con los errores.
 *
 * Líneas `Grafo` (`AppLog`, sin la posición de la persona): `Grafo v180 cargado: 26 nodos, 31 aristas, 8 entradas`
 * (`AppLog.i`), `Grafo: aviso: …` (`AppLog.w`, una por aviso), `grafo.json inválido (N errores): …; rutas
 * desactivadas` o `grafo.json no se pudo leer (…); rutas desactivadas` (`AppLog.w`) y, desde 6.4,
 * `Grafo: N de M lugares del grafo sin lugar en el backend: …` (`AppLog.w`, una vez por proceso).
 */
object GrafoDeLaApp {

    const val ARCHIVO = "grafo.json"
    const val TAG = "Grafo"

    @Volatile
    private var carga: CargaGrafo? = null

    @Volatile
    private var emparejamientoAvisado = false

    /** Lee (la primera vez) y devuelve la carga. Rápido (~10 KB); se puede llamar desde el hilo principal. */
    @Synchronized
    fun cargar(context: Context): CargaGrafo {
        carga?.let { return it }
        val leida = try {
            val texto = context.applicationContext.assets.open(ARCHIVO).bufferedReader(Charsets.UTF_8).use { it.readText() }
            LectorGrafo.leer(texto)
        } catch (e: Exception) {
            AppLog.w(TAG, "$ARCHIVO no se pudo leer (${e.javaClass.simpleName}); rutas desactivadas")
            CargaGrafo.Invalido(listOf("no se pudo leer $ARCHIVO"))
        }
        when (leida) {
            is CargaGrafo.Valido -> {
                val g = leida.grafo
                AppLog.i(TAG, "Grafo v${g.version} cargado: ${g.nodos.size} nodos, ${g.aristas.size} aristas, ${g.entradas.size} entradas")
                leida.avisos.forEach { AppLog.w(TAG, "Grafo: aviso: $it") }
            }
            is CargaGrafo.Invalido -> if (leida.errores != listOf("no se pudo leer $ARCHIVO")) {
                AppLog.w(
                    TAG,
                    "$ARCHIVO inválido (${leida.errores.size} errores): ${leida.errores.take(5).joinToString("; ")}; rutas desactivadas",
                )
            }
        }
        carga = leida
        return leida
    }

    /** El planificador sobre el grafo válido, o `null` si las rutas están desactivadas. */
    fun planificador(context: Context): Planificador? =
        (cargar(context) as? CargaGrafo.Valido)?.let { Planificador(it.grafo) }

    /**
     * Avisa (una vez por proceso, línea `Grafo`) de los lugares del grafo que no casan con ningún lugar del backend.
     * La llama Selección de destino (6.4) al cargar `GET /v1/places`.
     */
    fun avisarEmparejamiento(context: Context, lugares: List<LugarDestino>) {
        if (emparejamientoAvisado) return
        val grafo = (cargar(context) as? CargaGrafo.Valido)?.grafo ?: return
        emparejamientoAvisado = true
        val e = EmparejarLugares.emparejar(grafo.lugares, lugares)
        if (e.sinLugarEnBackend.isNotEmpty()) {
            AppLog.w(
                TAG,
                "Grafo: ${e.sinLugarEnBackend.size} de ${grafo.lugares.size} lugares del grafo sin lugar en el backend: " +
                    e.sinLugarEnBackend.joinToString(),
            )
        }
    }
}
