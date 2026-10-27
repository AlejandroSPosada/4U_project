package com.example.myapplication.ui.ubicacion

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.compose.currentStateAsState
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.myapplication.data.repository.LUGARES_DE_PRUEBA
import com.example.myapplication.data.repository.RESULTADO_DE_PRUEBA
import com.example.myapplication.domain.model.ResultadoUbicacion
import com.example.myapplication.domain.model.UbicacionEstimada
import com.example.myapplication.domain.usecase.DescribirUbicacion
import com.example.myapplication.sensors.EscucharOrientacion
import com.example.myapplication.sensors.tieneSensorRotacion
import com.example.myapplication.ui.theme.CampusColors

/*
 * Vista 6.3 — Resultado de ubicación (FE-3.2).
 *
 * Dice y muestra dónde está la persona (lugar cercano, referencias con dirección relativa, confianza) y, si eligió un
 * destino en 6.4, su distancia y dirección en línea recta (la navegación guiada es de FE-5.1). Sin mapa ni comandos de
 * voz (decisión del usuario del 2026-10-26; voz: FE-3.5; alertas cercanas: FE-3.6).
 *   - Textos               -> domain/usecase/DescribirUbicacion
 *   - Datos (ubicación)    -> domain/model/SesionDeNavegacion (decisión abierta 15)
 *   - Estado y acciones    -> ResultadoUbicacionState
 */

@Composable
fun ResultadoUbicacionScreen(
    onVolverAUbicarme: () -> Unit,
    onIrALugar: () -> Unit,
    onInicio: () -> Unit,
    viewModel: ResultadoUbicacionViewModel = viewModel(),
) {
    val ctx = LocalContext.current
    val estado by viewModel.estado.collectAsStateWithLifecycle()

    // Brújula solo mientras la pantalla se ve (la dirección relativa usa el rumbo actual).
    val lifecycleOwner = LocalLifecycleOwner.current
    val ciclo by lifecycleOwner.lifecycle.currentStateAsState()
    val tieneSensor = remember { tieneSensorRotacion(ctx) }
    EscucharOrientacion(
        activo = tieneSensor && ciclo.isAtLeast(Lifecycle.State.STARTED),
        onOrientacion = viewModel::onOrientacion,
    )

    LaunchedEffect(Unit) { viewModel.alAbrir() }

    // Al dejar de verse la pantalla, calla.
    DisposableEffect(lifecycleOwner) {
        val obs = LifecycleEventObserver { _, e ->
            if (e == Lifecycle.Event.ON_STOP) viewModel.alPausar()
        }
        lifecycleOwner.lifecycle.addObserver(obs)
        onDispose { lifecycleOwner.lifecycle.removeObserver(obs) }
    }

    val acciones = remember(viewModel) {
        ResultadoAcciones(
            onRepetir = viewModel::repetir,
            onVolverAUbicarme = { viewModel.alPausar(); onVolverAUbicarme() },
            onIrALugar = { viewModel.alPausar(); onIrALugar() },
            onInicio = { viewModel.alPausar(); onInicio() },
        )
    }
    ResultadoUbicacionContent(estado = estado, acciones = acciones)
}

/** Contenido sin lógica de la vista 6.3. Botones de 64 dp o más; TalkBack lee el texto de cada botón. */
@Composable
internal fun ResultadoUbicacionContent(
    estado: ResultadoUiState,
    acciones: ResultadoAcciones,
    modifier: Modifier = Modifier,
) {
    val d = estado.descripcion
    Column(
        modifier = modifier
            .fillMaxSize()
            .background(CampusColors.Fondo)
            .systemBarsPadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text(
            text = "Tu ubicación",
            color = CampusColors.TextoSecundario,
            fontSize = 18.sp,
            modifier = Modifier.semantics { heading() },
        )
        Text(
            text = d.titulo,
            color = CampusColors.TextoPrincipal,
            fontSize = 30.sp,
            lineHeight = 36.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.semantics { heading() },
        )
        d.coordenadas?.let { Text(it, color = CampusColors.TextoSecundario, fontSize = 14.sp) }
        d.subtitulo?.let { Text(it, color = CampusColors.TextoSecundario, fontSize = 22.sp) }

        if (d.detalles.isNotEmpty()) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(CampusColors.Superficie, RoundedCornerShape(20.dp))
                    .border(1.dp, CampusColors.Borde, RoundedCornerShape(20.dp))
                    .padding(18.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                d.detalles.forEach { Text(it, color = CampusColors.TextoPrincipal, fontSize = 20.sp, lineHeight = 26.sp) }
            }
        }
        d.confianza?.let {
            Text(
                text = it,
                color = if (d.sugerirRepetir) CampusColors.Peligro else CampusColors.Exito,
                fontSize = 20.sp,
                fontWeight = FontWeight.Medium,
            )
        }

        Spacer(Modifier.height(4.dp))
        val irALugar = if (estado.hayPosicion) "Ir a un lugar desde aquí" else "Ir a un lugar"
        // Con confianza baja, sin coincidencias o sin ubicación, «Volver a ubicarme» va primero y relleno.
        if (d.sugerirRepetir) {
            BotonPrincipal("Volver a ubicarme", acciones.onVolverAUbicarme)
            BotonSecundario("Repetir en voz alta", acciones.onRepetir)
            BotonSecundario(irALugar, acciones.onIrALugar)
        } else {
            BotonPrincipal("Repetir en voz alta", acciones.onRepetir)
            BotonSecundario(irALugar, acciones.onIrALugar)
            BotonSecundario("Volver a ubicarme", acciones.onVolverAUbicarme)
        }
        BotonSecundario("Volver al inicio", acciones.onInicio)
    }
}

@Composable
private fun BotonPrincipal(texto: String, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth().heightIn(min = 64.dp),
        shape = RoundedCornerShape(18.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = CampusColors.Primario,
            contentColor = CampusColors.TextoPrincipal,
        ),
    ) { Text(texto, fontSize = 20.sp, fontWeight = FontWeight.Medium) }
}

@Composable
private fun BotonSecundario(texto: String, onClick: () -> Unit) {
    OutlinedButton(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth().heightIn(min = 64.dp),
        shape = RoundedCornerShape(18.dp),
        border = BorderStroke(2.dp, CampusColors.Primario),
        colors = ButtonDefaults.outlinedButtonColors(contentColor = CampusColors.Acento),
    ) { Text(texto, fontSize = 20.sp, fontWeight = FontWeight.Medium) }
}

@Preview(showBackground = true, heightDp = 900)
@Composable
private fun PreviewResultadoConDestino() {
    val u = UbicacionEstimada(RESULTADO_DE_PRUEBA, 0L, 0.0)
    ResultadoUbicacionContent(
        ResultadoUiState(DescribirUbicacion.describir(u, 0.0, LUGARES_DE_PRUEBA.last()), hayPosicion = true),
        ResultadoAcciones(),
    )
}

@Preview(showBackground = true, heightDp = 900)
@Composable
private fun PreviewResultadoSinCoincidencias() {
    val u = UbicacionEstimada(ResultadoUbicacion.SinCoincidencias(5), 0L, null)
    ResultadoUbicacionContent(
        ResultadoUiState(DescribirUbicacion.describir(u, null, null), hayPosicion = false),
        ResultadoAcciones(),
    )
}
