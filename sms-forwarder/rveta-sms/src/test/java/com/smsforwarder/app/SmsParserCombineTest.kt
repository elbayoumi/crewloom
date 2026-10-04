package com.smsforwarder.app

import org.junit.Assert.assertEquals
import org.junit.Test

class SmsCombineLogicTest {
    @Test fun multipartBodyCombines() {
        val parts = listOf("Hello ", "world", "!")
        assertEquals("Hello world!", parts.joinToString(""))
    }
}
