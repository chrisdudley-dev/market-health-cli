package dev.chrisdudley.markethealth

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import org.json.JSONArray
import org.json.JSONObject

// Values are returned by the Python service. The ViewModel contains no score/policy math.
data class UiState(val data: JSONObject = JSONObject(), val busy: Boolean = false, val error: String? = null)

class MarketViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = CoreRepository.get(application)
    private val mutable = MutableStateFlow(UiState())
    val state: StateFlow<UiState> = mutable
    private val mutableHistory = MutableStateFlow(JSONArray())
    val history: StateFlow<JSONArray> = mutableHistory
    private var activeHistoryFilters: JSONObject? = null
    private var historyRequestVersion = 0L
    init { reload() }

    fun reload() = execute { repository.resume() }
    // Presentation reconciliation only: no market fetch, policy evaluation,
    // notification delivery or WorkManager scheduling is initiated here.
    fun reconcile() = execute {
        val current = repository.state()
        // History is a separate UI flow: keep its current filters while reading
        // the latest persisted page, instead of leaving that page cached too.
        activeHistoryFilters?.let { history(it) }
        current
    }
    fun refresh() = execute { repository.refresh() }
    fun editHolding(payload: JSONObject) = execute { JSONObject(repository.call("holding", payload)) }
    fun removeHolding(payload: JSONObject) = execute { JSONObject(repository.call("remove", payload)) }
    fun saveSettings(payload: JSONObject) = execute {
        val result = JSONObject(repository.call("settings", payload))
        val settings = result.getJSONObject("settings")
        MonitorScheduler.apply(getApplication(), settings.getBoolean("background"), settings.getLong("interval"))
        result
    }
    fun history(filters: JSONObject = JSONObject(), append: Boolean = false) {
        val query = JSONObject(filters.toString())
        if (!append) activeHistoryFilters = JSONObject(query.toString())
        val requestVersion = ++historyRequestVersion
        viewModelScope.launch {
            try {
                if (append && mutableHistory.value.length() > 0)
                    query.put("before_id", mutableHistory.value.getJSONObject(mutableHistory.value.length() - 1).getInt("id"))
                val page = JSONArray(repository.call("history", query))
                if (requestVersion != historyRequestVersion) return@launch
                if (append) {
                    val combined = JSONArray(mutableHistory.value.toString())
                    for (i in 0 until page.length()) combined.put(page.getJSONObject(i))
                    mutableHistory.value = combined
                } else mutableHistory.value = page
            }
            catch (e: Exception) {
                if (requestVersion == historyRequestVersion) mutable.value = mutable.value.copy(error = e.message)
            }
        }
    }
    private fun execute(operation: suspend () -> JSONObject) {
        if (mutable.value.busy) return
        viewModelScope.launch {
            mutable.value = mutable.value.copy(busy = true, error = null)
            try { mutable.value = UiState(operation()) }
            catch (e: Exception) {
                val previous = runCatching { repository.state() }.getOrDefault(mutable.value.data)
                mutable.value = UiState(previous, false, e.message ?: "Operation failed")
            }
        }
    }
}
