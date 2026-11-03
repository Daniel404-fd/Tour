package ru.habittracker.app.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.time.LocalDate

/** Токены — те же, что у программы для ПК (desktop/tracker/ui/theme.py). */
data class Tokens(
    val bg: Color, val surface: Color, val surface2: Color, val text: Color, val text2: Color, val text3: Color,
    val border: Color, val borderStrong: Color, val accent: Color, val accentText: Color, val accentSoft: Color,
    val teal: Color, val tealText: Color, val tealSoft: Color, val tealOnSoft: Color, val link: Color,
    val danger: Color, val dangerSoft: Color, val warn: Color, val warnSoft: Color, val empty: Color,
    val todayBg: Color, val now: Color,
)

fun hex(s: String) = Color(android.graphics.Color.parseColor(s))

val LightTokens = Tokens(
    bg = hex("#F3F2EE"), surface = hex("#FFFFFF"), surface2 = hex("#F7F6F3"), text = hex("#1A1C1E"),
    text2 = hex("#4D5156"), text3 = hex("#666A70"), border = hex("#E1DFD8"), borderStrong = hex("#CFCCC3"),
    accent = hex("#4338CA"), accentText = hex("#FFFFFF"), accentSoft = hex("#E8E7FB"),
    teal = hex("#0F6E6A"), tealText = hex("#FFFFFF"), tealSoft = hex("#E1F0EE"), tealOnSoft = hex("#0B4F4C"),
    link = hex("#0F6E6A"), danger = hex("#B42318"), dangerSoft = hex("#FDECEA"), warn = hex("#8A5A00"),
    warnSoft = hex("#FFF3D6"), empty = hex("#E6E4DE"), todayBg = hex("#E7F3F2"), now = hex("#D93025"),
)
val DarkTokens = Tokens(
    bg = hex("#151719"), surface = hex("#1E2124"), surface2 = hex("#24282C"), text = hex("#ECEDEE"),
    text2 = hex("#B3B8BD"), text3 = hex("#9AA0A6"), border = hex("#30343A"), borderStrong = hex("#41464D"),
    accent = hex("#8B85F7"), accentText = hex("#14123A"), accentSoft = hex("#2B2950"),
    teal = hex("#0E4F4C"), tealText = hex("#FFFFFF"), tealSoft = hex("#173634"), tealOnSoft = hex("#8EDBD4"),
    link = hex("#5FD1C9"), danger = hex("#FF8A80"), dangerSoft = hex("#3D2220"), warn = hex("#F2C46D"),
    warnSoft = hex("#3A2F17"), empty = hex("#2E3237"), todayBg = hex("#17302E"), now = hex("#FF6B5E"),
)

val LocalTok = staticCompositionLocalOf { LightTokens }
val tok: Tokens @Composable get() = LocalTok.current

private fun scheme(t: Tokens, dark: Boolean): ColorScheme = if (dark) darkColorScheme(
    primary = t.teal, onPrimary = t.tealText, primaryContainer = t.tealSoft, onPrimaryContainer = t.tealOnSoft,
    secondary = t.accent, onSecondary = t.accentText, secondaryContainer = t.accentSoft,
    background = t.bg, onBackground = t.text, surface = t.surface, onSurface = t.text,
    surfaceVariant = t.surface2, onSurfaceVariant = t.text2, outline = t.borderStrong, outlineVariant = t.border,
    error = t.danger, surfaceContainer = t.surface, surfaceContainerHigh = t.surface2,
) else lightColorScheme(
    primary = t.teal, onPrimary = t.tealText, primaryContainer = t.tealSoft, onPrimaryContainer = t.tealOnSoft,
    secondary = t.accent, onSecondary = t.accentText, secondaryContainer = t.accentSoft,
    background = t.bg, onBackground = t.text, surface = t.surface, onSurface = t.text,
    surfaceVariant = t.surface2, onSurfaceVariant = t.text2, outline = t.borderStrong, outlineVariant = t.border,
    error = t.danger, surfaceContainer = t.surface, surfaceContainerHigh = t.surface2,
)

@Composable
fun TrackerTheme(content: @Composable () -> Unit) {
    val dark = isSystemInDarkTheme()       // как на ПК: следуем системной теме
    val t = if (dark) DarkTokens else LightTokens
    CompositionLocalProvider(LocalTok provides t) {
        MaterialTheme(colorScheme = scheme(t, dark), typography = Typography(), content = content)
    }
}

