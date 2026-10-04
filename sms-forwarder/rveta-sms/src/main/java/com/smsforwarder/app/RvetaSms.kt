package com.smsforwarder.app

import android.content.Context

object RvetaSms {

    fun configure(context: Context, baseUrl: String, deviceId: String, token: String) {
        val c = AppConfig(context)
        c.baseUrl = baseUrl
        c.deviceId = deviceId
        c.deviceToken = token
    }

    fun pendingCount(context: Context): Int = PendingSmsStore.get(context).pendingCount()

    fun lastStatus(context: Context): String = PendingSmsStore.get(context).lastStatus()

    fun retryPending(context: Context) {
        for (id in PendingSmsStore.get(context).allIdsByState(DeliveryState.PENDING)) {
            SmsReceiver.enqueue(context, id)
        }
    }
}
