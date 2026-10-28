package com.example.myapplication.domain.ruta

import com.example.myapplication.domain.ruta.GrafosDePrueba.cuadrado
import com.example.myapplication.domain.ruta.GrafosDePrueba.lat
import com.example.myapplication.domain.ruta.GrafosDePrueba.lng
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * FE-5.1, criterio C2: la posición se proyecta sobre la **arista** más cercana (no el nodo más cercano) y la ruta más
 * corta sale de ese nodo virtual, sin aristas bloqueadas, a la entrada más cercana del lugar.
 */
class ProyeccionRutaTest {

    private fun proyectar(g: Grafo, x: Double, y: Double) = Proyeccion.masCercana(g, lat(y), lng(x))!!

    @Test
    fun proyectaSobreElSegmentoConFraccionYDistancia() {
        val p = proyectar(cuadrado(), 10.0, -5.0)
        assertEquals("ab", p.arista.id)
        assertEquals(0.1, p.t, 0.002)
        assertEquals(5.0, p.distanciaM, 0.05)
        assertEquals(lat(0.0), p.lat, 1e-7)
        assertEquals(lng(10.0), p.lng, 1e-7)
        assertEquals(10.0, p.metrosHastaA, 0.2)
        assertEquals(90.0, p.metrosHastaB, 0.2)
    }

    @Test
    fun fueraDelSegmentoSeRecortaAlExtremo() {
        val p = proyectar(cuadrado(), -30.0, -40.0)
        assertEquals(0.0, p.t, 1e-9)
        assertEquals(50.0, p.distanciaM, 0.1)
    }

    @Test
    fun noUsaAristasBloqueadas() {
        // (105, 50) está a 5 m de B–C; con B–C bloqueada, lo más cerca son los extremos B o C (a ~50,25 m).
        val libre = proyectar(cuadrado(), 105.0, 50.0)
        assertEquals("bc", libre.arista.id)
        assertEquals(5.0, libre.distanciaM, 0.05)
        val bloqueada = proyectar(cuadrado(bloquearBC = true), 105.0, 50.0)
        assertEquals(50.25, bloqueada.distanciaM, 0.2)
    }

    @Test
    fun sinAristasUsablesNoHayProyeccion() {
        val g = Grafo(1, 1, null, cuadrado().nodos, cuadrado().aristas.map { it.copy(bloqueada = true) })
        assertNull(Proyeccion.masCercana(g, lat(0.0), lng(0.0)))
    }

    @Test
    fun laRutaSaleDelPuntoProyectadoNoDelNodoMasCercano() {
        // A 45 m de A y 55 m de B: el nodo más cercano es A, pero la ruta a C va hacia B (55 + 100), no hacia atrás.
        val g = cuadrado()
        val inicio = proyectar(g, 45.0, -3.0)
        val camino = CalculoRuta.masCorta(g, inicio, setOf("C"))!!
        assertEquals(listOf("B", "C"), camino.nodos.map { it.id })
        assertEquals(155.0, camino.metros, 0.5)
        assertEquals("C", camino.entrada.id)
    }

    @Test
    fun evitaLasAristasBloqueadas() {
        val g = cuadrado(bloquearBC = true)
        val camino = CalculoRuta.masCorta(g, proyectar(g, 45.0, -3.0), setOf("C"))!!
        assertEquals(listOf("A", "D", "C"), camino.nodos.map { it.id })
        assertEquals(245.0, camino.metros, 0.5)
    }

    @Test
    fun conVariasEntradasGanaLaMasCercanaPorElCamino() {
        val g = cuadrado(entradaE = true)
        val camino = CalculoRuta.masCorta(g, proyectar(g, 90.0, -2.0), setOf("C", "E"))!!
        assertEquals("E", camino.entrada.id)
        assertEquals(60.0, camino.metros, 0.5)
    }

    @Test
    fun sinCaminoODestinosVaciosDaNull() {
        // C solo se alcanza por B–C (bloqueada) y C–D; si C–D también se bloquea, C queda inalcanzable.
        val base = cuadrado(bloquearBC = true)
        val g = Grafo(1, 1, null, base.nodos, base.aristas.map { if (it.id == "cd") it.copy(bloqueada = true) else it })
        val inicio = proyectar(g, 45.0, -3.0)
        assertNull(CalculoRuta.masCorta(g, inicio, setOf("C")))
        assertNull(CalculoRuta.masCorta(g, inicio, emptySet()))
    }

    @Test
    fun enUnNodoDestinoLaRutaMideCero() {
        val g = cuadrado()
        val camino = CalculoRuta.masCorta(g, proyectar(g, 100.0, 100.0), setOf("C"))!!
        assertEquals(listOf("C"), camino.nodos.map { it.id })
        assertEquals(0.0, camino.metros, 0.01)
    }
}
