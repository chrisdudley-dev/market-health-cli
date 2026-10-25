package dev.chrisdudley.markethealth

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.work.*
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CancellationException

object MonitorScheduler {
    const val NAME = "market-health-periodic-refresh"
    fun request(minutes: Long): PeriodicWorkRequest {
        require(minutes in listOf(15L, 30L, 60L)) { "Android periodic work supports 15, 30 or 60 minutes" }
        return PeriodicWorkRequestBuilder<RefreshWorker>(minutes, TimeUnit.MINUTES)
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .build()
    }
    fun apply(context: Context, enabled: Boolean, minutes: Long) {
        val manager = WorkManager.getInstance(context)
        if (enabled) manager.enqueueUniquePeriodicWork(NAME, ExistingPeriodicWorkPolicy.UPDATE, request(minutes))
        else manager.cancelUniqueWork(NAME)
    }
}

object RefreshCycleIds {
    @android.annotation.SuppressLint("ApplySharedPref", "UseKtx")
    fun get(context: Context, workId: String, attempt: Int): String {
        val preferences = context.getSharedPreferences("refresh-work", Context.MODE_PRIVATE)
        val existing = preferences.getString(workId, null)
        if (attempt > 0 && existing != null) return existing
        val cycle = java.util.UUID.randomUUID().toString()
        check(preferences.edit().putString(workId, cycle).commit()) { "Unable to persist refresh cycle" }
        return cycle
    }
}

class RefreshWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    @android.annotation.SuppressLint("ApplySharedPref", "UseKtx") // Synchronous persistence on the worker thread is required before scoring.
    override suspend fun doWork(): Result {
        val repository = CoreRepository.get(applicationContext)
        return try {
            // Re-read persisted setting after reboot/process restart; never rely on Activity state.
            val settings = repository.state().getJSONObject("settings")
            if (!settings.optBoolean("background")) Result.success()
            else {
                // Work retries must not consume a second rescue refresh if the DB
                // committed before the process died or notification delivery failed.
                val cycle = RefreshCycleIds.get(applicationContext, id.toString(), runAttemptCount)
                repository.refresh(cycle)
                // Keep the token until the next attempt-0 cycle replaces it. A
                // crash before WorkManager records success must still reuse it.
                Result.success()
            }
        } catch (e: CancellationException) { throw e }
        catch (e: Exception) { Result.retry() }
    }
}

object NotificationPublisher {
    const val CHANNEL = "mh-policy-transitions"
    fun permitted(context: Context): Boolean =
        (Build.VERSION.SDK_INT < 33 || ContextCompat.checkSelfPermission(context,
            Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) &&
            NotificationManagerCompat.from(context).areNotificationsEnabled()

    suspend fun deliver(context: Context, repository: CoreRepository, pending: JSONArray) {
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel(CHANNEL, "Owned policy transitions", NotificationManager.IMPORTANCE_DEFAULT))
        for (i in 0 until pending.length()) {
            val row = pending.getJSONObject(i)
            val id = row.getInt("id")
            var status = "permission_denied"
            var error = "Notification permission or channel is disabled"
            if (permitted(context) && manager.getNotificationChannel(CHANNEL).importance != NotificationManager.IMPORTANCE_NONE) {
                val intent = PendingIntent.getActivity(context, 0, Intent(context, MainActivity::class.java),
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
                val notification = NotificationCompat.Builder(context, CHANNEL)
                    .setSmallIcon(R.drawable.ic_market_health).setContentTitle(row.getString("title"))
                    .setContentText(row.getString("body"))
                    .setStyle(NotificationCompat.BigTextStyle().bigText(row.getString("body")))
                    .setContentIntent(intent).setAutoCancel(true).setOnlyAlertOnce(true).build()
                try {
                    NotificationManagerCompat.from(context).notify(id, notification)
                    status = "submitted"; error = ""
                } catch (e: SecurityException) { error = e.message ?: error }
            }
            // A crash before this write reuses the same Android ID with onlyAlertOnce.
            repository.call("notification_result", JSONObject().put("id", id).put("status", status).put("error", error))
        }
    }
}
