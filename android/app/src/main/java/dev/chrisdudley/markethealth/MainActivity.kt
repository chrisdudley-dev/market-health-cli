package dev.chrisdudley.markethealth

import android.Manifest
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject

class MainActivity : ComponentActivity() {
    private val model: MarketViewModel by viewModels()
    private val notificationPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { model.reload() }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!RuntimeCompatibility.supported()) {
            setContent { MaterialTheme(colorScheme = colors) {
                Column(Modifier.fillMaxSize().background(bg).padding(24.dp)) {
                    Text("Market Health · compatibility", style = MaterialTheme.typography.headlineSmall)
                    Text("This build supports devices using 4 KB or 16 KB memory pages. This device uses a different page size. No scores or policy decisions have been calculated.")
                }
            } }
            return
        }
        setContent { MarketHealth(model) {
            if (Build.VERSION.SDK_INT >= 33 && !NotificationPublisher.permitted(this))
                notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        } }
    }
}

private val destinations = listOf("Dashboard", "Portfolio", "Trading List", "Buy Candidates", "Market Health", "History", "Policy", "Settings")
private val bg = Color(0xFF101723)
private val colors = darkColorScheme(primary = Color(0xFF62E2BC), background = bg, surface = Color(0xFF192638))
private fun JSONArray.objects() = (0 until length()).map { getJSONObject(it) }
private fun JSONObject.array(name: String) = optJSONArray(name) ?: JSONArray()
private fun JSONObject.obj(name: String) = optJSONObject(name) ?: JSONObject()
private fun JSONObject.label(name: String): String = if (isNull(name) || !has(name)) "—" else optString(name)
private fun actionColor(action: String) = when (action) {
    "BUY" -> Color(0xFF62E2BC); "SELL", "DATA ERROR" -> Color(0xFFFF7F91)
    "WATCH" -> Color(0xFFF1C36A); "HOLD — RESCUE" -> Color(0xFFC7A0FF)
    else -> Color(0xFF91C3FA)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun MarketHealth(model: MarketViewModel, requestNotifications: () -> Unit) {
    val state by model.state.collectAsStateWithLifecycle()
    var page by rememberSaveable { mutableStateOf("Dashboard") }
    var selected by remember { mutableStateOf<JSONObject?>(null) }
    var editing by remember { mutableStateOf<JSONObject?>(null) }
    val drawer = rememberDrawerState(DrawerValue.Closed)
    val scope = rememberCoroutineScope()
    MaterialTheme(colorScheme = colors) {
        ModalNavigationDrawer(drawerState = drawer, drawerContent = {
            ModalDrawerSheet { Text("MH / Market Health", modifier = Modifier.padding(24.dp), style = MaterialTheme.typography.titleLarge)
                destinations.forEach { name -> NavigationDrawerItem(label = { Text(name) }, selected = page == name,
                    onClick = { page = name; scope.launch { drawer.close() } }, modifier = Modifier.padding(horizontal = 12.dp)) }
            }
        }) {
            Scaffold(topBar = {
                TopAppBar(title = { Text(page) }, navigationIcon = { TextButton(onClick = { scope.launch { drawer.open() } }) { Text("Menu") } },
                    actions = { TextButton(onClick = { model.refresh() }, enabled = !state.busy) { Text("Refresh") } })
            }, floatingActionButton = {
                if (page in listOf("Portfolio", "Market Health", "Buy Candidates")) FloatingActionButton(onClick = { editing = JSONObject() }) { Text("+ Owned", Modifier.padding(8.dp)) }
            }) { padding ->
                Column(Modifier.fillMaxSize().background(bg).padding(padding).padding(horizontal = 16.dp)) {
                    Status(state)
                    if (state.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
                    state.error?.let { Text(it, color = colors.error, modifier = Modifier.padding(vertical = 8.dp)) }
                    when (page) {
                        "Dashboard" -> Dashboard(state.data)
                        "Portfolio" -> Portfolio(state.data, onEdit = { editing = it }, onRemove = { model.removeHolding(it) })
                        "Trading List", "Buy Candidates", "Market Health" -> ScoresPage(page, state.data) { selected = it }
                        "History" -> History(model) { selected = it }
                        "Policy" -> Text(state.data.optString("policy", "Loading policy…"), modifier = Modifier.verticalScroll(rememberScrollState()).padding(vertical = 12.dp))
                        "Settings" -> Settings(state.data.obj("settings")) { values ->
                            model.saveSettings(values)
                            if (values.optBoolean("background") || values.optBoolean("notify_buy")) requestNotifications()
                        }
                    }
                }
            }
        }
        selected?.let { Detail(it, onOwned = { editing = JSONObject().put("symbol", it.getString("symbol")); selected = null }, onClose = { selected = null }) }
        editing?.let { HoldingEditor(it, state.data.array("accounts"), onClose = { editing = null }) { value -> model.editHolding(value); editing = null } }
    }
}

@Composable private fun Status(state: UiState) {
    val status = state.data.obj("status")
    var now by remember { mutableStateOf(java.time.Instant.now()) }
    LaunchedEffect(Unit) { while (true) { kotlinx.coroutines.delay(60_000); now = java.time.Instant.now() } }
    val old = runCatching { java.time.Duration.between(java.time.Instant.parse(status.getString("timestamp")), now).seconds > state.data.obj("settings").optInt("interval", 15) * 60 }.getOrDefault(false)
    val label = if (status.length() == 0) "No refresh yet" else status.label("status").uppercase() + " · " + status.label("timestamp")
    Text(if (old || status.optString("status") in listOf("error", "partial")) "STALE · $label" else label,
        style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(vertical = 8.dp))
}

@Composable private fun Dashboard(data: JSONObject) {
    val holdings = data.array("holdings").objects()
    val owned = holdings.map { it.getString("symbol") }.toSet()
    val rows = data.array("rows").objects()
    LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { Text("Market scores. Clear decisions.", style = MaterialTheme.typography.headlineSmall) }
        item { Metric("Owned positions", owned.size.toString()) }
        item { Metric("BUY candidates", rows.count { it.getString("symbol") !in owned && it.obj("result").optBoolean("buy_qualified") }.toString()) }
        items(listOf("HOLD", "WATCH", "SELL", "HOLD — RESCUE")) { action ->
            Metric(action, rows.count { it.getString("symbol") in owned && it.optString("current_action") == action }.toString())
        }
        item { Metric("Net Liq (manual)", data.obj("settings").label("net_liq")) }
        item { Metric("Cash (manual)", data.obj("settings").label("cash")) }
        item { Spacer(Modifier.height(24.dp)) }
    }
}
@Composable private fun Metric(label: String, value: String) {
    Card(Modifier.fillMaxWidth()) { Row(Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label); Text(value, fontWeight = FontWeight.Bold)
    } }
}

