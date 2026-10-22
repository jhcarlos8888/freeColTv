package com.freecoltv.app.ui.login

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.freecoltv.app.data.DataGraph
import com.freecoltv.app.data.auth.AuthResult
import com.freecoltv.app.databinding.ActivityLoginBinding
import com.freecoltv.app.ui.home.ChannelListActivity
import kotlinx.coroutines.launch

class LoginActivity : AppCompatActivity() {

    private lateinit var binding: ActivityLoginBinding
    private val auth = DataGraph.authRepository

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityLoginBinding.inflate(layoutInflater)
        setContentView(binding.root)

        // Si ya hay sesión, saltar directo a canales.
        if (auth.currentSession() != null) {
            goChannels()
            return
        }

        binding.buttonLogin.setOnClickListener { attemptLogin() }
    }

    private fun attemptLogin() {
        val user = binding.inputUsername.text?.toString().orEmpty()
        val pass = binding.inputPassword.text?.toString().orEmpty()

        if (user.isBlank() || pass.isBlank()) {
            toast(getString(com.freecoltv.app.R.string.login_empty))
            return
        }

        setLoading(true)
        lifecycleScope.launch {
            when (val result = auth.login(user, pass)) {
                is AuthResult.Success -> goChannels()
                is AuthResult.Failure -> {
                    setLoading(false)
                    toast(result.message)
                }
            }
        }
    }

    private fun setLoading(loading: Boolean) {
        binding.progress.visibility = if (loading) View.VISIBLE else View.GONE
        binding.buttonLogin.isEnabled = !loading
    }

    private fun goChannels() {
        startActivity(Intent(this, ChannelListActivity::class.java))
        finish()
    }

    private fun toast(msg: String) =
        Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()
}
