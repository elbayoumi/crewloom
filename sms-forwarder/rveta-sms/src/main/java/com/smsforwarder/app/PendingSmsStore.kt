package com.smsforwarder.app

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteConstraintException
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import java.util.UUID

data class PendingSms(
    val messageId: String,
    val sender: String,
    val body: String,
    val receivedAtMillis: Long,
    val subscriptionId: Int,
    val senderName: String?,
    val state: DeliveryState,
    val attempts: Int,
    val lastError: String?,
    val createdAt: Long,
    val updatedAt: Long
)

class PendingSmsStore private constructor(context: Context) : SQLiteOpenHelper(context, "pending_sms.db", null, 3) {

    companion object {
        @Volatile private var INSTANCE: PendingSmsStore? = null
        fun get(context: Context): PendingSmsStore {
            return INSTANCE ?: synchronized(this) {
                INSTANCE ?: PendingSmsStore(context.applicationContext).also { INSTANCE = it }
            }
        }
    }

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """CREATE TABLE pending_sms (
                message_id TEXT PRIMARY KEY,
                sender TEXT NOT NULL,
                body TEXT NOT NULL,
                received_at_ms INTEGER NOT NULL,
                subscription_id INTEGER NOT NULL,
                sender_name TEXT,
                state TEXT NOT NULL,
                attempts INTEGER NOT NULL,
                last_error TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(sender, received_at_ms, subscription_id, body)
            )"""
        )
        db.execSQL("CREATE INDEX idx_state ON pending_sms(state)")
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        if (oldVersion < 2) {
            db.execSQL("DROP TABLE IF EXISTS pending_sms")
            onCreate(db)
        }
        if (oldVersion < 3) {
            db.execSQL("ALTER TABLE pending_sms ADD COLUMN sender_name TEXT")
        }
    }

    fun insertIfNew(sender: String, body: String, receivedAtMillis: Long, subscriptionId: Int, senderName: String?): String? {
        val now = System.currentTimeMillis()
        val id = UUID.randomUUID().toString()
        val values = ContentValues().apply {
            put("message_id", id)
            put("sender", sender)
            put("body", body)
            put("received_at_ms", receivedAtMillis)
            put("subscription_id", subscriptionId)
            put("sender_name", senderName)
            put("state", DeliveryState.PENDING.name)
            put("attempts", 0)
            put("created_at", now)
            put("updated_at", now)
        }
        return try {
            val result = writableDatabase.insertWithOnConflict("pending_sms", null, values, SQLiteDatabase.CONFLICT_IGNORE)
            if (result != -1L) id else null
        } catch (e: SQLiteConstraintException) {
            null
        }
    }

    fun get(messageId: String): PendingSms? {
        val cursor = readableDatabase.query("pending_sms", null, "message_id=?", arrayOf(messageId), null, null, null)
        return try { if (cursor.moveToFirst()) fromCursor(cursor) else null } finally { cursor.close() }
    }

    fun pendingCount(): Int {
        val cursor = readableDatabase.rawQuery("SELECT COUNT(*) FROM pending_sms WHERE state=?", arrayOf(DeliveryState.PENDING.name))
        return try { cursor.moveToFirst(); cursor.getInt(0) } finally { cursor.close() }
    }

    fun allIdsByState(state: DeliveryState): List<String> {
        val out = mutableListOf<String>()
        val cursor = readableDatabase.rawQuery("SELECT message_id FROM pending_sms WHERE state=?", arrayOf(state.name))
        try { while (cursor.moveToNext()) out.add(cursor.getString(0)) } finally { cursor.close() }
        return out
    }

    fun markState(messageId: String, state: DeliveryState, lastError: String?) {
        val values = ContentValues().apply {
            put("state", state.name)
            put("last_error", lastError)
            put("updated_at", System.currentTimeMillis())
        }
        writableDatabase.update("pending_sms", values, "message_id=?", arrayOf(messageId))
    }

    fun incrementAttempts(messageId: String) {
        writableDatabase.execSQL(
            "UPDATE pending_sms SET attempts=attempts+1, updated_at=? WHERE message_id=?",
            arrayOf<Any?>(System.currentTimeMillis(), messageId)
        )
    }

    fun resetToPending(messageId: String) {
        writableDatabase.execSQL(
            "UPDATE pending_sms SET state=?, attempts=0, last_error=NULL, updated_at=? WHERE message_id=?",
            arrayOf<Any?>(DeliveryState.PENDING.name, System.currentTimeMillis(), messageId)
        )
    }

    fun failedIds(error: String): List<String> {
        val out = mutableListOf<String>()
        val cursor = readableDatabase.rawQuery(
            "SELECT message_id FROM pending_sms WHERE state=? AND last_error=?",
            arrayOf(DeliveryState.FAILED.name, error)
        )
        try { while (cursor.moveToNext()) out.add(cursor.getString(0)) } finally { cursor.close() }
        return out
    }

    fun delete(messageId: String) {
        writableDatabase.delete("pending_sms", "message_id=?", arrayOf(messageId))
    }

    fun cleanup() {
        val cutoffDelivered = System.currentTimeMillis() - 24L * 60 * 60 * 1000
        val cutoffFailed = System.currentTimeMillis() - 7L * 24 * 60 * 60 * 1000
        writableDatabase.delete("pending_sms", "state=? AND updated_at<?", arrayOf(DeliveryState.DELIVERED.name, cutoffDelivered.toString()))
        writableDatabase.delete("pending_sms", "state=? AND updated_at<?", arrayOf(DeliveryState.FAILED.name, cutoffFailed.toString()))
        // Bound only already-delivered history; PENDING rows are never discarded.
        val cap = 500
        writableDatabase.execSQL(
            "DELETE FROM pending_sms WHERE state='DELIVERED' AND message_id NOT IN (SELECT message_id FROM pending_sms WHERE state='DELIVERED' ORDER BY created_at DESC LIMIT ?)",
            arrayOf<Any?>(cap)
        )
    }

    fun lastStatus(): String {
        val cursor = readableDatabase.rawQuery("SELECT state, last_error FROM pending_sms ORDER BY updated_at DESC LIMIT 1", null)
        return try {
            if (cursor.moveToFirst()) {
                val state = cursor.getString(0)
                val err = cursor.getString(1)
                if (err != null) "$state: $err" else state
            } else "No messages yet"
        } finally { cursor.close() }
    }

    private fun fromCursor(cursor: android.database.Cursor): PendingSms {
        val nameIdx = cursor.getColumnIndex("sender_name")
        return PendingSms(
            messageId = cursor.getString(0),
            sender = cursor.getString(1),
            body = cursor.getString(2),
            receivedAtMillis = cursor.getLong(3),
            subscriptionId = cursor.getInt(4),
            state = runCatching { DeliveryState.valueOf(cursor.getString(5)) }
                .getOrDefault(DeliveryState.PENDING),
            attempts = cursor.getInt(6),
            lastError = cursor.getString(7),
            createdAt = cursor.getLong(8),
            updatedAt = cursor.getLong(9),
            senderName = if (nameIdx >= 0) cursor.getString(nameIdx) else null
        )
    }
}