// ---------------------------------------------------------------- общие элементы

@Composable
fun Card(title: String? = null, action: (@Composable RowScope.() -> Unit)? = null, modifier: Modifier = Modifier,
         content: @Composable ColumnScope.() -> Unit) {
    Surface(modifier = modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp), color = tok.surface,
        border = BorderStroke(1.dp, tok.border)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (title != null || action != null) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (title != null) Text(title, style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.SemiBold),
                        modifier = Modifier.weight(1f))
                    action?.invoke(this)
                }
            }
            content()
        }
    }
}

@Composable
fun Caption(text: String, color: Color = tok.text2, modifier: Modifier = Modifier, maxLines: Int = Int.MAX_VALUE) =
    Text(text, color = color, fontSize = 13.sp, modifier = modifier, maxLines = maxLines, overflow = TextOverflow.Ellipsis)

@Composable
fun Secondary(text: String, color: Color = tok.text2, modifier: Modifier = Modifier) =
    Text(text, color = color, fontSize = 15.sp, modifier = modifier)

/** Фирменный элемент: прогресс из синих «кирпичиков». */
@Composable
fun BlocksProgress(value: Double, modifier: Modifier = Modifier, height: Dp = 10.dp) {
    val t = tok
    val pct = (value * 100).toInt()
    Canvas(modifier.fillMaxWidth().height(height).semantics { contentDescription = "Прогресс $pct%" }) {
        drawRoundRect(t.empty, cornerRadius = CornerRadius(4.dp.toPx()))
        val block = 8.dp.toPx(); val gap = 2.dp.toPx()
        val n = ((size.width * value.coerceIn(0.0, 1.0)) / (block + gap)).toInt()
        for (i in 0 until n) drawRoundRect(t.accent, topLeft = Offset(i * (block + gap), 0f),
            size = Size(block, size.height), cornerRadius = CornerRadius(2.dp.toPx()))
    }
}

/** Полоса дней: заполненная клетка — день выполнен, сегодняшний обведён. */
@Composable
fun HeatStrip(days: List<LocalDate>, marks: Set<LocalDate>, today: LocalDate, cell: Dp = 9.dp, gap: Dp = 3.dp) {
    val t = tok
    val done = days.count { it in marks }
    Canvas(Modifier.width((cell + gap) * days.size).height(cell + 2.dp)
        .semantics { contentDescription = "Выполнено $done из ${days.size} дней" }) {
        val c = cell.toPx(); val g = gap.toPx()
        days.forEachIndexed { i, d ->
            val tl = Offset(i * (c + g) + 1f, 1f)
            drawRoundRect(if (d in marks) t.accent else t.empty, topLeft = tl, size = Size(c, c), cornerRadius = CornerRadius(2.5f))
            if (d == today) drawRoundRect(t.text, topLeft = tl, size = Size(c, c), cornerRadius = CornerRadius(2.5f), style = Stroke(1.2f))
        }
    }
}

@Composable
fun Chip(text: String, selected: Boolean, dot: Color? = null, onClick: () -> Unit) {
    val t = tok
    Row(Modifier.clip(RoundedCornerShape(16.dp))
        .background(if (selected) t.tealSoft else t.surface)
        .border(1.dp, if (selected) t.teal else t.borderStrong, RoundedCornerShape(16.dp))
        .clickable(onClick = onClick).padding(horizontal = 12.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically) {
        if (dot != null) { Box(Modifier.size(8.dp).clip(CircleShape).background(dot)); Box(Modifier.width(6.dp)) }
        Text(text, color = if (selected) t.tealOnSoft else t.text, fontSize = 14.sp)
    }
}

@Composable
fun Dot(color: Color, size: Dp = 8.dp) = Box(Modifier.size(size).clip(CircleShape).background(color))

@Composable
fun EmptyText(text: String) = Text(text, color = tok.text2, fontSize = 15.sp, modifier = Modifier.padding(PaddingValues(vertical = 24.dp, horizontal = 8.dp)))

val Header = TextStyle(fontSize = 26.sp, fontWeight = FontWeight.SemiBold)
