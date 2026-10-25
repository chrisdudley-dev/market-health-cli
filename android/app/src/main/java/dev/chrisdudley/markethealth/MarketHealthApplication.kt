package dev.chrisdudley.markethealth

import android.app.Application
import android.system.Os
import android.system.OsConstants
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

object RuntimeCompatibility {
    fun supported(): Boolean = Os.sysconf(OsConstants._SC_PAGESIZE) in listOf(4096L, 16384L)
}

class MarketHealthApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        if (RuntimeCompatibility.supported() && !Python.isStarted()) Python.start(AndroidPlatform(this))
    }
}
