package dev.chrisdudley.markethealth

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import org.json.JSONArray
import org.json.JSONObject

@Composable internal fun HoldingEditor(initial: JSONObject, accounts: JSONArray, busy: Boolean,
    onClose: () -> Unit, onSave: (JSONObject) -> Unit, operationError: String?) {
    var symbol by remember { mutableStateOf(initial.optString("symbol")) }
    var account by remember { mutableStateOf(initial.optString("account", "Other")) }
    var shares by remember { mutableStateOf(initial.optString("shares", "")) }
    var cost by remember { mutableStateOf(if (initial.isNull("cost_basis")) "" else initial.optString("cost_basis")) }
    var notes by remember { mutableStateOf(initial.optString("notes")) }
    var error by remember { mutableStateOf<String?>(null) }
    AlertDialog(onDismissRequest = { if (!busy) onClose() }, title = { Text(if (initial.has("account")) "Edit holding" else "Add holding") }, text = {
        Column(Modifier.verticalScroll(rememberScrollState()).imePadding(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Manual portfolio · stored on this device", style = MaterialTheme.typography.bodySmall)
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                accounts.strings().forEach { label -> FilterChip(selected = account == label, onClick = { account = label }, label = { Text(label) }) }
            }
            OutlinedTextField(symbol, { symbol = it.uppercase() }, label = { Text("Symbol") }, singleLine = true, enabled = !busy, modifier = Modifier.testTag("holding-symbol"))
            OutlinedTextField(account, { account = it }, label = { Text("Account label") }, singleLine = true, enabled = !busy)
            OutlinedTextField(shares, { shares = it }, label = { Text("Shares") }, singleLine = true, enabled = !busy,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = Modifier.testTag("holding-shares"))
            OutlinedTextField(cost, { cost = it }, label = { Text("Cost basis / share (optional)") }, singleLine = true, enabled = !busy,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal))
            OutlinedTextField(notes, { notes = it }, label = { Text("Notes (optional)") }, enabled = !busy)
            (error ?: operationError)?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        }
    }, confirmButton = { TextButton(enabled = !busy, modifier = Modifier.testTag("save-holding"), onClick = {
        val amount = shares.toDoubleOrNull()
        val basis = cost.toDoubleOrNull()
        if (symbol.isBlank() || account.isBlank()) error = "Enter a symbol and account label."
        else if (amount == null || !amount.isFinite() || amount < 0 || (cost.isNotBlank() && (basis == null || !basis.isFinite() || basis < 0)))
            error = "Enter finite, nonnegative shares and optional cost basis."
        else {
            error = null
            val value = JSONObject().put("symbol", symbol).put("account", account).put("shares", amount)
                .put("cost_basis", basis ?: JSONObject.NULL).put("notes", notes)
            if (initial.has("account")) value.put("original", JSONArray().put(initial.getString("symbol")).put(initial.getString("account")))
            onSave(value)
        }
    }) { Text(if (busy) "Saving…" else "Save holding") } }, dismissButton = { TextButton(onClick = onClose, enabled = !busy) { Text("Cancel") } })
}

