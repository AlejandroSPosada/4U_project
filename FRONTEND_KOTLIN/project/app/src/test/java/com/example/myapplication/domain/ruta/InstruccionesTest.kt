package com.example.myapplication.domain.ruta

import com.example.myapplication.domain.ruta.GrafosDePrueba.codo
import com.example.myapplication.domain.ruta.GrafosDePrueba.cuadrado
import com.example.myapplication.domain.ruta.GrafosDePrueba.lat
import com.example.myapplication.domain.ruta.GrafosDePrueba.lng
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * FE-5.1, criterio C2: instrucciones a partir de los ángulos entre tramos (casi recto se junta; giros leves, normales y
 * cerrados a izquierda o derecha; la primera respecto al rumbo de la persona; «Has llegado» al final).
 */
class InstruccionesTest {

    private fun ruta(g: Grafo, x: Double, y: Double, rumbo: Double?): Ruta {
        val r = Planificador(g).calcular(lat(y), lng(x), listOf("Meta"), "Meta", rumbo)
        return (r as ResultadoRuta.Encontrada).ruta
    }

    private fun textos(r: Ruta) = r.instrucciones.map { it.texto }

    @Test
    fun clasificaPorUmbrales() {
        assertEquals(Giro.RECTO to Lado.NINGUNO, Instrucciones.clasificar(19.9))
        assertEquals(Giro.LEVE to Lado.DERECHA, Instrucciones.clasificar(20.0))
        assertEquals(Giro.LEVE to Lado.IZQUIERDA, Instrucciones.clasificar(-44.9))
        assertEquals(Giro.NORMAL to Lado.DERECHA, Instrucciones.clasificar(45.0))
        assertEquals(Giro.NORMAL to Lado.IZQUIERDA, Instrucciones.clasificar(-119.9))
        assertEquals(Giro.CERRADO to Lado.DERECHA, Instrucciones.clasificar(120.0))
        assertEquals(Giro.VUELTA to Lado.NINGUNO, Instrucciones.clasificar(150.0))
        assertEquals(Giro.VUELTA to Lado.NINGUNO, Instrucciones.clasificar(180.0))
        assertEquals("1 metro", Instrucciones.metrosTexto(0.3))
        assertEquals("40 metros", Instrucciones.metrosTexto(39.6))
    }

    @Test
    fun primeraRespectoAlRumboYGiroALaIzquierda() {
        // Desde (10, -5) a C: hacia el este 90 m hasta B y a la izquierda (norte) 100 m.
        assertEquals(
            listOf("Sigue recto 90 metros.", "Gira a la izquierda y sigue recto 100 metros.", "Has llegado a Meta."),
            textos(ruta(cuadrado(), 10.0, -5.0, rumbo = 90.0)),
        )
        assertEquals("Date la vuelta y sigue recto 90 metros.", ruta(cuadrado(), 10.0, -5.0, rumbo = 270.0).primera.texto)
        assertEquals("Gira a tu derecha y sigue recto 90 metros.", ruta(cuadrado(), 10.0, -5.0, rumbo = 0.0).primera.texto)
        assertEquals("Gira levemente a tu izquierda y sigue recto 90 metros.", ruta(cuadrado(), 10.0, -5.0, rumbo = 120.0).primera.texto)
        assertEquals("Camina 90 metros por el camino.", ruta(cuadrado(), 10.0, -5.0, rumbo = null).primera.texto)
    }

    @Test
    fun casiRectoSeJuntaConElAnterior() {
        val r = ruta(codo(10.0), 0.0, -1.0, rumbo = 90.0)
        assertEquals(listOf("Sigue recto 150 metros.", "Has llegado a Meta."), textos(r))
        assertEquals(150.0, r.metros, 0.5)
    }

    @Test
    fun girosLeveNormalYCerrado() {
        assertEquals("Gira levemente a la izquierda y sigue recto 50 metros.", ruta(codo(30.0), 0.0, -1.0, 90.0).instrucciones[1].texto)
        assertEquals("Gira a la derecha y sigue recto 50 metros.", ruta(codo(-60.0), 0.0, -1.0, 90.0).instrucciones[1].texto)
        assertEquals("Gira cerrado a la izquierda y sigue recto 50 metros.", ruta(codo(135.0), 0.0, -1.0, 90.0).instrucciones[1].texto)
    }

    @Test
    fun lejosDelCaminoLaPrimeraLlevaAlCamino() {
        // (50, -40): a 40 m de A–B. Ve al camino (norte), gira a la derecha hacia B y a la izquierda hacia C.
        val r = ruta(cuadrado(), 50.0, -40.0, rumbo = 180.0)
        assertTrue(r.fueraDelCamino)
        assertEquals(40.0, r.metrosAlCamino, 0.1)
        assertEquals(190.0, r.metros, 0.6)
        assertEquals(
            listOf(
                "Ve hasta el camino más cercano: date la vuelta y sigue recto 40 metros.",
                "Gira a la derecha y sigue recto 50 metros.",
                "Gira a la izquierda y sigue recto 100 metros.",
                "Has llegado a Meta.",
            ),
            textos(r),
        )
        assertEquals(TipoInstruccion.IR_AL_CAMINO, r.primera.tipo)
        assertEquals("Ve hasta el camino más cercano, a 40 metros.", ruta(cuadrado(), 50.0, -40.0, null).primera.texto)
    }

    @Test
    fun aMenosDelUmbralNoHayTramoAlCamino() {
        val r = ruta(cuadrado(), 50.0, -14.0, rumbo = 90.0)
        assertFalse(r.fueraDelCamino)
        assertEquals(150.0, r.metros, 0.5)
        assertEquals("Sigue recto 50 metros.", r.primera.texto)
        // El dibujo sí empieza en la persona.
        assertEquals(lat(-14.0), r.puntos.first().lat, 1e-7)
    }

    @Test
    fun distanciasAcumuladasYPuntosDeManiobra() {
        val r = ruta(cuadrado(), 10.0, -5.0, rumbo = 90.0)
        val (salida, giro, llegada) = r.instrucciones
        assertEquals(TipoInstruccion.SALIDA, salida.tipo)
        assertEquals(0.0, salida.desdeM, 1e-9)
        assertEquals(TipoInstruccion.GIRO, giro.tipo)
        assertEquals(Giro.NORMAL, giro.giro)
        assertEquals(Lado.IZQUIERDA, giro.lado)
        assertEquals(90.0, giro.desdeM, 0.5)
        assertEquals(lat(0.0), giro.lat, 1e-7)
        assertEquals(lng(100.0), giro.lng, 1e-7)
        assertEquals(TipoInstruccion.LLEGADA, llegada.tipo)
        assertEquals(r.metros, llegada.desdeM, 0.01)
        assertEquals(r.metros, r.instrucciones.sumOf { it.metros }, 0.01)
    }

    @Test
    fun enLaEntradaSoloHayLlegada() {
        val r = ruta(cuadrado(), 100.0, 100.0, rumbo = 0.0)
        assertEquals(listOf("Has llegado a Meta."), textos(r))
        assertEquals(0.0, r.metros, 0.01)
    }
}
