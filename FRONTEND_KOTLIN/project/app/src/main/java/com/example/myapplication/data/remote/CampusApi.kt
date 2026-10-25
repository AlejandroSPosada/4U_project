package com.example.myapplication.data.remote

import retrofit2.Response
import retrofit2.http.GET

/**
 * Rutas de la API del backend (contrato: `BACKEND_FASTAPI/docs/ARCHITECTURE.md` §5). La URL base ya termina en
 * `/v1/`, así que las rutas van **sin barra inicial** (`"health"`, no `"/health"`): con barra, Retrofit descartaría el
 * `/v1`. Todas devuelven `Response<T>` y se llaman con [llamar], que aplica el mapeo de errores de §5.10.
 *
 * FE-1.2 en adelante añaden aquí sus rutas (login, places, alerts, admin…).
 */
interface CampusApi {

    /** `GET /v1/health` (backend §5.3). Indicador de conexión de Inicio. */
    @GET("health")
    suspend fun salud(): Response<SaludDto>
}
