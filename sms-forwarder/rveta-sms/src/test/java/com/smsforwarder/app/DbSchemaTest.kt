package com.smsforwarder.app

import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Regression guard: a fresh install runs onCreate() only (never onUpgrade()).
 * Any column the write path uses must therefore exist in the CREATE TABLE statement,
 * otherwise every inbound SMS crashes the app on a new device.
 */
class DbSchemaTest {

    @Test
    fun createTableContainsEveryColumnWrittenAtRuntime() {
        val source = File("src/main/java/com/smsforwarder/app/PendingSmsStore.kt").readText()
        val create = source.substringAfter("CREATE TABLE pending_sms (").substringBefore("UNIQUE")
        listOf(
            "message_id", "sender", "body", "received_at_ms",
            "subscription_id", "sender_name", "state", "attempts",
            "last_error", "created_at", "updated_at"
        ).forEach { column ->
            assertTrue("CREATE TABLE is missing column '$column'", create.contains(column))
        }
    }

    @Test
    fun cleanupNeverDeletesUndeliveredRows() {
        val source = File("src/main/java/com/smsforwarder/app/PendingSmsStore.kt").readText()
        val cleanup = source.substringAfter("fun cleanup()").substringBefore("fun lastStatus")
        val pendingDelete = cleanup.contains("state='PENDING' AND message_id NOT IN")
        assertTrue("cleanup() must not discard PENDING (undelivered) messages", !pendingDelete)
    }
}
