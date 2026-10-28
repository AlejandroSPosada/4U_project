package com.example.myapplication.domain.ruta

import com.example.myapplication.domain.model.CategoriaLugar
import com.example.myapplication.domain.model.LugarDestino
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** FE-5.1, criterio C3 (en la JVM): las entradas del grafo casan con los lugares del backend por nombre normalizado. */
class EmparejamientoTest {

    private fun lugar(id: String, nombre: String, alias: List<String> = emptyList()) =
        LugarDestino(id, nombre, CategoriaLugar.BLOQUE, 6.2, -75.57, alias)

    @Test
    fun normalizaSinTildesNiSignos() {
        assertEquals("cafeconverso", EmparejarLugares.normalizar("Café Con.verso"))
        assertEquals("bloque35", EmparejarLugares.normalizar(" Bloque  35 "))
        assertEquals("cafeteria", EmparejarLugares.normalizar("CAFETERÍA"))
        assertEquals("bano", EmparejarLugares.normalizar("Baño"))
    }

    @Test
    fun casaPorNombreOAliasYDistingueLosExactos() {
        val lugares = listOf(
            lugar("1", "Bloque 35"),
            lugar("2", "Bloque 33"),
            lugar("3", "Biblioteca Central", alias = listOf("biblioteca")),
            lugar("4", "Auditorio"),
        )
        val e = EmparejarLugares.emparejar(listOf("Bloque 35", "bloque 33", "biblioteca", "cocnverso", "biblioteca"), lugares)
        assertEquals(setOf("Bloque 35", "bloque 33", "biblioteca"), e.coinciden.keys)
        assertEquals("3", e.coinciden.getValue("biblioteca").id)
        assertEquals(setOf("Bloque 35"), e.exactos)
        assertEquals(listOf("cocnverso"), e.sinLugarEnBackend)
        assertEquals(listOf("4"), e.sinEntrada.map { it.id })
        assertTrue(EmparejarLugares.coincide("bloque35", lugares[0]))
        assertFalse(EmparejarLugares.coincide("bloque 3", lugares[0]))
    }

    @Test
    fun conLosLugaresDeDevHoySoloCasaBloque35() {
        // GET /v1/places en dev el 2026-10-28: un solo lugar, «Bloque 35» (backend §5.3).
        val e = EmparejarLugares.emparejar(GrafosDePrueba.real().lugares, listOf(lugar("b35", "Bloque 35")))
        assertEquals(setOf("Bloque 35"), e.exactos)
        assertEquals(
            listOf("bloque 33", "biblioteca", "bloque 38", "cocnverso", "bloque 34", "cafeteria"),
            e.sinLugarEnBackend,
        )
    }
}
