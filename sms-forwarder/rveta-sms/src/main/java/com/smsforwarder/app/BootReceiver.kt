package com.smsforwarder.app

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import java.util.concurrent.Executors

class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        val pending = goAsync()
        val app = context.applicationContext
        EXECUTOR.execute {
            try {
                val store = PendingSmsStore.get(app)
                for (id in store.allIdsByState(DeliveryState.PENDING)) {
                    SmsReceiver.enqueue(app, id)
                }
                // Recover anything that failed for a transient reason before the reboot.
                for (id in store.failedIds("missing_config")) {
                    store.resetToPending(id)
                    SmsReceiver.enqueue(app, id)
                }
                RvetaSms.checkOutbox(app)
                TickerWorker.kick(app)
            } catch (e: Exception) {
                Log.w("RvetaSms", "boot recovery failed: ${e.javaClass.simpleName}")
            } finally {
                pending.finish()
            }
        }
    }

    companion object {
        private val EXECUTOR = Executors.newSingleThreadExecutor { r ->
            Thread(r, "rveta-sms-boot").apply { isDaemon = true }
        }
    }
}
