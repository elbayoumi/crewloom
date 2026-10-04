package com.smsforwarder.app

import android.content.Context
import androidx.work.Worker
import androidx.work.WorkerParameters

class SmsForwardWorker(context: Context, params: WorkerParameters) : Worker(context, params) {

    companion object {
        const val KEY_MESSAGE_ID = "message_id"
    }

    override fun doWork(): Result {
        val messageId = inputData.getString(KEY_MESSAGE_ID) ?: return Result.success()
        val store = PendingSmsStore.get(applicationContext)
        val record = store.get(messageId) ?: return Result.success()
        if (record.state != DeliveryState.PENDING) return Result.success()
        if (record.attempts >= RetryPolicy.MAX_ATTEMPTS) {
            store.markState(messageId, DeliveryState.FAILED, "max_attempts")
            return Result.success()
        }

        val config = AppConfig(applicationContext)
        if (config.baseUrl.isBlank() || config.deviceId.isBlank() || config.deviceToken.isBlank()) {
            store.markState(messageId, DeliveryState.FAILED, "missing_config")
            return Result.success()
        }

        store.incrementAttempts(messageId)
        val payload = SmsPayload(
            sender = record.sender,
            message = record.body,
            receivedAt = SmsPayload.formatTimestamp(record.receivedAtMillis),
            deviceId = config.deviceId,
            messageId = record.messageId,
            senderName = record.senderName
        )

        val result = ApiClient(config.baseUrl).postSms(config.deviceToken, payload.toJson())
        return when (RetryPolicy.decide(result.httpCode)) {
            RetryPolicy.Decision.DELIVERED -> {
                store.markState(messageId, DeliveryState.DELIVERED, null)
                Result.success()
            }
            RetryPolicy.Decision.RETRY -> {
                if (record.attempts + 1 >= RetryPolicy.MAX_ATTEMPTS) {
                    store.markState(messageId, DeliveryState.FAILED, "max_attempts")
                    Result.success()
                } else {
                    store.markState(messageId, DeliveryState.PENDING, result.error ?: "http_${result.httpCode}")
                    Result.retry()
                }
            }
            RetryPolicy.Decision.GIVE_UP -> {
                store.markState(messageId, DeliveryState.FAILED, "http_${result.httpCode}")
                Result.success()
            }
        }
    }
}
