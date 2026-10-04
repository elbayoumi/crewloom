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
    private val REQ_SCAN = 501

    private val neededPermissions = arrayOf(Manifest.permission.RECEIVE_SMS, Manifest.permission.SEND_SMS)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val config = AppConfig(this)
        handlePairing(intent)
        if (AppConfig(this).deviceId.isBlank()) AppConfig(this).deviceId = DeviceIdentity.stableId(this)
        intent.getStringExtra("base_url")?.let { config.baseUrl = it }
        intent.getStringExtra("device_id")?.let { config.deviceId = it }
        intent.getStringExtra("token")?.let { config.deviceToken = it }
        binding.editBaseUrl.setText(config.baseUrl)
        binding.editDeviceId.setText(config.deviceId)

        binding.btnSave.setOnClickListener {
            config.baseUrl = binding.editBaseUrl.text.toString()
            config.deviceId = binding.editDeviceId.text.toString()
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

        binding.btnScan.setOnClickListener {
            try {
                startActivityForResult(Intent(this, ScanQrActivity::class.java), REQ_SCAN)
            } catch (e: Exception) {
                Toast.makeText(this, "Scanner unavailable", Toast.LENGTH_SHORT).show()
            }
        }
        binding.btnCheckSends.setOnClickListener {
            RvetaSms.checkOutbox(this)
            Toast.makeText(this, "Checking pending sends…", Toast.LENGTH_SHORT).show()
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

    private fun handlePairing(intent: Intent) {
        if (intent.data?.scheme != "rveta") return
        val config = AppConfig(this)
        val d = intent.data?.getQueryParameter("d")
        val t = intent.data?.getQueryParameter("t")
        if (!d.isNullOrBlank() && !t.isNullOrBlank()) {
            if (config.baseUrl.isBlank()) config.baseUrl = "https://bmc.moaf.uk/sms-backend"
            config.deviceId = d
            config.deviceToken = t
            Toast.makeText(this, "Paired: $d", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handlePairing(intent)
        val config = AppConfig(this)
        handlePairing(intent)
        if (AppConfig(this).deviceId.isBlank()) AppConfig(this).deviceId = DeviceIdentity.stableId(this)
        intent.getStringExtra("base_url")?.let { config.baseUrl = it }
        intent.getStringExtra("device_id")?.let { config.deviceId = it }
        intent.getStringExtra("token")?.let { config.deviceToken = it }
        binding.editBaseUrl.setText(config.baseUrl)
        binding.editDeviceId.setText(config.deviceId)
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

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQ_SCAN && resultCode == RESULT_OK) {
            val text = data?.getStringExtra("scan_result") ?: return
            if (applyPairingData(text)) {
                Toast.makeText(this, "Device linked", Toast.LENGTH_SHORT).show()
                refreshStatus()
            } else {
                Toast.makeText(this, "Invalid QR code", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun applyPairingData(text: String): Boolean {
        val uri = android.net.Uri.parse(text)
        if (uri.scheme != "rveta" && uri.scheme != "https") return false
        val d = uri.getQueryParameter("d")?.takeIf { it.isNotBlank() && it != "undefined" } ?: return false
        val t = uri.getQueryParameter("t")?.takeIf { it.isNotBlank() && it != "undefined" } ?: return false
        val b = uri.getQueryParameter("b")
        val config = AppConfig(this)
        if (!b.isNullOrBlank()) config.baseUrl = b
        if (config.baseUrl.isBlank()) config.baseUrl = "https://bmc.moaf.uk/sms-backend"
        config.deviceId = d
        config.deviceToken = t
        binding.editDeviceId.setText(d)
        return true
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
                messageId = "test-" + java.util.UUID.randomUUID().toString(),
                deviceInfo = DeviceIdentity.info(this@MainActivity).toString()
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
        binding.textLast.text = "Last status: " + store.lastStatus() + "\nDevice fingerprint: " + DeviceIdentity.fingerprintShort(this)
    }
}
