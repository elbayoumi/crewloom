package com.smsforwarder.app

import com.google.zxing.BarcodeFormat
import com.google.zxing.BinaryBitmap
import com.google.zxing.DecodeHintType
import com.google.zxing.MultiFormatReader
import com.google.zxing.PlanarYUVLuminanceSource
import com.google.zxing.common.HybridBinarizer

object ScannerDecoder {

    /** Crop the center region (where the viewfinder is) from a luminance buffer. */
    fun cropCenter(raw: ByteArray, rowStride: Int, width: Int, height: Int, ratio: Double = 0.7): ByteArray {
        val side = (minOf(width, height) * ratio).toInt()
        val left = (width - side) / 2
        val top = (height - side) / 2
        val out = ByteArray(side * side)
        for (y in 0 until side) {
            System.arraycopy(raw, (top + y) * rowStride + left, out, y * side, side)
        }
        return out
    }

    /** Decode a QR from a luminance buffer (already cropped). Returns null if not decodable. */
    fun decode(luminance: ByteArray, width: Int, height: Int): String? {
        return try {
            val hints = mapOf(
                DecodeHintType.POSSIBLE_FORMATS to listOf(BarcodeFormat.QR_CODE),
                DecodeHintType.TRY_HARDER to true
            )
            val source = PlanarYUVLuminanceSource(luminance, width, height, 0, 0, width, height, false)
            MultiFormatReader().apply { setHints(hints) }.decodeWithState(BinaryBitmap(HybridBinarizer(source))).text
        } catch (e: Exception) {
            null
        }
    }

    fun isOurs(text: String): Boolean {
        val t = text.trim()
        if (t.startsWith("rveta://")) return true
        val web = t.startsWith("http://") || t.startsWith("https://")
        if (!web) return false
        if (t.contains("session=")) return true
        return t.contains("d=") && t.contains("t=")
    }
}
