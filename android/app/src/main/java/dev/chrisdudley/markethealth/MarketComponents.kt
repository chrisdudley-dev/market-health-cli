package dev.chrisdudley.markethealth

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import org.json.JSONObject
import java.time.Instant

internal enum class MarketIcon(val resource: Int) {
    OVERVIEW(R.drawable.ic_mh_overview), MARKETS(R.drawable.ic_mh_markets),
    PORTFOLIO(R.drawable.ic_mh_portfolio), HISTORY(R.drawable.ic_mh_history),
    LIST(R.drawable.ic_mh_list), CANDIDATES(R.drawable.ic_mh_candidates),
    POLICY(R.drawable.ic_mh_policy), SETTINGS(R.drawable.ic_mh_settings),
    MENU(R.drawable.ic_mh_menu), REFRESH(R.drawable.ic_mh_refresh),
    PLUS(R.drawable.ic_mh_plus), CLOSE(R.drawable.ic_mh_close),
    CHEVRON(R.drawable.ic_mh_chevron), EXPAND(R.drawable.ic_mh_expand),
    EDIT(R.drawable.ic_mh_edit), REMOVE(R.drawable.ic_mh_remove),
    INFO(R.drawable.ic_mh_info), WARNING(R.drawable.ic_mh_warning),
    CHECK(R.drawable.ic_mh_check), UP(R.drawable.ic_mh_up),
    DOWN(R.drawable.ic_mh_down), PAUSE(R.drawable.ic_mh_pause),
    EYE(R.drawable.ic_mh_eye), SEARCH(R.drawable.ic_mh_search),
    FILTER(R.drawable.ic_mh_filter)
}

@Composable internal fun MarketGlyph(icon: MarketIcon, modifier: Modifier = Modifier, description: String? = null,
    tint: Color = LocalContentColor.current) {
    Icon(painterResource(icon.resource), description, modifier.size(22.dp), tint = tint)
}
@Composable internal fun SectionHeading(title: String, subtitle: String? = null) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(title, style = MaterialTheme.typography.titleLarge, modifier = Modifier.semantics { heading() })
        if (subtitle != null) Text(subtitle, style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
@Composable internal fun SectionCard(modifier: Modifier = Modifier,
    content: @Composable ColumnScope.() -> Unit) {
    Surface(modifier.fillMaxWidth(), shape = MarketSpace.card,
        color = MaterialTheme.colorScheme.surface, tonalElevation = 0.dp) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp), content = content)
    }
}
@Composable internal fun PolicyChip(action: String, modifier: Modifier = Modifier) {
    val palette = LocalMarketColors.current
    val color = when (action) {
        "BUY" -> palette.buy
        "HOLD" -> palette.hold
        "WATCH" -> palette.watch
        "SELL", "DATA ERROR" -> palette.sell
        "HOLD — RESCUE" -> palette.rescue
        else -> palette.neutral
    }
    val icon = when (action) {
        "BUY" -> MarketIcon.UP
        "HOLD" -> MarketIcon.PAUSE
        "WATCH" -> MarketIcon.EYE
        "SELL" -> MarketIcon.DOWN
        "DATA ERROR" -> MarketIcon.WARNING
        "HOLD — RESCUE" -> MarketIcon.POLICY
        "PENDING REFRESH" -> MarketIcon.REFRESH
        else -> MarketIcon.INFO
    }
    Surface(modifier, color = color.copy(alpha = .12f), shape = RoundedCornerShape(50)) {
        Row(Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            MarketGlyph(icon, tint = color, modifier = Modifier.size(16.dp))
            Text(action.ifBlank { "UNKNOWN" }, style = MaterialTheme.typography.labelMedium,
                color = color, fontWeight = FontWeight.SemiBold)
        }
    }
}

private data class ScoreDisplay(val field: String, val label: String, val color: Color)

