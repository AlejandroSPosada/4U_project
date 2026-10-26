package com.example.myapplication.ui.admin.lugares

import com.example.myapplication.domain.model.CategoriaLugar
import com.example.myapplication.domain.model.DatosLugar
import com.example.myapplication.domain.model.LugarAdmin
import com.example.myapplication.domain.model.LugarDestino
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.util.Locale

/**
 * Reglas del formulario de lugar (FE-3.4; apoyo de C2: la coordenada que se ve en el pie «Punto: …» es exactamente la
 * que se envía al backend). Lógica pura: `FormularioLugar` y `filtrarLugares`.
 */
class FormularioLugarTest {

    private lateinit var idiomaAnterior: Locale

    @Before
    fun idiomaDelTelefono() {
        idiomaAnterior = Locale.getDefault()
        Locale.setDefault(Locale.forLanguageTag("es-CO")) // con coma decimal: el texto del punto no debe cambiar
    }

    @After
    fun restaurar() {
        Locale.setDefault(idiomaAnterior)
    }

    private val valido = CamposLugar(
        nombre = "  Bloque 19 ",
        aliasTexto = "diecinueve, el 19",
        descripcion = "  ",
        categoria = CategoriaLugar.BLOQUE,
        punto = 6.2005123 to -75.5783119,
        referencias = " Junto a la cafetería ",
    )

    private fun admin(id: String, nombre: String, lat: Double, lng: Double, cat: CategoriaLugar = CategoriaLugar.BLOQUE) =
        LugarAdmin(LugarDestino(id, nombre, cat, lat, lng, alias = listOf("alias de $nombre")), "desc", "refs", 2)

    @Test
    fun redondear_aSeisDecimales_conNegativos() {
        assertEquals(6.200512, FormularioLugar.redondear(6.2005123456), 0.0)
        assertEquals(6.200513, FormularioLugar.redondear(6.2005126), 0.0)
        assertEquals(-75.578312, FormularioLugar.redondear(-75.5783119), 0.0)
        assertEquals(-75.578311, FormularioLugar.redondear(-75.578311), 0.0)
    }

    @Test
    fun textoPunto_conPuntoDecimal_aunqueElTelefonoEsteEnEspanol() {
        assertEquals("Punto: 6.200512, -75.578311", FormularioLugar.textoPunto(6.200512 to -75.578311))
        assertEquals("Punto: 6.200000, -75.500000", FormularioLugar.textoPunto(6.2 to -75.5))
        assertEquals(FormularioLugar.SIN_PUNTO, FormularioLugar.textoPunto(null))
    }

    @Test
    fun datos_recortaTextos_vaciosANull_yLaCoordenadaEsLaDelPie() {
        val d = FormularioLugar.datos(valido)

        assertEquals(
            DatosLugar(
                nombre = "Bloque 19", categoria = CategoriaLugar.BLOQUE, lat = 6.200512, lng = -75.578312,
                alias = listOf("diecinueve", "el 19"), descripcion = null, referencias = "Junto a la cafetería",
            ),
            d,
        )
        // Lo que se muestra en el pie, leído como número, es exactamente lo que se envía (C2).
        val pie = FormularioLugar.textoPunto(d!!.lat to d.lng).removePrefix("Punto: ").split(", ")
        assertEquals(d.lat, pie[0].toDouble(), 0.0)
        assertEquals(d.lng, pie[1].toDouble(), 0.0)
    }

    @Test
    fun aliasDeTexto_separaPorComasYLineas_sinVaciosNiRepetidos() {
        assertEquals(
            listOf("biblioteca", "la biblioteca", "biblio"),
            FormularioLugar.aliasDeTexto(" biblioteca, la biblioteca,,\nBiblioteca , biblio\n"),
        )
        assertEquals(emptyList<String>(), FormularioLugar.aliasDeTexto("  ,  "))
        assertEquals("a, b", FormularioLugar.textoDeAlias(listOf("a", "b")))
    }

    @Test
    fun validar_valido_sinErrores() {
        assertFalse(FormularioLugar.validar(valido).hay)
    }

    @Test
    fun validar_nombre_limitesTrasRecortar() {
        assertEquals(FormularioLugar.ERROR_NOMBRE_CORTO, FormularioLugar.validar(valido.copy(nombre = "  B ")).nombre)
        assertNull(FormularioLugar.validar(valido.copy(nombre = " Bx ")).nombre)
        assertNull(FormularioLugar.validar(valido.copy(nombre = "x".repeat(80))).nombre)
        assertEquals(FormularioLugar.ERROR_NOMBRE_LARGO, FormularioLugar.validar(valido.copy(nombre = "x".repeat(81))).nombre)
    }

    @Test
    fun validar_sinCategoriaNiPunto_yNoHayDatos() {
        val sinNada = valido.copy(categoria = null, punto = null)
        val e = FormularioLugar.validar(sinNada)

        assertEquals(FormularioLugar.ERROR_CATEGORIA, e.categoria)
        assertEquals(FormularioLugar.ERROR_PUNTO, e.punto)
        assertNull(FormularioLugar.datos(sinNada))
    }

    @Test
    fun validar_alias_yTextosLargos() {
        val muchos = (1..21).joinToString(",") { "alias$it" }
        assertEquals(FormularioLugar.ERROR_ALIAS_MUCHOS, FormularioLugar.validar(valido.copy(aliasTexto = muchos)).alias)
        assertEquals(FormularioLugar.ERROR_ALIAS_LARGO, FormularioLugar.validar(valido.copy(aliasTexto = "x".repeat(61))).alias)
        assertNull(FormularioLugar.validar(valido.copy(aliasTexto = "x".repeat(60))).alias)
        val e = FormularioLugar.validar(valido.copy(descripcion = "d".repeat(301), referencias = "r".repeat(301)))
        assertEquals(FormularioLugar.ERROR_TEXTO_LARGO, e.descripcion)
        assertEquals(FormularioLugar.ERROR_TEXTO_LARGO, e.referencias)
        assertNull(FormularioLugar.validar(valido.copy(descripcion = " " + "d".repeat(300) + " ")).descripcion)
    }

    @Test
    fun campos_deUnLugarGuardado_yVuelveAlosMismosDatos() {
        val l = admin("id-1", "Biblioteca Central", 6.2009, -75.5783, CategoriaLugar.BIBLIOTECA)

        val c = FormularioLugar.campos(l)

        assertEquals("alias de Biblioteca Central", c.aliasTexto)
        assertEquals(6.2009 to -75.5783, c.punto)
        assertEquals(l.datos(), FormularioLugar.datos(c))
    }

    @Test
    fun filtrar_porCategoriaYBuscador_comoEnDestino() {
        val todos = listOf(
            admin("1", "Biblioteca Central", 6.2, -75.5, CategoriaLugar.BIBLIOTECA),
            admin("2", "Bloque 19", 6.2, -75.5),
            admin("3", "Bloque 38", 6.2, -75.5),
        )

        assertEquals(listOf("2", "3"), filtrarLugares(todos, "", CategoriaLugar.BLOQUE).map { it.id })
        assertEquals(listOf("3"), filtrarLugares(todos, "38", null).map { it.id })
        assertEquals(listOf("1"), filtrarLugares(todos, "alias de biblio", null).map { it.id })
        assertTrue(filtrarLugares(todos, "38", CategoriaLugar.BIBLIOTECA).isEmpty())
    }
}
