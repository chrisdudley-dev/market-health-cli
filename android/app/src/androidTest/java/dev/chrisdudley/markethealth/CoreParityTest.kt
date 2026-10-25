package dev.chrisdudley.markethealth

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.chaquo.python.Python
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.UUID

@RunWith(AndroidJUnit4::class)
class CoreParityTest {
    @Test fun frozenCliAndEmbeddedAndroidResultsAreExactlyEqual() {
        val assets = InstrumentationRegistry.getInstrumentation().context.assets
        val input = assets.open("parity-input.json").bufferedReader().use { it.readText() }
        val expected = JSONArray(assets.open("parity-expected.json").bufferedReader().use { it.readText() })
        val result = JSONArray(Python.getInstance().getModule("market_health.android_bridge")
            .callAttr("fixture_result", input).toString())
        assertEquals(expected.length(), result.length())
        for (i in 0 until expected.length()) {
            val want = expected.getJSONObject(i)
            val got = result.getJSONObject(i)
            for (key in listOf("c", "h1", "h5", "blend", "stop", "buy")) {
                assertEquals("${want.getJSONObject("scores").getString("symbol")} $key",
                    want.getJSONObject("scores").getDouble(key), got.getJSONObject("scores").getDouble(key), 0.0)
            }
            for (key in listOf("symbol", "state", "glyph"))
                assertEquals(key, want.getJSONObject("scores").getString(key), got.getJSONObject("scores").getString(key))
            assertEquals(want.getJSONObject("decision").getString("action"), got.getJSONObject("decision").getString("action"))
            assertEquals(want.getJSONObject("decision").getJSONArray("reason_codes").toString(),
                got.getJSONObject("decision").getJSONArray("reason_codes").toString())
        }
    }

    @Test fun chartTransportWithEmptyProviderSessionsMatchesCli() {
        val assets = InstrumentationRegistry.getInstrumentation().context.assets
        val document = JSONObject(assets.open("parity-input.json").bufferedReader().use { it.readText() })
        val series = document.getJSONObject("series")
        val charts = JSONObject()
        for (symbol in series.keys()) {
            val block = series.getJSONObject(symbol)
            val dates = block.getJSONArray("dates")
            val timestamps = JSONArray()
            for (i in 0 until dates.length()) {
                val epoch = java.time.LocalDate.parse(dates.getString(i)).atTime(16, 0)
                    .toEpochSecond(java.time.ZoneOffset.UTC)
                if (i == 0) timestamps.put(epoch - 86400)
                timestamps.put(epoch)
            }
            val quotes = JSONObject()
            for (field in listOf("Open", "High", "Low", "Close", "Volume")) {
                val values = JSONArray().put(JSONObject.NULL)
                val source = block.getJSONArray(field)
                for (i in 0 until source.length()) values.put(source.get(i))
                quotes.put(field.lowercase(), values)
            }
            charts.put(symbol, JSONObject().put("chart", JSONObject().put("error", JSONObject.NULL)
                .put("result", JSONArray().put(JSONObject()
                    .put("meta", JSONObject().put("exchangeTimezoneName", "America/New_York"))
                    .put("timestamp", timestamps)
                    .put("indicators", JSONObject().put("quote", JSONArray().put(quotes)))))))
        }
        document.remove("series")
        document.put("charts", charts)
        val result = JSONArray(Python.getInstance().getModule("market_health.android_bridge")
            .callAttr("fixture_result", document.toString()).toString())
        val expected = JSONArray(assets.open("parity-expected.json").bufferedReader().use { it.readText() })
        for (i in 0 until expected.length()) {
            val want = expected.getJSONObject(i)
            val got = result.getJSONObject(i)
            for (field in listOf("c", "h1", "h5", "blend", "stop", "buy"))
                assertEquals(field, want.getJSONObject("scores").getDouble(field), got.getJSONObject("scores").getDouble(field), 0.0)
            for (field in listOf("state", "glyph"))
                assertEquals(field, want.getJSONObject("scores").getString(field), got.getJSONObject("scores").getString(field))
            assertEquals(want.getJSONObject("decision").getString("action"), got.getJSONObject("decision").getString("action"))
            assertEquals(want.getJSONObject("decision").getJSONArray("reason_codes").toString(),
                got.getJSONObject("decision").getJSONArray("reason_codes").toString())
        }
    }

