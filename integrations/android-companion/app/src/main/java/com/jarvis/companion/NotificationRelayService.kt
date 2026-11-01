package com.jarvis.companion
import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import org.json.JSONObject
import android.util.Base64
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec
class NotificationRelayService:NotificationListenerService(){
 private val sensitive=Regex("(?i)(senha|password|passcode|c[oó]digo.{0,12}(verifica|autentica|seguran)|verification code|one.?time.?password|\\botp\\b|token|chave.{0,8}(pix|seguran)|cart[aã]o|cvv|cvc|saldo|pix recebido|fatura|banco|bank|medical|sa[uú]de|diagn[oó]stico|receita m[eé]dica|authenticator|2fa)")
 private val blockedPackages=listOf("authenticator","password","wallet","bank","banco","health","saude")
 override fun onNotificationPosted(sbn:StatusBarNotification){
  val topic=SecretStore.get(this,"topic")?:return;val secret=SecretStore.get(this,"secret")?:return
  val pkg=sbn.packageName?:return;if(blockedPackages.any{pkg.contains(it,true)})return
  val extras=sbn.notification?.extras?:return
  val title=extras.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty()
  val body=(extras.getCharSequence(Notification.EXTRA_BIG_TEXT)?:extras.getCharSequence(Notification.EXTRA_TEXT))?.toString().orEmpty()
  if(title.isBlank()&&body.isBlank())return
  if(sensitive.containsMatchIn(title)||sensitive.containsMatchIn(body))return
  val app=try{packageManager.getApplicationLabel(packageManager.getApplicationInfo(pkg,0)).toString()}catch(_:Exception){pkg}
  val payload=JSONObject().apply{put("kind","notification");put("app",app.take(100));put("package",pkg.take(160));put("title",title.take(200));put("text",body.take(1500));put("posted_at",sbn.postTime)}.toString()
  Thread{publish(topic,secret,payload)}.start()
 }
 private fun publish(topic:String,secret:String,payload:String){
  try{
   val key=MessageDigest.getInstance("SHA-256").digest(secret.toByteArray(Charsets.UTF_8))
   val nonce=ByteArray(12).also{SecureRandom().nextBytes(it)}
   val cipher=Cipher.getInstance("AES/GCM/NoPadding")
   cipher.init(Cipher.ENCRYPT_MODE,SecretKeySpec(key,"AES"),GCMParameterSpec(128,nonce))
   cipher.updateAAD("JARVIS-MOBILE-v1".toByteArray(Charsets.UTF_8))
   val blob=nonce+cipher.doFinal(payload.toByteArray(Charsets.UTF_8))
   val token="v1."+Base64.encodeToString(blob,Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
   val conn=URL("https://ntfy.sh/"+topic).openConnection() as HttpURLConnection
   conn.requestMethod="POST";conn.doOutput=true;conn.connectTimeout=10000;conn.readTimeout=10000
   conn.setRequestProperty("Content-Type","text/plain; charset=utf-8");conn.setRequestProperty("Cache","no")
   conn.outputStream.use{it.write(token.toByteArray(Charsets.UTF_8))};conn.inputStream.close();conn.disconnect()
  }catch(_:Exception){/* Do not write notification content to Android logs. */}
 }
}
