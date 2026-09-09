package com.example.myapplication.ui.inicio

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.*
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import coil3.compose.AsyncImage

// ── Paleta de colores ─────────────────────────────────────────────────────────
private val BackgroundColor = Color(0xFF0D0D14)
private val OrbCenter       = Color(0xFF9B4DFF)
private val OrbMid          = Color(0xFF6B2BCC)
private val OrbEdge         = Color(0xFF3D0080)
private val GlowColor       = Color(0xFF7B3FE4)
private val TextPrimary     = Color(0xFFFFFFFF)
private val TextSecondary   = Color(0xFFAAAAAA)
private val AccentPurple    = Color(0xFF9B4DFF)

// ── Pantalla: Inicio — Img 1 ──────────────────────────────────────────────────
@Composable
fun InicioScreen(
    onImagenesListas: (List<Uri>) -> Unit = {},
    viewModel: InicioViewModel = viewModel()
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()

    // ── Selector de galería (máx. 3 imágenes) ─────────────────────────────────
    val galleryLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.PickMultipleVisualMedia(maxItems = 3)
    ) { uris ->
        if (uris.isNotEmpty()) {
            viewModel.onImagenesSeleccionadas(uris)
            if (uris.size == 3) {
                // TODO: navegar a CapturaScreen/ResultadoScreen con las URIs
                onImagenesListas(uris.take(3))
            }
        }
    }

    val infiniteTransition = rememberInfiniteTransition(label = "orb_anim")

    val pulseScale by infiniteTransition.animateFloat(
        initialValue = 1.57f,
        targetValue  = 1.73f,
        animationSpec = infiniteRepeatable(
            animation  = tween(1800, easing = EaseInOutSine),
            repeatMode = RepeatMode.Reverse
        ),
        label = "pulse_scale"
    )
    val glowAlpha by infiniteTransition.animateFloat(
        initialValue = 0.45f,
        targetValue  = 0.75f,
        animationSpec = infiniteRepeatable(
            animation  = tween(1800, easing = EaseInOutSine),
            repeatMode = RepeatMode.Reverse
        ),
        label = "glow_alpha"
    )
    val waveAlpha by infiniteTransition.animateFloat(
        initialValue = 0.4f,
        targetValue  = 1.0f,
        animationSpec = infiniteRepeatable(
            animation  = tween(1200, easing = EaseInOut),
            repeatMode = RepeatMode.Reverse
        ),
        label = "wave_alpha"
    )

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(BackgroundColor),
        contentAlignment = Alignment.Center
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .systemBarsPadding()
                .padding(horizontal = 32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.SpaceBetween
        ) {
            // ── Sección superior ─────────────────────────────────────────────
            Column(
                modifier = Modifier.padding(top = 56.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                SignalIcon(waveAlpha = waveAlpha)

                Spacer(modifier = Modifier.height(28.dp))

                Text(
                    text       = "Presiona para identificar\ndónde te encuentras",
                    color      = TextPrimary,
                    fontSize   = 22.sp,
                    fontWeight = FontWeight.SemiBold,
                    textAlign  = TextAlign.Center,
                    lineHeight = 30.sp
                )

                Spacer(modifier = Modifier.height(14.dp))

                Text(
                    text       = "Al presionar, se tomarán 3 fotos\nde tu entorno.",
                    color      = TextSecondary,
                    fontSize   = 15.sp,
                    textAlign  = TextAlign.Center,
                    lineHeight = 22.sp
                )
            }

            // ── Orbe central ─────────────────────────────────────────────────
            Box(contentAlignment = Alignment.Center) {
                GlowingOrb(
                    pulseScale = pulseScale,
                    glowAlpha  = glowAlpha,
                    onClick    = {
                        galleryLauncher.launch(
                            PickVisualMediaRequest(
                                ActivityResultContracts.PickVisualMedia.ImageOnly
                            )
                        )
                    }
                )

                // Miniaturas de las imágenes seleccionadas (superpuestas al orbe)
                if (uiState.imagenesSeleccionadas.isNotEmpty()) {
                    ImageThumbnailStrip(uris = uiState.imagenesSeleccionadas)
                }
            }

            // ── Pie de página ─────────────────────────────────────────────────
            Row(
                modifier = Modifier.padding(bottom = 32.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.Center
            ) {
                Canvas(modifier = Modifier.size(18.dp)) {
                    drawVolumeIcon(AccentPurple)
                }
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text     = "Activa el lector de pantalla",
                    color    = AccentPurple,
                    fontSize = 14.sp
                )
            }
        }
    }
}