@Composable internal fun SettingsScreen(settings: JSONObject, theme: ThemeMode, onTheme: (ThemeMode) -> Unit,
    notificationsAllowed: Boolean, busy: Boolean, requestNotifications: () -> Unit, onSave: (JSONObject) -> Unit) {
    var net by remember(settings.toString()) { mutableStateOf(if (settings.isNull("net_liq")) "" else settings.optString("net_liq")) }
    var cash by remember(settings.toString()) { mutableStateOf(if (settings.isNull("cash")) "" else settings.optString("cash")) }
    var target by remember(settings.toString()) { mutableStateOf(settings.optString("target_positions", "8")) }
    var interval by remember(settings.toString()) { mutableIntStateOf(settings.optInt("interval", 15)) }
    val toggles = remember(settings.toString()) { mutableStateMapOf<String, Boolean>().apply {
        listOf("background", "notify_sell", "notify_watch", "notify_hold", "notify_rescue", "notify_buy").forEach { put(it, settings.optBoolean(it)) }
    } }
    var error by remember { mutableStateOf<String?>(null) }
    LazyColumn(Modifier.testTag("settings-list"), verticalArrangement = Arrangement.spacedBy(16.dp), contentPadding = screenPadding) {
        item { SectionHeading("Make it yours", "Appearance, monitoring and manual portfolio inputs") }
        item { SectionCard {
            SectionHeading("Appearance")
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                ThemeMode.entries.forEach { value -> FilterChip(selected = theme == value, onClick = { onTheme(value) }, label = { Text(value.label) }, modifier = Modifier.testTag("theme-${value.name}")) }
            }
        } }
        item { SectionCard {
            SectionHeading("Background monitoring")
            SettingSwitch("Enable background monitoring", toggles["background"] == true) { toggles["background"] = it }
            Text("Refresh cadence · approximate", style = MaterialTheme.typography.labelLarge)
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(15, 30, 60).forEach { minutes -> FilterChip(selected = interval == minutes, onClick = { interval = minutes }, label = { Text("${minutes} min") }) }
            }
            Text("Android may defer work for battery or network conditions. Monitoring does not require an open app or a foreground service.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        } }
        item { SectionCard {
            SectionHeading("Notifications")
            InformationPanel(if (notificationsAllowed) "Android notifications allowed" else "Android notifications disabled",
                "Permission and channel settings control delivery. Unchanged policy states never produce duplicate notifications.", warning = !notificationsAllowed)
            if (!notificationsAllowed) TextButton(onClick = requestNotifications) { Text("Request notification permission") }
            mapOf("notify_sell" to "Notify on SELL", "notify_watch" to "Notify on WATCH", "notify_hold" to "Notify on HOLD recovery",
                "notify_rescue" to "Notify on rescue", "notify_buy" to "Notify on new BUY candidates").forEach { (key, label) ->
                SettingSwitch(label, toggles[key] == true) { toggles[key] = it }
            }
        } }
        item { SectionCard {
            SectionHeading("Manual sizing inputs", "Used by the shared engine. No account connection.")
            OutlinedTextField(net, { net = it }, label = { Text("Net Liquidation Value (manual)") }, singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = Modifier.fillMaxWidth())
            OutlinedTextField(cash, { cash = it }, label = { Text("Cash (optional)") }, singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = Modifier.fillMaxWidth())
            OutlinedTextField(target, { target = it }, label = { Text("Target positions") }, singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = Modifier.fillMaxWidth())
        } }
        error?.let { message -> item { InformationPanel("Check settings", message, error = true) } }
        item { Button(enabled = !busy && settings.length() > 0, onClick = {
            val n = net.toDoubleOrNull(); val c = cash.toDoubleOrNull(); val t = target.toIntOrNull()
            if ((net.isNotBlank() && (n == null || !n.isFinite() || n < 0)) || (cash.isNotBlank() && (c == null || !c.isFinite() || c < 0)) || t == null || t < 1)
                error = "Check Net Liq, cash and target positions."
            else {
                error = null
                val value = JSONObject().put("net_liq", n ?: JSONObject.NULL).put("cash", c ?: JSONObject.NULL).put("target_positions", t).put("interval", interval)
                toggles.forEach { (key, enabled) -> value.put(key, enabled) }
                onSave(value)
            }
        }, modifier = Modifier.fillMaxWidth().testTag("save-settings")) { Text(if (busy) "Saving…" else "Save settings") } }
        item { SectionCard {
            SectionHeading("Data & application")
            ValuePair("Source", "Yahoo Finance chart HTTPS · Python Market Health engine")
            ValuePair("Application", "Market Health ${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})")
            ValuePair("State", "Local SQLite · manual holdings and accounts")
            Text("Quotes and saved results may be delayed. Inspect timestamps and data warnings before relying on a result.", style = MaterialTheme.typography.bodySmall)
        } }
    }
}

@Composable private fun SettingSwitch(label: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).toggleable(checked, role = Role.Switch, onValueChange = onChange),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(label, Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
        Switch(checked = checked, onCheckedChange = null)
    }
}
