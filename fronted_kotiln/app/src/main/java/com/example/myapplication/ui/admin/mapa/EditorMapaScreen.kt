package com.example.myapplication.ui.admin.mapa

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.CloudUpload
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Layers
import androidx.compose.material.icons.filled.MyLocation
import androidx.compose.material.icons.filled.OpenWith
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.myapplication.data.repository.AlertasRepositoryProvider
import com.example.myapplication.domain.model.Alerta
import com.example.myapplication.domain.model.PrioridadAlerta
import com.example.myapplication.domain.model.TipoAlerta
import com.example.myapplication.ui.components.CapasMapa
import com.example.myapplication.ui.components.MapaCampus
import com.example.myapplication.ui.components.MapaCampusController
import kotlinx.coroutines.launch
import java.util.Locale

// Paleta del mockup (oscuro + morado)
private val Fondo = Color(0xFF0D0B14)
private val Panel = Color(0xF2141022)
private val Morado = Color(0xFF7C5CFF)
private val MoradoClaro = Color(0xFFB3A6FF)
private val Texto = Color(0xFFE9E6F5)
private val TextoSuave = Color(0xFFA9A3C2)
private val Ambar = Color(0xFFFFB020)
private val Rojo = Color(0xFFFF4D6D)
private val Azul = Color(0xFF4DA3FF)
private val Verde = Color(0xFF3DDC97)

/**
 * Editor de mapa y alertas (vista 7.8, ARCHITECTURE.md).
 *
 * @param posicionAdmin posición actual estimada del admin (PDR) para el botón "Mi posición";
 *  null si todavía no hay una. Pares (latitud, longitud).
 */