// ── Miniaturas de imágenes seleccionadas ──────────────────────────────────────
@Composable
private fun ImageThumbnailStrip(uris: List<Uri>) {
    val selected = uris.size
    val needed   = 3

    Row(
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalAlignment     = Alignment.CenterVertically
    ) {
        repeat(needed) { index ->
            val uri = uris.getOrNull(index)
            Box(
                modifier = Modifier
                    .size(72.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .border(
                        width = 2.dp,
                        color = if (uri != null) AccentPurple else Color.White.copy(alpha = 0.3f),
                        shape = RoundedCornerShape(12.dp)
                    )
                    .background(Color(0x55000000)),
                contentAlignment = Alignment.Center
            ) {
                if (uri != null) {
                    AsyncImage(
                        model             = uri,
                        contentDescription = "Imagen ${index + 1}",
                        contentScale      = ContentScale.Crop,
                        modifier          = Modifier.fillMaxSize()
                    )
                } else {
                    Text(
                        text     = "${index + 1}",
                        color    = Color.White.copy(alpha = 0.4f),
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
        }
    }
}

// ── Icono de señal (ondas concéntricas + punto central) ───────────────────────
@Composable
private fun SignalIcon(waveAlpha: Float) {
    Canvas(modifier = Modifier.size(64.dp)) {
        val cx = size.width  / 2f
        val cy = size.height / 2f

        drawCircle(
            color  = Color.White,
            radius = 5.dp.toPx(),
            center = Offset(cx, cy)
        )

        val radii = listOf(14.dp.toPx(), 22.dp.toPx(), 30.dp.toPx())
        radii.forEachIndexed { i, r ->
            val alpha  = (waveAlpha - i * 0.18f).coerceIn(0f, 1f)
            val stroke = Stroke(width = 2.2.dp.toPx(), cap = StrokeCap.Round)
            val topLeft = Offset(cx - r, cy - r)
            val arcSize = Size(r * 2, r * 2)

            drawArc(
                color      = Color.White.copy(alpha = alpha),
                startAngle = 210f,
                sweepAngle = 120f,
                useCenter  = false,
                style      = stroke,
                topLeft    = topLeft,
                size       = arcSize
            )
            drawArc(
                color      = Color.White.copy(alpha = alpha),
                startAngle = 30f,
                sweepAngle = 120f,
                useCenter  = false,
                style      = stroke,
                topLeft    = topLeft,
                size       = arcSize
            )
        }
    }
}

// ── Orbe con brillo y pulso ───────────────────────────────────────────────────
@Composable
private fun GlowingOrb(
    pulseScale: Float,
    glowAlpha: Float,
    onClick: () -> Unit
) {
    val interactionSource = remember { MutableInteractionSource() }

    Canvas(
        modifier = Modifier
            .size(280.dp)
            .clickable(
                interactionSource = interactionSource,
                indication        = null
            ) { onClick() }
    ) {
        drawGlowingOrb(pulseScale, glowAlpha)
    }
}

private fun DrawScope.drawGlowingOrb(pulseScale: Float, glowAlpha: Float) {
    val cx     = size.width  / 2f
    val cy     = size.height / 2f
    val radius = (size.minDimension / 2f) * 0.80f * pulseScale

    listOf(
        radius * 1.38f to glowAlpha * 0.08f,
        radius * 1.25f to glowAlpha * 0.16f,
        radius * 1.13f to glowAlpha * 0.26f,
        radius * 1.05f to glowAlpha * 0.38f
    ).forEach { (r, a) ->
        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(GlowColor.copy(alpha = a), Color.Transparent),
                center = Offset(cx, cy),
                radius = r
            ),
            radius = r,
            center = Offset(cx, cy)
        )
    }

    drawCircle(
        brush = Brush.radialGradient(
            colors = listOf(OrbCenter, OrbMid, OrbEdge, Color(0x00000000)),
            center = Offset(cx - radius * 0.15f, cy - radius * 0.15f),
            radius = radius * 1.2f
        ),
        radius = radius,
        center = Offset(cx, cy)
    )

    drawCircle(
        brush = Brush.sweepGradient(
            colors = listOf(
                GlowColor.copy(alpha = 0.6f),
                Color.Transparent,
                GlowColor.copy(alpha = 0.85f),
                GlowColor.copy(alpha = 0.3f),
                Color.Transparent
            ),
            center = Offset(cx, cy)
        ),
        radius = radius,
        center = Offset(cx, cy),
        style  = Stroke(width = 2.5.dp.toPx())
    )

    drawCircle(
        brush = Brush.radialGradient(
            colors = listOf(Color.White.copy(alpha = 0.22f), Color.Transparent),
            center = Offset(cx - radius * 0.28f, cy - radius * 0.28f),
            radius = radius * 0.55f
        ),
        radius = radius * 0.55f,
        center = Offset(cx - radius * 0.28f, cy - radius * 0.28f)
    )
}

// ── Icono de volumen dibujado manualmente ─────────────────────────────────────
private fun DrawScope.drawVolumeIcon(color: Color) {
    val w = size.width
    val h = size.height
    val stroke = Stroke(width = 1.5.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round)

    val path = Path().apply {
        moveTo(w * 0.18f, h * 0.35f)
        lineTo(w * 0.38f, h * 0.35f)
        lineTo(w * 0.62f, h * 0.15f)
        lineTo(w * 0.62f, h * 0.85f)
        lineTo(w * 0.38f, h * 0.65f)
        lineTo(w * 0.18f, h * 0.65f)
        close()
    }
    drawPath(path, color = color, style = stroke)

    drawArc(
        color      = color,
        startAngle = -40f,
        sweepAngle = 80f,
        useCenter  = false,
        style      = stroke,
        topLeft    = Offset(w * 0.60f, h * 0.28f),
        size       = Size(w * 0.18f, h * 0.44f)
    )
    drawArc(
        color      = color,
        startAngle = -50f,
        sweepAngle = 100f,
        useCenter  = false,
        style      = stroke,
        topLeft    = Offset(w * 0.62f, h * 0.16f),
        size       = Size(w * 0.26f, h * 0.68f)
    )
}
