package com.example.myapplication.ui.admin.mapa

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.MyLocation
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.example.myapplication.domain.model.Alerta
import com.example.myapplication.domain.model.PrioridadAlerta
import com.example.myapplication.domain.model.TipoAlerta
import java.util.Locale

/**
 * Formulario de alerta (vista 7.9, versión básica).
 * Pendiente respecto al brief: dictado por voz, "Escuchar cómo sonará" y vigencia (fecha inicio/fin).
 * Cada cambio se propaga de inmediato (onCambio) para que el mapa dibuje el radio en vivo.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AlertaFormSheet(
    alerta: Alerta,
    esNueva: Boolean,
    errorMensaje: String?,
    onCambio: ((Alerta) -> Alerta) -> Unit,
    onAjustarEnMapa: () -> Unit,
    onGuardar: () -> Unit,
    onCancelar: () -> Unit,
    onEliminar: () -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    ModalBottomSheet(onDismissRequest = onCancelar, sheetState = sheetState) {
        Column(
            Modifier
                .fillMaxWidth()
                .heightIn(max = 640.dp)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp)
                .navigationBarsPadding(),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text(
                if (esNueva) "Nueva alerta" else "Editar alerta",
                style = MaterialTheme.typography.titleLarge,
            )

            OutlinedTextField(
                value = alerta.mensaje,
                onValueChange = { v -> onCambio { it.copy(mensaje = v.take(Alerta.MENSAJE_MAX)) } },
                label = { Text("Mensaje") },
                placeholder = { Text("Ten cuidado, hay bancas cerca, no te vayas a estrellar") },
                supportingText = {
                    Text(errorMensaje ?: "Escribe exactamente lo que se le dirá al usuario (${alerta.mensaje.length}/${Alerta.MENSAJE_MAX})")
                },
                isError = errorMensaje != null,
                minLines = 2,
                maxLines = 4,
                modifier = Modifier.fillMaxWidth(),
            )

            Text("Tipo", style = MaterialTheme.typography.labelLarge)
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                TipoAlerta.entries.forEach { t ->
                    FilterChip(
                        selected = alerta.tipo == t,
                        onClick = { onCambio { it.copy(tipo = t) } },
                        label = { Text(t.etiqueta) },
                    )
                }
            }

            Text("Prioridad", style = MaterialTheme.typography.labelLarge)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                PrioridadAlerta.entries.forEach { p ->
                    FilterChip(
                        selected = alerta.prioridad == p,
                        onClick = { onCambio { it.copy(prioridad = p) } },
                        label = { Text(p.etiqueta) },
                    )
                }
            }

            Text("Radio de activación: ${alerta.radioM} m", style = MaterialTheme.typography.labelLarge)
            Slider(
                value = alerta.radioM.toFloat(),
                onValueChange = { v -> onCambio { it.copy(radioM = (Math.round(v / 5f) * 5).coerceIn(Alerta.RADIO_MIN_M, Alerta.RADIO_MAX_M)) } },
                valueRange = Alerta.RADIO_MIN_M.toFloat()..Alerta.RADIO_MAX_M.toFloat(),
                modifier = Modifier.semantics { contentDescription = "Radio de activación en metros" },
            )

            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween,
                modifier = Modifier.fillMaxWidth()) {
                Text(
                    "Posición: ${fmt(alerta.latitud)}, ${fmt(alerta.longitud)}",
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.weight(1f),
                )
                OutlinedButton(onClick = onAjustarEnMapa) {
                    Icon(Icons.Default.MyLocation, contentDescription = null)
                    Text("  Ajustar en el mapa")
                }
            }

            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween,
                modifier = Modifier.fillMaxWidth()) {
                Text(if (alerta.activa) "Activa" else "Inactiva", style = MaterialTheme.typography.bodyLarge)
                Switch(
                    checked = alerta.activa,
                    onCheckedChange = { v -> onCambio { it.copy(activa = v) } },
                    modifier = Modifier.semantics { contentDescription = "Alerta activa" },
                )
            }

            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(onClick = onCancelar, modifier = Modifier.weight(1f).heightIn(min = 56.dp)) {
                    Text("Cancelar")
                }
                Button(onClick = onGuardar, modifier = Modifier.weight(1f).heightIn(min = 56.dp)) {
                    Text("Guardar")
                }
            }
            if (!esNueva) {
                OutlinedButton(
                    onClick = onEliminar,
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = Color(0xFFFF4D6D)),
                    modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp),
                ) {
                    Icon(Icons.Default.Delete, contentDescription = null)
                    Text("  Eliminar alerta")
                }
            }
            Spacer(Modifier.height(16.dp))
        }
    }
}

private fun fmt(v: Double) = String.format(Locale.US, "%.6f", v)