@Composable
fun EditorMapaScreen(
    onVolver: () -> Unit,
    onVerLista: () -> Unit,
    posicionAdmin: () -> Pair<Double, Double>? = { null },
    viewModel: EditorMapaViewModel = viewModel(
        factory = EditorMapaViewModel.factory(AlertasRepositoryProvider.instancia),
    ),
) {
    val estado by viewModel.ui.collectAsStateWithLifecycle()
    val controller = remember { MapaCampusController() }
    val snackbar = remember { SnackbarHostState() }
    var posicion by remember { mutableStateOf<Pair<Double, Double>?>(null) }
    var salirPendiente by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(estado.mensaje) {
        estado.mensaje?.let {
            snackbar.showSnackbar(it)
            viewModel.onMensajeMostrado()
        }
    }

    // Atrás: primero sale de los modos temporales; con cambios sin sincronizar pide confirmar.
    BackHandler {
        when {
            estado.moviendo -> viewModel.onMoverCancelar()
            estado.colocando -> viewModel.onNuevaAlerta()
            estado.pendientes > 0 -> salirPendiente = true
            else -> onVolver()
        }
    }

    Box(Modifier.fillMaxSize().background(Fondo)) {
        MapaCampus(
            controller = controller,
            alertas = estado.alertasParaMapa,
            seleccionId = estado.idResaltado,
            moverId = if (estado.moviendo) estado.borrador?.id else null,
            modoColocar = estado.colocando,
            capas = estado.capas,
            posicionAdmin = posicion,
            onAlertaToque = viewModel::onAlertaToque,
            onMapaToque = viewModel::onMapaToque,
            onAlertaMovida = viewModel::onAlertaMovida,
            modifier = Modifier.fillMaxSize(),
        )

        // ------------------------------------------------------------ parte superior
        Column(
            Modifier
                .align(Alignment.TopCenter)
                .fillMaxWidth()
                .background(Brush.verticalGradient(listOf(Fondo.copy(alpha = 0.92f), Color.Transparent)))
                .statusBarsPadding()
                .padding(horizontal = 12.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Encabezado(
                pendientes = estado.pendientes,
                onVolver = { if (estado.pendientes > 0) salirPendiente = true else onVolver() },
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.Top) {
                TarjetaCapas(estado.capas) { t -> viewModel.onCapas(t) }
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        FiltroDropdown(
                            modifier = Modifier.weight(1f), titulo = "Tipo", valorTexto = estado.filtroTipo?.etiqueta ?: "Todos",
                            opciones = listOf<Pair<String, TipoAlerta?>>("Todos" to null) + TipoAlerta.entries.map { it.etiqueta to it },
                            onSeleccion = viewModel::onFiltroTipo,
                        )
                        FiltroDropdown(
                            modifier = Modifier.weight(1f), titulo = "Prioridad", valorTexto = estado.filtroPrioridad?.etiqueta ?: "Todas",
                            opciones = listOf<Pair<String, PrioridadAlerta?>>("Todas" to null) + PrioridadAlerta.entries.map { it.etiqueta to it },
                            onSeleccion = viewModel::onFiltroPrioridad,
                        )
                        FiltroDropdown(
                            modifier = Modifier.weight(1f), titulo = "Estado",
                            valorTexto = when (estado.filtroActiva) { true -> "Activas"; false -> "Inactivas"; null -> "Todos" },
                            opciones = listOf<Pair<String, Boolean?>>("Todos" to null, "Activas" to true, "Inactivas" to false),
                            onSeleccion = viewModel::onFiltroActiva,
                        )
                    }
                    Column(Modifier.align(Alignment.End), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        BotonFlotanteTexto(Icons.Default.MyLocation, "Mi posición") {
                            val p = posicionAdmin()
                            if (p == null) {
                                posicion = null
                                scope.launch { snackbar.showSnackbar("Aún no hay una posición estimada") }
                            } else {
                                posicion = p
                                controller.centrarEn(p.first, p.second, 18.5)
                            }
                        }
                        BotonFlotanteTexto(Icons.AutoMirrored.Filled.List, "Ver lista", onClick = onVerLista)
                    }
                }
            }
        }

        // ------------------------------------------------------------ parte inferior
        Column(
            Modifier
                .align(Alignment.BottomCenter)
                .fillMaxWidth()
                .navigationBarsPadding()
                .padding(horizontal = 12.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            // Avisos de modo
            AnimatedVisibility(visible = estado.colocando) {
                BannerModo(
                    texto = "Toca el mapa para fijar el punto de la alerta",
                    accion = "Cancelar", onAccion = viewModel::onNuevaAlerta,
                )
            }
            AnimatedVisibility(visible = estado.moviendo) {
                BannerModo(
                    texto = "Arrastra el marcador al nuevo lugar",
                    accion = "Listo", onAccion = viewModel::onMoverListo,
                    secundaria = "Cancelar", onSecundaria = viewModel::onMoverCancelar,
                )
            }

            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Bottom) {
                ControlesZoom(onMas = controller::zoomIn, onMenos = controller::zoomOut)
                Spacer(Modifier.weight(1f))
                if (!estado.moviendo) {
                    Button(
                        onClick = viewModel::onNuevaAlerta,
                        colors = ButtonDefaults.buttonColors(containerColor = Morado, contentColor = Color.White),
                        shape = RoundedCornerShape(28.dp),
                        modifier = Modifier.heightIn(min = 56.dp),
                    ) {
                        Icon(if (estado.colocando) Icons.Default.Close else Icons.Default.Add, contentDescription = null)
                        Text(if (estado.colocando) "  Cancelar" else "  Nueva alerta", fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                    }
                }
            }

            val sel = estado.seleccionada
            AnimatedVisibility(visible = sel != null && !estado.moviendo && !estado.formularioVisible) {
                if (sel != null) {
                    TarjetaAlerta(
                        alerta = sel,
                        onCerrar = viewModel::onDeseleccionar,
                        onMover = viewModel::onMoverSeleccionada,
                        onEditar = viewModel::onEditarSeleccionada,
                        onEliminar = { viewModel.onEliminarSolicitada(sel.id) },
                    )
                }
            }

            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(
                    onClick = onVerLista,
                    border = BorderStroke(1.dp, Morado),
                    colors = ButtonDefaults.outlinedButtonColors(containerColor = Panel, contentColor = MoradoClaro),
                    shape = RoundedCornerShape(16.dp),
                    modifier = Modifier.weight(0.9f).heightIn(min = 56.dp),
                ) {
                    Icon(Icons.AutoMirrored.Filled.List, contentDescription = null)
                    Text("  Ver lista")
                }
                Button(
                    onClick = viewModel::onSincronizar,
                    enabled = !estado.sincronizando,
                    colors = ButtonDefaults.buttonColors(containerColor = Morado, contentColor = Color.White),
                    shape = RoundedCornerShape(16.dp),
                    modifier = Modifier.weight(1.6f).heightIn(min = 56.dp).semantics {
                        contentDescription = if (estado.pendientes > 0)
                            "Guardar y sincronizar. ${estado.pendientes} cambios pendientes"
                        else "Guardar y sincronizar. Sin cambios pendientes"
                    },
                ) {
                    if (estado.sincronizando) {
                        CircularProgressIndicator(Modifier.size(20.dp), color = Color.White, strokeWidth = 2.dp)
                    } else {
                        Icon(Icons.Default.CloudUpload, contentDescription = null)
                    }
                    Text("  Guardar / Sincronizar  ", fontWeight = FontWeight.SemiBold)
                    Box(Modifier.size(10.dp).background(if (estado.pendientes > 0) Ambar else Verde, CircleShape))
                }
            }
        }

        SnackbarHost(
            snackbar,
            Modifier.align(Alignment.BottomCenter).navigationBarsPadding().padding(bottom = 90.dp),
        )
    }

    // ---------------------------------------------------------------- formulario
    val borrador = estado.borrador
    if (estado.formularioVisible && borrador != null) {
        AlertaFormSheet(
            alerta = borrador,
            esNueva = estado.borradorEsNuevo,
            errorMensaje = estado.errorMensaje,
            onCambio = viewModel::onBorradorCambio,
            onAjustarEnMapa = viewModel::onAjustarEnMapa,
            onGuardar = viewModel::onGuardarFormulario,
            onCancelar = viewModel::onCancelarFormulario,
            onEliminar = { viewModel.onEliminarSolicitada(borrador.id) },
        )
    }

    // ---------------------------------------------------------------- diálogos
    if (estado.confirmarEliminarId != null) {
        AlertDialog(
            onDismissRequest = viewModel::onEliminarDescartada,
            title = { Text("¿Eliminar alerta?") },
            text = { Text("Dejará de avisarse a los usuarios cuando se sincronice. No se puede deshacer.") },
            confirmButton = { TextButton(onClick = viewModel::onEliminarConfirmada) { Text("Eliminar", color = Rojo) } },
            dismissButton = { TextButton(onClick = viewModel::onEliminarDescartada) { Text("Cancelar") } },
        )
    }
    if (salirPendiente) {
        AlertDialog(
            onDismissRequest = { salirPendiente = false },
            title = { Text("Hay cambios sin sincronizar") },
            text = { Text("Quedan ${estado.pendientes} cambios pendientes de enviar. Se conservan, pero los usuarios no los verán hasta sincronizar.") },
            confirmButton = { TextButton(onClick = { salirPendiente = false; onVolver() }) { Text("Salir") } },
            dismissButton = { TextButton(onClick = { salirPendiente = false }) { Text("Quedarme") } },
        )
    }
}

