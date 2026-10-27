package dev.chrisdudley.markethealth

import android.Manifest
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.repeatOnLifecycle
import androidx.work.WorkManager
import kotlinx.coroutines.delay
import java.time.Instant

class MainActivity : ComponentActivity() {
    private val model: MarketViewModel by viewModels()
    private val notificationPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { model.reload() }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!RuntimeCompatibility.supported()) {
            setContent { MarketHealthTheme { Surface { Column(Modifier.fillMaxSize().padding(24.dp)) {
                Text("Market Health · compatibility", style = MaterialTheme.typography.headlineSmall)
                Text("This build supports 4 KB or 16 KB memory pages. This device uses a different page size. No scores or policy decisions have been calculated.")
            } } } }
            return
        }
        // Observe persisted work while visible. This does not schedule or execute work.
        setContent { MarketHealth(model) {
            if (Build.VERSION.SDK_INT >= 33 && !NotificationPublisher.permitted(this))
                notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        } }
    }
    override fun onResume() {
        super.onResume()
        if (RuntimeCompatibility.supported()) model.reconcile()
    }
}

@Composable fun MarketHealth(model: MarketViewModel, requestNotifications: () -> Unit) {
    val state by model.state.collectAsStateWithLifecycle()
    val history by model.history.collectAsStateWithLifecycle()
    val historyQuery by model.historyQuery.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val appearance = remember { ThemePreferences(context) }
    val theme by appearance.mode.collectAsStateWithLifecycle()
    val lifecycle = androidx.lifecycle.compose.LocalLifecycleOwner.current.lifecycle
    var now by remember { mutableStateOf(Instant.now()) }
    LaunchedEffect(model, lifecycle) {
        lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            WorkManager.getInstance(context).getWorkInfosForUniqueWorkFlow(MonitorScheduler.NAME)
                .collect { model.reconcile() }
        }
    }
    LaunchedEffect(lifecycle) {
        lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            while (true) { now = Instant.now(); delay(60_000) }
        }
    }
    MarketHealthTheme(theme) {
        MarketAppContent(state, history, now, theme, appearance::select,
            NotificationPublisher.permitted(context), rememberNetworkAvailable(),
            UiActions(model::refresh, model::history, model::editHolding, model::removeHolding,
                { payload, done ->
                    model.saveSettings(payload, done)
                    if (payload.optBoolean("background") || payload.optBoolean("notify_buy")) requestNotifications()
                }, requestNotifications), historyQuery)
    }
}
