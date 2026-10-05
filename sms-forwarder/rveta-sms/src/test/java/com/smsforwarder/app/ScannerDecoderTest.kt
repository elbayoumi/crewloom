package com.smsforwarder.app

import com.google.zxing.BarcodeFormat
import com.google.zxing.EncodeHintType
import com.google.zxing.qrcode.QRCodeWriter
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ScannerDecoderTest {

    private fun qrLuminance(text: String, size: Int = 320): ByteArray {
        val hints = mapOf(EncodeHintType.MARGIN to 1)
        val matrix = QRCodeWriter().encode(text, BarcodeFormat.QR_CODE, size, size, hints)
        val out = ByteArray(size * size)
        for (y in 0 until size) for (x in 0 until size) {
            out[y * size + x] = if (matrix[x, y]) 0 else 0xFF.toByte()
        }
        return out
    }

    @Test
    fun decodesRvetaPairingQr() {
        val text = "rveta://pair?d=rv-abc123&t=abc123def456"
        val lum = qrLuminance(text)
        val side = Math.sqrt(lum.size.toDouble()).toInt()
        assertEquals(text, ScannerDecoder.decode(lum, side, side))
    }

    @Test
    fun decodesHttpsPairingLink() {
        val text = "https://bmc.moaf.uk/sms-backend/go?d=rv-xyz&t=tok999"
        val lum = qrLuminance(text)
        val side = Math.sqrt(lum.size.toDouble()).toInt()
        assertEquals(text, ScannerDecoder.decode(lum, side, side))
    }

    @Test
    fun decodesThroughCameraStyleCropWithRowStride() {
        val text = "rveta://session?d=deadbeef"
        val qr = qrLuminance(text, 200)
        val camW = 640; val camH = 480; val rowStride = 640
        val frame = ByteArray(rowStride * camH) { 0xFF.toByte() }
        // place QR in the center of a camera frame with padded row stride
        val offX = (camW - 200) / 2
        val offY = (camH - 200) / 2
        for (y in 0 until 200) for (x in 0 until 200) {
            frame[(offY + y) * rowStride + offX + x] = qr[y * 200 + x]
        }
        val cropped = ScannerDecoder.cropCenter(frame, rowStride, camW, camH)
        val side = Math.sqrt(cropped.size.toDouble()).toInt()
        assertEquals(text, ScannerDecoder.decode(cropped, side, side))
    }

    @Test
    fun acceptsSessionHttpsLink() {
        val text = "https://bmc.moaf.uk/sms-backend/go?session=abc123def456"
        assertTrue(ScannerDecoder.isOurs(text))
        val lum = qrLuminance(text)
        val side = Math.sqrt(lum.size.toDouble()).toInt()
        assertEquals(text, ScannerDecoder.decode(lum, side, side))
    }

    @Test
    fun ignoresForeignQr() {
        val lum = qrLuminance("https://example.com/some-other-qr")
        val side = Math.sqrt(lum.size.toDouble()).toInt()
        val decoded = ScannerDecoder.decode(lum, side, side)
        assertNotNull(decoded)
        assertTrue(!ScannerDecoder.isOurs(decoded!!))
    }

    @Test
    fun returnsNullOnBlankFrame() {
        assertNull(ScannerDecoder.decode(ByteArray(100 * 100) { 0xFF.toByte() }, 100, 100))
    }
}
