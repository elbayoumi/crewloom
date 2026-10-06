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
    private val neededPermissions = arrayOf(
        Manifest.permission.RECEIVE_SMS,
        Manifest.permission.SEND_SMS,
        Manifest.permission.POST_NOTIFICATIONS
    )
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
        binding.switchFastSend.isChecked = PushService.isEnabled(this)
        binding.switchFastSend.setOnCheckedChangeListener { _, checked ->
            PushService.setEnabled(this, checked)
            binding.textStatus.text = if (checked) "Instant send ON" else "Instant send OFF (battery saver)"
        }
        binding.btnPermissions.setOnClickListener { ensureSmsPermission() }
        binding.btnBattery.setOnClickListener { openBatteryOptimization() }

        scheduleOutboxCheck()
        TickerWorker.kick(this)
        KeepAliveReceiver.arm(this)
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
        recoverFailed()
        Toast.makeText(this, "Registered", Toast.LENGTH_SHORT).show()
        refreshStatus()
    }

    /** Re-queue messages that failed only because configuration was missing. */
    private fun recoverFailed() {
        val store = PendingSmsStore.get(this)
        for (id in store.failedIds("missing_config")) {
            store.resetToPending(id)
            SmsReceiver.enqueue(this, id)
        }
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
                val base = config.baseUrl.trimEnd('/')
                val conn = (java.net.URL(base + "/api/v1/devices/register").openConnection() as java.net.HttpURLConnection).apply {
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
        val data = intent.data ?: return
        if (data.scheme == "rveta" || data.scheme == "http" || data.scheme == "https") {
            processQr(data.toString(), fromScan = false)
        }
    }

    private fun approveSession(sessionId: String) {
        Thread {
            try {
                val cfg = AppConfig(this)
                val body = org.json.JSONObject()
                    .put("session", sessionId)
                    .put("token", cfg.deviceToken)
                    .toString()
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
                runOnUiThread { toast(if (ok) "Linked ✓" else "Link failed") }
            } catch (e: Exception) {
                runOnUiThread { toast("Link error") }
            }
        }.start()
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
            processQr(text, fromScan = true)
        }
    }

    /** Single handler for every QR source: in-app scanner and OS deep links. */
    private fun processQr(rawText: String, fromScan: Boolean) {
        val raw = rawText.trim()
        val uri = runCatching { Uri.parse(raw) }.getOrNull()
        if (uri == null) return toastInvalid(fromScan)

        val isWeb = uri.scheme == "http" || uri.scheme == "https"
        val host = uri.host ?: ""
        if (isWeb && !isTrustedHost(host)) return toastInvalid(fromScan)
        val session = uri.getQueryParameter("session") ?: param(raw, "session")
        val deviceId = uri.getQueryParameter("d") ?: param(raw, "d")
        val token = uri.getQueryParameter("t") ?: param(raw, "t")
        val base = uri.getQueryParameter("b") ?: param(raw, "b")

        // 0) keep instant-send mode in sync with the dashboard state
        syncPush()

        // 1) laptop <-> phone session link (generated by the dashboard)
        if (!session.isNullOrBlank() && (isWeb || uri.scheme == "rveta")) {
            approveSession(session)
            toast(if (fromScan) "Linking…" else "Linked ✓")
            return
        }

        // 2) device pairing link
        if (!deviceId.isNullOrBlank() && !token.isNullOrBlank()) {
            val config = AppConfig(this)
            if (!base.isNullOrBlank()) config.baseUrl = base
            if (config.baseUrl.isBlank()) config.baseUrl = "https://bmc.moaf.uk/sms-backend"
            if (config.deviceId.isBlank()) config.deviceId = deviceId
            config.deviceToken = token
            lockDeviceId()
            registerDevice()
            refreshStatus()
            toast("Device linked")
            return
        }

        // 3) rveta://session?d=<sid>
        if (uri.scheme == "rveta" && uri.host == "session") {
            val sid = deviceId ?: return toastInvalid(fromScan)
            approveSession(sid)
            toast("Linking…")
            return
        }

        toastInvalid(fromScan)
    }

    /** Ask the server whether anyone has the dashboard open; enable fast send if so. */
    private fun syncPush() {
        Thread {
            try {
                val cfg = AppConfig(this)
                if (cfg.deviceId.isBlank() || cfg.deviceToken.isBlank() || cfg.baseUrl.isBlank()) return@Thread
                val url = cfg.baseUrl.trimEnd('/') + "/api/v1/push/status?device_id=" +
                    java.net.URLEncoder.encode(cfg.deviceId, "UTF-8")
                val conn = (java.net.URL(url).openConnection() as java.net.HttpURLConnection).apply {
                    requestMethod = "GET"
                    connectTimeout = 8000
                    readTimeout = 8000
                    setRequestProperty("Authorization", "Bearer " + cfg.deviceToken)
                }
                val body = conn.inputStream.bufferedReader().readText()
                conn.disconnect()
                val open = org.json.JSONObject(body).optBoolean("dashboard_open", false)
                Log.i("RvetaPush", "dashboard_open=$open -> " + if (open) "instant mode" else "periodic mode")
                RvetaSms.syncPushMode(this, open)
            } catch (e: Exception) {
                Log.w("RvetaPush", "status check failed: " + e.javaClass.simpleName)
            }
        }.start()
    }

    private fun param(raw: String, key: String): String? =
        raw.substringAfter('?', "").split('&').firstOrNull {
            it.substringBefore('=') == key
        }?.substringAfter('=', "")
            ?.let { runCatching { Uri.decode(it) }.getOrDefault(it) }
            ?.takeIf { it.isNotBlank() }

    /** Only our own backend may reconfigure this device. */
    private fun isTrustedHost(host: String): Boolean =
        host == "bmc.moaf.uk" || host == "www.bmc.moaf.uk"

    private fun toastInvalid(fromScan: Boolean) {
        Toast.makeText(this, "Invalid QR code", Toast.LENGTH_SHORT).show()
    }

    private fun toast(msg: String) = Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()

    override fun onResume() {
        super.onResume()
        lockDeviceId()
        syncPush()
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
        val storeBroken = AppConfig(this).tokenStoreError != null
        binding.textLinked.text = when {
            storeBroken -> "Secure storage unavailable — pairing cannot save"
            config.deviceToken.isBlank() -> "Not linked — scan a QR"
            else -> "Linked ✓"
        }
        binding.textLinked.setTextColor(
            Color.parseColor(if (storeBroken || config.deviceToken.isBlank()) "#F44336" else "#4CAF50")
        )
    }
}
