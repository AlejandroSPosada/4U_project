package com.example.myapplication.domain.ruta

import com.example.myapplication.domain.model.LugarDestino
import java.text.Normalizer
import java.util.Locale

/**
 * Cómo casan las entradas del grafo (`lugar`, texto) con los lugares del backend (`GET /v1/places`). [coinciden]: lugar
 * del grafo → lugar del backend; [exactos]: los que además se escriben igual (mismo texto); [sinLugarEnBackend]: lugares
 * del grafo que no casan con ninguno; [sinEntrada]: lugares del backend sin entrada en el grafo (destinos fuera del
 * grafo: la app da la dirección en línea recta, como antes de FE-5.1).
 */
data class Emparejamiento(
    val coinciden: Map<String, LugarDestino>,
    val exactos: Set<String>,
    val sinLugarEnBackend: List<String>,
    val sinEntrada: List<LugarDestino>,
)

/**
 * Empareja por nombre normalizado (FE-5.1; `EmparejamientoTest`): minúsculas, sin tildes y **solo letras y números**
 * (sin espacios ni signos: «Café Con.verso» → `cafeconverso`, «bloque 35» → `bloque35`). Un lugar casa con una entrada
 * si su `nombre` **o uno de sus `alias`** normalizado es igual al `lugar` normalizado.
 */
object EmparejarLugares {

    private val marcas = Regex("\\p{M}+")
    private val noAlfanumerico = Regex("[^a-z0-9]+")

    fun normalizar(texto: String): String =
        Normalizer.normalize(texto.lowercase(Locale.ROOT), Normalizer.Form.NFD)
            .replace(marcas, "")
            .replace(noAlfanumerico, "")

    /** Nombres normalizados (nombre y alias) de un lugar del backend. */
    fun claves(lugar: LugarDestino): Set<String> =
        (listOf(lugar.nombre) + lugar.alias).map { normalizar(it) }.filter { it.isNotEmpty() }.toSet()

    fun coincide(lugarGrafo: String, lugar: LugarDestino): Boolean = normalizar(lugarGrafo) in claves(lugar)

    fun emparejar(lugaresGrafo: Collection<String>, lugares: List<LugarDestino>): Emparejamiento {
        val coinciden = LinkedHashMap<String, LugarDestino>()
        val exactos = LinkedHashSet<String>()
        val sinLugar = mutableListOf<String>()
        for (lg in lugaresGrafo.distinct()) {
            val l = lugares.firstOrNull { it.nombre == lg } ?: lugares.firstOrNull { coincide(lg, it) }
            if (l == null) {
                sinLugar += lg
            } else {
                coinciden[lg] = l
                if (l.nombre == lg) exactos += lg
            }
        }
        val usados = coinciden.values.map { it.id }.toSet()
        return Emparejamiento(coinciden, exactos, sinLugar, lugares.filter { it.id !in usados })
    }
}
