package dev.chrisdudley.markethealth

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import androidx.core.view.WindowInsetsControllerCompat
import androidx.core.content.edit

enum class ThemeMode(val label: String) { SYSTEM("System"), LIGHT("Light"), DARK("Dark") }

/** Appearance only, deliberately separate from authoritative portfolio/settings SQLite. */
internal class ThemePreferences(context: Context) {
    private val preferences = context.getSharedPreferences("market-health-appearance", Context.MODE_PRIVATE)
    private val mutable = MutableStateFlow(runCatching {
        ThemeMode.valueOf(preferences.getString("theme", ThemeMode.SYSTEM.name)!!)
    }.getOrDefault(ThemeMode.SYSTEM))
    val mode: StateFlow<ThemeMode> = mutable
    fun select(mode: ThemeMode) {
        preferences.edit { putString("theme", mode.name) }
        mutable.value = mode
    }
}

internal object MarketSpace {
    val xs = 4.dp
    val sm = 8.dp
    val md = 12.dp
    val lg = 16.dp
    val xl = 24.dp
    val xxl = 32.dp
    val touch = 48.dp
    val card = RoundedCornerShape(20.dp)
}

private val LightColors = lightColorScheme(
    primary = Color(0xFF006B57), onPrimary = Color.White,
    primaryContainer = Color(0xFFD2F4E8), onPrimaryContainer = Color(0xFF003D30),
    secondary = Color(0xFF365E78), onSecondary = Color.White,
    secondaryContainer = Color(0xFFD8EAF5), onSecondaryContainer = Color(0xFF123347),
    tertiary = Color(0xFF6D4D8F), onTertiary = Color.White,
    background = Color(0xFFF3F6F8), onBackground = Color(0xFF152C3A),
    surface = Color.White, onSurface = Color(0xFF152C3A),
    surfaceVariant = Color(0xFFE5EDF1), onSurfaceVariant = Color(0xFF4B606D),
    surfaceContainerLow = Color.White, surfaceContainer = Color(0xFFEDF2F5),
    surfaceContainerHigh = Color(0xFFE4ECF0),
    outline = Color(0xFF71828C), outlineVariant = Color(0xFFD3DEE5),
    error = Color(0xFFAD2430), onError = Color.White,
    errorContainer = Color(0xFFFFE0E1), onErrorContainer = Color(0xFF6D0A17)
)
private val DarkColors = darkColorScheme(
    primary = Color(0xFF75DDC0), onPrimary = Color(0xFF00382B),
    primaryContainer = Color(0xFF134F42), onPrimaryContainer = Color(0xFFB7F6DF),
    secondary = Color(0xFFB1D3ED), onSecondary = Color(0xFF15364C),
    secondaryContainer = Color(0xFF2A495F), onSecondaryContainer = Color(0xFFD8EAF5),
    tertiary = Color(0xFFD7BBF5), onTertiary = Color(0xFF3C2458),
    background = Color(0xFF0D1821), onBackground = Color(0xFFE2EDF4),
    surface = Color(0xFF14242F), onSurface = Color(0xFFE2EDF4),
    surfaceVariant = Color(0xFF283E4B), onSurfaceVariant = Color(0xFFB6C8D3),
    surfaceContainerLow = Color(0xFF14242F), surfaceContainer = Color(0xFF1B2E3B),
    surfaceContainerHigh = Color(0xFF223845),
    outline = Color(0xFF869BA8), outlineVariant = Color(0xFF38505E),
    error = Color(0xFFFFB3BA), onError = Color(0xFF650F1D),
    errorContainer = Color(0xFF5D202A), onErrorContainer = Color(0xFFFFDADF)
)

@Immutable
internal data class MarketSemanticColors(
    val buy: Color, val hold: Color, val watch: Color, val sell: Color,
    val rescue: Color, val neutral: Color,
    val current: Color, val h1: Color, val h5: Color, val blend: Color
)
internal fun marketSemanticColors(dark: Boolean) = if (dark) MarketSemanticColors(
    Color(0xFF8BDBB2), Color(0xFFACCAFF), Color(0xFFF5CB83), Color(0xFFFFB3BA),
    Color(0xFFD8BAFF), Color(0xFFB6C8D3),
    Color(0xFFACCAFF), Color(0xFF75DDC0), Color(0xFFD8BAFF), Color(0xFFE2EDF4)
) else MarketSemanticColors(
    Color(0xFF146C43), Color(0xFF2455A3), Color(0xFF855000), Color(0xFFAD2430),
    Color(0xFF714394), Color(0xFF4B606D),
    Color(0xFF2455A3), Color(0xFF006B57), Color(0xFF714394), Color(0xFF152C3A)
)
internal val LocalMarketColors = staticCompositionLocalOf { marketSemanticColors(false) }

private val MarketTypography = Typography(
    displaySmall = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.Bold, fontSize = 32.sp, lineHeight = 38.sp),
    headlineMedium = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.Bold, fontSize = 26.sp, lineHeight = 32.sp),
    headlineSmall = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.SemiBold, fontSize = 22.sp, lineHeight = 28.sp),
    titleLarge = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.SemiBold, fontSize = 20.sp, lineHeight = 26.sp),
    titleMedium = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.SemiBold, fontSize = 16.sp, lineHeight = 23.sp),
    bodyLarge = TextStyle(fontFamily = FontFamily.SansSerif, fontSize = 16.sp, lineHeight = 24.sp),
    bodyMedium = TextStyle(fontFamily = FontFamily.SansSerif, fontSize = 14.sp, lineHeight = 21.sp),
    bodySmall = TextStyle(fontFamily = FontFamily.SansSerif, fontSize = 12.sp, lineHeight = 18.sp),
    labelLarge = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, lineHeight = 20.sp),
    labelMedium = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.Medium, fontSize = 12.sp, lineHeight = 17.sp),
    labelSmall = TextStyle(fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.Medium, fontSize = 11.sp, lineHeight = 16.sp)
)

@Composable
fun MarketHealthTheme(mode: ThemeMode = ThemeMode.SYSTEM, content: @Composable () -> Unit) {
    val dark = when (mode) {
        ThemeMode.SYSTEM -> isSystemInDarkTheme()
        ThemeMode.LIGHT -> false
        ThemeMode.DARK -> true
    }
    val view = LocalView.current
    if (!view.isInEditMode) SideEffect {
        view.context.activityOrNull()?.window?.let { window ->
            WindowInsetsControllerCompat(window, view).apply {
                isAppearanceLightStatusBars = !dark
                isAppearanceLightNavigationBars = !dark
            }
        }
    }
    CompositionLocalProvider(LocalMarketColors provides marketSemanticColors(dark)) {
        MaterialTheme(
            colorScheme = if (dark) DarkColors else LightColors,
            typography = MarketTypography,
            shapes = Shapes(extraSmall = RoundedCornerShape(8.dp), small = RoundedCornerShape(12.dp),
                medium = RoundedCornerShape(16.dp), large = MarketSpace.card, extraLarge = RoundedCornerShape(28.dp)),
            content = content
        )
    }
}

private fun Context.activityOrNull(): Activity? = when (this) {
    is Activity -> this
    is ContextWrapper -> baseContext.activityOrNull()
    else -> null
}