@Composable internal fun ScoreStrip(scores: JSONObject, modifier: Modifier = Modifier) {
    val palette = LocalMarketColors.current
    val fields = listOf(ScoreDisplay("c", "Current (C)", palette.current),
        ScoreDisplay("h1", "H1", palette.h1), ScoreDisplay("h5", "H5", palette.h5),
        ScoreDisplay("blend", "Blend", palette.blend))
    val fontScale = LocalDensity.current.fontScale
    BoxWithConstraints(modifier.fillMaxWidth()) {
        val columns = if (maxWidth < 280.dp || fontScale > 1.3f) 2 else 4
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            fields.chunked(columns).forEach { chunk ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    chunk.forEach { field ->
                        val value = scores.numberOrNull(field.field)
                        val label = if (value == null) "Unavailable" else displayScore(scores, field.field)
                        Column(Modifier.weight(1f).testTag("score-" + field.field)
                            .clearAndSetSemantics { contentDescription = field.label + " score " + label },
                            verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(field.label, style = MaterialTheme.typography.labelMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Text(label, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                            Box(Modifier.fillMaxWidth().height(4.dp)
                                .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(4.dp))) {
                                // Rendering scale only. Source values and exact audit remain unchanged.
                                if (value != null) Box(Modifier.fillMaxWidth((value / 100.0).toFloat().coerceIn(0f, 1f))
                                    .fillMaxHeight().background(field.color, RoundedCornerShape(4.dp)))
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable internal fun ValuePair(label: String, value: String, modifier: Modifier = Modifier) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(3.dp)) {
        Text(label, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.Medium)
    }
}

@Composable internal fun InformationPanel(title: String, detail: String,
    modifier: Modifier = Modifier, warning: Boolean = false, error: Boolean = false) {
    val color = if (error) MaterialTheme.colorScheme.onErrorContainer
        else if (warning) LocalMarketColors.current.watch else MaterialTheme.colorScheme.onSurfaceVariant
    val background = if (error) MaterialTheme.colorScheme.errorContainer
        else if (warning) color.copy(alpha = .1f) else MaterialTheme.colorScheme.surfaceContainer
    Surface(modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp), color = background) {
        Row(Modifier.padding(12.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            MarketGlyph(if (warning || error) MarketIcon.WARNING else MarketIcon.INFO, tint = color)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(title, style = MaterialTheme.typography.labelLarge, color = color)
                Text(detail, style = MaterialTheme.typography.bodySmall, color = color)
            }
        }
    }
}

@Composable internal fun RefreshStatus(data: JSONObject, now: Instant, modifier: Modifier = Modifier) {
    val status = refreshPresentation(data, now)
    val color = if (status.error) MaterialTheme.colorScheme.error
        else if (status.stale) LocalMarketColors.current.watch else MaterialTheme.colorScheme.primary
    Row(modifier.fillMaxWidth().testTag("refresh-status").semantics { liveRegion = LiveRegionMode.Polite },
        horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
        MarketGlyph(if (status.stale || status.error) MarketIcon.WARNING else if (status.timestamp.isBlank()) MarketIcon.INFO else MarketIcon.CHECK,
            tint = color, modifier = Modifier.size(18.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(status.label, style = MaterialTheme.typography.labelLarge, color = color)
            if (status.timestamp.isNotBlank()) Text(displayTime(status.timestamp),
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.testTag("refresh-timestamp-" + status.timestamp))
        }
    }
}

@Composable internal fun EmptyPanel(title: String, body: String, icon: MarketIcon,
    modifier: Modifier = Modifier, action: String? = null, onAction: () -> Unit = {}) {
    SectionCard(modifier.testTag("empty-state")) {
        Surface(shape = RoundedCornerShape(16.dp), color = MaterialTheme.colorScheme.primaryContainer) {
            MarketGlyph(icon, tint = MaterialTheme.colorScheme.onPrimaryContainer, modifier = Modifier.padding(14.dp).size(28.dp))
        }
        Text(title, style = MaterialTheme.typography.titleLarge, modifier = Modifier.semantics { heading() })
        Text(body, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        if (action != null) Button(onClick = onAction, modifier = Modifier.heightIn(min = 48.dp)) { Text(action) }
    }
}

@Composable internal fun LoadingPanels(modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth().semantics { contentDescription = "Loading Market Health" },
        verticalArrangement = Arrangement.spacedBy(16.dp)) {
        LinearProgressIndicator(Modifier.fillMaxWidth())
        repeat(3) {
            Surface(shape = MarketSpace.card, color = MaterialTheme.colorScheme.surface) {
                Column(Modifier.fillMaxWidth().padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Box(Modifier.fillMaxWidth(.45f).height(18.dp).background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(4.dp)))
                    Box(Modifier.fillMaxWidth(.75f).height(12.dp).background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(4.dp)))
                    Box(Modifier.fillMaxWidth().height(36.dp).background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(8.dp)))
                }
            }
        }
    }
}

@Composable internal fun AuditText(label: String, value: String) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(label, style = MaterialTheme.typography.labelLarge)
        Text(value, style = MaterialTheme.typography.bodySmall, fontFamily = FontFamily.Monospace,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable internal fun ExpandableSection(title: String, initiallyExpanded: Boolean = false,
    content: @Composable ColumnScope.() -> Unit) {
    var expanded by remember { mutableStateOf(initiallyExpanded) }
    SectionCard {
        TextButton(onClick = { expanded = !expanded }, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
            .semantics { stateDescription = if (expanded) "Expanded" else "Collapsed" }) {
            Text(title, Modifier.weight(1f), style = MaterialTheme.typography.titleMedium)
            MarketGlyph(if (expanded) MarketIcon.EXPAND else MarketIcon.CHEVRON)
        }
        if (expanded) content()
    }
}

@Composable internal fun SymbolIdentity(symbol: String, subtitle: String, action: String) {
    val large = LocalDensity.current.fontScale > 1.3f
    if (large) Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(symbol, style = MaterialTheme.typography.titleLarge)
        Text(subtitle, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        PolicyChip(action)
    } else Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Column(Modifier.weight(1f)) {
            Text(symbol, style = MaterialTheme.typography.titleLarge)
            Text(subtitle, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        PolicyChip(action)
    }
}
