package com.freecoltv.app.data.auth

import com.freecoltv.app.data.model.Session
import kotlinx.coroutines.delay

/**
 * Implementación de prueba. Acepta cualquier usuario no vacío con la
 * contraseña "demo" (o el usuario "demo"/"demo"), simulando latencia de red.
 * Sustituir por una implementación real contra el backend IPTV.
 */
class MockAuthRepository : AuthRepository {

    private var session: Session? = null

    override suspend fun login(username: String, password: String): AuthResult {
        delay(600) // simula la llamada de red
        if (username.isBlank() || password.isBlank()) {
            return AuthResult.Failure("Rellena usuario y contraseña")
        }
        val ok = password == "demo" || (username == "demo" && password == "demo")
        return if (ok) {
            val s = Session(
                userId = "u-${username.trim()}",
                token = "mock-token-${System.currentTimeMillis()}",
                displayName = username.trim(),
            )
            session = s
            AuthResult.Success(s)
        } else {
            AuthResult.Failure("Usuario o contraseña incorrectos")
        }
    }

    override fun logout() {
        session = null
    }

    override fun currentSession(): Session? = session
}
