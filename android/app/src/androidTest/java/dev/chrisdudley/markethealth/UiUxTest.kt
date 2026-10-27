package dev.chrisdudley.markethealth

import android.graphics.Bitmap
import android.os.Handler
import android.os.HandlerThread
import android.view.FrameMetrics
import androidx.compose.foundation.layout.*
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.activity.ComponentActivity
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.time.Instant
import java.util.Collections

/** Declared synthetic presentation fixtures; source scores/reasons stay frozen and exact. */
internal object UiFixtures {
    val timestamp = "2025-08-13T00:00:00Z"
    fun data(): JSONObject {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val expected = JSONArray(instrumentation.context.assets.open("parity-expected.json").bufferedReader().use { it.readText() })
        val rows = JSONArray()
        for (i in 0 until expected.length()) {
            val fixture = expected.getJSONObject(i)
            val scores = JSONObject(fixture.getJSONObject("scores").toString())
            val result = JSONObject(fixture.getJSONObject("decision").toString())
            rows.put(JSONObject().put("id", i + 1).put("scan_id", 1).put("timestamp", timestamp)
                .put("symbol", scores.getString("symbol")).put("scores", scores).put("result", result)
                .put("action", result.getString("action")).put("current_action", result.getString("action"))
                .put("previous_action", "WATCH").put("owned", i == 0).put("policy_version", "fixture"))
        }
        val policy = runBlocking { CoreRepository.get(instrumentation.targetContext).state().getString("policy") }
        val status = JSONObject().put("timestamp", timestamp).put("status", "ok").put("scan_key", "synthetic-ui")
        return JSONObject().put("rows", rows).put("status", status).put("policy", policy)
            .put("holdings", JSONArray().put(JSONObject().put("symbol", rows.getJSONObject(0).symbol()).put("account", "Sample account").put("shares", 3).put("cost_basis", 80)))
            .put("accounts", JSONArray().put("Sample account").put("Other"))
            .put("settings", JSONObject().put("interval", 30).put("background", false).put("net_liq", 25000).put("cash", 5000).put("target_positions", 8))
            .put("ui_metadata", JSONObject().put("last_successful_refresh", status).put("recent_transitions", JSONArray().put(rows.getJSONObject(0))))
    }
    fun history(data: JSONObject, count: Int = 12): JSONArray = JSONArray().apply {
        // Repeated frozen scores at explicitly synthetic timestamps, never live/persisted evidence.
        repeat(count) { i -> put(JSONObject(data.array("rows").getJSONObject(i % data.array("rows").length()).toString())
            .put("id", i + 100).put("timestamp", Instant.parse(timestamp).minusSeconds(i * 86400L).toString())) }
    }
    fun stress(data: JSONObject): JSONObject = JSONObject(data.toString()).put("rows", JSONArray().apply {
        repeat(25) { i -> put(JSONObject(data.array("rows").getJSONObject(i % 3).toString()).put("symbol", "QA${i.toString().padStart(2, '0')}")) }
    })
}

