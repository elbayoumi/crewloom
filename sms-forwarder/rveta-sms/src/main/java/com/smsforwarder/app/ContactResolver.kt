package com.smsforwarder.app

import android.content.Context
import android.net.Uri
import android.provider.ContactsContract
import java.util.concurrent.ConcurrentHashMap

object ContactResolver {

    private val cache = ConcurrentHashMap<String, String>()

    fun lookup(context: Context, number: String): String {
        cache[number]?.let { return it }
        val normalized = number.filter { it.isDigit() || it == '+' }
        if (normalized.length < 3) return ""
        val uri: Uri = Uri.withAppendedPath(
            ContactsContract.PhoneLookup.CONTENT_FILTER_URI,
            Uri.encode(normalized)
        )
        var name = ""
        try {
            context.contentResolver.query(
                uri,
                arrayOf(ContactsContract.PhoneLookup.DISPLAY_NAME),
                null,
                null,
                null
            )?.use { cursor ->
                if (cursor.moveToFirst()) {
                    val idx = cursor.getColumnIndex(ContactsContract.PhoneLookup.DISPLAY_NAME)
                    if (idx >= 0) name = cursor.getString(idx) ?: ""
                }
            }
        } catch (e: Exception) {
            name = ""
        }
        cache[number] = name
        return name
    }
}
