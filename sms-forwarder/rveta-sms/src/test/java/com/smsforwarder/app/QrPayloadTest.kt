package com.smsforwarder.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** Mirrors MainActivity.processQr() routing rules so we can prove QR handling without a device. */
object QrRoute {
    sealed class Result {
        object Invalid : Result()
        data class Session(val id: String) : Result()
        data class Pair(val deviceId: String, val token: String) : Result()
    }

    private fun param(raw: String, key: String): String? =
        raw.substringAfter('?', "").split('&').firstOrNull { it.substringBefore('=') == key }
            ?.substringAfter('=', "")?.takeIf { it.isNotBlank() }

    fun route(text: String): Result {
        val raw = text.trim()
        val scheme = raw.substringBefore("://", "")
        val isWeb = scheme == "http" || scheme == "https"
        val afterHost = raw.substringAfter("://", "")
        val host = afterHost.substringBefore('/').substringBefore('?')
        val session = param(raw, "session")
        val d = param(raw, "d")
        val t = param(raw, "t")
        if (!session.isNullOrBlank() && (isWeb || scheme == "rveta")) return Result.Session(session)
        if (!d.isNullOrBlank() && !t.isNullOrBlank()) return Result.Pair(d, t)
        if (scheme == "rveta" && host == "session" && !d.isNullOrBlank()) return Result.Session(d)
        return Result.Invalid
    }
}

class QrPayloadTest {
    @Test fun dashboardSessionHttpsLink() {
        val r = QrRoute.route("https://bmc.moaf.uk/sms-backend/go?session=8addbacb31564fc4")
        assertTrue(r is QrRoute.Result.Session)
        assertEquals("8addbacb31564fc4", (r as QrRoute.Result.Session).id)
    }
    @Test fun dashboardPairHttpsLink() {
        val r = QrRoute.route("https://bmc.moaf.uk/sms-backend/go?d=rv-abc&t=tok123")
        assertTrue(r is QrRoute.Result.Pair)
    }
    @Test fun deepLinkSession() {
        val r = QrRoute.route("rveta://session?d=beef1234")
        assertEquals("beef1234", (r as QrRoute.Result.Session).id)
    }
    @Test fun deepLinkPair() {
        val r = QrRoute.route("rveta://pair?d=rv-xyz&t=tok999")
        assertEquals("rv-xyz", (r as QrRoute.Result.Pair).deviceId)
        assertEquals("tok999", (r as QrRoute.Result.Pair).token)
    }
    @Test fun foreignQrIsInvalid() {
        assertTrue(QrRoute.route("https://example.com/hello") is QrRoute.Result.Invalid)
    }
    @Test fun urlEncodedTokenStillRoutes() {
        val r = QrRoute.route("rveta://pair?d=rv-1&t=abc%2Fdef%3D")
        assertTrue(r is QrRoute.Result.Pair)
    }
}
