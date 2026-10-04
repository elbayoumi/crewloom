package com.smsforwarder.app

import android.content.Intent
import android.provider.Telephony

data class ParsedSms(
    val sender: String,
    val body: String,
    val receivedAtMillis: Long,
    val subscriptionId: Int
)

object SmsParser {

    const val EXTRA_SUBSCRIPTION = "subscription"

    fun parseIntent(intent: Intent): List<ParsedSms> {
        if (intent.action != Telephony.Sms.Intents.SMS_RECEIVED_ACTION) return emptyList()
        val parts = Telephony.Sms.Intents.getMessagesFromIntent(intent) ?: return emptyList()
        val subscriptionId = intent.getIntExtra(EXTRA_SUBSCRIPTION, -1)
        val grouped = LinkedHashMap<String, MutableList<android.telephony.SmsMessage>>()
        for (part in parts) {
            val key = (part.displayOriginatingAddress ?: "") + "|" + part.timestampMillis
            grouped.getOrPut(key) { mutableListOf() }.add(part)
        }
        val result = mutableListOf<ParsedSms>()
        for (group in grouped.values) {
            val sender = group.first().displayOriginatingAddress ?: continue
            val body = group.joinToString("") { it.displayMessageBody ?: "" }
            result.add(
                ParsedSms(
                    sender = sender,
                    body = body,
                    receivedAtMillis = group.first().timestampMillis,
                    subscriptionId = subscriptionId
                )
            )
        }
        return result
    }
}