@Composable private fun ScoresPage(page: String, data: JSONObject, onSelect: (JSONObject) -> Unit) {
    var query by remember { mutableStateOf("") }
    val owned = data.array("holdings").objects().map { it.getString("symbol") }.toSet()
    val rows = data.array("rows").objects().filter { r ->
        r.getString("symbol").contains(query, true) && when (page) {
            "Trading List" -> r.getString("symbol") in owned
            "Buy Candidates" -> r.getString("symbol") !in owned && r.obj("result").optBoolean("buy_qualified")
            else -> true
        }
    }.sortedBy { it.getString("symbol") }
    OutlinedTextField(query, { query = it }, label = { Text("Search symbol") }, modifier = Modifier.fillMaxWidth())
    LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp), contentPadding = PaddingValues(vertical = 12.dp)) {
        if (rows.isEmpty()) item { Text("No matching positions or qualifying candidates.") }
        items(rows) { row -> ScoreCard(row, onSelect) }
        item { Spacer(Modifier.height(72.dp)) }
    }
}
@Composable private fun ScoreCard(row: JSONObject, onSelect: (JSONObject) -> Unit) {
    val scores = row.obj("scores")
    val action = row.optString("current_action", row.optString("action"))
    Card(Modifier.fillMaxWidth().clickable { onSelect(row) }) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(row.label("symbol"), style = MaterialTheme.typography.titleLarge)
                Text(action, color = actionColor(action), fontWeight = FontWeight.Bold)
            }
            if (row.has("owned_shares")) Text("Owned shares: ${row.label("owned_shares")}", style = MaterialTheme.typography.bodySmall)
            Text("C ${scores.label("c")}  ·  H1 ${scores.label("h1")}  ·  H5 ${scores.label("h5")}  ·  Blend ${scores.label("blend")}")
            Text("State ${scores.label("state")}  ·  Stop ${scores.label("stop")}  ·  Buy ${scores.label("buy")}", style = MaterialTheme.typography.bodySmall)
            Text(row.obj("result").label("human_explanation"), style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable private fun Portfolio(data: JSONObject, onEdit: (JSONObject) -> Unit, onRemove: (JSONObject) -> Unit) {
    val holdings = data.array("holdings").objects()
    LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp), contentPadding = PaddingValues(vertical = 12.dp)) {
        if (holdings.isEmpty()) item { Text("Tap + Owned to enter a local holding and account label.") }
        items(holdings) { holding -> Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp)) {
                Text(holding.label("symbol"), style = MaterialTheme.typography.titleLarge)
                Text("${holding.label("shares")} shares · ${holding.label("account")}")
                Text("Cost / share: ${holding.label("cost_basis")}")
                Text(holding.optString("notes"))
                Row { TextButton(onClick = { onEdit(holding) }) { Text("Edit") }; TextButton(onClick = { onRemove(holding) }) { Text("Remove") } }
            }
        } }
        item { Spacer(Modifier.height(80.dp)) }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable private fun Detail(row: JSONObject, onOwned: () -> Unit, onClose: () -> Unit) {
    ModalBottomSheet(onDismissRequest = onClose) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("${row.label("symbol")} · ${row.label("action")}", style = MaterialTheme.typography.headlineSmall)
            Text(row.obj("result").label("human_explanation"))
            Text("Decision: ${row.label("timestamp")}\nPrevious: ${row.label("previous_action")}\nPrice data: ${row.obj("scores").label("asof")}")
            row.obj("result").array("checks").objects().forEach { check ->
                Text("${if (check.optBoolean("passed")) "TRUE" else "FALSE"} · ${check.label("rule")}\n${check.label("actual")}")
            }
            Text("Reason codes: ${row.obj("result").array("reason_codes")}")
            Text("Rescue count: ${row.obj("result").label("rescue_count")} · Can add: ${row.obj("result").label("can_add")}")
            Text("Position sizing", fontWeight = FontWeight.Bold)
            Text(row.obj("sizing").optString("explanation", "Enter Net Liq in Settings. A current price or Buy value is needed."))
            Text("GlyphSpec", fontWeight = FontWeight.Bold); Text(row.obj("scores").label("glyph"))
            Button(onClick = onOwned) { Text("Mark Owned manually") }
            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable private fun HoldingEditor(initial: JSONObject, accounts: JSONArray, onClose: () -> Unit, onSave: (JSONObject) -> Unit) {
    var symbol by remember { mutableStateOf(initial.optString("symbol")) }
    var account by remember { mutableStateOf(initial.optString("account", "Other")) }
    var shares by remember { mutableStateOf(initial.optString("shares", "")) }
    var cost by remember { mutableStateOf(if (initial.isNull("cost_basis")) "" else initial.optString("cost_basis")) }
    var notes by remember { mutableStateOf(initial.optString("notes")) }
    var error by remember { mutableStateOf("") }
    AlertDialog(onDismissRequest = onClose, title = { Text("Local holding · Owned") }, text = {
        Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Choose an account below or enter a new local label.", style = MaterialTheme.typography.bodySmall)
            Row(Modifier.horizontalScroll(androidx.compose.foundation.rememberScrollState())) {
                for (i in 0 until accounts.length()) TextButton(onClick = { account = accounts.getString(i) }) { Text(accounts.getString(i)) }
            }
            OutlinedTextField(symbol, { symbol = it.uppercase() }, label = { Text("Symbol") })
            OutlinedTextField(account, { account = it }, label = { Text("Account label") })
            OutlinedTextField(shares, { shares = it }, label = { Text("Shares") })
            OutlinedTextField(cost, { cost = it }, label = { Text("Cost basis / share (optional)") })
            OutlinedTextField(notes, { notes = it }, label = { Text("Notes (optional)") })
            Text(error, color = MaterialTheme.colorScheme.error)
        }
    }, confirmButton = { TextButton(onClick = {
        val amount = shares.toDoubleOrNull()
        val basis = cost.toDoubleOrNull()
        if (amount == null || !amount.isFinite() || amount < 0 || (cost.isNotBlank() && (basis == null || !basis.isFinite() || basis < 0))) error = "Enter finite, nonnegative shares and optional cost basis."
        else {
            val value = JSONObject().put("symbol", symbol).put("account", account).put("shares", amount)
                .put("cost_basis", basis ?: JSONObject.NULL).put("notes", notes)
            if (initial.has("account")) value.put("original", JSONArray().put(initial.getString("symbol")).put(initial.getString("account")))
            onSave(value)
        }
    }) { Text("Save Owned") } }, dismissButton = { TextButton(onClick = onClose) { Text("Cancel") } })
}

