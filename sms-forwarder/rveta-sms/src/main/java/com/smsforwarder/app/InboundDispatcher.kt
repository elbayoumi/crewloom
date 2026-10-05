package com.smsforwarder.app

import android.content.Context

/**
 * Delivers a queued inbound SMS immediately, on whatever thread calls it, so an
 * arriving message reaches the backend without waiting for the scheduler.
 * The WorkManager job remains as the retry path for anything not confirmed here.
 */
object InboundDispatcher {

    /** @return true when the backend confirmed delivery. */
    fun deliver(context: Context, messageId: String): Boolean {
        val store = PendingSmsStore.get(context)
        val record = store.get(messageId) ?: return false
        if (record.state != DeliveryState.PENDING) return record.state == DeliveryState.DELIVERED

        val config = AppConfig(context)
        if (config.baseUrl.isBlank() || config.deviceId.isBlank() || config.deviceToken.isBlank()) {
            store.markState(messageId, DeliveryState.FAILED, "missing_config")
            return false
        }
        if (record.attempts >= RetryPolicy.MAX_ATTEMPTS) {
            store.markState(messageId, DeliveryState.FAILED, "max_attempts")
            return false
        }

        store.incrementAttempts(messageId)
        val payload = SmsPayload(
            sender = record.sender,
            message = record.body,
            receivedAt = SmsPayload.formatTimestamp(record.receivedAtMillis),
            deviceId = config.deviceId,
            messageId = record.messageId,
            senderName = record.senderName,
            deviceInfo = DeviceIdentity.info(context).toString()
        )
        val result = ApiClient(config.baseUrl).postSms(config.deviceToken, payload.toJson())
        return when (RetryPolicy.decide(result.httpCode)) {
            RetryPolicy.Decision.DELIVERED -> {
                store.markState(messageId, DeliveryState.DELIVERED, null)
                true
            }
            RetryPolicy.Decision.RETRY -> {
                store.markState(messageId, DeliveryState.PENDING, result.error ?: "http_${result.httpCode}")
                false
            }
            RetryPolicy.Decision.GIVE_UP -> {
                store.markState(messageId, DeliveryState.FAILED, "http_${result.httpCode}")
                false
            }
        }
    }
}
