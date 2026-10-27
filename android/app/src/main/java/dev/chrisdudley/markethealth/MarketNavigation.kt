package dev.chrisdudley.markethealth

import android.content.Context
import android.net.*
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant

internal data class UiActions(
    val refresh: () -> Unit,
    val history: (JSONObject, Boolean) -> Unit,
    val saveHolding: (JSONObject, () -> Unit) -> Unit,
    val removeHolding: (JSONObject, () -> Unit) -> Unit,
    val saveSettings: (JSONObject, () -> Unit) -> Unit,
    val notifications: () -> Unit
)
internal enum class Destination(val title: String, val icon: MarketIcon, val short: String = title) {
    DASHBOARD("Dashboard", MarketIcon.OVERVIEW), MARKET("Market Health", MarketIcon.MARKETS, "Markets"),
    PORTFOLIO("Portfolio", MarketIcon.PORTFOLIO), HISTORY("History", MarketIcon.HISTORY),
    TRADING("Trading List", MarketIcon.LIST), CANDIDATES("Buy Candidates", MarketIcon.CANDIDATES),
    POLICY("Policy", MarketIcon.POLICY), SETTINGS("Settings", MarketIcon.SETTINGS)
}
private val primaryDestinations = listOf(Destination.DASHBOARD, Destination.MARKET, Destination.PORTFOLIO, Destination.HISTORY)

@Composable internal fun rememberNetworkAvailable(): Boolean {
    val context = LocalContext.current
    var available by remember { mutableStateOf(true) }
    DisposableEffect(context) {
        val manager = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        fun update() { available = manager.getNetworkCapabilities(manager.activeNetwork)
            ?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) == true }
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) = update()
            override fun onLost(network: Network) = update()
            override fun onCapabilitiesChanged(network: Network, capabilities: NetworkCapabilities) = update()
        }
        update()
        manager.registerDefaultNetworkCallback(callback)
        onDispose { manager.unregisterNetworkCallback(callback) }
    }
    return available
}