@Composable private fun History(model: MarketViewModel, onSelect: (JSONObject) -> Unit) {
    val rows by model.history.collectAsStateWithLifecycle()
    var symbol by remember { mutableStateOf("") }; var action by remember { mutableStateOf("") }
    var account by remember { mutableStateOf("") }; var date by remember { mutableStateOf("") }
    LaunchedEffect(Unit) { model.history() }
    Column {
        Row { OutlinedTextField(symbol, { symbol = it }, label = { Text("Symbol") }, modifier = Modifier.weight(1f)); OutlinedTextField(action, { action = it.uppercase() }, label = { Text("Action") }, modifier = Modifier.weight(1f)) }
        Row { OutlinedTextField(account, { account = it }, label = { Text("Account") }, modifier = Modifier.weight(1f)); OutlinedTextField(date, { date = it }, label = { Text("UTC YYYY-MM-DD") }, modifier = Modifier.weight(1f)) }
        TextButton(onClick = { model.history(JSONObject().put("symbol", symbol).put("action", action).put("account", account).put("date", date)) }) { Text("Filter history") }
        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(rows.objects()) { row -> ScoreCard(row, onSelect) }
            if (rows.length() > 0) item { TextButton(onClick = { model.history(JSONObject().put("symbol", symbol).put("action", action).put("account", account).put("date", date), append = true) }) { Text("Load older decisions") } }
        }
    }
}

