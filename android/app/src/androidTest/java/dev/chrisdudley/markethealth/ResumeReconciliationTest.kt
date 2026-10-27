package dev.chrisdudley.markethealth

import android.content.Context
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.ViewModelProvider
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.work.*
import androidx.work.testing.TestListenableWorkerBuilder
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.time.Instant
import java.util.UUID

/** Disposable emulator test. Never invoke on the preserved physical candidate. */
@RunWith(AndroidJUnit4::class)
class ResumeReconciliationTest {
    @get:Rule val rule = createEmptyComposeRule()

    @Test fun sameActivityAdoptsBackgroundCommitOnResumeWithoutRefreshOrRecreation(): Unit = runBlocking {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val repository = CoreRepository.get(context)
        val previousSettings = repository.state().getJSONObject("settings")
        val fixture = JSONObject(instrumentation.context.assets.open("parity-input.json")
            .bufferedReader().use { it.readText() })
        val firstTimestamp = fixture.getString("asof")
        val nextTimestamp = Instant.parse(firstTimestamp).plusSeconds(60).toString()
        val firstCycle = "resume-initial-${UUID.randomUUID()}"
        val nextDocument = JSONObject(fixture.toString()).put("asof", nextTimestamp)
        repository.refreshDocument(JSONObject(fixture.toString()), firstCycle)
        val scenario = ActivityScenario.launch(MainActivity::class.java)
        try {
            rule.waitUntil(30_000) {
                rule.onAllNodes(hasTestTag("refresh-timestamp-" + firstTimestamp)).fetchSemanticsNodes().isNotEmpty()
            }
            var originalActivity: MainActivity? = null
            var originalModel: MarketViewModel? = null
            val historyFilters = JSONObject().put("symbol", repository.state()
                .getJSONArray("rows").getJSONObject(0).getString("symbol"))
            scenario.onActivity {
                originalActivity = it
                originalModel = ViewModelProvider(it)[MarketViewModel::class.java]
                originalModel!!.history(historyFilters)
            }
            rule.waitUntil(30_000) { originalModel!!.history.value.length() > 0 }
            // Stop, retain Activity/ViewModel, then commit using the real worker
            // and shared persistence path with a deterministic fixture transport.
            scenario.moveToState(Lifecycle.State.CREATED)
            repository.call("settings", JSONObject().put("background", true))
            val cycles = mutableListOf<String>()
            val gateway = object : RefreshGateway {
                override suspend fun state() = repository.state()
                override suspend fun refresh(refreshId: String): JSONObject {
                    cycles.add(refreshId)
                    return repository.refreshDocument(JSONObject(nextDocument.toString()), refreshId)
                }
            }
            val factory = object : WorkerFactory() {
                override fun createWorker(appContext: Context, workerClassName: String,
                    workerParameters: WorkerParameters): ListenableWorker? =
                    if (workerClassName == RefreshWorker::class.java.name)
                        RefreshWorker(appContext, workerParameters, gateway) else null
            }
            val worker = TestListenableWorkerBuilder<RefreshWorker>(context).setWorkerFactory(factory).build()
            assertEquals(ListenableWorker.Result.success(), worker.doWork())
            assertEquals(1, cycles.size)
            val authoritative = repository.state()
            val expectedHistory = org.json.JSONArray(repository.call("history", historyFilters)).toString()
            assertEquals(nextTimestamp, authoritative.getJSONObject("status").getString("timestamp"))
            assertNotEquals(firstCycle, authoritative.getJSONObject("status").getString("scan_key"))

            scenario.moveToState(Lifecycle.State.RESUMED)
            rule.waitUntil(30_000) {
                rule.onAllNodes(hasTestTag("refresh-timestamp-" + nextTimestamp)).fetchSemanticsNodes().isNotEmpty()
            }
            rule.onNode(hasTestTag("refresh-timestamp-" + nextTimestamp)).assertIsDisplayed()
            rule.waitUntil(30_000) {
                originalModel!!.history.value.toString() == expectedHistory
            }
            scenario.onActivity {
                assertSame("no Activity recreation", originalActivity, it)
                val model = ViewModelProvider(it)[MarketViewModel::class.java]
                assertSame("no fresh ViewModel initialization", originalModel, model)
                val visible = model.state.value.data
                // Compare authoritative DTOs, not duplicated formula expectations.
                for (field in listOf("status", "rows", "holdings", "settings", "notifications"))
                    assertEquals(field, authoritative.get(field).toString(), visible.get(field).toString())
            }
            assertEquals("resume did not start a second calculation", 1, cycles.size)
            assertEquals("resume did not create another scan", authoritative.getJSONObject("status").toString(),
                repository.state().getJSONObject("status").toString())
        } finally {
            scenario.close()
            repository.call("settings", previousSettings)
        }
    }
}
