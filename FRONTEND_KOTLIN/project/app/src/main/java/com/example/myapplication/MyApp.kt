package com.example.myapplication

import android.app.Application
import android.os.Build
import com.example.myapplication.data.remote.ClienteApi
import com.example.myapplication.logs.AppLog
import com.example.myapplication.session.EventosSesion
import com.example.myapplication.session.SessionManager
import com.example.myapplication.session.VigilanteSesion

class MyApp : Application() {
    override fun onCreate() {
        super.onCreate()
        AppLog.init(this)
        AppLog.i("App", "Inicio. ${Build.MANUFACTURER} ${Build.MODEL}, Android ${Build.VERSION.SDK_INT}")

        val previo = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { hilo, error ->
            AppLog.e("CRASH", "Excepción no capturada en hilo '${hilo.name}'", error)
            previo?.uncaughtException(hilo, error)
        }

        // El admin debe iniciar sesión cada vez que se abre la app desde cero
        val sesion = SessionManager(this)
        runCatching { sesion.cerrarSesion() }
            .onFailure { AppLog.e("App", "No se pudo limpiar la sesión", it) }

        // FE-1.2: sesión de las rutas /v1/admin y /v1/collect (token, expira_en y 401 de sesión → Login).
        ClienteApi.vigilante = VigilanteSesion(
            session = sesion,
            onSinSesion = EventosSesion::emitir,
            registrar = { AppLog.w(TAG_SESION, it) },
        )
    }

    private companion object {
        const val TAG_SESION = "Sesion"
    }
}