@RunWith(AndroidJUnit4::class)
class UiUxTest {
    @get:Rule val rule = createAndroidComposeRule<ComponentActivity>()
    private var refreshes = 0
    private var loads = 0
    private fun content(data: JSONObject = UiFixtures.data(), history: JSONArray = UiFixtures.history(data),
        mode: ThemeMode = ThemeMode.LIGHT, font: Float? = null, busy: Boolean = false,
        error: String? = null, network: Boolean = true) {
        rule.setContent {
            var appearance by remember { mutableStateOf(mode) }
            MarketHealthTheme(appearance) {
                val density = LocalDensity.current
                CompositionLocalProvider(LocalDensity provides Density(density.density, font ?: density.fontScale)) {
                    MarketAppContent(UiState(data, busy, error), history, Instant.parse(UiFixtures.timestamp), appearance,
                        { appearance = it }, true, network, UiActions({ refreshes++ }, { _, _ -> loads++ }, { _, done -> done() }, { _, done -> done() }, { _, done -> done() }, {}))
                }
            }
        }
    }
    private fun go(page: Destination) {
        rule.onNodeWithTag("open-menu").performClick()
        rule.onNodeWithTag("drawer-${page.name}").performScrollTo().performClick()
        rule.onNodeWithTag("page-title").assertTextEquals(page.title)
    }
    @Test fun allDestinationsAndThemesRender() {
        content()
        Destination.entries.forEach(::go)
        go(Destination.SETTINGS)
        for (mode in listOf("DARK", "LIGHT", "SYSTEM")) rule.onNodeWithTag("theme-$mode").performScrollTo().performClick().assertIsSelected()
    }
    @Test fun scoreValuesAndDetailAuditUseAuthoritativeValues() {
        val data = UiFixtures.data()
        content(data)
        go(Destination.MARKET)
        val symbol = data.array("rows").getJSONObject(0).symbol()
        rule.onNodeWithTag("symbols-list").performScrollToNode(hasTestTag("symbol-$symbol"))
        rule.onNodeWithTag("symbol-$symbol").performClick()
        rule.onNodeWithTag("symbol-detail").assertIsDisplayed()
        val scores = data.array("rows").getJSONObject(0).obj("scores")
        rule.onNodeWithContentDescription("Current (C) score " + displayScore(scores, "c")).assertIsDisplayed()
        rule.onNodeWithTag("symbol-detail").performScrollToNode(hasText("Technical audit · GlyphSpec"))
        rule.onNodeWithText("Technical audit · GlyphSpec").performClick()
        rule.onNodeWithTag("symbol-detail").performScrollToNode(hasText(scores.raw("glyph")))
        rule.onNodeWithText(scores.raw("glyph"), substring = false).assertIsDisplayed()
    }
    @Test fun searchFilterSortAndExistingMembershipArePreserved() {
        val data = UiFixtures.data()
        val source = allSymbolRows(data)
        assertEquals(source.filter { it.symbol() in ownedSymbols(data) }.map { it.symbol() }.sorted(),
            visibleSymbols(data, "Trading List", "", SymbolFilter.ALL, SymbolSort.SYMBOL).map { it.symbol() })
        assertEquals(source.filter { buyCandidate(it, ownedSymbols(data)) }.map { it.symbol() }.sorted(),
            visibleSymbols(data, "Buy Candidates", "", SymbolFilter.ALL, SymbolSort.SYMBOL).map { it.symbol() })
        content(data)
        go(Destination.MARKET)
        rule.onNodeWithTag("symbol-search").performTextInput("XLE")
        rule.onNodeWithTag("symbol-XLE").performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("symbol-search").performTextClearance()
        rule.onNodeWithTag("filter-OWNED").performScrollTo().performClick()
        rule.onNodeWithText("1 symbols").assertIsDisplayed()
        rule.onNodeWithTag("sort-menu").performScrollTo().performClick()
        rule.onNodeWithTag("sort-BLEND").performClick()
        rule.onNodeWithTag("sort-menu").assertTextEquals("Sort: Blend score")
    }
    @Test fun emptyOfflineErrorAndLoadingStatesStayExplicit() {
        content(JSONObject().put("rows", JSONArray()).put("holdings", JSONArray()).put("settings", JSONObject()), history = JSONArray(), error = "Provider unavailable", network = false)
        rule.onNodeWithText("Network unavailable").assertIsDisplayed()
        rule.onNodeWithText("Provider unavailable").assertIsDisplayed()
        go(Destination.PORTFOLIO)
        rule.onNodeWithText("Your portfolio starts here").assertIsDisplayed()
        go(Destination.HISTORY)
        rule.onNodeWithText("No recorded decisions").performScrollTo().assertIsDisplayed()
        go(Destination.CANDIDATES)
        rule.onNodeWithText("No buy candidates").performScrollTo().assertIsDisplayed()
    }
    @Test fun loadingDoesNotInventSavedResults() {
        content(JSONObject(), JSONArray(), busy = true)
        rule.onNodeWithContentDescription("Loading Market Health").assertIsDisplayed()
        rule.onNodeWithTag("refresh").assertIsNotEnabled()
    }
    @Test fun staleStatusAndOneRefreshPath() {
        val data = UiFixtures.data().put("status", JSONObject().put("timestamp", "2025-08-01T00:00:00Z").put("status", "ok"))
        content(data)
        rule.onNodeWithText("Saved results · stale").assertIsDisplayed()
        rule.onNodeWithTag("refresh").performClick()
        assertEquals(1, refreshes)
        rule.onNodeWithTag("pull-refresh").performTouchInput { swipeDown(startY = 5f, endY = height * .8f, durationMillis = 600) }
        rule.waitForIdle()
        assertEquals("pull gesture uses the same supplied refresh action", 2, refreshes)
    }
    @Test fun historyRetainsRecordedTransitionsAndPointOnlyData() {
        val data = UiFixtures.data()
        val history = UiFixtures.history(data)
        content(data, history)
        go(Destination.HISTORY)
        rule.onNodeWithTag("history-chart").performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("history-list").performScrollToNode(hasText("Decision timeline"))
        rule.onNodeWithText("Decision timeline").assertIsDisplayed()
        rule.onNodeWithTag("history-list").performScrollToNode(hasTestTag("history-100"))
        rule.onNodeWithTag("history-100").assertIsDisplayed()
        val row = history.getJSONObject(0)
        rule.onNodeWithText("${row.raw("previous_action")} → ${row.raw("action")}").assertIsDisplayed()
        assertEquals(4, chartPoints(history.objects(), row.symbol()).size)
        assertEquals(0, chartPoints(listOf(JSONObject(row.toString()).put("timestamp", "unknown")), row.symbol()).size)
    }
    @Test fun largeFontKeepsControlsAndDetailReachable() {
        content(font = 2f)
        go(Destination.MARKET)
        rule.onNodeWithTag("symbols-list").performScrollToNode(hasTestTag("symbol-XLE"))
        rule.onNodeWithTag("symbol-XLE").performClick()
        rule.onNodeWithTag("symbol-detail").performScrollToNode(hasText("Technical audit · GlyphSpec"))
        rule.onNodeWithText("Technical audit · GlyphSpec").performClick()
        rule.onNodeWithTag("symbol-detail").performScrollToNode(hasText("GlyphSpec", substring = false))
        rule.onNodeWithText("GlyphSpec", substring = false).assertIsDisplayed()
        rule.onNodeWithContentDescription("Close symbol detail").performClick()
        go(Destination.SETTINGS)
        rule.onNodeWithTag("settings-list").performScrollToNode(hasTestTag("save-settings"))
        rule.onNodeWithTag("save-settings").assertIsDisplayed()
    }
    @Test fun appearancePersistsOutsideAuthoritativeSettings(): Unit = runBlocking {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val repository = CoreRepository.get(context)
        val before = repository.state()
        val preferences = ThemePreferences(context)
        val original = preferences.mode.value
        try {
            preferences.select(ThemeMode.DARK)
            assertEquals(ThemeMode.DARK, ThemePreferences(context).mode.value)
            preferences.select(ThemeMode.LIGHT)
            assertEquals(ThemeMode.LIGHT, ThemePreferences(context).mode.value)
            val after = repository.state()
            for (field in listOf("settings", "rows", "holdings", "status", "notifications"))
                assertEquals(field, before.get(field).toString(), after.get(field).toString())
        } finally { preferences.select(original) }
    }
    @Test fun currentDetailReconcilesWhileHistoricalSelectionRetainsOriginal() {
        val initial = UiFixtures.data()
        val state = mutableStateOf(initial)
        val history = UiFixtures.history(initial)
        val noWrites = UiActions({}, { _, _ -> }, { _, done -> done() }, { _, done -> done() }, { _, done -> done() }, {})
        rule.setContent { MarketHealthTheme(ThemeMode.LIGHT) {
            MarketAppContent(UiState(state.value), history, Instant.parse(UiFixtures.timestamp), ThemeMode.LIGHT, {}, true, true, noWrites)
        } }
        go(Destination.MARKET)
        rule.onNodeWithTag("symbols-list").performScrollToNode(hasTestTag("symbol-XLE"))
        rule.onNodeWithTag("symbol-XLE").performClick()
        val changed = JSONObject(initial.toString())
        val different = initial.array("rows").getJSONObject(1).obj("scores")
        changed.array("rows").objects().first { it.symbol() == "XLE" }.put("scores", different)
        rule.runOnUiThread { state.value = changed }
        rule.onNodeWithContentDescription("Current (C) score " + displayScore(different, "c")).assertIsDisplayed()
        rule.onNodeWithContentDescription("Close symbol detail").performClick()
        go(Destination.HISTORY)
        rule.onNodeWithTag("history-list").performScrollToNode(hasTestTag("history-100"))
        rule.onNodeWithTag("history-100").performClick()
        rule.onNodeWithText("Recorded decision").assertIsDisplayed()
        val recorded = history.getJSONObject(0).obj("scores")
        rule.runOnUiThread { state.value = initial }
        rule.onNodeWithContentDescription("Current (C) score " + displayScore(recorded, "c")).assertIsDisplayed()
    }
    @Test fun visualEvidenceForSevenMajorScreensLightAndDark() {
        assumeTrue(InstrumentationRegistry.getArguments().getString("mhVisualEvidence") == "true")
        content()
        for (theme in listOf("LIGHT", "DARK")) {
            go(Destination.SETTINGS)
            rule.onNodeWithTag("theme-$theme").performScrollTo().performClick()
            for ((page, file) in listOf(Destination.DASHBOARD to "dashboard", Destination.MARKET to "market-health", Destination.PORTFOLIO to "portfolio", Destination.HISTORY to "history", Destination.POLICY to "policy", Destination.SETTINGS to "settings")) {
                go(page)
                capture("$file-${theme.lowercase()}")
                if (page == Destination.MARKET) {
                    rule.onNodeWithTag("symbols-list").performScrollToNode(hasTestTag("symbol-XLE"))
        rule.onNodeWithTag("symbol-XLE").performClick()
                    capture("symbol-detail-${theme.lowercase()}")
                    rule.onNodeWithContentDescription("Close symbol detail").performClick()
                }
            }
        }
    }
    private fun capture(name: String) {
        rule.waitForIdle()
        val folder = File(rule.activity.getExternalFilesDir(null), "ui-ux-evidence").apply { mkdirs() }
        val bitmap = rule.onRoot().captureToImage().asAndroidBitmap()
        File(folder, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }
    @Test fun componentGoldenIsDeterministicOnDeclaredProfile() {
        assumeTrue(InstrumentationRegistry.getArguments().getString("mhGolden") == "true")
        val scores = UiFixtures.data().array("rows").getJSONObject(0).obj("scores")
        rule.setContent { MarketHealthTheme(ThemeMode.LIGHT) {
            Surface(Modifier.width(328.dp)) { Column(Modifier.padding(16.dp)) { ScoreStrip(scores) } }
        } }
        rule.waitForIdle()
        val a = rule.onRoot().captureToImage().asAndroidBitmap()
        rule.waitForIdle()
        val b = rule.onRoot().captureToImage().asAndroidBitmap()
        assertTrue("unchanged score component repeats pixel-exactly", a.sameAs(b))
        val folder = File(rule.activity.getExternalFilesDir(null), "ui-ux-evidence").apply { mkdirs() }
        File(folder, "score-strip-light-golden.png").outputStream().use { a.compress(Bitmap.CompressFormat.PNG, 100, it) }
        if (InstrumentationRegistry.getArguments().getString("mhCompareGolden") == "true") {
            val golden = InstrumentationRegistry.getInstrumentation().context.assets.open("goldens/score-strip-light.png").use { android.graphics.BitmapFactory.decodeStream(it) }
            assertEquals(golden.width, a.width); assertEquals(golden.height, a.height)
            assertTrue("score component matches committed profile golden exactly", golden.sameAs(a))
        }
    }
    @Test fun profileRenderingOnDisposableEmulator() {
        assumeTrue(InstrumentationRegistry.getArguments().getString("mhPerformance") == "true")
        val data = UiFixtures.stress(UiFixtures.data())
        val history = UiFixtures.history(data, 300)
        val samples = Collections.synchronizedList(mutableListOf<Long>())
        val thread = HandlerThread("mh-ui-frame-observer").apply { start() }
        val listener = android.view.Window.OnFrameMetricsAvailableListener { _, frame, _ -> samples.add(frame.getMetric(FrameMetrics.TOTAL_DURATION)) }
        rule.runOnUiThread { rule.activity.window.addOnFrameMetricsAvailableListener(listener, Handler(thread.looper)) }
        val records = JSONArray()
        try {
            fun measure(name: String, operation: () -> Unit) {
                samples.clear()
                val start = System.nanoTime()
                operation(); rule.waitForIdle()
                val elapsed = (System.nanoTime() - start) / 1e6
                val durations = synchronized(samples) { samples.toList().sorted() }
                fun percentile(fraction: Double) = if (durations.isEmpty()) JSONObject.NULL else durations[((durations.size - 1) * fraction).toInt()] / 1e6
                records.put(JSONObject().put("scenario", name).put("elapsed_ms_including_test_automation", elapsed)
                    .put("frames", durations.size).put("frame_p50_ms", percentile(.5)).put("frame_p95_ms", percentile(.95)))
            }
            measure("initial dashboard") { content(data, history) }
            measure("25-symbol list scroll") {
                go(Destination.MARKET)
                rule.onNodeWithTag("symbols-list").performScrollToNode(hasTestTag("symbol-QA24"))
                rule.onNodeWithTag("symbols-list").performScrollToIndex(0)
            }
            measure("history chart and timeline") {
                go(Destination.HISTORY)
                rule.onNodeWithTag("history-list").performScrollToNode(hasTestTag("history-150"))
            }
            measure("navigation") { go(Destination.PORTFOLIO); go(Destination.POLICY); go(Destination.SETTINGS); go(Destination.DASHBOARD) }
            val report = JSONObject().put("kind", "debug emulator observation, not physical release benchmark")
                .put("test_data", "25 synthetic presentation rows, 300 repeated frozen-score history rows")
                .put("scenarios", records)
            File(rule.activity.getExternalFilesDir(null), "ui-ux-performance.json").writeText(report.toString(2))
            assertTrue(records.length() == 4)
        } finally {
            rule.runOnUiThread { rule.activity.window.removeOnFrameMetricsAvailableListener(listener) }
            thread.quitSafely()
        }
    }
}
