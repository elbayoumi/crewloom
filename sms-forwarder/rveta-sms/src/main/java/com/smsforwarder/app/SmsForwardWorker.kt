package com.smsforwarder.app

import android.content.Context
import androidx.work.Worker
import androidx.work.WorkerParameters

/** Retry path for inbound SMS that were not confirmed on the first immediate attempt. */
class SmsForwardWorker(context: Context, params: WorkerParameters) : Worker(context, params) {

    companion object {
        const val KEY_MESSAGE_ID = "message_id"
    }

    override fun doWork(): Result {
        val messageId = inputData.getString(KEY_MESSAGE_ID) ?: return Result.success()
        val store = PendingSmsStore.get(applicationContext)
        val record = store.get(messageId) ?: return Result.success()
        if (record.state != DeliveryState.PENDING) return Result.success()
        if (InboundDispatcher.deliver(applicationContext, messageId)) return Result.success()
        val after = store.get(messageId)
        return if (after?.state == DeliveryState.PENDING && after.attempts < RetryPolicy.MAX_ATTEMPTS) {
            Result.retry()
        } else {
            Result.success()
        }
    }
}
