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
import androidx.compose.ui.graphics.toArgb
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.graphics.ColorUtils
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
    // спокойная «бумажная» палитра, как в Notion: почти белый фон, тёплый графитовый текст, тонкие границы
    bg = hex("#FBFBFA"), surface = hex("#FFFFFF"), surface2 = hex("#F7F7F5"), text = hex("#2F2E2B"),
    text2 = hex("#45433F"), text3 = hex("#5F5D58"), border = hex("#EAE9E6"), borderStrong = hex("#C9C7C1"),
    accent = hex("#4338CA"), accentText = hex("#FFFFFF"), accentSoft = hex("#E8E7FB"),
    teal = hex("#0F6E6A"), tealText = hex("#FFFFFF"), tealSoft = hex("#E1F0EE"), tealOnSoft = hex("#0B4F4C"),
    link = hex("#0F6E6A"), danger = hex("#B42318"), dangerSoft = hex("#FDECEA"), warn = hex("#8A5A00"),
    warnSoft = hex("#FFF3D6"), empty = hex("#E6E4DE"), todayBg = hex("#E7F3F2"), now = hex("#D93025"),
)
val DarkTokens = Tokens(
    bg = hex("#191919"), surface = hex("#202020"), surface2 = hex("#262626"), text = hex("#E9E9E7"),
    text2 = hex("#CFCECA"), text3 = hex("#ABAAA6"), border = hex("#2F2F2F"), borderStrong = hex("#555555"),
    accent = hex("#8B85F7"), accentText = hex("#14123A"), accentSoft = hex("#2B2950"),
    teal = hex("#0F6E6A"), tealText = hex("#FFFFFF"), tealSoft = hex("#1D4340"), tealOnSoft = hex("#A6EBE4"),
    link = hex("#5FD1C9"), danger = hex("#FF8A80"), dangerSoft = hex("#3D2220"), warn = hex("#F2C46D"),
    warnSoft = hex("#3A2F17"), empty = hex("#2E3237"), todayBg = hex("#17302E"), now = hex("#FF6B5E"),
)

// ---------------------------------------------------------------- своё оформление

val PRIMARY_PRESETS = listOf("#0F6E6A" to "Бирюзовый", "#1D4ED8" to "Синий", "#4338CA" to "Индиго",
    "#7E22CE" to "Фиолетовый", "#BE185D" to "Малиновый", "#B91C1C" to "Красный", "#B45309" to "Янтарный",
    "#15803D" to "Зелёный", "#374151" to "Графит")
val ACCENT_PRESETS = listOf("#4338CA" to "Индиго", "#1D4ED8" to "Синий", "#0F766E" to "Бирюзовый",
    "#15803D" to "Зелёный", "#B45309" to "Янтарный", "#BE185D" to "Малиновый", "#7E22CE" to "Фиолетовый")

/** Настройки оформления телефона (хранятся локально, не синхронизируются). */
object Appearance {
    private var prefs: android.content.SharedPreferences? = null
    var primary by mutableStateOf<String?>(null); private set
    var accent by mutableStateOf<String?>(null); private set
    var mode by mutableStateOf("system"); private set     // system | light | dark
    var font by mutableStateOf("default"); private set    // ключ из FONT_CHOICES
    var scale by mutableStateOf(1f); private set          // размер текста поверх системного

    fun load(ctx: android.content.Context) {
        val p = ctx.getSharedPreferences("appearance", android.content.Context.MODE_PRIVATE)
        prefs = p
        primary = p.getString("primary", null); accent = p.getString("accent", null); mode = p.getString("mode", "system") ?: "system"
        font = p.getString("font", "default") ?: "default"; scale = p.getFloat("scale", 1f)
    }
    fun setFont(font: String = this.font, scale: Float = this.scale) {
        this.font = font; this.scale = scale
        prefs?.edit()?.putString("font", font)?.putFloat("scale", scale)?.apply()
    }
    fun update(primary: String? = this.primary, accent: String? = this.accent, mode: String = this.mode) {
        this.primary = primary; this.accent = accent; this.mode = mode
        prefs?.edit()?.putString("primary", primary)?.putString("accent", accent)?.putString("mode", mode)?.apply()
    }
    fun reset() { update(null, null, "system"); setFont("default", 1f) }
}

object Contrast {
    fun ratio(a: Color, b: Color) = ColorUtils.calculateContrast(a.copy(alpha = 1f).toArgb(), b.copy(alpha = 1f).toArgb())
    fun mix(a: Color, b: Color, t: Float) = Color(ColorUtils.blendARGB(a.toArgb(), b.toArgb(), t))
    /** Темнее/светлее (тот же оттенок), пока контраст с фоном не станет ≥ target. */
    fun shift(c: Color, against: Color, target: Double, lighter: Boolean): Color {
        val hsl = FloatArray(3)
        ColorUtils.colorToHSL(c.toArgb(), hsl)
        var out = c
        repeat(60) {
            if (ratio(out, against) >= target) return out
            hsl[2] = if (lighter) minOf(1f, hsl[2] + 0.02f) else maxOf(0f, hsl[2] - 0.02f)
            out = Color(ColorUtils.HSLToColor(hsl))
        }
        return out
    }
}

