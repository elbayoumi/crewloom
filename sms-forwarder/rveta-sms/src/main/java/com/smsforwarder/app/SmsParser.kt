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
        if (parts.isEmpty()) return emptyList()
        val subscriptionId = intent.getIntExtra(EXTRA_SUBSCRIPTION, -1)

        val groups = LinkedHashMap<String, MutableList<android.telephony.SmsMessage>>()
        for (part in parts) {
            val sender = part.displayOriginatingAddress ?: continue
            groups.getOrPut(sender) { mutableListOf() }.add(part)
        }

        return groups.map { (sender, group) ->
            ParsedSms(
                sender = sender,
                body = group.joinToString("") { it.displayMessageBody ?: "" },
                receivedAtMillis = group.first().timestampMillis,
                subscriptionId = subscriptionId
            )
        }
    }
}
