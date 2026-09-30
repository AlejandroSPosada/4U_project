package com.example.myapplication.ui.inicio

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.*
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
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
import kotlin.math.roundToInt

// ─── Palette ──────────────────────────────────────────────────────────────────
private val BackgroundColor = Color(0xFF0D0D14)
private val OrbCenter       = Color(0xFF9B4DFF)
private val OrbMid          = Color(0xFF6B2BCC)
private val OrbEdge         = Color(0xFF3D0080)
private val GlowColor       = Color(0xFF7B3FE4)
private val AccentPurple    = Color(0xFF9B4DFF)
private val CardBg          = Color(0x22FFFFFF)

// ─── Screen ───────────────────────────────────────────────────────────────────
@Composable
fun InicioScreen(viewModel: InicioViewModel = viewModel()) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()

    // Single image picker
    val galleryLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.PickVisualMedia()
    ) { uri ->
        if (uri != null) viewModel.onImagenSeleccionada(uri)
    }

    val infiniteTransition = rememberInfiniteTransition(label = "orb_anim")
    val pulseScale by infiniteTransition.animateFloat(
        initialValue = 1.57f, targetValue = 1.73f,
        animationSpec = infiniteRepeatable(tween(1800, easing = EaseInOutSine), RepeatMode.Reverse),
        label = "pulse"
    )
    val glowAlpha by infiniteTransition.animateFloat(
        initialValue = 0.45f, targetValue = 0.75f,
        animationSpec = infiniteRepeatable(tween(1800, easing = EaseInOutSine), RepeatMode.Reverse),
        label = "glow"
    )
    val waveAlpha by infiniteTransition.animateFloat(
        initialValue = 0.4f, targetValue = 1.0f,
        animationSpec = infiniteRepeatable(tween(1200, easing = EaseInOut), RepeatMode.Reverse),
        label = "wave"
    )

    Box(
        modifier = Modifier.fillMaxSize().background(BackgroundColor),
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
            // Top
            Column(
                modifier = Modifier.padding(top = 56.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                SignalIcon(waveAlpha)
                Spacer(Modifier.height(28.dp))
                Text(
                    text = when (uiState.predictionState) {
                        is PredictionState.Loading -> "Identificando..."
                        is PredictionState.Success -> "Ubicacion encontrada"
                        is PredictionState.Error   -> "Intentalo de nuevo"
                        else                       -> "Toca para identificar\ndonde te encuentras"
                    },
                    color = Color.White,
                    fontSize = 20.sp,
                    fontWeight = FontWeight.SemiBold,
                    textAlign = TextAlign.Center,
                    lineHeight = 28.sp
                )
            }

            // Center: orb + image preview + result
            Box(contentAlignment = Alignment.Center) {
                GlowingOrb(
                    pulseScale = pulseScale,
                    glowAlpha  = glowAlpha,
                    onClick    = {
                        // Allow tapping again anytime
                        galleryLauncher.launch(
                            PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)
                        )
                    }
                )

                // Selected image (shown on the orb)
                if (uiState.imagenSeleccionada != null) {
                    AsyncImage(
                        model = uiState.imagenSeleccionada,
                        contentDescription = "Imagen seleccionada",
                        contentScale = ContentScale.Crop,
                        modifier = Modifier
                            .size(160.dp)
                            .clip(CircleShape)
                            .border(3.dp, AccentPurple, CircleShape)
                    )
                }

                // Loading spinner overlay
                if (uiState.predictionState is PredictionState.Loading) {
                    CircularProgressIndicator(
                        color = AccentPurple,
                        strokeWidth = 3.dp,
                        modifier = Modifier.size(190.dp)
                    )
                }
            }

            // Result card + footer
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                modifier = Modifier.padding(bottom = 48.dp)
            ) {
                // Result card
                AnimatedVisibility(
                    visible = uiState.predictionState is PredictionState.Success,
                    enter   = fadeIn() + scaleIn(),
                    exit    = fadeOut()
                ) {
                    val result = (uiState.predictionState as? PredictionState.Success)?.result
                    if (result != null) {
                        ResultCard(result)
                    }
                }

                // Error message
                if (uiState.predictionState is PredictionState.Error) {
                    Text(
                        text = (uiState.predictionState as PredictionState.Error).message,
                        color = Color(0xFFFF6B6B),
                        fontSize = 13.sp,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.padding(top = 12.dp)
                    )
                }

                Spacer(Modifier.height(16.dp))

                // Footer hint
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.Center
                ) {
                    Canvas(modifier = Modifier.size(18.dp)) { drawVolumeIcon(AccentPurple) }
                    Spacer(Modifier.width(8.dp))
                    Text(
                        text = if (uiState.predictionState is PredictionState.Success)
                            "Toca el orbe para nueva foto"
                        else
                            "Activa el lector de pantalla",
                        color = AccentPurple,
                        fontSize = 14.sp
                    )
                }
            }
        }
    }
}

