package com.smsforwarder.app

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.view.animation.LinearInterpolator
import android.util.Log
import android.os.PowerManager
import android.provider.Settings
import android.animation.ObjectAnimator
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.smsforwarder.app.databinding.ActivityMainBinding

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private val REQ_SCAN = 501
    private val neededPermissions = arrayOf(Manifest.permission.RECEIVE_SMS, Manifest.permission.SEND_SMS)
    private var pulse: ObjectAnimator? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        handlePairing(intent)
        val config = AppConfig(this)
        lockDeviceId()

        binding.btnScan.setOnClickListener {
            try {
                startActivityForResult(Intent(this, ScanQrActivity::class.java), REQ_SCAN)
            } catch (e: Exception) {
                Toast.makeText(this, "Scanner unavailable", Toast.LENGTH_SHORT).show()
            }
        }
        binding.btnSave.setOnClickListener { saveAndRegister() }
        binding.btnRefresh.setOnClickListener { refreshStatus() }
        binding.btnTest.setOnClickListener { runTest() }
        binding.btnPermissions.setOnClickListener { ensureSmsPermission() }
        binding.btnBattery.setOnClickListener { openBatteryOptimization() }

        scheduleOutboxCheck()
        refreshStatus()
        startPulse()
    }

    private fun startPulse() {
        pulse?.cancel()
        pulse = ObjectAnimator.ofFloat(binding.pulseDot, "alpha", 1f, 0.25f).apply {
            duration = 900
            repeatMode = ObjectAnimator.REVERSE
            repeatCount = ObjectAnimator.INFINITE
            interpolator = LinearInterpolator()
            start()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        pulse?.cancel()
    }

    private fun lockDeviceId() {
        val config = AppConfig(this)
        val auto = DeviceIdentity.immutableId(this)
        if (config.deviceId.isBlank()) config.deviceId = auto
        binding.textDeviceId.text = config.deviceId
        binding.editName.setText(config.deviceName)
    }

    private fun saveAndRegister() {
        val config = AppConfig(this)
        config.deviceName = binding.editName.text.toString().trim()
        lockDeviceId()
        registerDevice()
        Toast.makeText(this, "Registered", Toast.LENGTH_SHORT).show()
        refreshStatus()
    }

    private fun registerDevice() {
        val config = AppConfig(this)
        if (config.deviceId.isBlank() || config.deviceToken.isBlank()) return
        Thread {
            try {
                val info = DeviceIdentity.info(this).toString()
                val body = org.json.JSONObject()
                    .put("device_id", config.deviceId)
                    .put("name", config.deviceName)
                    .put("device_info", info)
                    .toString()
                val conn = (java.net.URL("https://bmc.moaf.uk/sms-backend/api/v1/devices/register").openConnection() as java.net.HttpURLConnection).apply {
                    requestMethod = "POST"
                    doOutput = true
                    connectTimeout = 10000
                    readTimeout = 10000
                    setRequestProperty("Authorization", "Bearer " + config.deviceToken)
                    setRequestProperty("Content-Type", "application/json")
                }
                conn.outputStream.use { it.write(body.toByteArray()) }
                conn.responseCode
                conn.disconnect()
            } catch (e: Exception) {
                Log.w("Rveta", "register failed")
            }
        }.start()
    }

    private fun scheduleOutboxCheck() {
        val periodic = androidx.work.PeriodicWorkRequestBuilder<OutboxWorker>(15, java.util.concurrent.TimeUnit.MINUTES)
            .setConstraints(androidx.work.Constraints.Builder().setRequiredNetworkType(androidx.work.NetworkType.CONNECTED).build())
            .build()
        androidx.work.WorkManager.getInstance(this).enqueueUniquePeriodicWork(
            "outbox_check", androidx.work.ExistingPeriodicWorkPolicy.KEEP, periodic
        )
    }

    private fun handlePairing(intent: Intent) {
        if (intent.data?.scheme != "rveta") return
        if (intent.data?.host == "session") {
            val sid = intent.data?.getQueryParameter("d") ?: return
            Thread {
                try {
                    val cfg = AppConfig(this)
                    val body = "{\"session\":\"" + sid + "\",\"token\":\"" + cfg.deviceToken + "\"}"
                    val conn = (java.net.URL(cfg.baseUrl.trimEnd('/') + "/api/session/grant").openConnection() as java.net.HttpURLConnection).apply {
                        requestMethod = "POST"
                        doOutput = true
                        connectTimeout = 10000
                        readTimeout = 10000
                        setRequestProperty("Authorization", "Bearer " + cfg.deviceToken)
                        setRequestProperty("Content-Type", "application/json")
                    }
                    conn.outputStream.use { it.write(body.toByteArray()) }
                    val ok = conn.responseCode in 200..299
                    conn.disconnect()
                    runOnUiThread { Toast.makeText(this, if (ok) "Linked ✓" else "Link failed", Toast.LENGTH_SHORT).show() }
                } catch (e: Exception) {
                    runOnUiThread { Toast.makeText(this, "Link error", Toast.LENGTH_SHORT).show() }
                }
            }.start()
            return
        }
        applyPairingData(intent.data?.toString() ?: "")
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handlePairing(intent)
        lockDeviceId()
        refreshStatus()
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQ_SCAN && resultCode == RESULT_OK) {
            val text = data?.getStringExtra("scan_result") ?: return
            if (applyPairingData(text)) {
                registerDevice()
                Toast.makeText(this, "Device linked", Toast.LENGTH_SHORT).show()
                refreshStatus()
            } else {
                Toast.makeText(this, "Invalid QR code", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun applyPairingData(text: String): Boolean {
        val uri = Uri.parse(text)
        if (uri.scheme != "rveta" && uri.scheme != "https") return false
        if (uri.host == "session") return true
        val d = uri.getQueryParameter("d")?.takeIf { it.isNotBlank() && it != "undefined" } ?: return false
        val t = uri.getQueryParameter("t")?.takeIf { it.isNotBlank() && it != "undefined" } ?: return false
        val b = uri.getQueryParameter("b")
        val config = AppConfig(this)
        if (!b.isNullOrBlank()) config.baseUrl = b
        if (config.baseUrl.isBlank()) config.baseUrl = "https://bmc.moaf.uk/sms-backend"
        if (config.deviceId.isBlank()) config.deviceId = d
        config.deviceToken = t
        lockDeviceId()
        return true
    }

    override fun onResume() {
        super.onResume()
        lockDeviceId()
        if (AppConfig(this).deviceToken.isNotBlank()) registerDevice()
        if (missingPermissions().isNotEmpty()) {
            binding.textPermission.text = "SMS permission required"
            binding.textPermission.setTextColor(Color.parseColor("#F44336"))
            ensureSmsPermission()
        } else {
            binding.textPermission.text = "SMS permission granted"
            binding.textPermission.setTextColor(Color.parseColor("#4CAF50"))
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
                android.app.AlertDialog.Builder(this)
                    .setTitle("Permission required")
                    .setMessage("This app needs SMS permission to forward your messages.")
                    .setPositiveButton("Allow") { _, _ -> ActivityCompat.requestPermissions(this, missing.toTypedArray(), 100) }
                    .setNegativeButton("Open settings") { _, _ ->
                        startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                            data = Uri.fromParts("package", packageName, null)
                        })
                    }
                    .setCancelable(false).show()
            } else {
                ActivityCompat.requestPermissions(this, missing.toTypedArray(), 100)
            }
        }
    }

    private fun openBatteryOptimization() {
        try {
            val pm = getSystemService(POWER_SERVICE) as PowerManager
            if (!pm.isIgnoringBatteryOptimizations(packageName)) {
                startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                    data = Uri.parse("package:$packageName")
                })
            } else {
                Toast.makeText(this, "Already disabled", Toast.LENGTH_SHORT).show()
            }
        } catch (e: Exception) {
            startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
        }
    }

    private fun runTest() {
        val config = AppConfig(this)
        if (config.deviceId.isBlank() || config.deviceToken.isBlank()) {
            binding.textStatus.text = "Scan a QR to link first"
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
                binding.textStatus.text = "Status: " + (result.httpCode?.let { "HTTP $it" } ?: "error ${result.error}")
            }
        }.start()
    }

    private fun refreshStatus() {
        val config = AppConfig(this)
        val store = PendingSmsStore.get(this)
        binding.textPending.text = "Pending queue: " + store.pendingCount()
        binding.textLast.text = "Last: " + store.lastStatus()
        binding.textLinked.text = if (config.deviceToken.isBlank()) "Not linked — scan a QR" else "Linked ✓"
        binding.textLinked.setTextColor(
            Color.parseColor(if (config.deviceToken.isBlank()) "#F44336" else "#4CAF50")
        )
    }
}
