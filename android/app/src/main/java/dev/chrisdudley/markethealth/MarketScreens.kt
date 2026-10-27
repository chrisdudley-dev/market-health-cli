package dev.chrisdudley.markethealth

import androidx.compose.foundation.background
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import org.json.JSONObject

internal val screenPadding = PaddingValues(top = 8.dp, bottom = 100.dp)

@Composable internal fun DashboardScreen(data: JSONObject, onMarkets: () -> Unit, onPortfolio: () -> Unit,
    onSelect: (JSONObject) -> Unit, onRefresh: () -> Unit) {
    val rows = remember(data) { allSymbolRows(data) }
    val owned = remember(data) { ownedSymbols(data) }
    val counts = remember(data) { rows.groupingBy { it.policyAction() }.eachCount().toSortedMap() }
    val metadata = data.obj("ui_metadata")
    val settings = data.obj("settings")
    LazyColumn(Modifier.testTag("dashboard-list"), verticalArrangement = Arrangement.spacedBy(16.dp), contentPadding = screenPadding) {
        item { Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("Your market, at a glance", style = MaterialTheme.typography.headlineMedium)
            Text("Market Health overview", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        } }
        item { Surface(shape = MarketSpace.card, color = MaterialTheme.colorScheme.primaryContainer) {
            Column(Modifier.fillMaxWidth().padding(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                Text("LATEST SAVED SCAN", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onPrimaryContainer)
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(24.dp)) {
                    Column(Modifier.weight(1f)) {
                        Text(rows.size.toString(), style = MaterialTheme.typography.displaySmall, color = MaterialTheme.colorScheme.onPrimaryContainer)
                        Text("symbols with results", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onPrimaryContainer)
                    }
                    Column(Modifier.weight(1f)) {
                        Text(owned.size.toString(), style = MaterialTheme.typography.displaySmall, color = MaterialTheme.colorScheme.onPrimaryContainer)
                        Text("owned symbols", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onPrimaryContainer)
                    }
                }
                val successful = metadata.optJSONObject("last_successful_refresh")
                Text("Last successful refresh\n" + (successful?.optString("timestamp")?.let(::displayTime) ?: "No successful refresh recorded"),
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onPrimaryContainer)
                TextButton(onClick = onMarkets) { Text("Explore Market Health"); MarketGlyph(MarketIcon.CHEVRON) }
            }
        } }
        if (rows.isEmpty()) item { EmptyPanel("Start with a refresh", "Load the current universe to see scores and deterministic policy decisions.",
            MarketIcon.MARKETS, action = "Refresh market data", onAction = onRefresh) }
        else {
            item { SectionHeading("Policy overview", "Counts from saved results · all symbols") }
            item { SectionCard { counts.forEach { (action, count) ->
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        PolicyChip(action, Modifier.weight(1f)); Text(count.toString(), Modifier.padding(start = 16.dp), style = MaterialTheme.typography.titleMedium)
                    }
                    Box(Modifier.fillMaxWidth().height(4.dp).background(MaterialTheme.colorScheme.surfaceVariant, MarketSpace.card)) {
                        Box(Modifier.fillMaxWidth(count.toFloat() / rows.size).fillMaxHeight().background(MaterialTheme.colorScheme.primary, MarketSpace.card))
                    }
                }
            } } }
        }
        item { SectionHeading("Your portfolio") }
        item { SectionCard {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(24.dp)) {
                ValuePair("BUY candidates", rows.count { buyCandidate(it, owned) }.toString(), Modifier.weight(1f))
                ValuePair("Manual Net Liq", displayNumber(settings.numberOrNull("net_liq")), Modifier.weight(1f))
            }
            val ownedRows = rows.filter { it.symbol() in owned }
            Text(if (ownedRows.isEmpty()) "Add your manual holdings to follow owned-position policy."
                else ownedRows.groupingBy { it.policyAction() }.eachCount().entries.joinToString(" · ") { "${it.value} ${it.key}" },
                style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            TextButton(onClick = onPortfolio) { Text("View portfolio"); MarketGlyph(MarketIcon.CHEVRON) }
        } }
        item { val enabled = settings.optBoolean("background")
            InformationPanel(if (enabled) "Background monitoring enabled" else "Monitoring is off",
                if (enabled) "About every ${settings.optInt("interval", 15)} minutes. Android may defer work for battery or network conditions."
                else "Enable monitoring in Settings to refresh when the app is closed.") }
        val recent = metadata.array("recent_transitions").objects()
        if (recent.isNotEmpty()) {
            item { SectionHeading("Recent recorded changes", "Latest three policy transitions · no inferred causes") }
            items(recent, key = { "recent-${it.raw("id")}" }) { TimelineCard(it, onSelect) }
        }
    }
}

