# JARVIS — configuração local

## Um único arquivo .env

O JARVIS lê **somente** o arquivo `.env` localizado na mesma pasta de `server.py`.

- `.env`: fonte única das configurações desta instalação.
- `.env.example`: apenas modelo; nunca é carregado.
- `.estado/preferencias.json`: preferências antigas são ignoradas para evitar que uma voz antiga sobrescreva o `.env`.
- O arquivo global `~/.config/vortex-marketing/.env` e variáveis `JARVIS_*` / `ELEVENLABS_*` do Windows não são consultados.

Copie `.env.example` para `.env` uma única vez e preencha a chave `ELEVENLABS_API_KEY` diretamente no seu computador. Nunca envie essa chave pelo chat nem faça commit do `.env`. A engrenagem salva a voz e a velocidade no mesmo `.env`, preservando a chave e as demais configurações.

O endpoint local `http://localhost:8790/api/saude` informa o caminho do arquivo ativo, a voz escolhida e se o ElevenLabs está configurado. Ele **não** retorna o conteúdo da chave.

## Voz

- `ELEVENLABS_API_KEY`: chave da conta ElevenLabs.
- `JARVIS_VOZ`: ID selecionado em `vozes.json`.
- `JARVIS_MODELO_VOZ`: padrão `eleven_multilingual_v2`.
- `JARVIS_VELOCIDADE_VOZ`: valor entre 0.7 e 1.2.

Quando a chave não estiver configurada, o navegador usa uma voz local em português, se existir. Quando a API do ElevenLabs falhar, o JARVIS avisa e **não troca silenciosamente** para uma voz diferente.

## Reconhecimento facial

O reconhecimento facial ocorre na inicialização. Enquanto sua identidade não for confirmada, a câmera permanece ativa para verificar o rosto. Depois da primeira correspondência, a câmera é liberada e a análise termina. O próximo reconhecimento só acontece ao iniciar o JARVIS novamente.

No PowerShell, dentro da pasta desta instalação:

```powershell
.\.venv-security\Scripts\python.exe -m pip install -r requirements-security.txt
.\.venv-security\Scripts\python.exe -c "import numpy, cv2, insightface, onnxruntime; print('Reconhecimento facial OK')"
.\.venv-security\Scripts\python.exe -m security.face_guard enroll "Seu nome"
.\.venv-security\Scripts\python.exe server.py
```

Use o mesmo ambiente Python em que instalou as dependências faciais.

## Guia inicial e painel

Depois do primeiro reconhecimento, o guia aparece uma vez por navegador. Ele explica os atalhos de voz/texto e o estado das integrações. A resposta falada é revelada progressivamente no painel enquanto o áudio toca; cartões concluídos permanecem visíveis.

## Relatórios

Dizer “boa noite” ou solicitar o encerramento do dia gera o relatório. Os relatórios concluídos sem erro são salvos localmente em `.estado/relatorios/` e o mais recente aparece no painel.

## Integrações

As notificações móveis dependem da configuração da ponte Android/ntfy. E-mail, agenda e clima continuam explicitamente marcados como não conectados até que um provedor e suas credenciais/OAuth sejam configurados. O JARVIS não inventa mensagens, compromissos ou condições climáticas.
