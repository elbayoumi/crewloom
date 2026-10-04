package com.smsforwarder.app

enum class DeliveryState { PENDING, DELIVERED, FAILED }

object RetryPolicy {
    enum class Decision { DELIVERED, RETRY, GIVE_UP }

    fun decide(httpCode: Int?): Decision {
        if (httpCode == null) return Decision.RETRY
        return when {
            httpCode in 200..299 -> Decision.DELIVERED
            httpCode == 408 || httpCode == 429 -> Decision.RETRY
            httpCode in 500..599 -> Decision.RETRY
            else -> Decision.GIVE_UP
        }
    }

    const val MAX_ATTEMPTS = 25
}