@Composable internal fun SymbolsScreen(page: String, data: JSONObject, onSelect: (JSONObject) -> Unit) {
    var query by rememberSaveable(page) { mutableStateOf("") }
    var filter by rememberSaveable(page) { mutableStateOf(SymbolFilter.ALL) }
    var sort by rememberSaveable(page) { mutableStateOf(SymbolSort.SYMBOL) }
    var sortMenu by remember { mutableStateOf(false) }
    val rows = remember(data, page, query, filter, sort) { visibleSymbols(data, page, query, filter, sort) }
    val owned = remember(data) { ownedSymbols(data) }
    LazyColumn(Modifier.fillMaxSize().testTag("symbols-list"), verticalArrangement = Arrangement.spacedBy(12.dp), contentPadding = screenPadding) {
        item { SectionHeading(if (page == "Market Health") "Market Health universe" else page,
            when (page) { "Trading List" -> "Your owned symbols and their current policy."
                "Buy Candidates" -> "Unowned symbols passing all authoritative BUY gates."
                else -> "Saved scores and deterministic policy for each symbol." }) }
        item { OutlinedTextField(query, { query = it }, singleLine = true, label = { Text("Search symbol") },
            leadingIcon = { MarketGlyph(MarketIcon.SEARCH) }, modifier = Modifier.fillMaxWidth().testTag("symbol-search")) }
        item { Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            SymbolFilter.entries.forEach { value -> FilterChip(selected = filter == value, onClick = { filter = value }, label = { Text(value.label) },
                modifier = Modifier.testTag("filter-${value.name}")) }
        } }
        item { FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("${rows.size} symbols", style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(vertical = 12.dp))
            Box { TextButton(onClick = { sortMenu = true }, modifier = Modifier.testTag("sort-menu")) {
                MarketGlyph(MarketIcon.FILTER); Spacer(Modifier.width(6.dp)); Text("Sort: ${sort.label}")
            }
                DropdownMenu(expanded = sortMenu, onDismissRequest = { sortMenu = false }) {
                    SymbolSort.entries.forEach { value -> DropdownMenuItem(text = { Text(value.label) }, onClick = { sort = value; sortMenu = false }, modifier = Modifier.testTag("sort-${value.name}")) }
                }
            }
        } }
        if (rows.isEmpty()) item { EmptyPanel(if (page == "Buy Candidates" && query.isBlank() && filter == SymbolFilter.ALL) "No buy candidates" else "No matching symbols",
            if (page == "Buy Candidates") "No unowned saved result meets all BUY gates in this view. Requirements remain unchanged."
            else "Try another search or filter, add a holding, or refresh to load results.", MarketIcon.SEARCH) }
        items(rows, key = { it.symbol() }) { row -> SymbolCard(row, row.symbol() in owned, onSelect) }
    }
}

