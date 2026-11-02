package com.jarvis.companion

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.SleepSessionRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.request.AggregateRequest
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.security.SecureRandom
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec
import android.util.Base64

class MainActivity : ComponentActivity() {
    private lateinit var topicField: EditText
    private lateinit var secretField: EditText
    private lateinit var statusView: TextView
    private lateinit var healthView: TextView
    private lateinit var lastSendView: TextView
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private val healthPermissions by lazy {
        setOf(
            HealthPermission.getReadPermission(SleepSessionRecord::class),
            HealthPermission.getReadPermission(StepsRecord::class)
        )
    }

    private val healthPermissionLauncher = registerForActivityResult(
        PermissionController.createRequestPermissionResultContract()
    ) { granted ->
        if (granted.containsAll(healthPermissions)) syncHealth()
        else healthView.text = "Permissão negada. O sono e os passos continuam privados; você pode liberar depois."
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        buildScreen()
        refreshStatus()
    }

    private fun buildScreen() {
        val page = ScrollView(this)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 34, 24, 30)
            setBackgroundColor(0xFF06111A.toInt())
        }
        page.addView(root)
        root.addView(TextView(this).apply {
            text = "J.A.R.V.I.S."
            textSize = 27f
            setTextColor(0xFF8CEBFF.toInt())
            letterSpacing = 0.20f
        })
        root.addView(TextView(this).apply {
            text = "COMPANION · CENTRAL DO SEU ASSISTENTE"
            textSize = 10f
            setTextColor(0xFF7997A5.toInt())
            setPadding(0, 4, 0, 22)
        })

        val pairing = card(root, "PAREAMENTO COM O COMPUTADOR")
        topicField = EditText(this).apply {
            hint = "Tópico de entrada (ntfy)"
            setText(SecretStore.get(this@MainActivity, "topic") ?: "")
            setTextColor(0xFFEAFBFF.toInt())
            setHintTextColor(0xFF6D8794.toInt())
            singleLine = true
        }
        secretField = EditText(this).apply {
            hint = "Segredo de pareamento"
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD
            setText(SecretStore.get(this@MainActivity, "secret") ?: "")
            setTextColor(0xFFEAFBFF.toInt())
            setHintTextColor(0xFF6D8794.toInt())
            singleLine = true
        }
        pairing.addView(topicField)
        pairing.addView(secretField)
        pairing.addView(actionButton("Salvar pareamento") {
            val topic = topicField.text.toString().trim()
            val secret = secretField.text.toString().trim()
            if (topic.isNotBlank() && secret.length >= 24) {
                SecretStore.put(this, "topic", topic)
                SecretStore.put(this, "secret", secret)
                statusView.text = "Pareamento salvo com armazenamento criptografado do Android."
                refreshStatus()
            } else statusView.text = "Informe o tópico e o segredo com pelo menos 24 caracteres."
        })
        statusView = TextView(this).apply {
            textSize = 12f
            setTextColor(0xFFA9C4CF.toInt())
            setPadding(0, 12, 0, 0)
        }
        pairing.addView(statusView)
        pairing.addView(actionButton("Ativar acesso às notificações") {
            startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
        })

        val health = card(root, "SAMSUNG HEALTH · SONO E ATIVIDADE")
        health.addView(TextView(this).apply {
            text = "O JARVIS lê sessões de sono e passos sincronizados pelo Samsung Health via Health Connect. Nenhum dado é enviado até você tocar em sincronizar."
            textSize = 12f
            setTextColor(0xFF9AB5C1.toInt())
            setPadding(0, 0, 0, 12)
        })
        healthView = TextView(this).apply {
            text = "Verificando Health Connect…"
            textSize = 12f
            setTextColor(0xFF8CEBFF.toInt())
        }
        health.addView(healthView)
        health.addView(actionButton("Conectar Samsung Health / Health Connect") {
            connectHealth()
        })
        health.addView(actionButton("Sincronizar sono e passos agora") {
            connectHealth(syncAfterPermission = true)
        })

        val diagnostics = card(root, "DIAGNÓSTICO")
        lastSendView = TextView(this).apply {
            text = "Último envio: ainda não realizado."
            textSize = 12f
            setTextColor(0xFFA9C4CF.toInt())
        }
        diagnostics.addView(lastSendView)
        diagnostics.addView(actionButton("Atualizar diagnóstico") { refreshStatus() })
        diagnostics.addView(actionButton("Abrir Health Connect") {
            try {
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=com.google.android.apps.healthdata")))
            } catch (_: Exception) {
                startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:com.google.android.apps.healthdata")))
            }
        })

        setContentView(page)
    }

    private fun card(parent: LinearLayout, heading: String): LinearLayout {
        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(18, 16, 18, 18)
            setBackgroundColor(0xFF0B202D.toInt())
        }
        val title = TextView(this).apply {
            text = heading
            textSize = 10f
            letterSpacing = 0.12f
            setTextColor(0xFF8CEBFF.toInt())
            setPadding(0, 0, 0, 12)
        }
        panel.addView(title)
        val params = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        ).apply { bottomMargin = 14 }
        parent.addView(panel, params)
        return panel
    }

    private fun actionButton(label: String, action: () -> Unit): Button {
        return Button(this).apply {
            text = label
            isAllCaps = false
            textSize = 12f
            setTextColor(0xFFEAFBFF.toInt())
            setBackgroundColor(0xFF12394A.toInt())
            setOnClickListener { action() }
        }
    }

    private fun refreshStatus() {
        val paired = !SecretStore.get(this, "topic").isNullOrBlank() &&
            !SecretStore.get(this, "secret").isNullOrBlank()
        val enabled = Settings.Secure.getString(contentResolver, "enabled_notification_listeners")
            .orEmpty().contains(NotificationRelayService::class.java.name)
        if (::statusView.isInitialized) {
            statusView.text = buildString {
                append("Pareamento: ")
                append(if (paired) "salvo" else "pendente")
                append("\nAcesso às notificações: ")
                append(if (enabled) "autorizado" else "desativado")
            }
        }
        if (::lastSendView.isInitialized) {
            lastSendView.text = "Último envio: " + getSharedPreferences("jarvis_relay_status", MODE_PRIVATE)
                .getString("last_status", "ainda não realizado.")
        }
        if (::healthView.isInitialized) {
            val sdk = HealthConnectClient.getSdkStatus(this)
            healthView.text = when (sdk) {
                HealthConnectClient.SDK_AVAILABLE -> "Health Connect disponível. Permissões serão verificadas ao conectar."
                HealthConnectClient.SDK_UNAVAILABLE_PROVIDER_UPDATE_REQUIRED -> "Atualize ou instale Health Connect para continuar."
                else -> "Health Connect não está disponível neste aparelho."
            }
        }
    }

    private fun connectHealth(syncAfterPermission: Boolean = true) {
        val sdk = HealthConnectClient.getSdkStatus(this)
        if (sdk == HealthConnectClient.SDK_UNAVAILABLE_PROVIDER_UPDATE_REQUIRED ||
            sdk == HealthConnectClient.SDK_UNAVAILABLE
        ) {
            healthView.text = "Instale/atualize o Health Connect e ative a sincronização do Samsung Health."
            try {
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=com.google.android.apps.healthdata")))
            } catch (_: Exception) { }
            return
        }
        scope.launch {
            try {
                val client = HealthConnectClient.getOrCreate(this@MainActivity)
                val granted = client.permissionController.getGrantedPermissions()
                if (granted.containsAll(healthPermissions)) {
                    healthView.text = "Permissões ativas. Preparando leitura segura…"
                    if (syncAfterPermission) syncHealth()
                } else {
                    healthView.text = "Selecione Sono e Passos na tela de permissões do Android."
                    healthPermissionLauncher.launch(healthPermissions)
                }
            } catch (error: Exception) {
                healthView.text = "Não foi possível abrir Health Connect: " + (error.message ?: error.javaClass.simpleName)
            }
        }
    }

    private fun syncHealth() {
        scope.launch {
            healthView.text = "Lendo sessões de sono e passos autorizados…"
            try {
                val summary = withContext(Dispatchers.IO) {
                    val client = HealthConnectClient.getOrCreate(this@MainActivity)
                    val now = Instant.now()
                    val from = now.minusSeconds(10L * 24 * 60 * 60)
                    val sleep = client.readRecords(
                        ReadRecordsRequest(
                            SleepSessionRecord::class,
                            timeRangeFilter = TimeRangeFilter.between(from, now),
                            pageSize = 50
                        )
                    )
                    val zone = ZoneId.systemDefault()
                    val dayStart = LocalDate.now(zone).atStartOfDay(zone).toInstant()
                    val stepsResult = client.aggregate(
                        AggregateRequest(
                            metrics = setOf(StepsRecord.COUNT_TOTAL),
                            timeRangeFilter = TimeRangeFilter.between(dayStart, now)
                        )
                    )
                    val steps = stepsResult[StepsRecord.COUNT_TOTAL] ?: 0L
                    val sessions = JSONArray()
                    sleep.records.sortedByDescending { it.endTime }.take(10).forEach { session ->
                        val stages = JSONArray()
                        session.stages.take(20).forEach { stage ->
                            stages.put(JSONObject().apply {
                                put("start", stage.startTime.toString())
                                put("end", stage.endTime.toString())
                                put("type", stage.stage)
                            })
                        }
                        sessions.put(JSONObject().apply {
                            put("start", session.startTime.toString())
                            put("end", session.endTime.toString())
                            put("duration_minutes", Duration.between(session.startTime, session.endTime).toMinutes())
                            put("stages", stages)
                        })
                    }
                    JSONObject().apply {
                        put("kind", "health_sync")
                        put("source", "health_connect")
                        put("synced_at", Instant.now().epochSecond)
                        put("steps_today", steps)
                        put("sleep_sessions", sessions)
                    }.toString()
                }
                val topic = SecretStore.get(this@MainActivity, "topic") ?: throw IllegalStateException("Salve o pareamento primeiro.")
                val secret = SecretStore.get(this@MainActivity, "secret") ?: throw IllegalStateException("Salve o segredo de pareamento primeiro.")
                withContext(Dispatchers.IO) { publishEncrypted(topic, secret, summary) }
                healthView.text = "Sincronização enviada ao JARVIS. Passos hoje: " +
                    JSONObject(summary).optLong("steps_today").toString()
                getSharedPreferences("jarvis_relay_status", MODE_PRIVATE).edit()
                    .putString("health_status", "Dados de sono e passos enviados ao JARVIS.").apply()
            } catch (error: Exception) {
                healthView.text = "Falha na sincronização: " + (error.message ?: error.javaClass.simpleName)
            }
        }
    }

    private fun publishEncrypted(topic: String, secret: String, payload: String) {
        var connection: HttpURLConnection? = null
        try {
            val key = MessageDigest.getInstance("SHA-256").digest(secret.toByteArray(Charsets.UTF_8))
            val nonce = ByteArray(12).also { SecureRandom().nextBytes(it) }
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.ENCRYPT_MODE, SecretKeySpec(key, "AES"), GCMParameterSpec(128, nonce))
            cipher.updateAAD("JARVIS-MOBILE-v1".toByteArray(Charsets.UTF_8))
            val encrypted = nonce + cipher.doFinal(payload.toByteArray(Charsets.UTF_8))
            val token = "v1." + Base64.encodeToString(encrypted, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
            connection = URL("https://ntfy.sh/" + topic).openConnection() as HttpURLConnection
            connection.requestMethod = "POST"
            connection.doOutput = true
            connection.connectTimeout = 10000
            connection.readTimeout = 10000
            connection.setRequestProperty("Content-Type", "text/plain; charset=utf-8")
            connection.setRequestProperty("Cache", "no")
            connection.outputStream.use { it.write(token.toByteArray(Charsets.UTF_8)) }
            val code = connection.responseCode
            if (code !in 200..299) throw IllegalStateException("ntfy respondeu HTTP " + code)
            connection.inputStream.close()
            getSharedPreferences("jarvis_relay_status", MODE_PRIVATE).edit()
                .putString("last_status", "Dados de saúde enviados ao ntfy · HTTP " + code).apply()
        } finally {
            connection?.disconnect()
        }
    }

    override fun onResume() {
        super.onResume()
        if (::statusView.isInitialized) refreshStatus()
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }
}