// ============================================================================ piezas

@Composable
private fun Encabezado(pendientes: Int, onVolver: () -> Unit) {
    Row(verticalAlignment = Alignment.Top) {
        IconButton(onClick = onVolver, modifier = Modifier.size(48.dp)) {
            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Volver", tint = MoradoClaro)
        }
        Column(Modifier.weight(1f).padding(start = 4.dp)) {
            Text(
                buildAnnotatedString {
                    withStyle(SpanStyle(color = Texto)) { append("Editor de mapa y ") }
                    withStyle(SpanStyle(color = MoradoClaro)) { append("alertas") }
                },
                fontSize = 21.sp, fontWeight = FontWeight.SemiBold,
            )
            Text("Modifica el mapa eafit.mbtiles agregando, moviendo y gestionando alertas y lugares.",
                color = TextoSuave, fontSize = 12.sp, lineHeight = 15.sp)
        }
        if (pendientes > 0) {
            Surface(
                shape = RoundedCornerShape(20.dp), color = Panel, border = BorderStroke(1.dp, Ambar),
                modifier = Modifier.padding(start = 6.dp).semantics { contentDescription = "$pendientes cambios pendientes" },
            ) {
                Row(Modifier.padding(horizontal = 10.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.CloudUpload, null, tint = Ambar, modifier = Modifier.size(18.dp))
                    Text("  Cambios\n  pendientes", color = Ambar, fontSize = 11.sp, lineHeight = 13.sp)
                }
            }
        }
    }
}

