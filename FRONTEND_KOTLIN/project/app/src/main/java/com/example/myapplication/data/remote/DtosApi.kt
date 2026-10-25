package com.example.myapplication.data.remote

import com.google.gson.annotations.SerializedName

/*
 * DTOs: el JSON del backend tal cual (backend §5.3 y §5.5), con los nombres en snake_case por @SerializedName.
 *
 * Todos los campos son anulables y con valor por defecto: Gson crea los objetos sin pasar por el constructor de
 * Kotlin, así que un campo que falta queda en null aunque el tipo diga lo contrario y los valores por defecto no se
 * aplican. Las comprobaciones (campo obligatorio, enumerado conocido) se hacen en MapeoDatosApi, que lanza
 * RespuestaInesperadaException si algo obligatorio falta.
 */

/** `GET /v1/health`. */
data class SaludDto(
    @SerializedName("estado") val estado: String? = null,
    @SerializedName("version") val version: String? = null,
    @SerializedName("commit") val commit: String? = null,
)

/** `usuario` de `POST /v1/auth/login`. */
data class UsuarioDto(
    @SerializedName("id") val id: String? = null,
    @SerializedName("nombre") val nombre: String? = null,
    @SerializedName("correo") val correo: String? = null,
    @SerializedName("rol") val rol: String? = null,
)

/** Respuesta 200 de `POST /v1/auth/login`. */
data class LoginRespuestaDto(
    @SerializedName("token") val token: String? = null,
    @SerializedName("expira_en") val expiraEn: String? = null,
    @SerializedName("usuario") val usuario: UsuarioDto? = null,
)

/** `LugarPublico` de `GET /v1/places`. */
data class LugarPublicoDto(
    @SerializedName("id") val id: String? = null,
    @SerializedName("nombre") val nombre: String? = null,
    @SerializedName("categoria") val categoria: String? = null,
    @SerializedName("lat") val lat: Double? = null,
    @SerializedName("lng") val lng: Double? = null,
    @SerializedName("alias") val alias: List<String>? = null,
    @SerializedName("descripcion") val descripcion: String? = null,
    @SerializedName("referencias") val referencias: String? = null,
    @SerializedName("imagen_url") val imagenUrl: String? = null,
    @SerializedName("distancia_m") val distanciaM: Double? = null,
)

/** `Alerta` de `GET /v1/alerts` (y la base de `AlertaAdmin`). */
data class AlertaDto(
    @SerializedName("id") val id: String? = null,
    @SerializedName("lat") val lat: Double? = null,
    @SerializedName("lng") val lng: Double? = null,
    @SerializedName("mensaje") val mensaje: String? = null,
    @SerializedName("tipo") val tipo: String? = null,
    @SerializedName("prioridad") val prioridad: String? = null,
    @SerializedName("radio_m") val radioM: Int? = null,
    @SerializedName("activa") val activa: Boolean? = null,
    @SerializedName("vigencia_desde") val vigenciaDesde: String? = null,
    @SerializedName("vigencia_hasta") val vigenciaHasta: String? = null,
    @SerializedName("actualizado_en") val actualizadoEn: String? = null,
    @SerializedName("version") val version: Int? = null,
)

/** `ultimo_video` de `GET /v1/admin/stats`. */
data class UltimoVideoDto(
    @SerializedName("numero") val numero: Int? = null,
    @SerializedName("creado_en") val creadoEn: String? = null,
)

/** `GET /v1/admin/stats`. */
data class EstadisticasAdminDto(
    @SerializedName("total_fotos") val totalFotos: Int? = null,
    @SerializedName("total_lugares") val totalLugares: Int? = null,
    @SerializedName("alertas_activas") val alertasActivas: Int? = null,
    @SerializedName("ultimo_video") val ultimoVideo: UltimoVideoDto? = null,
)

/** `{id, nombre}` de `lugar` y `creado_por`. */
data class ReferenciaDto(
    @SerializedName("id") val id: String? = null,
    @SerializedName("nombre") val nombre: String? = null,
)

/** `ImagenAdmin` de `GET /v1/admin/videos/{id}` e `/v1/admin/images`. */
data class ImagenAdminDto(
    @SerializedName("id") val id: String? = null,
    @SerializedName("video_id") val videoId: String? = null,
    @SerializedName("orden") val orden: Int? = null,
    @SerializedName("lat") val lat: Double? = null,
    @SerializedName("lng") val lng: Double? = null,
    @SerializedName("rumbo") val rumbo: Double? = null,
    @SerializedName("capturada_en") val capturadaEn: String? = null,
    @SerializedName("estado") val estado: String? = null,
    @SerializedName("error") val error: String? = null,
    @SerializedName("calidad") val calidad: String? = null,
    @SerializedName("lugar") val lugar: ReferenciaDto? = null,
    @SerializedName("notas") val notas: String? = null,
    @SerializedName("url") val url: String? = null,
    @SerializedName("url_miniatura") val urlMiniatura: String? = null,
    @SerializedName("url_expira_en") val urlExpiraEn: String? = null,
)

/** `VideoResumen` (y `VideoResumen` + `fotos` de `GET /v1/admin/videos/{id}`). */
data class VideoResumenDto(
    @SerializedName("id") val id: String? = null,
    @SerializedName("numero") val numero: Int? = null,
    @SerializedName("nombre") val nombre: String? = null,
    @SerializedName("ref_cliente") val refCliente: String? = null,
    @SerializedName("estado") val estado: String? = null,
    @SerializedName("creado_en") val creadoEn: String? = null,
    @SerializedName("total_fotos") val totalFotos: Int? = null,
    @SerializedName("fotos") val fotos: List<ImagenAdminDto>? = null,
)
