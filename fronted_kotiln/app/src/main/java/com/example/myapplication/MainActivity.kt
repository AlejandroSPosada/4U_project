package com.example.myapplication

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.example.myapplication.ui.inicio.InicioScreen
import com.example.myapplication.ui.destino.SeleccionDestinoScreen
import com.example.myapplication.ui.ubicacion.EscaneoScreen
import com.example.myapplication.ui.auth.LoginScreen
import com.example.myapplication.ui.admin.panel.PanelAdminScreen
import com.example.myapplication.ui.admin.mapa.EditorMapaScreen
import com.example.myapplication.ui.admin.imagenes.GaleriaScreen
import com.example.myapplication.ui.admin.videos.VideoDetalleScreen
import com.example.myapplication.ui.admin.videos.VideosScreen
import com.example.myapplication.map.MapaPublicoScreen
import com.example.myapplication.ui.admin.recoleccion.UbicacionManualScreen

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MaterialTheme {
                AppNav()
            }
        }
    }
}

/** Permisos de tiempo de ejecución de la app. */
object Permisos {
    val CAMARA = Manifest.permission.CAMERA
    val MICROFONO = Manifest.permission.RECORD_AUDIO

    /** Todos los que se piden al abrir Inicio por primera vez. */
    val INICIALES: Array<String> = buildList {
        add(CAMARA)
        add(MICROFONO)
        // ACTIVITY_RECOGNITION solo existe como permiso de ejecución desde Android 10
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            add(Manifest.permission.ACTIVITY_RECOGNITION)
        }
    }.toTypedArray()
}

