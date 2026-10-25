package com.example.myapplication.data.remote

import com.example.myapplication.domain.model.Alerta
import com.example.myapplication.domain.model.CalidadFoto
import com.example.myapplication.domain.model.CategoriaLugar
import com.example.myapplication.domain.model.EstadoFoto
import com.example.myapplication.domain.model.Foto
import com.example.myapplication.domain.model.LugarDestino
import com.example.myapplication.domain.model.ResumenAdmin
import com.example.myapplication.domain.model.Rol
import com.example.myapplication.domain.model.Usuario
import com.example.myapplication.domain.model.Video
import java.text.ParseException
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone
import kotlin.math.roundToInt

/**
 * Mapeo de datos de ARCHITECTURE §5.10 (backend JSON → modelos de la app). Lógica pura, sin Android: se prueba en
 * `MapeoDatosApiTest`. Un campo obligatorio que falta lanza [RespuestaInesperadaException].
 */
object MapeoDatosApi {

    /**
     * Enumerado en minúsculas del backend → enum de Kotlin (`"biblioteca"` → `BIBLIOTECA`). `null` si no existe.
     * Usa `Locale.ROOT`: con el idioma del teléfono en turco, `"biblioteca".uppercase()` daría una `İ`.
     */
    inline fun <reified E : Enum<E>> enumDe(valor: String?): E? {
        if (valor == null) return null
        val nombre = valor.trim().uppercase(Locale.ROOT)
        return enumValues<E>().firstOrNull { it.name == nombre }
    }

    fun usuario(dto: UsuarioDto?): Usuario {
        val u = dto ?: throw RespuestaInesperadaException("login sin usuario")
        return Usuario(
            id = obligatorio(u.id, "usuario.id"),
            nombre = u.nombre ?: "",
            correo = obligatorio(u.correo, "usuario.correo"),
            rol = enumDe<Rol>(u.rol) ?: throw RespuestaInesperadaException("rol desconocido: ${u.rol}"),
        )
    }

    /** `expira_en` del login en milisegundos (FE-1.2 lo guarda con la sesión). */
    fun expiraEnMs(dto: LoginRespuestaDto): Long =
        isoAMilis(dto.expiraEn) ?: throw RespuestaInesperadaException("expira_en ausente o inválido")

    /** `LugarPublico` → `LugarDestino`. `null` si la categoría no la conoce la app (se descarta el lugar). */
    fun lugarDestino(dto: LugarPublicoDto): LugarDestino? {
        val categoria = enumDe<CategoriaLugar>(dto.categoria) ?: return null
        return LugarDestino(
            id = obligatorio(dto.id, "lugar.id"),
            nombre = obligatorio(dto.nombre, "lugar.nombre"),
            categoria = categoria,
            lat = obligatorio(dto.lat, "lugar.lat"),
            lng = obligatorio(dto.lng, "lugar.lng"),
            alias = dto.alias.orEmpty(),
            distanciaMetros = dto.distanciaM?.roundToInt(),
            imagenUrl = dto.imagenUrl,
        )
    }

    /** `Alerta` del backend → `Alerta` (`radio_m` → `radio`; `tipo` y `prioridad` quedan como texto). */
    fun alerta(dto: AlertaDto): Alerta = Alerta(
        id = obligatorio(dto.id, "alerta.id"),
        lat = obligatorio(dto.lat, "alerta.lat"),
        lng = obligatorio(dto.lng, "alerta.lng"),
        mensaje = obligatorio(dto.mensaje, "alerta.mensaje"),
        tipo = dto.tipo ?: "otro",
        prioridad = dto.prioridad ?: "normal",
        radio = dto.radioM ?: 15,
        activa = dto.activa ?: true,
    )

    /** `GET /v1/admin/stats` → `ResumenAdmin`. [fotosPendientes] sale de la cola local de subida, no del backend. */
    fun resumenAdmin(dto: EstadisticasAdminDto, fotosPendientes: Int): ResumenAdmin = ResumenAdmin(
        totalFotos = obligatorio(dto.totalFotos, "total_fotos"),
        totalLugares = obligatorio(dto.totalLugares, "total_lugares"),
        alertasActivas = obligatorio(dto.alertasActivas, "alertas_activas"),
        ultimoVideoNumero = dto.ultimoVideo?.numero,
        ultimoVideoFecha = isoAMilis(dto.ultimoVideo?.creadoEn),
        fotosPendientes = fotosPendientes,
    )

    /**
     * `estado` de `ImagenAdmin` → `EstadoFoto`. `pendiente_subida` (y cualquier valor desconocido) da `null`: la app
     * aún no tiene `EstadoFoto.PENDIENTE` (lo añade FE-2.1). [foto] lo muestra entretanto como `SUBIDA`.
     */
    fun estadoFoto(valor: String?): EstadoFoto? = enumDe<EstadoFoto>(valor)

    /** `ImagenAdmin` → `Foto` del video [videoNombre]. URLs `null` (hasta BE-4.1) quedan como `""`. */
    fun foto(dto: ImagenAdminDto, videoNombre: String): Foto = Foto(
        id = obligatorio(dto.id, "imagen.id"),
        videoId = obligatorio(dto.videoId, "imagen.video_id"),
        videoNombre = videoNombre,
        urlFoto = dto.url ?: "",
        urlMiniatura = dto.urlMiniatura ?: "",
        lat = obligatorio(dto.lat, "imagen.lat"),
        lng = obligatorio(dto.lng, "imagen.lng"),
        rumbo = dto.rumbo?.toFloat(),
        capturadaEn = dto.capturadaEn,
        lugar = dto.lugar?.nombre,
        estado = estadoFoto(dto.estado) ?: EstadoFoto.SUBIDA,
        calidad = enumDe<CalidadFoto>(dto.calidad) ?: CalidadFoto.NORMAL,
    )

    /** `VideoResumen` (+ `fotos` si viene del detalle) → `Video`. El `id` es el UUID del backend. */
    fun video(dto: VideoResumenDto): Video {
        val nombre = dto.nombre ?: ""
        return Video(
            id = obligatorio(dto.id, "video.id"),
            nombre = nombre,
            creadoEn = dto.creadoEn,
            fotos = dto.fotos.orEmpty().sortedBy { it.orden ?: Int.MAX_VALUE }.map { foto(it, nombre) },
        )
    }

    /**
     * Fecha ISO-8601 en UTC del backend (`2026-10-23T15:04:05Z`, backend §5.1) → milisegundos epoch, o `null`.
     * Acepta fracciones de segundo (se descartan) y solo la zona `Z`. Usa `SimpleDateFormat` y no `java.time`
     * porque `minSdk = 24` (java.time llega en la API 26).
     */
    fun isoAMilis(texto: String?): Long? {
        val t = texto?.trim()?.takeIf { it.endsWith("Z") } ?: return null
        val sinZona = t.dropLast(1).substringBefore('.')
        val formato = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.ROOT).apply {
            timeZone = TimeZone.getTimeZone("UTC")
            isLenient = false
        }
        return try {
            formato.parse(sinZona)?.time
        } catch (_: ParseException) {
            null
        }
    }

    private fun <T : Any> obligatorio(valor: T?, campo: String): T =
        valor ?: throw RespuestaInesperadaException("falta $campo")
}
