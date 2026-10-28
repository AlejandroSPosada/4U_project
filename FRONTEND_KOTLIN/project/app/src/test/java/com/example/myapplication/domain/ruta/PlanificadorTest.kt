package com.example.myapplication.domain.ruta

import com.example.myapplication.domain.model.CategoriaLugar
import com.example.myapplication.domain.model.LugarCercano
import com.example.myapplication.domain.model.LugarDestino
import com.example.myapplication.domain.model.NivelConfianza
import com.example.myapplication.domain.model.PosicionEstimada
import com.example.myapplication.domain.model.ResultadoUbicacion
import com.example.myapplication.domain.model.UbicacionEstimada
import com.example.myapplication.domain.usecase.DescribirUbicacion
import com.google.gson.JsonParser
import org.junit.Assert.assertEquals
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * FE-5.1, criterio C4 (en la JVM): con el `grafo.json` real, la ruta de la validación en casa (`validate51.py`:
 * destino `bloque35` y posición de prueba 6.201434, −75.578427, sobre la arista n0008–n0014) y lo que dice la vista
 * 6.3 con ruta y sin ella.
 */
class PlanificadorTest {

    private val planificador = Planificador(GrafosDePrueba.real())

    /** La misma posición que `POSICION_PRUEBA` de `validate51.py`. */
    private val latPrueba = 6.201434
    private val lngPrueba = -75.578427

    private val bloque35 = LugarDestino("b35", "Bloque 35", CategoriaLugar.BLOQUE, 6.201286, -75.578834)

    @Test
    fun rutaDeLaValidacionEnCasa() {
        val r = planificador.calcular(latPrueba, lngPrueba, listOf("bloque35"), "Bloque 35", null)
        val ruta = (r as ResultadoRuta.Encontrada).ruta
        assertEquals("n0007", ruta.entrada.id)
        assertEquals("a0043", ruta.inicio.arista.id)
        assertEquals(59.7, ruta.metros, 0.3)
        assertTrue(ruta.metrosAlCamino < 1.0)
        assertEquals(
            listOf("Camina 45 metros por el camino.", "Gira a la izquierda y sigue recto 14 metros.", "Has llegado a Bloque 35."),
            ruta.instrucciones.map { it.texto },
        )
        // Lo que muestra el aviso del mapa y lo que busca validate51.py C4b.
        assertEquals("Ruta a Bloque 35: 60 m por el camino", com.example.myapplication.map.TextosRutaMapa.titulo("Bloque 35", ruta.metros))
    }

    @Test
    fun laPrimeraDependeDelRumbo() {
        val norte = planificador.rutaA(bloque35, latPrueba, lngPrueba, 0.0)!!
        assertEquals("Gira a tu izquierda y sigue recto 45 metros.", norte.primera.texto)
        val oeste = planificador.rutaA(bloque35, latPrueba, lngPrueba, 270.0)!!
        assertEquals("Sigue recto 45 metros.", oeste.primera.texto)
    }

    @Test
    fun unLugarConDosEntradasVaALaMasCercana() {
        val biblio = planificador.calcular(latPrueba, lngPrueba, listOf("Biblioteca"), "Biblioteca", null)
        val ruta = (biblio as ResultadoRuta.Encontrada).ruta
        assertEquals("n0010", ruta.entrada.id) // la del norte; la otra (n0030) queda a ~150 m
        assertEquals(40.0, ruta.metros, 1.5)
        assertEquals(2, planificador.entradasDe(listOf("BIBLIOTECA")).size)
    }

    @Test
    fun casaPorAliasYDestinoFueraDelGrafo() {
        val conAlias = LugarDestino("c", "Cafetería Central", CategoriaLugar.CAFETERIA, 6.2, -75.57, alias = listOf("cafetería"))
        assertEquals("n0031", planificador.rutaA(conAlias, latPrueba, lngPrueba, null)!!.entrada.id)
        val fuera = LugarDestino("x", "Auditorio", CategoriaLugar.AUDITORIO, 6.2, -75.57)
        assertSame(ResultadoRuta.DestinoFueraDelGrafo, planificador.calcular(latPrueba, lngPrueba, fuera, null))
    }

    @Test
    fun jsonParaElMapa() {
        val ruta = planificador.rutaA(bloque35, latPrueba, lngPrueba, null)!!
        val o = JsonParser.parseString(ruta.json()).asJsonObject
        assertEquals("Bloque 35", o.get("destino").asString)
        assertEquals(59.7, o.get("metros").asDouble, 0.3)
        assertEquals("Camina 45 metros por el camino.", o.get("primera").asString)
        val puntos = o.getAsJsonArray("puntos")
        assertEquals(ruta.puntos.size, puntos.size())
        assertEquals(6.2013034, puntos.last().asJsonArray[0].asDouble, 1e-7) // la entrada n0007
    }

    private fun ubicadoEn(lat: Double, lng: Double) = UbicacionEstimada(
        ResultadoUbicacion.Ubicado(
            posicion = PosicionEstimada(lat, lng, 5.0),
            confianza = 0.8,
            nivel = NivelConfianza.ALTA,
            correccionRumboGrados = -10.0,
            lugarCercano = LugarCercano("b38", "Bloque 38", 15.0),
            referencias = emptyList(),
            fotosUsadas = 5,
            fotosConCoincidencia = 5,
        ),
        obtenidaEnMs = 0L,
        rumboAlTerminar = null,
    )

    @Test
    fun laVista63DiceLaDistanciaPorElCaminoYLaPrimeraInstruccion() {
        // Brújula 10° + corrección −10° = norte: el camino va al oeste, «a tu izquierda».
        val d = DescribirUbicacion.describir(ubicadoEn(latPrueba, lngPrueba), 10.0, bloque35, planificador)
        assertEquals(
            listOf(
                "Tu destino, Bloque 35, está a unos 60 metros por el camino.",
                "Gira a tu izquierda y sigue recto 45 metros.",
                DescribirUbicacion.LLEGARA_NAVEGACION,
            ),
            d.detalles,
        )
        assertTrue(d.hablado.endsWith("Confianza alta. Tu destino, Bloque 35, está a unos 60 metros por el camino. " +
            "Gira a tu izquierda y sigue recto 45 metros. ${DescribirUbicacion.LLEGARA_NAVEGACION}"))
    }

    @Test
    fun laVista63SinRutaSigueEnLineaRecta() {
        val fuera = LugarDestino("x", "Auditorio", CategoriaLugar.AUDITORIO, latPrueba + 0.001, lngPrueba)
        val conPlan = DescribirUbicacion.describir(ubicadoEn(latPrueba, lngPrueba), 10.0, fuera, planificador)
        val sinPlan = DescribirUbicacion.describir(ubicadoEn(latPrueba, lngPrueba), 10.0, fuera, null)
        assertEquals(sinPlan, conPlan)
        assertEquals("Tu destino, Auditorio, está al frente, a unos 111 metros.", conPlan.detalles.first())
    }
}
