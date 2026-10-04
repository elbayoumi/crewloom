package com.smsforwarder.app

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import java.util.concurrent.Executors

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        val pending = goAsync()
        Executors.newSingleThreadExecutor().execute {
            try {
                val store = PendingSmsStore.get(context)
                for (id in store.allIdsByState(DeliveryState.PENDING)) {
                    SmsReceiver.enqueue(context, id)
                }
            } finally {
                pending.finish()
            }
        }
    }
}
