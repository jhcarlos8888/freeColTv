package com.freecoltv.app.data.channel

import com.freecoltv.app.data.model.Channel
import com.freecoltv.app.data.model.LiveAddress

/**
 * Parser mínimo y tolerante de playlists M3U/M3U8 para canales IPTV.
 *
 * Formato esperado por entrada:
 * ```
 * #EXTINF:-1 tvg-id="X.co" tvg-logo="https://..." group-title="General",Nombre del Canal
 * http://host/stream.m3u8
 * ```
 *
 * Ignora directivas que no sean EXTINF (p. ej. #EXTVLCOPT) y líneas en blanco.
 * No valida que el stream exista ni esté desbloqueado geográficamente.
 */
object M3uParser {

    /**
     * @param content texto completo de la playlist
     * @param sourceTag etiqueta que se usa como prefijo de código si no hay tvg-id
     * @return canales parseados, en el orden de la playlist
     */
    fun parse(content: String, sourceTag: String = "src"): List<Channel> {
        val channels = mutableListOf<Channel>()
        var pendingName: String? = null
        var pendingLogo: String? = null
        var pendingGroup: String? = null
        var pendingId: String? = null

        for (rawLine in content.lineSequence()) {
            val line = rawLine.trim()
            if (line.isEmpty()) continue

            if (line.startsWith("#EXTINF", ignoreCase = true)) {
                pendingName = extractDisplayName(line)
                pendingLogo = extractAttr(line, "tvg-logo")
                pendingGroup = extractAttr(line, "group-title")
                pendingId = extractAttr(line, "tvg-id")
            } else if (line.startsWith("#")) {
                // Otras directivas (#EXTM3U, #EXTVLCOPT, comentarios): se ignoran.
                continue
            } else {
                // Línea de URL: cierra la entrada pendiente.
                val name = pendingName
                if (name != null) {
                    channels += Channel(
                        code = pendingId ?: "$sourceTag-${channels.size + 1}",
                        name = name,
                        number = channels.size + 1,
                        logoUrl = pendingLogo,
                        tags = pendingGroup,
                        addresses = listOf(
                            LiveAddress(url = line, quality = "auto", format = "hls")
                        ),
                    )
                }
                pendingName = null
                pendingLogo = null
                pendingGroup = null
                pendingId = null
            }
        }
        return channels
    }

    /** Obtiene el valor de un atributo `clave="valor"` dentro de la línea EXTINF. */
    private fun extractAttr(line: String, key: String): String? {
        val regex = Regex("""(?i)\b$key="([^"]*)"""")
        val match = regex.find(line) ?: return null
        return match.groupValues[1].takeIf { it.isNotBlank() }
    }

    /**
     * El nombre va tras la coma final que cierra los atributos:
     * `#EXTINF:-1 a="b",Mi Canal` → `Mi Canal`.
     * Si no hay atributos con comillas, toma el texto tras la primera coma.
     */
    private fun extractDisplayName(line: String): String {
        val lastQuote = line.lastIndexOf('"')
        val commaIdx = if (lastQuote >= 0) {
            line.indexOf(',', startIndex = lastQuote)
        } else {
            line.indexOf(',')
        }
        val name = if (commaIdx >= 0) line.substring(commaIdx + 1) else return ""
        return name.trim()
    }
}
