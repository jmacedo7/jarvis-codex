# JARVIS security companion

## Instalação no Windows

Recomendo Python 3.11 em ambiente virtual dedicado; o Python 3.15 instalado pode ainda não ter wheels compatíveis para todas as dependências nativas.

```powershell
py -3.11 -m venv .venv-security
.\.venv-security\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r security\requirements.txt
python -m security.setup
```

## Cadastrar familiares

```powershell
python -m security.face_guard enroll "Nome"
python -m security.face_guard list
python -m security.face_guard remove "Nome"
```

Cadastre cada familiar com consentimento, um por vez e em sessão privada. A base biométrica é protegida pelo Windows DPAPI e vinculada ao perfil Windows. Frames não são salvos nem enviados. O modelo pré-treinado buffalo_l é baixado pelo InsightFace na primeira execução; os termos do modelo são diferentes da licença do código InsightFace e devem ser revisados antes de qualquer uso comercial.

O servidor JARVIS inicia a ponte móvel e a câmera quando configurado. Reconhecimento é apenas um recurso de alerta, não autenticação ou controle físico de acesso. Alertas são limitados a um por minuto. Para desativar a câmera, use JARVIS_FACE_ENABLED=0 no .env.

O projeto Android está em integrations/android-companion. Veja o README para pareamento e geração do APK. Tópicos e segredo são gerados localmente e nunca devem ser enviados ao GitHub.
