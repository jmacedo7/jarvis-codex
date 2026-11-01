# JARVIS — configuração local

## Qual arquivo é o ativo?

- `.env` na raiz desta instalação é o arquivo de configuração principal.
- `.env.example` é somente um modelo/documentação. O JARVIS **não carrega** esse arquivo.
- `.venv-security` é o ambiente virtual do Python (uma pasta com o interpretador e as bibliotecas); não é arquivo de configuração.
- O JARVIS também aceita um arquivo global em `~/.config/vortex-marketing/.env`.
- A precedência atual é: variáveis de ambiente do Windows > `.env` da instalação > arquivo global > valores padrão.

Para ver os caminhos e a origem de cada configuração sem revelar chaves ou segredos, abra o JARVIS e visite `http://localhost:8790/api/saude`.

## Instalar as dependências faciais

No PowerShell, dentro da pasta desta instalação:

```powershell
cd C:\Users\eojvm\jarvis-security
.\.venv-security\Scripts\python.exe -m pip install -r requirements-security.txt
.\.venv-security\Scripts\python.exe -c "import numpy, cv2, insightface, onnxruntime; print('Reconhecimento facial OK')"
```

O arquivo `requirements-security.txt` lista as dependências do módulo facial. Use sempre o Python de `.venv-security`, não o Python global do Windows.

## Iniciar

```powershell
.\.venv-security\Scripts\python.exe server.py
```

A tela bloqueia os atalhos de voz e texto até o reconhecimento facial ser concluído. Depois do desbloqueio, a câmera continua monitorando em segundo plano para manter os alertas de pessoa não reconhecida.
