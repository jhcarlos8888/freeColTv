package com.freecoltv.app.data.channel

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class M3uParserTest {

    private val sample = """
        #EXTM3U
        #EXTINF:-1 tvg-id="BluRadio.co@SD" tvg-logo="https://logo.co/br.png" group-title="General",Blu Radio (720p)
        https://mdstrm.com/live-stream-playlist/abc.m3u8
        #EXTVLCOPT:http-user-agent=Foo
        #EXTINF:-1 tvg-id="Anc.co@SD" group-title="Entertainment",ANC Television (720p)
        http://live.amelbatv.co:81/anctvlive/index.m3u8
        #EXTINF:-1,Otro Canal
        https://ejemplo.net/o.m3u8
    """.trimIndent()

    @Test
    fun `parsea todas las entradas con URL`() {
        val channels = M3uParser.parse(sample, "test")
        assertEquals(3, channels.size)
    }

    @Test
    fun `extrae nombre logo y grupo`() {
        val c = M3uParser.parse(sample, "test")[0]
        assertEquals("Blu Radio (720p)", c.name)
        assertEquals("https://logo.co/br.png", c.logoUrl)
        assertEquals("General", c.tags)
        assertEquals("BluRadio.co@SD", c.code)
    }

    @Test
    fun `ignora directivas EXTVLCOPT`() {
        val channels = M3uParser.parse(sample, "test")
        // La directiva no genera un canal fantasma con URL basura.
        assertEquals(3, channels.size)
        assertTrue(channels.none { it.name.contains("EXTVLCOPT") })
    }

    @Test
    fun `asigna numeracion correlativa`() {
        val channels = M3uParser.parse(sample, "test")
        assertEquals(listOf(1, 2, 3), channels.map { it.number })
    }

    @Test
    fun `genera codigo cuando no hay tvg-id`() {
        val channels = M3uParser.parse(sample, "test")
        assertEquals("test-3", channels[2].code)
        assertEquals("Otro Canal", channels[2].name)
        assertNull(channels[2].logoUrl)
    }

    @Test
    fun `la URL queda en primaryUrl de la primera direccion`() {
        val c = M3uParser.parse(sample, "test")[1]
        assertEquals("http://live.amelbatv.co:81/anctvlive/index.m3u8", c.primaryUrl)
    }

    @Test
    fun `playlist vacia devuelve lista vacia`() {
        assertTrue(M3uParser.parse("#EXTM3U", "test").isEmpty())
    }
}
