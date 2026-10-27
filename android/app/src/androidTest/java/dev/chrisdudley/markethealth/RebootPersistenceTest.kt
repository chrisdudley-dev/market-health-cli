package dev.chrisdudley.markethealth

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.work.WorkInfo
import androidx.work.WorkManager
import com.chaquo.python.Python
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** Only the release runner invokes seed/reboot/verify; it never targets a phone. */
@RunWith(AndroidJUnit4::class)
class RebootPersistenceTest {
    @Test fun rescueHistoryAndPeriodicScheduleSurviveReboot(): Unit = runBlocking {
        val phase = InstrumentationRegistry.getArguments().getString("mhRebootPhase")
        assumeTrue(phase == "seed" || phase == "verify")
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val path = File(context.filesDir, "release-reboot.sqlite3")
        val python = Python.getInstance()
        val json = python.getModule("json")
        val storeModule = python.getModule("market_health.storage.sqlite")
        if (phase == "seed") {
            for (suffix in listOf("", "-wal", "-shm")) File(path.absolutePath + suffix).delete()
        }
        val store = storeModule.callAttr("Store", path.absolutePath)
        fun rows() = JSONArray(json.callAttr("dumps", store.callAttr("latest")).toString())
        fun apply(key: String) {
            val scores = python.getModule("market_health.policy.models").callAttr("Scores", "RPG", 52, 62, 59, 56)
            val tuple = python.getModule("builtins").callAttr("tuple", arrayOf(scores))
            val scan = python.getModule("market_health.engine_api").callAttr("Scan", key, java.time.Instant.now().toString(), tuple, "live engine")
            store.callAttr("apply_scan", scan)
        }
        val manager = WorkManager.getInstance(context)
        val preferences = context.getSharedPreferences("release-reboot-proof", android.content.Context.MODE_PRIVATE)
        if (phase == "seed") {
            store.callAttr("save_holding", "RPG", "Reboot QA", 3)
            apply("reboot-seed")
            assertEquals("HOLD — RESCUE", rows().getJSONObject(0).getString("action"))
            assertEquals(1, rows().getJSONObject(0).getJSONObject("result").getInt("rescue_count"))
            // This checks persistent periodic scheduling without a public data-source dependency.
            CoreRepository.get(context).call("settings", JSONObject().put("background", false))
            MonitorScheduler.apply(context, true, 15)
            val info = withTimeout(15_000) {
                var infos = manager.getWorkInfosForUniqueWork(MonitorScheduler.NAME).get()
                while (infos.none { it.state != WorkInfo.State.CANCELLED }) {
                    delay(100)
                    infos = manager.getWorkInfosForUniqueWork(MonitorScheduler.NAME).get()
                }
                infos.first { it.state != WorkInfo.State.CANCELLED }
            }
            check(preferences.edit().putString("work-id", info.id.toString()).commit())
        } else {
            assertEquals("HOLD — RESCUE", rows().getJSONObject(0).getString("action"))
            assertEquals(1, rows().getJSONObject(0).getJSONObject("result").getInt("rescue_count"))
            val holdings = JSONArray(json.callAttr("dumps", store.callAttr("holdings")).toString())
            assertEquals(3.0, holdings.getJSONObject(0).getDouble("shares"), 0.0)
            assertEquals("Reboot QA", holdings.getJSONObject(0).getString("account"))
            val expectedWork = preferences.getString("work-id", null)
            assertNotNull(expectedWork)
            assertTrue(manager.getWorkInfosForUniqueWork(MonitorScheduler.NAME).get().any {
                it.id.toString() == expectedWork && it.state != WorkInfo.State.CANCELLED
            })
            apply("reboot-second")
            assertEquals("SELL", rows().getJSONObject(0).getString("action"))
            assertEquals(2, rows().getJSONObject(0).getJSONObject("result").getInt("rescue_count"))
            assertEquals(2, JSONArray(json.callAttr("dumps", store.callAttr("history")).toString()).length())
            assertEquals(1, JSONArray(json.callAttr("dumps", store.callAttr("pending_notifications")).toString()).length())
            apply("reboot-third")
            assertEquals(1, JSONArray(json.callAttr("dumps", store.callAttr("pending_notifications")).toString()).length())
            MonitorScheduler.apply(context, false, 15)
        }
    }
}
