package dev.chrisdudley.markethealth

import org.json.JSONArray
import org.json.JSONObject
import java.text.NumberFormat
import java.time.Duration
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

// Presentation projection only. All scores, decisions, reasons and sizing come
// verbatim from the authoritative bridge. No financial formula belongs here.
internal fun JSONArray.objects(): List<JSONObject> = (0 until length()).mapNotNull { optJSONObject(it) }
internal fun JSONArray.strings(): List<String> = (0 until length()).map { optString(it) }
internal fun JSONObject.array(name: String): JSONArray = optJSONArray(name) ?: JSONArray()
internal fun JSONObject.obj(name: String): JSONObject = optJSONObject(name) ?: JSONObject()
internal fun JSONObject.raw(name: String): String = if (!has(name) || isNull(name)) "—" else get(name).toString()
internal fun JSONObject.numberOrNull(name: String): Double? =
    if (!has(name) || isNull(name)) null else optDouble(name, Double.NaN).takeIf { it.isFinite() }
internal fun JSONObject.policyAction(): String = optString("current_action", optString("action", "UNKNOWN"))
internal fun JSONObject.symbol(): String = optString("symbol", obj("scores").optString("symbol"))

internal fun displayNumber(value: Double?, places: Int = 2): String {
    if (value == null || !value.isFinite()) return "—"
    return NumberFormat.getNumberInstance(Locale.getDefault()).apply {
        maximumFractionDigits = places
        minimumFractionDigits = 0
    }.format(value)
}
internal fun displayScore(scores: JSONObject, field: String) = displayNumber(scores.numberOrNull(field), 1)
internal fun parseObservationTime(value: String): Instant? = runCatching { Instant.parse(value) }.getOrNull()
internal fun displayTime(value: String): String = parseObservationTime(value)?.let {
    DateTimeFormatter.ofPattern("MMM d, h:mm a", Locale.getDefault()).withZone(ZoneId.systemDefault()).format(it)
} ?: value.ifBlank { "Not available" }

internal fun ownedSymbols(data: JSONObject): Set<String> = data.array("holdings").objects().map { it.symbol() }.toSet()
internal fun allSymbolRows(data: JSONObject): List<JSONObject> = data.array("rows").objects()
internal fun buyCandidate(row: JSONObject, owned: Set<String>): Boolean =
    row.symbol() !in owned && row.obj("result").optBoolean("buy_qualified")

internal enum class SymbolFilter(val label: String, val action: String? = null) {
    ALL("All"), OWNED("Owned"), BUY("BUY", "BUY"), HOLD("HOLD", "HOLD"),
    WATCH("WATCH", "WATCH"), SELL("SELL", "SELL"), RESCUE("Rescue", "HOLD — RESCUE"),
    PROBLEMS("Data issues")
}
internal enum class SymbolSort(val label: String, val score: String? = null) {
    SYMBOL("Symbol"), BLEND("Blend score", "blend"), CURRENT("Current score", "c"),
    H1("H1 score", "h1"), H5("H5 score", "h5"), ACTION("Policy action")
}
internal fun visibleSymbols(data: JSONObject, page: String, query: String,
    filter: SymbolFilter, sort: SymbolSort): List<JSONObject> {
    val owned = ownedSymbols(data)
    val selected = allSymbolRows(data).filter { row ->
        row.symbol().contains(query.trim(), ignoreCase = true) &&
            when (page) {
                "Trading List" -> row.symbol() in owned
                "Buy Candidates" -> buyCandidate(row, owned)
                else -> true
            } && when (filter) {
                SymbolFilter.ALL -> true
                SymbolFilter.OWNED -> row.symbol() in owned
                SymbolFilter.PROBLEMS -> (!row.obj("scores").isNull("error") && row.obj("scores").optString("error").isNotBlank()) || row.policyAction() == "DATA ERROR"
                else -> row.policyAction() == filter.action
            }
    }
    return when (sort) {
        SymbolSort.SYMBOL -> selected.sortedBy { it.symbol() }
        SymbolSort.ACTION -> selected.sortedWith(compareBy<JSONObject> { it.policyAction() }.thenBy { it.symbol() })
        else -> selected.sortedWith(compareByDescending<JSONObject> {
            it.obj("scores").numberOrNull(sort.score!!) ?: Double.NEGATIVE_INFINITY
        }.thenBy { it.symbol() })
    }
}

internal data class RefreshPresentation(val label: String, val detail: String,
    val stale: Boolean, val error: Boolean, val timestamp: String)

internal fun refreshPresentation(data: JSONObject, now: Instant): RefreshPresentation {
    val status = data.obj("status")
    val timestamp = status.optString("timestamp")
    if (status.length() == 0) return RefreshPresentation("No refresh yet",
        "Refresh to load Market Health results.", false, false, "")
    val statusName = status.optString("status")
    val age = parseObservationTime(timestamp)?.let { Duration.between(it, now).seconds }
    // Same existing UI freshness window; this never alters engine quality/policy.
    val stale = (age != null && age > data.obj("settings").optLong("interval", 15) * 60) ||
        statusName in listOf("error", "partial")
    return when (statusName) {
        "error" -> RefreshPresentation("Refresh could not complete",
            status.optString("error", "Saved results are still available.").ifBlank { "Saved results are still available." },
            true, true, timestamp)
        "partial" -> RefreshPresentation("Incomplete results",
            "Some inputs are unavailable. Review data issues before using these results.", true, false, timestamp)
        else -> RefreshPresentation(if (stale) "Saved results · stale" else "Market data updated",
            displayTime(timestamp), stale, false, timestamp)
    }
}
