package com.smsforwarder.app

import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.nio.charset.StandardCharsets

class ApiClient(private val baseUrl: String) {

    data class Result(
        val httpCode: Int?,
        val error: String?
    )

    fun postSms(token: String, jsonBody: String): Result {
        var conn: HttpURLConnection? = null
        return try {
            val url = URL(baseUrl.trimEnd('/') + "/api/v1/incoming-sms")
            if (!url.protocol.equals("https", ignoreCase = true) && !url.host.equals("localhost") && !url.host.equals("127.0.0.1")) {
                return Result(null, "insecure_url")
            }
            conn = url.openConnection() as HttpURLConnection
            conn.requestMethod = "POST"
            conn.connectTimeout = 15000
            conn.readTimeout = 20000
            conn.doOutput = true
            conn.setRequestProperty("Authorization", "Bearer $token")
            conn.setRequestProperty("Content-Type", "application/json")
            conn.setRequestProperty("Accept", "application/json")
            val bytes = jsonBody.toByteArray(StandardCharsets.UTF_8)
            conn.outputStream.use { it.write(bytes) }
            val code = conn.responseCode
            Result(code, null)
        } catch (e: IOException) {
            Result(null, e.javaClass.simpleName)
        } catch (e: Exception) {
            Result(null, e.javaClass.simpleName)
        } finally {
            conn?.disconnect()
        }
    }
}
