package com.jarvis.companion

import android.app.Activity
import android.os.Bundle
import android.view.Gravity
import android.widget.LinearLayout
import android.widget.TextView

/**
 * Explains the limited Health Connect data access requested by JARVIS.
 * This screen is opened from Health Connect's permission/privacy-policy UI.
 */
class PermissionsRationaleActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(32, 32, 32, 32)
            setBackgroundColor(0xFF06111A.toInt())
        }
        content.addView(TextView(this).apply {
            text = "JARVIS Companion · Uso dos dados de saúde"
            textSize = 20f
            setTextColor(0xFF8CEBFF.toInt())
        })
        content.addView(TextView(this).apply {
            text = "O JARVIS solicita acesso somente de leitura a sessões de sono e contagem de passos no Health Connect. Esses dados são usados para compor o resumo de sono e atividade do seu painel pessoal. A leitura e o envio só acontecem quando você inicia a sincronização no aplicativo. O envio ao seu JARVIS é protegido por criptografia; o aplicativo não vende seus dados nem os utiliza para publicidade. Você pode revogar o acesso a qualquer momento nas configurações do Health Connect."
            textSize = 15f
            setTextColor(0xFFEAFBFF.toInt())
            setPadding(0, 20, 0, 0)
        })
        setContentView(content)
    }
}
