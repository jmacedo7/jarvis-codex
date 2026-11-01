# JARVIS Companion (Android)

Aplicativo Android para encaminhar notificações selecionadas por filtro local ao JARVIS. O conteúdo é criptografado com AES-256-GCM antes do HTTPS. O usuário precisa conceder explicitamente o acesso às notificações.

## Build

Abra esta pasta no Android Studio com JDK 17 e Android SDK 35, sincronize o Gradle e use Build > Build APK(s). Instale o APK debug no seu próprio Android.

## Pareamento

1. No PC, execute: python -m security.setup
2. Abra o arquivo local .estado/mobile_pairing.json. Nunca o envie a ninguém nem o publique.
3. No app, informe inbox_topic e shared_secret; salve.
4. Toque em Ativar acesso às notificações e habilite JARVIS Companion nas configurações do Android.
5. No aplicativo oficial ntfy, assine o alerts_topic para receber alertas do PC.

O aplicativo envia notificações cifradas para inbox_topic. O PC publica alertas genéricos em alerts_topic, sem imagens ou dados biométricos.

## Privacidade

O filtro é heurístico, não infalível. Bloqueia termos comuns de senha, OTP, banco, finanças e saúde, além de pacotes com nomes sensíveis. Revise o código antes de conceder acesso. O serviço ntfy vê os nomes dos tópicos, horários e tamanho dos dados cifrados, mas não o texto das notificações. O JARVIS guarda localmente as últimas 200 notificações aceitas.
