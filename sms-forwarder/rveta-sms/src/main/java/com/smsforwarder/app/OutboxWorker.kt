package com.smsforwarder.app

import android.content.Context
import androidx.work.Worker
import androidx.work.WorkerParameters

/** Periodic fallback that drains the outbox when the live push link is unavailable. */
class OutboxWorker(context: Context, params: WorkerParameters) : Worker(context, params) {

    companion object {
        private const val MAX_ATTEMPTS = 10
    }

    override fun doWork(): Result {
        val result = OutboxDispatcher.dispatch(applicationContext)
        return when {
            result >= 0 -> Result.success()
            runAttemptCount >= MAX_ATTEMPTS -> Result.success()
            else -> Result.retry()
        }
    }
}
