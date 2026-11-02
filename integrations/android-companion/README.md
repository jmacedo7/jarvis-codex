# JARVIS Companion (Android)

Companion para Android com encaminhamento de notificações selecionadas, pareamento criptografado AES-256-GCM e sincronização manual de sono/passos via Health Connect.

## Build do APK

- JDK 17 e Android SDK 35.
- Abra esta pasta no Android Studio e execute **Build > Build APK(s)**.
- Ou, na raiz desta pasta, execute `gradle assembleDebug --no-daemon`.
- O APK debug fica em `app/build/outputs/apk/debug/app-debug.apk`.

## Pareamento de notificações

1. No PC, dentro da pasta do JARVIS, execute `python -m security.setup`.
2. Abra o arquivo local `.estado/mobile_pairing.json`. Não envie o segredo a terceiros nem publique o arquivo.
3. Informe `inbox_topic` e `shared_secret` no Companion e salve.
4. Ative a permissão de acesso às notificações do JARVIS Companion nas configurações do Android.
5. O app encaminha notificações selecionadas e filtradas ao tópico inbox. O PC recebe por ntfy e descriptografa localmente.

## Samsung Health / Health Connect

O Companion lê **SleepSessionRecord** e **StepsRecord** pelo Health Connect. O envio ao JARVIS é manual; não há coleta contínua em segundo plano.

1. Instale/atualize Samsung Health e Health Connect.
2. Em Samsung Health, abra **Configurações > Health Connect** e habilite a sincronização de dados de sono e passos.
3. No JARVIS Companion, toque em **Conectar Samsung Health / Health Connect**.
4. Na tela de permissões do Android, libere **Sono** e **Passos**.
5. Toque em **Sincronizar sono e passos agora**. Os dados são cifrados com AES-256-GCM e enviados ao mesmo tópico ntfy do pareamento.
6. O painel do PC mostra a última sessão de sono sincronizada e a contagem de passos do dia.

A leitura depende de o Samsung Health ter escrito os dados no Health Connect. O usuário pode revogar as permissões no Health Connect a qualquer momento. As leituras são para bem-estar/fitness e não servem para diagnóstico ou tratamento médico.

## Privacidade

O filtro de notificações é heurístico e não infalível. Termos e aplicativos comuns de autenticação, finanças e saúde são bloqueados antes do envio. Dados de saúde não são sincronizados automaticamente: o usuário concede permissões e inicia cada sincronização manualmente. O conteúdo trafega criptografado; o ntfy ainda observa nome do tópico, horário e tamanho do pacote cifrado. O JARVIS guarda as últimas 200 notificações aceitas e o último resumo de saúde localmente em `.estado/`.
