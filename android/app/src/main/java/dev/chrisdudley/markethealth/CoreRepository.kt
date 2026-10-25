package dev.chrisdudley.markethealth

import android.content.Context
import com.chaquo.python.Python
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/** A single process-wide gateway; all maths, policy and DB writes stay in Python. */
class CoreRepository private constructor(private val application: android.app.Application) {
    private val mutex = Mutex()
    private val refreshMutex = Mutex()
    private val database get() = File(application.filesDir, "market-health.sqlite3").absolutePath

    suspend fun call(operation: String, payload: JSONObject = JSONObject()): String =
        withContext(Dispatchers.IO) {
            mutex.withLock {
                Python.getInstance().getModule("market_health.android_bridge")
                    .callAttr("call", database, operation, payload.toString()).toString()
            }
        }

    suspend fun state() = JSONObject(call("state"))

    suspend fun resume(): JSONObject {
        val current = state()
        NotificationPublisher.deliver(application, this, current.optJSONArray("notifications") ?: JSONArray())
        return state()
    }

    suspend fun refresh(refreshId: String = java.util.UUID.randomUUID().toString()): JSONObject = refreshMutex.withLock {
        val universe = JSONArray(call("universe"))
        val document = try {
            YahooChartSource.fetch(universe).put("refresh_id", refreshId)
        } catch (e: Exception) {
            call("failure", JSONObject().put("message", e.message ?: "Market refresh failed"))
            throw e
        }
        val result = JSONObject(call("refresh", document))
        NotificationPublisher.deliver(application, this, result.optJSONArray("notifications") ?: JSONArray())
        state()
    }

    companion object {
        @Volatile private var instance: CoreRepository? = null
        fun get(context: Context): CoreRepository = instance ?: synchronized(this) {
            instance ?: CoreRepository(context.applicationContext as android.app.Application).also { instance = it }
        }
    }
}