@Composable
private fun TarjetaCapas(capas: CapasMapa, onCambio: ((CapasMapa) -> CapasMapa) -> Unit) {
    Surface(shape = RoundedCornerShape(14.dp), color = Panel, border = BorderStroke(1.dp, Morado)) {
        Column(Modifier.padding(horizontal = 10.dp, vertical = 8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.Layers, null, tint = Morado, modifier = Modifier.size(20.dp))
                Text("  Capas", color = TextoSuave, fontSize = 13.sp)
            }
            FilaCapa("Alertas", capas.alertas) { v -> onCambio { it.copy(alertas = v) } }
            FilaCapa("Lugares", capas.lugares) { v -> onCambio { it.copy(lugares = v) } }
            FilaCapa("Cobertura de fotos", capas.cobertura) { v -> onCambio { it.copy(cobertura = v) } }
            FilaCapa("Rutas", capas.rutas) { v -> onCambio { it.copy(rutas = v) } }
        }
    }
}

@Composable
private fun FilaCapa(nombre: String, marcado: Boolean, onCambio: (Boolean) -> Unit) {
    Row(
        Modifier.heightIn(min = 32.dp).clickable { onCambio(!marcado) }
            .semantics { contentDescription = "Capa $nombre, ${if (marcado) "visible" else "oculta"}"; role = Role.Checkbox },
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Checkbox(
            checked = marcado, onCheckedChange = null,
            colors = CheckboxDefaults.colors(checkedColor = Morado, uncheckedColor = TextoSuave),
            modifier = Modifier.size(28.dp),
        )
        Text("  $nombre", color = Texto, fontSize = 12.sp)
    }
}

@Composable
private fun <T> FiltroDropdown(
    titulo: String,
    valorTexto: String,
    opciones: List<Pair<String, T?>>,
    onSeleccion: (T?) -> Unit,
    modifier: Modifier = Modifier,
) {
    var abierto by remember { mutableStateOf(false) }
    Box(modifier) {
        Surface(
            shape = RoundedCornerShape(14.dp), color = Panel, border = BorderStroke(1.dp, Morado),
            modifier = Modifier.fillMaxWidth().clickable { abierto = true }
                .semantics { contentDescription = "Filtro $titulo: $valorTexto"; role = Role.DropdownList },
        ) {
            Column(Modifier.padding(horizontal = 8.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(titulo, color = TextoSuave, fontSize = 12.sp, maxLines = 1)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(valorTexto, color = Texto, fontSize = 12.sp, maxLines = 1, modifier = Modifier.weight(1f))
                    Icon(Icons.Default.ArrowDropDown, null, tint = Morado, modifier = Modifier.size(20.dp))
                }
            }
        }
        DropdownMenu(expanded = abierto, onDismissRequest = { abierto = false }) {
            opciones.forEach { (etiqueta, valor) ->
                DropdownMenuItem(text = { Text(etiqueta) }, onClick = { abierto = false; onSeleccion(valor) })
            }
        }
    }
}

@Composable
private fun BotonFlotanteTexto(icono: ImageVector, texto: String, onClick: () -> Unit) {
    OutlinedButton(
        onClick = onClick,
        border = BorderStroke(1.dp, Morado),
        colors = ButtonDefaults.outlinedButtonColors(containerColor = Panel, contentColor = Texto),
        shape = RoundedCornerShape(16.dp),
        modifier = Modifier.width(150.dp).heightIn(min = 48.dp),
    ) {
        Icon(icono, contentDescription = null, tint = Morado)
        Text("  $texto", fontSize = 14.sp)
    }
}