    @Test fun rescueAndHistorySurviveFreshStoreInstances() {
        val python = Python.getInstance()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val path = File(context.cacheDir, "rescue-${UUID.randomUUID()}.sqlite3").absolutePath
        val bridge = python.getModule("market_health.android_bridge")
        bridge.callAttr("call", path, "holding", "{\"symbol\":\"RPG\",\"account\":\"Roth IRA\",\"shares\":3}")
        val model = python.getModule("market_health.policy.models").callAttr("Scores", "RPG", 52, 62, 59, 56)
        val tuple = python.getModule("builtins").callAttr("tuple", arrayOf(model))
        fun apply(key: String): JSONArray {
            val store = python.getModule("market_health.storage.sqlite").callAttr("Store", path)
            val scan = python.getModule("market_health.engine_api").callAttr("Scan", key, "2026-10-25T12:00:00Z", tuple, "live engine")
            store.callAttr("apply_scan", scan)
            return JSONArray(python.getModule("json").callAttr("dumps", store.callAttr("latest")).toString())
        }
        assertEquals("HOLD — RESCUE", apply("first").getJSONObject(0).getString("action"))
        assertEquals("SELL", apply("second").getJSONObject(0).getString("action"))
        val history = JSONArray(bridge.callAttr("call", path, "history", "{}").toString())
        assertEquals(2, history.length())
        val state = JSONObject(bridge.callAttr("call", path, "state", "{}").toString())
        assertEquals(1, state.getJSONArray("notifications").length())
        apply("third")
        val after = JSONObject(bridge.callAttr("call", path, "state", "{}").toString())
        assertEquals("SELL->SELL must not enqueue a duplicate", 1, after.getJSONArray("notifications").length())
    }

    @Test fun schedulingHonorsAndroidMinimum() {
        assertEquals(900_000L, MonitorScheduler.request(15).workSpec.intervalDuration)
        assertEquals(3_600_000L, MonitorScheduler.request(60).workSpec.intervalDuration)
        try { MonitorScheduler.request(5); fail("5-minute periodic work must be rejected") }
        catch (_: IllegalArgumentException) { }
    }
    @Test fun committedRefreshRetryReusesCycleAcrossFreshCalls() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val workId = UUID.randomUUID().toString()
        val first = RefreshCycleIds.get(context, workId, 0)
        assertEquals(first, RefreshCycleIds.get(context, workId, 1))
        assertEquals(first, RefreshCycleIds.get(context, workId, 2))
        val next = RefreshCycleIds.get(context, workId, 0)
        assertNotEquals(first, next)
        assertEquals(next, RefreshCycleIds.get(context, workId, 1))
    }

    @Test fun androidNotificationsHonorPermissionAndUnchangedStates(): Unit = kotlinx.coroutines.runBlocking {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val python = Python.getInstance()
        val path = File(context.filesDir, "market-health.sqlite3").absolutePath
        val symbol = "QAN" + UUID.randomUUID().toString().take(6).uppercase()
        val store = python.getModule("market_health.storage.sqlite").callAttr("Store", path)
        store.callAttr("save_holding", symbol, "Notification QA", 1)
        fun apply(key: String, h5: Int) {
            val scores = python.getModule("market_health.policy.models").callAttr("Scores", symbol, 58, 62, h5, 60)
            val rows = python.getModule("builtins").callAttr("tuple", arrayOf(scores))
            store.callAttr("apply_scan", python.getModule("market_health.engine_api").callAttr("Scan", key, "2026-10-25T12:00:00Z", rows, "live engine"))
        }
        val repository = CoreRepository.get(context)
        val manager = context.getSystemService(android.app.NotificationManager::class.java)
        apply(symbol + "-hold", 60)
        apply(symbol + "-sell", 53)
        if (android.os.Build.VERSION.SDK_INT >= 33 && !NotificationPublisher.permitted(context)) {
            NotificationPublisher.deliver(context, repository, repository.state().getJSONArray("notifications"))
            assertEquals(0, repository.state().getJSONArray("notifications").length())
            instrumentation.uiAutomation.grantRuntimePermission(context.packageName, android.Manifest.permission.POST_NOTIFICATIONS)
        }
        apply(symbol + "-recover", 60)
        val pending = repository.state().getJSONArray("notifications")
        assertTrue(pending.length() > 0)
        val notificationId = pending.getJSONObject(pending.length() - 1).getInt("id")
        NotificationPublisher.deliver(context, repository, pending)
        for (i in 0 until 20) {
            if (manager.activeNotifications.any { it.id == notificationId }) break
            kotlinx.coroutines.delay(250)
        }
        assertTrue("Android OS must contain the posted notification", manager.activeNotifications.any { it.id == notificationId })
        apply(symbol + "-unchanged", 60)
        assertEquals("HOLD->HOLD must have no pending notification", 0, repository.state().getJSONArray("notifications").length())
        assertEquals(1, manager.activeNotifications.count { it.id == notificationId })
        manager.cancel(notificationId)
        store.callAttr("remove_holding", symbol, "Notification QA")
    }

}
