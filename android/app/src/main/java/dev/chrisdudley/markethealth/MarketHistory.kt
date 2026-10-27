package dev.chrisdudley.markethealth

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant

@Composable internal fun HistoryScreen(history: JSONArray, activeFilters: JSONObject, load: (JSONObject, Boolean) -> Unit, onSelect: (JSONObject) -> Unit) {
    var symbol by rememberSaveable(activeFilters.toString()) { mutableStateOf(activeFilters.optString("symbol")) }
    var action by rememberSaveable(activeFilters.toString()) { mutableStateOf(activeFilters.optString("action")) }
    var account by rememberSaveable(activeFilters.toString()) { mutableStateOf(activeFilters.optString("account")) }
    var date by rememberSaveable(activeFilters.toString()) { mutableStateOf(activeFilters.optString("date")) }
    var filterOpen by rememberSaveable { mutableStateOf(false) }
    // Initial load does not overwrite an already active symbol filter from detail.
    LaunchedEffect(Unit) { load(activeFilters, false) }
    val rows = remember(history) { history.objects() }
    fun filters() = JSONObject().put("symbol", symbol).put("action", action).put("account", account).put("date", date)
    LazyColumn(Modifier.testTag("history-list"), verticalArrangement = Arrangement.spacedBy(16.dp), contentPadding = screenPadding) {
        item { SectionHeading("A record of every decision", "${rows.size} loaded observations · newest first") }
        item { OutlinedButton(onClick = { filterOpen = !filterOpen }, modifier = Modifier.fillMaxWidth()) {
            MarketGlyph(MarketIcon.FILTER); Spacer(Modifier.width(8.dp)); Text(if (filterOpen) "Hide history filters" else "Filter history")
        } }
        if (filterOpen) item { SectionCard {
            OutlinedTextField(symbol, { symbol = it.uppercase() }, label = { Text("Symbol") }, singleLine = true, modifier = Modifier.fillMaxWidth().testTag("history-symbol"))
            OutlinedTextField(action, { action = it.uppercase() }, label = { Text("Action") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(account, { account = it }, label = { Text("Account") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(date, { date = it }, label = { Text("UTC YYYY-MM-DD") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            Button(onClick = { load(filters(), false) }, modifier = Modifier.testTag("apply-history-filter")) { Text("Apply filters") }
        } }
        if (rows.isEmpty()) item { EmptyPanel("No recorded decisions", "Refresh to build history, or adjust the filters. Past observations are never fabricated.", MarketIcon.HISTORY) }
        else {
            item { HistoryChart(rows) }
            item { SectionHeading("Decision timeline", "Previous action → recorded action. Details retain exact reasons.") }
            items(rows, key = { it.raw("id") }) { TimelineCard(it, onSelect) }
            item { OutlinedButton(onClick = { load(filters(), true) }, modifier = Modifier.fillMaxWidth()) { Text("Load older decisions") } }
        }
    }
}

@Composable internal fun TimelineCard(row: JSONObject, onSelect: (JSONObject) -> Unit) {
    SectionCard(Modifier.testTag("history-${row.raw("id")}").clickable(onClickLabel = "Open recorded ${row.symbol()} decision") { onSelect(row) }) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            MarketGlyph(MarketIcon.HISTORY)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("${row.symbol()} · ${displayTime(row.optString("timestamp"))}", style = MaterialTheme.typography.titleMedium)
                Text("${row.raw("previous_action")} → ${row.raw("action")}", style = MaterialTheme.typography.bodyLarge)
                PolicyChip(row.optString("action"))
                Text(row.obj("result").array("reason_codes").strings().joinToString(" · ").ifBlank { "No reason codes recorded" },
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text("C ${displayScore(row.obj("scores"), "c")} · H1 ${displayScore(row.obj("scores"), "h1")} · H5 ${displayScore(row.obj("scores"), "h5")} · Blend ${displayScore(row.obj("scores"), "blend")}",
                    style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

internal data class HistoryPoint(val timestamp: Instant, val scores: JSONObject, val row: JSONObject)
internal fun chartPoints(rows: List<JSONObject>, symbol: String): List<HistoryPoint> = rows.filter { it.symbol() == symbol }.mapNotNull { row ->
    parseObservationTime(row.optString("timestamp"))?.let { HistoryPoint(it, row.obj("scores"), row) }
}.sortedBy { it.timestamp }

/** Points only: no interpolation, invented samples or connected lines across gaps. */
@Composable internal fun HistoryChart(rows: List<JSONObject>) {
    val symbols = remember(rows) { rows.map { it.symbol() }.distinct().sorted() }
    var requested by remember { mutableStateOf<String?>(null) }
    val symbol = requested?.takeIf { it in symbols } ?: symbols.firstOrNull().orEmpty()
    val points = remember(rows, symbol) { chartPoints(rows, symbol) }
    var days by remember(symbol) { mutableIntStateOf(0) }
    val latest = points.lastOrNull()?.timestamp
    val visible = remember(points, days) { if (days == 0 || latest == null) points else points.filter { it.timestamp >= latest.minusSeconds(days * 86400L) } }
    SectionCard(Modifier.testTag("history-chart")) {
        SectionHeading("Score history", "Recorded observations · 0–100 score scale")
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            symbols.forEach { value -> FilterChip(selected = symbol == value, onClick = { requested = value }, label = { Text(value) }) }
        }
        if (points.size > 1) {
            val span = java.time.Duration.between(points.first().timestamp, points.last().timestamp).toDays()
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                FilterChip(selected = days == 0, onClick = { days = 0 }, label = { Text("All loaded") })
                listOf(7, 30, 90).filter { span >= it }.forEach { range -> FilterChip(selected = days == range, onClick = { days = range }, label = { Text("${range}d loaded") }) }
            }
        }
        val palette = LocalMarketColors.current
        val fields = listOf("c" to palette.current, "h1" to palette.h1, "h5" to palette.h5, "blend" to palette.blend)
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            fields.forEachIndexed { index, pair -> Text(listOf("● C", "■ H1", "▲ H5", "◇ Blend")[index], color = pair.second, style = MaterialTheme.typography.labelMedium) }
        }
        if (visible.isEmpty()) Text("No timestamped observations available to plot.")
        else {
            val grid = MaterialTheme.colorScheme.outlineVariant
            Canvas(Modifier.fillMaxWidth().height(180.dp).semantics {
                contentDescription = "$symbol score history, ${visible.size} recorded observations. Individual points only. Exact data follows below."
            }) {
                val inset = 8.dp.toPx()
                val w = size.width - inset * 2
                val h = size.height - inset * 2
                listOf(0f, .5f, 1f).forEach { level -> drawLine(grid, Offset(inset, inset + h * level), Offset(size.width - inset, inset + h * level)) }
                val minTime = visible.first().timestamp.toEpochMilli()
                val timeSpan = (visible.last().timestamp.toEpochMilli() - minTime).coerceAtLeast(1)
                visible.forEach { point ->
                    val x = if (visible.size == 1) size.width / 2 else inset + w * ((point.timestamp.toEpochMilli() - minTime).toDouble() / timeSpan).toFloat()
                    fields.forEachIndexed { index, (field, color) -> point.scores.numberOrNull(field)?.let { value ->
                        val y = inset + h * (1 - (value / 100).toFloat().coerceIn(0f, 1f))
                        val r = 4.dp.toPx()
                        when (index) {
                            0 -> drawCircle(color, r, Offset(x, y))
                            1 -> drawRect(color, Offset(x - r, y - r), Size(r * 2, r * 2))
                            else -> { val p = Path().apply {
                                moveTo(x, y - r); lineTo(x + r, y + if (index == 2) r else 0f)
                                if (index == 3) lineTo(x, y + r)
                                lineTo(x - r, y + if (index == 2) r else 0f); close()
                            }; if (index == 3) drawPath(p, color, style = Stroke(2.dp.toPx())) else drawPath(p, color) }
                        }
                    } }
                }
            }
            Text("${displayTime(visible.first().timestamp.toString())} — ${displayTime(visible.last().timestamp.toString())}", style = MaterialTheme.typography.bodySmall)
        }
        Text("Points show only persisted observations. Missing values and times between points are gaps; no interpolation. Windows end at the latest loaded observation.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        ExpandableSection("Exact history data") {
            if (visible.size > 50) Text("Showing the latest 50 of ${visible.size} plotted observations.")
            visible.takeLast(50).reversed().forEach { point ->
                AuditText(point.row.raw("timestamp"), "C ${point.scores.raw("c")} · H1 ${point.scores.raw("h1")} · H5 ${point.scores.raw("h5")} · Blend ${point.scores.raw("blend")}")
            }
            val unplottable = rows.count { it.symbol() == symbol && parseObservationTime(it.optString("timestamp")) == null }
            if (unplottable > 0) Text("$unplottable observations have no parseable timestamp. They remain in the timeline.")
        }
    }
}
