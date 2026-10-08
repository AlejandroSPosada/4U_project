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
import com.example.myapplication.ui.ubicacion.EscaneoScreen
import com.example.myapplication.ui.auth.LoginScreen
import com.example.myapplication.ui.admin.panel.PanelAdminScreen
import com.example.myapplication.ui.admin.mapa.EditorMapaScreen

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

        // Placeholder para que el login no cierre la app al navegar
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

        // Placeholders para que los botones no cierren la app
        composable("admin/ubicacion-manual") { /* placeholder */ }
        composable("admin/lugares") { /* placeholder */ }
        composable("admin/mapa") { /* placeholder */ }
        composable("admin/imagenes") { /* placeholder */ }
        composable("admin/videos") { /* placeholder */ }
        composable("admin/estadisticas") { /* placeholder */ }
        composable("ajustes") { /* placeholder */ }
        composable("admin/ubicacion-manual") { /* placeholder */ }
        composable("admin/lugares") { /* placeholder */ }
        composable("admin/mapa") {
            EditorMapaScreen(
                onVolver = { nav.popBackStack() },
                onVerLista = { /* vista 17 aún no existe */ },
                posicionAdmin = { null },
            )
        }
        composable("admin/imagenes") { /* placeholder */ }
        composable("admin/videos") { /* placeholder */ }
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