@Composable private fun Settings(settings: JSONObject, onSave: (JSONObject) -> Unit) {
    if (settings.length() == 0) return
    var net by remember(settings.toString()) { mutableStateOf(if (settings.isNull("net_liq")) "" else settings.optString("net_liq")) }
    var cash by remember(settings.toString()) { mutableStateOf(if (settings.isNull("cash")) "" else settings.optString("cash")) }
    var target by remember { mutableStateOf(settings.optString("target_positions", "8")) }
    var interval by remember { mutableIntStateOf(settings.optInt("interval", 15)) }
    val toggles = remember(settings.toString()) { mutableStateMapOf<String, Boolean>().apply { listOf("background", "notify_sell", "notify_watch", "notify_hold", "notify_rescue", "notify_buy").forEach { put(it, settings.optBoolean(it)) } } }
    var error by remember { mutableStateOf("") }
    Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedTextField(net, { net = it }, label = { Text("Net Liquidation Value (manual)") })
        OutlinedTextField(cash, { cash = it }, label = { Text("Cash (optional)") })
        OutlinedTextField(target, { target = it }, label = { Text("Target positions") })
        Text("Background interval · approximate")
        Row { listOf(15,30,60).forEach { minutes -> FilterChip(selected = interval == minutes, onClick = { interval = minutes }, label = { Text("${minutes}m") }) } }
        Text("Android may defer work for battery or network conditions. Monitoring does not need an open app or a foreground service.", style = MaterialTheme.typography.bodySmall)
        val labels = mapOf("background" to "Enable background monitoring", "notify_sell" to "Notify on SELL", "notify_watch" to "Notify on WATCH", "notify_hold" to "Notify on HOLD recovery", "notify_rescue" to "Notify on rescue", "notify_buy" to "Notify on new BUY candidates")
        labels.forEach { (key,label) -> Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { Text(label, Modifier.weight(1f)); Switch(toggles[key] == true, { toggles[key] = it }) } }
        val context = androidx.compose.ui.platform.LocalContext.current
        Text(if (NotificationPublisher.permitted(context)) "Android notifications are allowed." else "Android notification permission is needed. Enable monitoring to request it.")
        Text("Unchanged policy states never produce duplicate notifications.")
        Text(error, color = MaterialTheme.colorScheme.error)
        Button(onClick = {
            val n = net.toDoubleOrNull(); val c = cash.toDoubleOrNull(); val t = target.toIntOrNull()
            if ((net.isNotBlank() && (n == null || !n.isFinite() || n < 0)) || (cash.isNotBlank() && (c == null || !c.isFinite() || c < 0)) || t == null || t < 1) error = "Check Net Liq, cash and target positions."
            else {
                val value = JSONObject().put("net_liq", n ?: JSONObject.NULL).put("cash", c ?: JSONObject.NULL).put("target_positions", t).put("interval", interval)
                toggles.forEach { (key,enabled) -> value.put(key,enabled) }
                onSave(value)
            }
        }) { Text("Save settings") }
        Spacer(Modifier.height(32.dp))
    }
}
