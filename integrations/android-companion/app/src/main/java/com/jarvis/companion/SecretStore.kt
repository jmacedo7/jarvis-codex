package com.jarvis.companion
import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
object SecretStore {
 private const val ALIAS="jarvis-companion-config-v1"
 private fun key():SecretKey {
  val ks=KeyStore.getInstance("AndroidKeyStore").apply{load(null)}
  (ks.getKey(ALIAS,null) as? SecretKey)?.let{return it}
  val gen=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore")
  gen.init(KeyGenParameterSpec.Builder(ALIAS,KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT).setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
  return gen.generateKey()
 }
 fun put(context:Context,name:String,value:String) {
  val c=Cipher.getInstance("AES/GCM/NoPadding"); c.init(Cipher.ENCRYPT_MODE,key())
  val bytes=c.iv+c.doFinal(value.toByteArray(Charsets.UTF_8))
  context.getSharedPreferences("jarvis",Context.MODE_PRIVATE).edit().putString(name,Base64.encodeToString(bytes,Base64.NO_WRAP)).apply()
 }
 fun get(context:Context,name:String):String? {
  return try {
   val encoded=context.getSharedPreferences("jarvis",Context.MODE_PRIVATE).getString(name,null) ?: return null
   val b=Base64.decode(encoded,Base64.NO_WRAP); val c=Cipher.getInstance("AES/GCM/NoPadding")
   c.init(Cipher.DECRYPT_MODE,key(),GCMParameterSpec(128,b.copyOfRange(0,12)))
   String(c.doFinal(b.copyOfRange(12,b.size)),Charsets.UTF_8)
  } catch(_:Exception){null}
 }
}
