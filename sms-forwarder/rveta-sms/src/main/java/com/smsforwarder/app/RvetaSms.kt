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

    fun checkOutbox(context: Context) {
        val req = androidx.work.OneTimeWorkRequestBuilder<OutboxWorker>()
            .setConstraints(androidx.work.Constraints.Builder().setRequiredNetworkType(androidx.work.NetworkType.CONNECTED).build())
            .build()
        androidx.work.WorkManager.getInstance(context).enqueueUniqueWork(
            "outbox_now", androidx.work.ExistingWorkPolicy.REPLACE, req
        )
    }

    fun retryPending(context: Context) {
        for (id in PendingSmsStore.get(context).allIdsByState(DeliveryState.PENDING)) {
            SmsReceiver.enqueue(context, id)
        }
    }
}
