package com.smsforwarder.app

import org.junit.Assert.assertTrue
import org.junit.Assert.assertEquals
import org.junit.Test
import java.text.SimpleDateFormat
import java.util.Locale

class SmsPayloadTest {
    @Test fun jsonMatchesContract() {
        val p = SmsPayload("+201001234567", "hello", "2026-10-04T01:36:00+03:00", "device-01", "id-1")
        val o = org.json.JSONObject(p.toJson())
        assertEquals("+201001234567", o.getString("sender"))
        assertEquals("hello", o.getString("message"))
        assertEquals("2026-10-04T01:36:00+03:00", o.getString("received_at"))
        assertEquals("device-01", o.getString("device_id"))
        assertEquals("id-1", o.getString("message_id"))
    }

    @Test fun timestampIsIso8601() {
        val s = SmsPayload.formatTimestamp(System.currentTimeMillis())
        val sdf = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US)
        sdf.isLenient = false
        sdf.parse(s)
    }
}
