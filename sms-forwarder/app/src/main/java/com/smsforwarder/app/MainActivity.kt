package com.smsforwarder.app

import android.Manifest
import android.app.AlertDialog
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.smsforwarder.app.databinding.ActivityMainBinding

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private val neededPermissions = arrayOf(Manifest.permission.RECEIVE_SMS, Manifest.permission.SEND_SMS)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val config = AppConfig(this)
        intent.getStringExtra("base_url")?.let { config.baseUrl = it }
        intent.getStringExtra("device_id")?.let { config.deviceId = it }
        intent.getStringExtra("token")?.let { config.deviceToken = it }
        binding.editBaseUrl.setText(config.baseUrl)
        binding.editDeviceId.setText(config.deviceId)
        binding.editToken.setText(config.deviceToken)

        binding.btnSave.setOnClickListener {
            config.baseUrl = binding.editBaseUrl.text.toString()
            config.deviceId = binding.editDeviceId.text.toString()
            config.deviceToken = binding.editToken.text.toString()
            Toast.makeText(this, "Saved", Toast.LENGTH_SHORT).show()
            val store = PendingSmsStore.get(this)
            for (id in store.allIdsByState(DeliveryState.FAILED)) {
                val rec = store.get(id)
                if (rec != null && rec.lastError == "missing_config") {
                    store.resetToPending(id)
                    SmsReceiver.enqueue(this, id)
                }
            }
            refreshStatus()
        }

        binding.btnTest.setOnClickListener { runTest() }
        binding.btnRefresh.setOnClickListener { refreshStatus() }
        binding.btnPermissions.setOnClickListener { ensureSmsPermission() }
        binding.btnBattery.setOnClickListener { openBatteryOptimization() }

        val outboxPeriodic = androidx.work.PeriodicWorkRequestBuilder<OutboxWorker>(15, java.util.concurrent.TimeUnit.MINUTES)
            .setConstraints(androidx.work.Constraints.Builder().setRequiredNetworkType(androidx.work.NetworkType.CONNECTED).build())
            .build()
        androidx.work.WorkManager.getInstance(this).enqueueUniquePeriodicWork("outbox_check", androidx.work.ExistingPeriodicWorkPolicy.KEEP, outboxPeriodic)
        androidx.work.WorkManager.getInstance(this).enqueueUniqueWork("outbox_now", androidx.work.ExistingWorkPolicy.KEEP, androidx.work.OneTimeWorkRequestBuilder<OutboxWorker>().build())

        refreshStatus()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        val config = AppConfig(this)
        intent.getStringExtra("base_url")?.let { config.baseUrl = it }
        intent.getStringExtra("device_id")?.let { config.deviceId = it }
        intent.getStringExtra("token")?.let { config.deviceToken = it }
        binding.editBaseUrl.setText(config.baseUrl)
        binding.editDeviceId.setText(config.deviceId)
        binding.editToken.setText(config.deviceToken)
    }

    override fun onResume() {
        super.onResume()
        if (missingPermissions().isNotEmpty()) {
            binding.textPermission.text = "⚠ SMS permission is required — tap \"Grant permissions\""
            binding.textPermission.setTextColor(android.graphics.Color.parseColor("#F44336"))
            ensureSmsPermission()
        } else {
            binding.textPermission.text = "✓ SMS permission granted"
            binding.textPermission.setTextColor(android.graphics.Color.parseColor("#4CAF50"))
        }
        refreshStatus()
    }

    private fun missingPermissions(): List<String> =
        neededPermissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }

    private fun ensureSmsPermission() {
        val missing = missingPermissions()
        if (missing.isNotEmpty()) {
            if (missing.any { ActivityCompat.shouldShowRequestPermissionRationale(this, it) }) {
                AlertDialog.Builder(this)
                    .setTitle("Permission required")
                    .setMessage("This app must receive SMS to forward them to your backend. Please allow the permission.")
                    .setPositiveButton("Allow") { _, _ -> ActivityCompat.requestPermissions(this, missing.toTypedArray(), 100) }
                    .setNegativeButton("Open settings") { _, _ -> openAppSettings() }
                    .setCancelable(false)
                    .show()
            } else {
                ActivityCompat.requestPermissions(this, missing.toTypedArray(), 100)
            }
        }
    }

    private fun openAppSettings() {
        startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
            data = Uri.fromParts("package", packageName, null)
        })
    }

    private fun openBatteryOptimization() {
        try {
            val pm = getSystemService(POWER_SERVICE) as PowerManager
            if (!pm.isIgnoringBatteryOptimizations(packageName)) {
                startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                    data = Uri.parse("package:$packageName")
                })
            } else {
                Toast.makeText(this, "Battery optimization already disabled", Toast.LENGTH_SHORT).show()
            }
        } catch (e: Exception) {
            startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
        }
    }

    private fun runTest() {
        val config = AppConfig(this)
        if (config.baseUrl.isBlank() || config.deviceToken.isBlank() || config.deviceId.isBlank()) {
            binding.textStatus.text = "Status: configure URL, token and device id first"
            return
        }
        Thread {
            val payload = SmsPayload(
                sender = "+10000000000",
                message = "test ping",
                receivedAt = SmsPayload.formatTimestamp(System.currentTimeMillis()),
                deviceId = config.deviceId,
                messageId = "test-" + java.util.UUID.randomUUID().toString()
            )
            val result = ApiClient(config.baseUrl).postSms(config.deviceToken, payload.toJson())
            runOnUiThread {
                binding.textStatus.text = "Status: " + when {
                    result.httpCode != null -> "HTTP ${result.httpCode}"
                    else -> "error ${result.error}"
                }
            }
        }.start()
    }

    private fun refreshStatus() {
        val store = PendingSmsStore.get(this)
        binding.textPending.text = "Pending queue: " + store.pendingCount()
        binding.textLast.text = "Last status: " + store.lastStatus()
    }
}