// ─── Result Card ──────────────────────────────────────────────────────────────
@Composable
private fun ResultCard(result: PredictionResult) {
    val pct = (result.similarity * 100).roundToInt()
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(20.dp))
            .background(CardBg)
            .border(1.dp, AccentPurple.copy(alpha = 0.4f), RoundedCornerShape(20.dp))
            .padding(vertical = 20.dp, horizontal = 24.dp),
        contentAlignment = Alignment.Center
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(
                text = result.location.uppercase(),
                color = Color.White,
                fontSize = 26.sp,
                fontWeight = FontWeight.Bold,
                textAlign = TextAlign.Center
            )
            Spacer(Modifier.height(6.dp))
            Text(
                text = "Similitud: $pct%",
                color = AccentPurple,
                fontSize = 15.sp,
                fontWeight = FontWeight.Medium
            )
        }
    }
}

// ─── Signal Icon ──────────────────────────────────────────────────────────────
@Composable
private fun SignalIcon(waveAlpha: Float) {
    Canvas(modifier = Modifier.size(64.dp)) {
        val cx = size.width / 2f
        val cy = size.height / 2f
        drawCircle(color = Color.White, radius = 5.dp.toPx(), center = Offset(cx, cy))
        listOf(14.dp.toPx(), 22.dp.toPx(), 30.dp.toPx()).forEachIndexed { i, r ->
            val alpha = (waveAlpha - i * 0.18f).coerceIn(0f, 1f)
            val stroke = Stroke(width = 2.2.dp.toPx(), cap = StrokeCap.Round)
            val tl = Offset(cx - r, cy - r)
            val sz = Size(r * 2, r * 2)
            drawArc(color = Color.White.copy(alpha = alpha), startAngle = 210f, sweepAngle = 120f, useCenter = false, topLeft = tl, size = sz, style = stroke)
            drawArc(color = Color.White.copy(alpha = alpha), startAngle = 30f,  sweepAngle = 120f, useCenter = false, topLeft = tl, size = sz, style = stroke)
        }
    }
}

// ─── Glowing Orb ─────────────────────────────────────────────────────────────
@Composable
private fun GlowingOrb(pulseScale: Float, glowAlpha: Float, onClick: () -> Unit) {
    Canvas(
        modifier = Modifier
            .size(280.dp)
            .clickable(
                interactionSource = remember { MutableInteractionSource() },
                indication        = null
            ) { onClick() }
    ) {
        val cx = size.width / 2f
        val cy = size.height / 2f
        val radius = (size.minDimension / 2f) * 0.80f * pulseScale

        listOf(
            radius * 1.38f to glowAlpha * 0.08f,
            radius * 1.25f to glowAlpha * 0.16f,
            radius * 1.13f to glowAlpha * 0.26f,
            radius * 1.05f to glowAlpha * 0.38f
        ).forEach { (r, a) ->
            drawCircle(
                brush = Brush.radialGradient(
                    listOf(GlowColor.copy(alpha = a), Color.Transparent),
                    Offset(cx, cy), r
                ),
                radius = r, center = Offset(cx, cy)
            )
        }
        drawCircle(
            brush = Brush.radialGradient(
                listOf(OrbCenter, OrbMid, OrbEdge, Color(0x00000000)),
                Offset(cx - radius * 0.15f, cy - radius * 0.15f), radius * 1.2f
            ),
            radius = radius, center = Offset(cx, cy)
        )
        drawCircle(
            brush = Brush.sweepGradient(
                listOf(
                    GlowColor.copy(0.6f), Color.Transparent,
                    GlowColor.copy(0.85f), GlowColor.copy(0.3f), Color.Transparent
                ), Offset(cx, cy)
            ),
            radius = radius, center = Offset(cx, cy),
            style = Stroke(2.5.dp.toPx())
        )
        drawCircle(
            brush = Brush.radialGradient(
                listOf(Color.White.copy(0.22f), Color.Transparent),
                Offset(cx - radius * 0.28f, cy - radius * 0.28f), radius * 0.55f
            ),
            radius = radius * 0.55f,
            center = Offset(cx - radius * 0.28f, cy - radius * 0.28f)
        )
    }
}

// ─── Volume Icon ──────────────────────────────────────────────────────────────
private fun DrawScope.drawVolumeIcon(color: Color) {
    val w = size.width; val h = size.height
    val stroke = Stroke(1.5.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round)
    val path = Path().apply {
        moveTo(w*.18f, h*.35f); lineTo(w*.38f, h*.35f)
        lineTo(w*.62f, h*.15f); lineTo(w*.62f, h*.85f)
        lineTo(w*.38f, h*.65f); lineTo(w*.18f, h*.65f); close()
    }
    drawPath(path, color, style = stroke)
    drawArc(
        color      = color,
        startAngle = -40f,
        sweepAngle = 80f,
        useCenter  = false,
        topLeft    = Offset(w * 0.60f, h * 0.28f),
        size       = Size(w * 0.18f, h * 0.44f),
        style      = stroke
    )
    drawArc(
        color      = color,
        startAngle = -50f,
        sweepAngle = 100f,
        useCenter  = false,
        topLeft    = Offset(w * 0.62f, h * 0.16f),
        size       = Size(w * 0.26f, h * 0.68f),
        style      = stroke
    )
}
