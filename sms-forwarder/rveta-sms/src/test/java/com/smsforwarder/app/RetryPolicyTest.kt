package com.smsforwarder.app

import org.junit.Assert.assertEquals
import org.junit.Test

class RetryPolicyTest {
    @Test fun successCodesDelivered() {
        for (code in listOf(200, 201, 204, 299)) assertEquals(RetryPolicy.Decision.DELIVERED, RetryPolicy.decide(code))
    }
    @Test fun retryableCodes() {
        for (code in listOf(408, 429, 500, 502, 503, 599)) assertEquals(RetryPolicy.Decision.RETRY, RetryPolicy.decide(code))
        assertEquals(RetryPolicy.Decision.RETRY, RetryPolicy.decide(null))
    }
    @Test fun permanentFailures() {
        for (code in listOf(400, 401, 403, 404, 422)) assertEquals(RetryPolicy.Decision.GIVE_UP, RetryPolicy.decide(code))
    }
}
