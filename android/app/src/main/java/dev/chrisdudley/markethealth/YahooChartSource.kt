package dev.chrisdudley.markethealth

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.time.Instant
import java.util.UUID

/** Transport only: raw chart responses go to the shared Python OHLCV normalizer. */
object YahooChartSource {
    suspend fun fetch(universe: JSONArray): JSONObject = coroutineScope {
        val symbols = (0 until universe.length()).map { universe.getString(it) }
        val needed = (symbols + listOf("SPY", "^VIX")).distinct()
        val semaphore = Semaphore(4)
        val responses = needed.map { symbol ->
            async(Dispatchers.IO) {
                semaphore.withPermit {
                    symbol to runCatching { chart(symbol) }
                }
            }
        }.awaitAll()
        val charts = JSONObject()
        val errors = JSONObject()
        for ((symbol, result) in responses) {
            result.fold(onSuccess = { charts.put(symbol, it) },
                onFailure = { errors.put(symbol, it.message ?: "Market data unavailable") })
        }
        if (!charts.has("SPY") || !charts.has("^VIX")) {
            error("Required SPY/VIX market data unavailable. Previous scores remain stale.")
        }
        JSONObject().put("symbols", universe).put("asof", Instant.now().toString())
            .put("refresh_id", UUID.randomUUID().toString()).put("charts", charts)
            .put("errors", errors).put("calendar", JSONObject())
    }

    private fun chart(symbol: String): JSONObject {
        val encoded = URLEncoder.encode(symbol, "UTF-8")
        val connection = URL("https://query1.finance.yahoo.com/v8/finance/chart/$encoded?range=1y&interval=1d&includePrePost=false&events=div%2Csplits&includeAdjustedClose=true")
            .openConnection() as HttpURLConnection
        try {
            connection.connectTimeout = 15_000
            connection.readTimeout = 30_000
            connection.setRequestProperty("User-Agent", "Mozilla/5.0 MarketHealth/Android")
            if (connection.responseCode != 200) error("$symbol: data source HTTP ${connection.responseCode}")
            val response = connection.inputStream.bufferedReader().use { it.readText() }
            val json = JSONObject(response)
            val chart = json.getJSONObject("chart")
            if (!chart.isNull("error") || chart.optJSONArray("result")?.length() != 1) {
                error("$symbol: no chart returned")
            }
            return json
        } finally { connection.disconnect() }
    }
}