@Composable internal fun SymbolCard(row: JSONObject, owned: Boolean, onSelect: (JSONObject) -> Unit) {
    SectionCard(Modifier.testTag("symbol-${row.symbol()}").clickable(onClickLabel = "Open ${row.symbol()} details") { onSelect(row) }) {
        SymbolIdentity(row.symbol(), if (owned) "Owned" else "Not owned", row.policyAction())
        ScoreStrip(row.obj("scores"))
        HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
        PriceSummary(listOf("State" to row.obj("scores").raw("state").ifBlank { "Not recorded" },
            "Stop" to displayNumber(row.obj("scores").numberOrNull("stop")), "Buy" to displayNumber(row.obj("scores").numberOrNull("buy"))))
        val error = row.obj("scores").optString("error")
        if (error.isNotBlank() && error != "null") InformationPanel("Data issue", error, error = true)
        else Text(row.obj("result").optString("human_explanation", "Policy explanation unavailable."),
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text("Observed ${displayTime(row.optString("timestamp"))}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable internal fun PortfolioScreen(data: JSONObject, onSelect: (JSONObject) -> Unit, onEdit: (JSONObject) -> Unit,
    onRemove: (JSONObject) -> Unit, onAdd: () -> Unit) {
    val holdings = remember(data) { data.array("holdings").objects() }
    val rows = remember(data) { allSymbolRows(data).associateBy { it.symbol() } }
    LazyColumn(Modifier.testTag("portfolio-list"), verticalArrangement = Arrangement.spacedBy(16.dp), contentPadding = screenPadding) {
        item { SectionHeading("Your manual holdings", "${holdings.size} account positions · ${ownedSymbols(data).size} symbols")
            Button(onClick = onAdd, modifier = Modifier.padding(top = 12.dp).testTag("add-holding")) { MarketGlyph(MarketIcon.PLUS); Spacer(Modifier.width(8.dp)); Text("Add holding") } }
        if (holdings.isEmpty()) item { EmptyPanel("Your portfolio starts here", "Add shares and an account label to track owned-position policy locally.",
            MarketIcon.PORTFOLIO, action = "Add your first holding", onAction = onAdd) }
        items(holdings, key = { "${it.symbol()}/${it.raw("account")}" }) { holding -> SectionCard {
            SymbolIdentity(holding.symbol(), holding.raw("account"), rows[holding.symbol()]?.policyAction() ?: "PENDING REFRESH")
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                ValuePair("Shares", holding.raw("shares"), Modifier.weight(1f))
                ValuePair("Cost / share", displayNumber(holding.numberOrNull("cost_basis")), Modifier.weight(1f))
            }
            rows[holding.symbol()]?.let { row ->
                ScoreStrip(row.obj("scores"))
                if (row.obj("result").optBoolean("rescue_active")) InformationPanel("Rescue active", row.obj("result").raw("human_explanation"), warning = true)
                Text("Last refresh ${displayTime(row.optString("timestamp"))}", style = MaterialTheme.typography.bodySmall)
                TextButton(onClick = { onSelect(row) }) { Text("View symbol details"); MarketGlyph(MarketIcon.CHEVRON) }
            } ?: InformationPanel("Awaiting result", "Refresh to load this symbol’s Market Health result.")
            if (holding.optString("notes").isNotBlank()) Text(holding.optString("notes"), style = MaterialTheme.typography.bodySmall)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { onEdit(holding) }, modifier = Modifier.weight(1f).testTag("edit-${holding.symbol()}")) { MarketGlyph(MarketIcon.EDIT); Spacer(Modifier.width(6.dp)); Text("Edit") }
                TextButton(onClick = { onRemove(holding) }, modifier = Modifier.weight(1f).testTag("remove-${holding.symbol()}")) { MarketGlyph(MarketIcon.REMOVE); Spacer(Modifier.width(6.dp)); Text("Remove", color = MaterialTheme.colorScheme.error) }
            }
        } }
    }
}

