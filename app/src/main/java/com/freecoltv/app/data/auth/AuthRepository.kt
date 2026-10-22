package com.freecoltv.app.data.auth

import com.freecoltv.app.data.model.Session

/** Resultado de una operación de autenticación. */
sealed class AuthResult {
    data class Success(val session: Session) : AuthResult()
    data class Failure(val message: String) : AuthResult()
}

/**
 * Contrato de autenticación. La app solo conoce esta interfaz; el backend
 * real se conecta implementándola (p. ej. contra tu servidor IPTV).
 */
interface AuthRepository {
    suspend fun login(username: String, password: String): AuthResult
    fun logout()
    fun currentSession(): Session?
}