/** Как derive() в программе для ПК: свой цвет, но текст не хуже 4.5:1. */
fun derive(base: Tokens, dark: Boolean, primary: String?, accent: String?): Tokens {
    var t = base
    val white = Color.White
    if (primary != null) {
        val p = hex(primary)
        var fill = Contrast.shift(p, white, 4.8, lighter = false)
        if (dark) fill = Contrast.mix(fill, Color.Black, 0.2f)
        val soft = Contrast.mix(t.surface, fill, if (dark) 0.35f else 0.16f)
        t = t.copy(teal = fill, tealText = white, tealSoft = soft,
            tealOnSoft = Contrast.shift(p, soft, 5.0, lighter = dark),
            link = Contrast.shift(p, t.surface, 4.8, lighter = dark),
            todayBg = Contrast.mix(t.bg, fill, if (dark) 0.22f else 0.10f))
    }
    if (accent != null) {
        val a0 = hex(accent)
        t = if (dark) {
            val a = Contrast.shift(a0, t.surface, 5.0, lighter = true)
            val txt = if (Contrast.ratio(a, hex("#121212")) >= 4.5) hex("#121212") else white
            t.copy(accent = a, accentText = txt, accentSoft = Contrast.mix(t.surface, a, 0.3f))
        } else {
            val a = Contrast.shift(a0, white, 5.0, lighter = false)
            t.copy(accent = a, accentText = white, accentSoft = Contrast.mix(t.surface, a, 0.16f))
        }
    }
    return t
}

val FONT_CHOICES = listOf("default" to "Стандартный", "condensed" to "Узкий", "serif" to "С засечками",
    "mono" to "Моноширинный", "light" to "Лёгкий")
val SCALE_CHOICES = listOf(0.9f to "Мельче", 1f to "Обычный", 1.1f to "Крупнее", 1.2f to "Крупный", 1.3f to "Очень крупный")

fun fontFamilyFor(key: String): androidx.compose.ui.text.font.FontFamily = when (key) {
    "condensed" -> androidx.compose.ui.text.font.FontFamily(android.graphics.Typeface.create("sans-serif-condensed", android.graphics.Typeface.NORMAL))
    "serif" -> androidx.compose.ui.text.font.FontFamily.Serif
    "mono" -> androidx.compose.ui.text.font.FontFamily.Monospace
    "light" -> androidx.compose.ui.text.font.FontFamily(android.graphics.Typeface.create("sans-serif-light", android.graphics.Typeface.NORMAL))
    else -> androidx.compose.ui.text.font.FontFamily.Default
}

private fun Typography.withFamily(f: androidx.compose.ui.text.font.FontFamily) = Typography(
    displayLarge.copy(fontFamily = f), displayMedium.copy(fontFamily = f), displaySmall.copy(fontFamily = f),
    headlineLarge.copy(fontFamily = f), headlineMedium.copy(fontFamily = f), headlineSmall.copy(fontFamily = f),
    titleLarge.copy(fontFamily = f), titleMedium.copy(fontFamily = f), titleSmall.copy(fontFamily = f),
    bodyLarge.copy(fontFamily = f), bodyMedium.copy(fontFamily = f), bodySmall.copy(fontFamily = f),
    labelLarge.copy(fontFamily = f), labelMedium.copy(fontFamily = f), labelSmall.copy(fontFamily = f))

val LocalTok = staticCompositionLocalOf { LightTokens }
val tok: Tokens @Composable get() = LocalTok.current

// В тёмной теме «primary» (текстовые кнопки, ссылки, переключатели) — светлый вариант основного цвета:
// тёмно-бирюзовый текст на тёмном фоне почти не читался.
private fun scheme(t: Tokens, dark: Boolean): ColorScheme = if (dark) darkColorScheme(
    primary = t.link, onPrimary = hex("#0B1514"), primaryContainer = t.tealSoft, onPrimaryContainer = t.tealOnSoft,
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
    val system = isSystemInDarkTheme()
    val dark = when (Appearance.mode) { "dark" -> true; "light" -> false; else -> system }
    val t = derive(if (dark) DarkTokens else LightTokens, dark, Appearance.primary, Appearance.accent)
    val density = androidx.compose.ui.platform.LocalDensity.current
    val family = fontFamilyFor(Appearance.font)
    CompositionLocalProvider(LocalTok provides t,
        androidx.compose.ui.platform.LocalDensity provides androidx.compose.ui.unit.Density(density.density, density.fontScale * Appearance.scale)) {
        MaterialTheme(colorScheme = scheme(t, dark), typography = Typography().withFamily(family), content = content)
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
    Text(text, color = color, fontSize = 14.sp, modifier = modifier, maxLines = maxLines, overflow = TextOverflow.Ellipsis)

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

val Header: TextStyle
    @Composable get() = TextStyle(fontSize = 28.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.3).sp,
        fontFamily = fontFamilyFor(Appearance.font))