@Composable internal fun SymbolDetailScreen(row: JSONObject, historical: Boolean, owned: Set<String>, onOwned: () -> Unit, onHistory: () -> Unit) {
    val result = row.obj("result")
    val scores = row.obj("scores")
    LazyColumn(Modifier.testTag("symbol-detail"), verticalArrangement = Arrangement.spacedBy(16.dp), contentPadding = screenPadding) {
        item { SectionHeading(if (historical) "Recorded decision" else "Current saved result",
            "${if (historical) if (row.optBoolean("owned")) "Owned at observation" else "Unowned at observation" else if (row.symbol() in owned) "Owned" else "Not owned"} · ${displayTime(row.optString("timestamp"))}") }
        item { SectionCard {
            PolicyChip(if (historical) row.optString("action") else row.policyAction())
            ScoreStrip(scores)
            Text(result.raw("human_explanation"), style = MaterialTheme.typography.bodyLarge)
        } }
        item { SectionCard {
            SectionHeading("Price levels")
            PriceSummary(listOf("Price" to displayNumber(scores.numberOrNull("price")),
                "Stop" to displayNumber(scores.numberOrNull("stop")), "Buy" to displayNumber(scores.numberOrNull("buy"))))
            ValuePair("State", scores.raw("state").ifBlank { "Not recorded" })
            ValuePair("Price observation", scores.raw("asof"))
            if (scores.optString("error").let { it.isNotBlank() && it != "null" }) InformationPanel("Data issue", scores.raw("error"), error = true)
        } }
        item { SectionCard {
            SectionHeading("Policy explanation", "Exact rule checks from the shared engine")
            result.array("checks").objects().forEach { check ->
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    MarketGlyph(if (check.optBoolean("passed")) MarketIcon.CHECK else MarketIcon.CLOSE)
                    Column(Modifier.weight(1f)) {
                        Text("${if (check.optBoolean("passed")) "TRUE" else "FALSE"} · ${check.raw("rule")}", style = MaterialTheme.typography.bodyMedium)
                        Text(check.raw("actual"), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
            AuditText("Reason codes", result.array("reason_codes").strings().joinToString("\n").ifBlank { "None recorded" })
        } }
        item { SectionCard {
            SectionHeading("Rescue & position sizing")
            ValuePair("Rescue", if (result.optBoolean("rescue_active")) "Active · ${result.raw("rescue_count")}" else "Inactive · count ${result.raw("rescue_count")}")
            ValuePair("Can add", result.raw("can_add"))
            val sizing = row.obj("sizing")
            Text(sizing.optString("explanation", if (historical) "Sizing is not stored with this historical decision." else "Enter manual Net Liq in Settings. A current price or Buy value is required."), style = MaterialTheme.typography.bodyMedium)
            if (sizing.length() > 0) {
                ValuePair("Suggested shares", sizing.raw("shares"))
                ValuePair("Position slot", sizing.raw("slot"))
                ValuePair("Sizing price", sizing.raw("price"))
            }
        } }
        item { if (!historical) OutlinedButton(onClick = onHistory, modifier = Modifier.fillMaxWidth()) { MarketGlyph(MarketIcon.HISTORY); Spacer(Modifier.width(8.dp)); Text("View score history") } }
        item { ExpandableSection("Technical audit · GlyphSpec") {
            for (field in listOf("c", "h1", "h5", "blend", "state", "stop", "buy")) AuditText(field, scores.raw(field))
            AuditText("GlyphSpec", scores.raw("glyph"))
            AuditText("Decision timestamp", row.raw("timestamp"))
            AuditText("Previous action", row.raw("previous_action"))
            AuditText("Policy version", row.raw("policy_version"))
            AuditText("Decision / scan", "${row.raw("id")} / ${row.raw("scan_id")}")
            AuditText("Data quality", scores.raw("error"))
        } }
        if (!historical) item { Button(onClick = onOwned, modifier = Modifier.fillMaxWidth()) { Text("Add manual holding") } }
    }
}

@Composable internal fun PolicyScreen(policy: String) {
    val paragraphs = remember(policy) { policy.split("\n\n").filter { it.isNotBlank() } }
    LazyColumn(Modifier.testTag("policy-list"), verticalArrangement = Arrangement.spacedBy(16.dp), contentPadding = screenPadding) {
        item { SectionHeading("Understand your policy", "Deterministic rules from the shared Python engine") }
        if (paragraphs.isEmpty()) item { EmptyPanel("Policy unavailable", "The application is still loading its authoritative policy description.", MarketIcon.POLICY) }
        items(paragraphs) { paragraph -> SectionCard { Text(paragraph, style = MaterialTheme.typography.bodyMedium) } }
        item { InformationPanel("Owned-position notifications", "When enabled, notifications follow recorded policy transitions. Unchanged states do not produce duplicate notifications. Delivery also depends on Android permission and channel settings.") }
    }
}