@Composable
private fun ControlesZoom(onMas: () -> Unit, onMenos: () -> Unit) {
    Surface(shape = RoundedCornerShape(16.dp), color = Panel, border = BorderStroke(1.dp, Morado)) {
        Column {
            IconButton(onClick = onMas, modifier = Modifier.size(52.dp)) {
                Icon(Icons.Default.Add, contentDescription = "Acercar", tint = MoradoClaro)
            }
            IconButton(onClick = onMenos, modifier = Modifier.size(52.dp)) {
                Icon(Icons.Default.Remove, contentDescription = "Alejar", tint = MoradoClaro)
            }
        }
    }
}

@Composable
private fun BannerModo(
    texto: String, accion: String, onAccion: () -> Unit,
    secundaria: String? = null, onSecundaria: () -> Unit = {},
) {
    Surface(shape = RoundedCornerShape(14.dp), color = Panel, border = BorderStroke(1.dp, Ambar)) {
        Row(Modifier.padding(start = 14.dp, end = 6.dp, top = 4.dp, bottom = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(texto, color = Texto, fontSize = 14.sp, modifier = Modifier.weight(1f))
            if (secundaria != null) TextButton(onClick = onSecundaria) { Text(secundaria, color = TextoSuave) }
            TextButton(onClick = onAccion) { Text(accion, color = Ambar, fontWeight = FontWeight.SemiBold) }
        }
    }
}

@Composable
private fun TarjetaAlerta(
    alerta: Alerta,
    onCerrar: () -> Unit,
    onMover: () -> Unit,
    onEditar: () -> Unit,
    onEliminar: () -> Unit,
) {
    val color = if (alerta.prioridad == PrioridadAlerta.ALTA) Rojo else Ambar
    Surface(shape = RoundedCornerShape(18.dp), color = Panel, border = BorderStroke(1.dp, Morado)) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.Top) {
                Icon(Icons.Default.Warning, null, tint = color, modifier = Modifier.size(34.dp))
                Column(Modifier.weight(1f).padding(horizontal = 10.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(alerta.tipo.etiqueta, color = Texto, fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
                        Text(
                            "  ${alerta.prioridad.etiqueta}  ", color = color, fontSize = 11.sp,
                            modifier = Modifier.padding(start = 8.dp)
                                .background(color.copy(alpha = 0.15f), RoundedCornerShape(10.dp))
                                .padding(horizontal = 2.dp, vertical = 2.dp),
                        )
                        if (!alerta.activa) Text("  Inactiva", color = TextoSuave, fontSize = 11.sp)
                    }
                    Text(alerta.mensaje, color = Texto.copy(alpha = 0.85f), fontSize = 13.sp, lineHeight = 17.sp, maxLines = 3)
                }
                IconButton(onClick = onCerrar, modifier = Modifier.size(40.dp)) {
                    Icon(Icons.Default.Close, contentDescription = "Cerrar", tint = Texto)
                }
            }
            Row(verticalAlignment = Alignment.Bottom) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("Posición: ${fmt(alerta.latitud)}, ${fmt(alerta.longitud)}", color = TextoSuave, fontSize = 12.sp)
                    Text("Radio de activación: ${alerta.radioM} m", color = TextoSuave, fontSize = 12.sp)
                }
                AccionTarjeta(Icons.Default.OpenWith, "Mover", Morado, onMover)
                Spacer(Modifier.width(6.dp))
                AccionTarjeta(Icons.Default.Edit, "Editar", Azul, onEditar)
                Spacer(Modifier.width(6.dp))
                AccionTarjeta(Icons.Default.Delete, "Eliminar", Rojo, onEliminar)
            }
        }
    }
}

@Composable
private fun AccionTarjeta(icono: ImageVector, texto: String, color: Color, onClick: () -> Unit) {
    OutlinedButton(
        onClick = onClick,
        border = BorderStroke(1.dp, color),
        colors = ButtonDefaults.outlinedButtonColors(contentColor = color),
        shape = RoundedCornerShape(12.dp),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 8.dp, vertical = 6.dp),
        modifier = Modifier.size(width = 62.dp, height = 56.dp),
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Icon(icono, contentDescription = null, modifier = Modifier.size(20.dp))
            Text(texto, fontSize = 11.sp, maxLines = 1)
        }
    }
}

private fun fmt(v: Double) = String.format(Locale.US, "%.4f", v)