/** Stateless bridge boundary: tests supply declared UI fixtures, never a production fake-data mode. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable internal fun MarketAppContent(state: UiState, history: JSONArray, now: Instant,
    theme: ThemeMode, onTheme: (ThemeMode) -> Unit, notificationsAllowed: Boolean, networkAvailable: Boolean,
    actions: UiActions, historyQuery: JSONObject = JSONObject()) {
    var destination by rememberSaveable { mutableStateOf(Destination.DASHBOARD) }
    var selectedSymbol by rememberSaveable { mutableStateOf<String?>(null) }
    var historical by remember { mutableStateOf<JSONObject?>(null) }
    var editing by remember { mutableStateOf<JSONObject?>(null) }
    var removing by remember { mutableStateOf<JSONObject?>(null) }
    val drawer = rememberDrawerState(DrawerValue.Closed)
    val scope = rememberCoroutineScope()
    val snackbars = remember { SnackbarHostState() }
    val selected = historical ?: selectedSymbol?.let { symbol -> allSymbolRows(state.data).find { it.symbol() == symbol } }
    fun navigate(value: Destination) { selectedSymbol = null; historical = null; destination = value }
    fun openCurrent(row: JSONObject) { selectedSymbol = row.symbol(); historical = null }
    BackHandler(enabled = selected != null) { selectedSymbol = null; historical = null }
    ModalNavigationDrawer(drawerState = drawer, drawerContent = {
        ModalDrawerSheet(Modifier.widthIn(max = 360.dp).verticalScroll(rememberScrollState())) {
            Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("MARKET HEALTH", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
                Text("A clearer market view", style = MaterialTheme.typography.titleLarge)
            }
            Destination.entries.forEach { page -> NavigationDrawerItem(
                label = { Text(page.title) }, selected = page == destination,
                icon = { MarketGlyph(page.icon) },
                onClick = { navigate(page); scope.launch { drawer.close() } },
                modifier = Modifier.padding(horizontal = 12.dp).testTag("drawer-${page.name}")) }
            Spacer(Modifier.height(24.dp))
        }
    }) {
        BoxWithConstraints(Modifier.fillMaxSize()) {
            val wide = maxWidth >= 700.dp
            Scaffold(snackbarHost = { SnackbarHost(snackbars) }, topBar = {
                TopAppBar(title = { Text(if (selected != null) selected.symbol() else destination.title,
                    style = MaterialTheme.typography.titleLarge, modifier = Modifier.testTag("page-title")) },
                    navigationIcon = { IconButton(onClick = {
                        if (selected != null) { selectedSymbol = null; historical = null }
                        else scope.launch { drawer.open() }
                    }, modifier = Modifier.testTag("open-menu")) {
                        MarketGlyph(if (selected != null) MarketIcon.CLOSE else MarketIcon.MENU,
                            description = if (selected != null) "Close symbol detail" else "Menu")
                    } }, actions = {
                        IconButton(onClick = actions.refresh, enabled = !state.busy, modifier = Modifier.testTag("refresh")) {
                            MarketGlyph(MarketIcon.REFRESH, description = "Refresh market data")
                        }
                    }, colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.background))
            }, bottomBar = {
                if (!wide && selected == null) NavigationBar(containerColor = MaterialTheme.colorScheme.surface) {
                    primaryDestinations.forEach { page -> NavigationBarItem(selected = destination == page,
                        onClick = { navigate(page) }, icon = { MarketGlyph(page.icon) }, label = { Text(page.short) },
                        modifier = Modifier.testTag("nav-${page.name}")) }
                }
            }            ) { insets ->
                Row(Modifier.fillMaxSize().padding(insets)) {
                    if (wide) NavigationRail(containerColor = MaterialTheme.colorScheme.background) {
                        primaryDestinations.forEach { page -> NavigationRailItem(selected = destination == page,
                            onClick = { navigate(page) }, icon = { MarketGlyph(page.icon) }, label = { Text(page.short) },
                            modifier = Modifier.testTag("nav-${page.name}")) }
                    }
                    Column(Modifier.fillMaxSize().widthIn(max = 1100.dp).padding(horizontal = if (wide) 24.dp else 16.dp)) {
                        RefreshStatus(state.data, now, Modifier.padding(bottom = 10.dp))
                        if (state.busy) LinearProgressIndicator(Modifier.fillMaxWidth().testTag("operation-progress"))
                        if (!networkAvailable) InformationPanel("Network unavailable", "Saved results remain visible. Connect to refresh.", warning = true)
                        state.error?.let { InformationPanel("Could not complete the action", it, error = true) }
                        val freshness = refreshPresentation(state.data, now)
                        if (freshness.stale) InformationPanel(if (freshness.error) "Refresh error" else "Saved data needs attention",
                            freshness.detail, warning = true, error = freshness.error, modifier = Modifier.padding(bottom = 8.dp))
                        if (state.data.length() == 0 && state.busy) LoadingPanels()
                        else if (selected != null) SymbolDetailScreen(selected, historical != null, ownedSymbols(state.data),
                            onOwned = { editing = JSONObject().put("symbol", selected.symbol()) },
                            onHistory = { actions.history(JSONObject().put("symbol", selected.symbol()), false); selectedSymbol = null; historical = null; destination = Destination.HISTORY })
                        else PullToRefreshBox(isRefreshing = state.busy, onRefresh = actions.refresh, modifier = Modifier.fillMaxSize().testTag("pull-refresh")) {
                            when (destination) {
                                Destination.DASHBOARD -> DashboardScreen(state.data,
                                    onMarkets = { navigate(Destination.MARKET) }, onPortfolio = { navigate(Destination.PORTFOLIO) },
                                    onSelect = { historical = it }, onRefresh = actions.refresh)
                                Destination.MARKET, Destination.TRADING, Destination.CANDIDATES -> SymbolsScreen(destination.title, state.data, ::openCurrent)
                                Destination.PORTFOLIO -> PortfolioScreen(state.data, ::openCurrent, { editing = it }, { removing = it }, { editing = JSONObject() })
                                Destination.HISTORY -> HistoryScreen(history, historyQuery, actions.history, onSelect = { historical = it })
                                Destination.POLICY -> PolicyScreen(state.data.optString("policy"))
                                Destination.SETTINGS -> SettingsScreen(state.data.obj("settings"), theme, onTheme,
                                    notificationsAllowed, state.busy, actions.notifications) { values -> actions.saveSettings(values) {
                                        scope.launch { snackbars.showSnackbar("Settings saved") }
                                    } }
                            }
                        }
                    }
                }
            }
        }
    }
    editing?.let { initial -> HoldingEditor(initial, state.data.array("accounts"), state.busy,
        onClose = { editing = null }, onSave = { payload -> actions.saveHolding(payload) {
            editing = null; scope.launch { snackbars.showSnackbar("Holding saved") }
        } }, operationError = state.error) }
    removing?.let { holding -> AlertDialog(onDismissRequest = { if (!state.busy) removing = null },
        title = { Text("Remove ${holding.symbol()}?") }, text = { Column {
            Text("Remove ${holding.raw("shares")} shares from ${holding.raw("account")} in your manual portfolio?")
            Text("This does not place an order.", style = MaterialTheme.typography.bodySmall)
            state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        } }, confirmButton = { TextButton(enabled = !state.busy, onClick = { actions.removeHolding(holding) {
            removing = null; scope.launch { snackbars.showSnackbar("Holding removed") }
        } }, modifier = Modifier.testTag("confirm-remove")) { Text("Remove holding", color = MaterialTheme.colorScheme.error) } },
        dismissButton = { TextButton(onClick = { removing = null }, enabled = !state.busy) { Text("Keep holding") } }) }
}
