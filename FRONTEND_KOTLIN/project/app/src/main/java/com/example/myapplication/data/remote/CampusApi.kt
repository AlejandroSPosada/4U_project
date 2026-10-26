package com.example.myapplication.data.remote

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path

/**
 * Rutas de la API del backend (contrato: `BACKEND_FASTAPI/docs/ARCHITECTURE.md` §5). La URL base ya termina en
 * `/v1/`, así que las rutas van **sin barra inicial** (`"health"`, no `"/health"`): con barra, Retrofit descartaría el
 * `/v1`. Todas devuelven `Response<T>` y se llaman con [llamar], que aplica el mapeo de errores de §5.10.
 *
 * Cada lote añade aquí sus rutas (places, alerts, admin…).
 */
interface CampusApi {

    /** `GET /v1/health` (backend §5.3). Indicador de conexión de Inicio. */
    @GET("health")
    suspend fun salud(): Response<SaludDto>

    /** `POST /v1/auth/login` (backend §5.3; FE-1.2). Ruta pública: no lleva `Authorization`. */
    @POST("auth/login")
    suspend fun login(@Body cuerpo: LoginPeticionDto): Response<LoginRespuestaDto>

    /** `POST /v1/collect/videos` (backend §5.4; FE-2.1): `201` nuevo, `200` si ya existía ese `ref_cliente`. */
    @POST("collect/videos")
    suspend fun crearVideo(@Body cuerpo: VideoCrearDto): Response<VideoResumenDto>

    /** `POST /v1/collect/videos/{id}/images` (backend §5.4; FE-2.1): registra hasta 50 fotos y da sus URLs `PUT`. */
    @POST("collect/videos/{id}/images")
    suspend fun registrarImagenes(
        @Path("id") videoId: String,
        @Body cuerpo: ImagenesRegistrarDto,
    ): Response<ImagenesRegistradasDto>

    /** `POST /v1/collect/videos/{id}/complete` (backend §5.4; FE-2.1). Sin cuerpo (Retrofit envía uno vacío). */
    @POST("collect/videos/{id}/complete")
    suspend fun completarSubida(@Path("id") videoId: String): Response<SubidaCompletadaDto>

    /** `GET /v1/admin/videos/{id}` (backend §5.5; FE-2.1): `VideoResumen` + `fotos` para el progreso por foto. */
    @GET("admin/videos/{id}")
    suspend fun video(@Path("id") videoId: String): Response<VideoResumenDto>
}