@Composable
fun AppNav() {
    val nav = rememberNavController()

    // Regla: cada ruta se registra UNA sola vez. Si se repite, la última reemplaza a la anterior
    // (un placeholder vacío puede tapar la pantalla real).
    NavHost(navController = nav, startDestination = "inicio") {

        composable("inicio") {
            // Un solo diálogo con cámara + micrófono + actividad física.
            // Inicio se muestra aunque el usuario niegue alguno (queda la opción táctil).
            var permisosPedidos by rememberSaveable { mutableStateOf(false) }

            if (!permisosPedidos) {
                PedirPermisos(
                    permisos = Permisos.INICIALES,
                    onResultado = { permisosPedidos = true },
                )
            } else {
                InicioScreen(
                    onUbicarme = { nav.navigate("ubicarme") },
                    onIrALugar = { nav.navigate("destino") },
                    onAccesoAdministrador = { nav.navigate("login") },
                )
            }
        }

        composable("ubicarme") {
            // La cámara es indispensable: si ya estaba concedida pasa directo;
            // si no, se vuelve a pedir. Si la niega, vuelve a Inicio.
            var camaraLista by rememberSaveable { mutableStateOf(false) }

            if (!camaraLista) {
                PedirPermisos(
                    permisos = arrayOf(Permisos.CAMARA),
                    onResultado = { concedido ->
                        if (concedido) camaraLista = true
                        else nav.popBackStack()
                    },
                )
            } else {
                EscaneoScreen(
                    onCancelar = { nav.popBackStack() },
                    onCompletado = {
                        // TODO: navegar al resultado del escaneo
                        // nav.navigate("resultado")
                        nav.popBackStack()
                    },
                )
            }
        }

        // 6.4 Selección de destino
        composable("destino") {
            SeleccionDestinoScreen(
                onVolver = { nav.popBackStack() },
                onDestinoConfirmado = { _ ->
                    // TODO: guardar el destino elegido y, tras el escaneo 360° (si no hay ubicación
                    // vigente), abrir NavegacionScreen (6.5). Por ahora solo lanza el escaneo.
                    nav.navigate("ubicarme")
                },
                onAjustes = { nav.navigate("ajustes") },
            )
        }

        composable("login") {
            LoginScreen(
                onLoginExitoso = {
                    nav.navigate("admin/panel") {
                        popUpTo("login") { inclusive = true }
                    }
                },
                onVolver = { nav.popBackStack() },
            )
        }

        composable("admin/panel") {
            PanelAdminScreen(
                onRecolector = { nav.navigate("admin/ubicacion-manual") },
                onLugares = { nav.navigate("admin/lugares") },
                onMapaAlertas = { nav.navigate("admin/mapa") },
                onImagenes = { nav.navigate("admin/imagenes") },
                onVideos = { nav.navigate("admin/videos") },
                onEstadisticas = { nav.navigate("admin/estadisticas") },
                onAjustes = { nav.navigate("ajustes") },
                onVolverModoPublico = { nav.popBackStack("inicio", inclusive = false) },
                onSesionCerrada = { nav.popBackStack("inicio", inclusive = false) },
                onSinSesion = {
                    nav.navigate("login") { popUpTo("admin/panel") { inclusive = true } }
                },
            )
        }

        // ── Vistas implementadas ──

        composable("admin/mapa") {
            EditorMapaScreen(
                onVolver = { nav.popBackStack() },
                onVerLista = { /* vista 17 aún no existe */ },
                posicionAdmin = { null }
            )
        }

        composable("admin/imagenes") {
            GaleriaScreen(
                onVolver = { nav.popBackStack() },
                onAbrirImagen = { _, _ -> }, // placeholder: aún no existe la vista 7.12
            )
        }

        // 7.13 Lista de videos
        composable("admin/videos") {
            VideosScreen(
                onVolver = { nav.popBackStack() },
                onAbrirVideo = { id -> nav.navigate("admin/videos/$id") },
            )
        }

        // 7.14 Detalle de video
        composable("admin/videos/{videoId}") { entrada ->
            val videoId = entrada.arguments?.getString("videoId") ?: return@composable
            VideoDetalleScreen(
                videoId = videoId,
                onVolver = { nav.popBackStack() },
                onAbrirImagen = { _, _ -> }, // placeholder: aún no existe la vista 7.12
            )
        }

        // ── Placeholders para que los botones no cierren la app ──
        // (navegar a una ruta que no está registrada cierra la app con un error)
        // 7.3 Ubicación manual inicial: por ahora aloja el mapa con seguimiento por pasos
        // (index.html + app.js + sensors/PdrTracker). Faltan los botones propios de 7.3.
        composable("admin/ubicacion-manual") {
            // ACTIVITY_RECOGNITION es para el contador de pasos; si se niega, el PDR usa el acelerómetro.
            var permisosPedidos by rememberSaveable { mutableStateOf(false) }
            if (!permisosPedidos) {
                PedirPermisos(
                    permisos = Permisos.INICIALES,
                    onResultado = { permisosPedidos = true },
                )
            } else {
                UbicacionManualScreen(
                    onVolver = { nav.popBackStack() },
                    onConfirmar = { inicio -> /* pendiente: crear video y abrir 7.4 */ },
                    onAjustes = { nav.navigate("ajustes") },
                )
            }
        }
        composable("admin/lugares") { /* placeholder */ }
        composable("admin/estadisticas") { /* placeholder */ }
        composable("ajustes") { /* placeholder */ }
    }
}

/**
 * Muestra el diálogo nativo del sistema para pedir los permisos indicados.
 * Si ya están concedidos, llama a onResultado(true) sin mostrar nada.
 */
@Composable
fun PedirPermisos(
    permisos: Array<String>,
    onResultado: (todosConcedidos: Boolean) -> Unit,
) {
    val context = LocalContext.current

    val launcher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { resultado ->
        onResultado(resultado.values.all { it })
    }

    LaunchedEffect(Unit) {
        val faltantes = permisos.filter {
            ContextCompat.checkSelfPermission(context, it) != PackageManager.PERMISSION_GRANTED
        }
        if (faltantes.isEmpty()) {
            onResultado(true)
        } else {
            launcher.launch(faltantes.toTypedArray())
        }
    }
}