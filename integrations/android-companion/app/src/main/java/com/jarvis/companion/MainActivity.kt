package com.jarvis.companion
import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.view.Gravity
import android.text.InputType
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
class MainActivity:Activity(){
 override fun onCreate(savedInstanceState:Bundle?){
  super.onCreate(savedInstanceState)
  val root=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(36,48,36,24);gravity=Gravity.CENTER_HORIZONTAL}
  root.addView(TextView(this).apply{text="JARVIS Companion";textSize=26f})
  root.addView(TextView(this).apply{text="Notificações filtradas localmente e criptografadas antes do envio.";textSize=15f;setPadding(0,18,0,24)})
  val topic=EditText(this).apply{hint="Tópico de entrada (ntfy)";setText(SecretStore.get(this@MainActivity,"topic")?:"")}
  val secret=EditText(this).apply{hint="Segredo de pareamento";inputType=InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD;setText(SecretStore.get(this@MainActivity,"secret")?:"")}
  val status=TextView(this).apply{text="Salve o pareamento e conceda acesso às notificações."}
  root.addView(topic);root.addView(secret)
  root.addView(Button(this).apply{text="Salvar pareamento";setOnClickListener{
   val t=topic.text.toString().trim();val s=secret.text.toString().trim()
   if(t.isNotBlank()&&s.length>=24){SecretStore.put(this@MainActivity,"topic",t);SecretStore.put(this@MainActivity,"secret",s);status.text="Configuração salva com criptografia do Android."}
   else status.text="Informe o tópico e o segredo (mínimo 24 caracteres)."
  }})
  root.addView(Button(this).apply{text="Ativar acesso às notificações";setOnClickListener{startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))}})
  root.addView(status);setContentView(root)
 }
}
