package com.example.myapplication.ui.admin.lugares

import com.example.myapplication.data.remote.ApiException
import com.example.myapplication.data.remote.CampoInvalido
import com.example.myapplication.data.remote.FalloApi
import com.example.myapplication.data.remote.MapeoErroresApi
import com.example.myapplication.data.remote.RespuestaInesperadaException
import com.example.myapplication.data.remote.SinConexionException
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * Qué muestra el formulario de lugar ante un error del backend (FE-3.4; apoyo de C3: el `409 NOMBRE_DUPLICADO` va bajo
 * el campo nombre). Parte de los cuerpos reales del contrato (backend §5.5 y §5.6) clasificados por `MapeoErroresApi`.
 */
class ErroresLugarTest {

    private fun desdeRespuesta(http: Int, cuerpo: String): ErroresLugar? =
        ErroresLugarMapeo.deExcepcion(ApiException(MapeoErroresApi.clasificar(http, cuerpo), http, "rid"))

    @Test
    fun nombreDuplicado409_vaBajoElNombre_ySoloAhi() {
        val e = desdeRespuesta(
            409,
            """{"error": {"codigo": "NOMBRE_DUPLICADO", "mensaje": "Ya existe un lugar con ese nombre (sin distinguir mayúsculas ni tildes).", "detalle": null}}""",
        )

        assertEquals(ErroresLugar(nombre = ErroresLugarMapeo.NOMBRE_DUPLICADO), e)
    }

    @Test
    fun validacion422_cadaCampoASuSitio_yLosDesconocidosAlGeneral() {
        val e = ErroresLugarMapeo.deFallo(
            FalloApi.Validacion(
                422, "VALIDACION", "x",
                listOf(
                    CampoInvalido("nombre", "Debe tener entre 2 y 80 caracteres."),
                    CampoInvalido("alias.3", "Vacío."),
                    CampoInvalido("body.descripcion", ""),
                    CampoInvalido("lat", "Fuera de rango."),
                    CampoInvalido("otro", "Raro."),
                ),
            ),
        )

        assertEquals("Debe tener entre 2 y 80 caracteres.", e?.nombre)
        assertEquals("Vacío.", e?.alias)
        assertEquals(ErroresLugarMapeo.CAMPO_INVALIDO, e?.descripcion)
        assertEquals("Fuera de rango.", e?.punto)
        assertEquals("Revisa los datos (otro: Raro.).", e?.general)
    }

    @Test
    fun sesionPerdida_noMuestraNada() {
        assertNull(ErroresLugarMapeo.deFallo(FalloApi.SesionVencida("TOKEN_EXPIRADO")))
        assertNull(
            ErroresLugarMapeo.deExcepcion(
                ApiException(FalloApi.SesionVencida(MapeoErroresApi.SIN_SESION_LOCAL), 401, null),
            ),
        )
    }

    @Test
    fun sinRed_lugarBorrado_yOtros_alMensajeGeneral() {
        assertEquals(ErroresLugar(general = ErroresLugarMapeo.SIN_CONEXION), ErroresLugarMapeo.deExcepcion(SinConexionException()))
        assertEquals(
            ErroresLugar(general = ErroresLugarMapeo.NO_EXISTE),
            desdeRespuesta(404, """{"error": {"codigo": "NO_ENCONTRADO", "mensaje": "x", "detalle": null}}"""),
        )
        assertEquals(
            ErroresLugar(general = ErroresLugarMapeo.SIN_PERMISOS),
            desdeRespuesta(403, """{"error": {"codigo": "SIN_PERMISOS", "mensaje": "x", "detalle": null}}"""),
        )
        assertEquals(
            ErroresLugar(general = ErroresLugarMapeo.ALGO_SALIO_MAL),
            desdeRespuesta(503, """{"error": {"codigo": "BASE_NO_DISPONIBLE", "mensaje": "x", "detalle": null}}"""),
        )
        assertEquals(
            ErroresLugar(general = ErroresLugarMapeo.ALGO_SALIO_MAL),
            ErroresLugarMapeo.deExcepcion(RespuestaInesperadaException("x")),
        )
    }

    @Test
    fun errorDeCargaDeLaLista_sinRedOGenerico_yNadaSinSesion() {
        assertEquals(ErroresLugarMapeo.SIN_CONEXION, ErroresLugarMapeo.errorDeCarga(SinConexionException()))
        assertEquals(ErroresLugarMapeo.ERROR_CARGA, ErroresLugarMapeo.errorDeCarga(RespuestaInesperadaException("x")))
        assertNull(ErroresLugarMapeo.errorDeCarga(ApiException(FalloApi.SesionVencida("TOKEN_INVALIDO"), 401, null)))
    }
}
