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

    /** Fast path: hold a live connection while the web dashboard is open. */
    fun syncPushMode(context: Context, dashboardOpen: Boolean) {
        if (dashboardOpen) PushService.start(context) else PushService.stop(context)
    }

    fun checkOutbox(context: Context) {
        val req = androidx.work.OneTimeWorkRequestBuilder<OutboxWorker>()
            .setConstraints(androidx.work.Constraints.Builder().setRequiredNetworkType(androidx.work.NetworkType.CONNECTED).build())
            .setBackoffCriteria(androidx.work.BackoffPolicy.EXPONENTIAL, 30, java.util.concurrent.TimeUnit.SECONDS)
            .build()
        androidx.work.WorkManager.getInstance(context).enqueueUniqueWork(
            "outbox_now", androidx.work.ExistingWorkPolicy.APPEND_OR_REPLACE, req
        )
    }

    fun retryPending(context: Context) {
        for (id in PendingSmsStore.get(context).allIdsByState(DeliveryState.PENDING)) {
            SmsReceiver.enqueue(context, id)
        }
    }
}
