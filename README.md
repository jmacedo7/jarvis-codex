# JARVIS com Codex

Um assistente que **executa** em vez de só conversar. Você segura a barra de espaço, fala, e o JARVIS envia o pedido ao Codex na sua pasta de trabalho. A resposta aparece na interface e, quando configurado, também é falada pelo ElevenLabs.

~~~
você fala → transcrição → Codex App Server → ferramentas e arquivos → resposta → voz
~~~

- **Entrada:** microfone (Whisper local ou ElevenLabs Scribe) e campo de texto.
- **Cérebro:** uma conversa persistente do Codex App Server.
- **Contexto:** pasta de trabalho, arquivos AGENTS.md, ferramentas e servidores MCP disponíveis no Codex.
- **Saída:** resposta na interface atual e, opcionalmente, ElevenLabs.
- **Interface:** a tela original de esfera animada foi mantida; os atalhos e o painel de voz continuam iguais.
- **Proteção:** sandbox do Codex, solicitações de aprovação e hook opcional do JARVIS para ações sensíveis.

## Requisitos

- Windows 10 ou macOS.
- Python 3.9 ou mais novo. O servidor JARVIS usa apenas a biblioteca padrão do Python.
- Codex CLI instalado e autenticado.
- Opcional: chave do ElevenLabs para voz e transcrição alternativa.
- Opcional: ffmpeg e Whisper local para transcrição sem custo por chamada.

### Instalar o Codex no Windows

Abra o PowerShell e execute:

~~~powershell
powershell -ExecutionPolicy ByPass -c "irm https://chatgpt.com/codex/install.ps1 | iex"
~~~

Ou, caso prefira npm:

~~~powershell
npm install -g @openai/codex
~~~

Depois execute codex no terminal e conclua o login. Confira com:

~~~powershell
codex --version
~~~

Documentação oficial: [Codex CLI](https://developers.openai.com/codex/cli).

## Instalar o JARVIS

No PowerShell:

~~~powershell
git clone https://github.com/jmacedo7/jarvis-codex.git
cd jarvis-codex
git switch codex-adaptation
Copy-Item .env.example .env
Copy-Item persona.example.md persona.md
~~~

Edite o .env e informe o diretório de trabalho em JARVIS_PASTA. O modelo pode ficar vazio para usar o padrão da sua conta Codex.

No macOS/Linux, os comandos equivalentes para copiar os arquivos são:

~~~bash
cp .env.example .env
cp persona.example.md persona.md
~~~

## Executar

~~~powershell
python server.py
~~~

O navegador abre em http://localhost:8790.

## Interface e atalhos

A interface continua com os mesmos comandos:

| Tecla | Ação |
|---|---|
| Segurar **espaço** | Falar com o JARVIS; pressionar durante o trabalho interrompe a tarefa |
| **T** | Digitar em vez de falar |
| **N** | Começar uma conversa nova |
| **H** | Mostrar ou esconder os detalhes |

Clique na janela não ativa o microfone. O painel de configurações de voz, as animações, os eventos SSE e o layout visual foram preservados.

## Configuração do Codex

As opções principais ficam no .env:

| Variável | Padrão | Função |
|---|---|---|
| JARVIS_CODEX_BIN | codex | Executável do Codex CLI |
| JARVIS_MODELO | vazio | Modelo; vazio usa o padrão da conta |
| JARVIS_ESFORCO | low | Esforço de raciocínio |
| JARVIS_APROVACAO | on-request | Política nativa de aprovação |
| JARVIS_REDE | 0 | Permite rede no sandbox quando definido como 1 |
| JARVIS_CONTEXTO | leve | Profundidade de leitura inicial: enxuta ou completa |
| JARVIS_PASTA | pasta pessoal | Área de trabalho do usuário |

O servidor inicia `codex app-server --listen stdio://` e conversa com ele por JSON-RPC/JSONL. O App Server mantém a thread, envia eventos incrementais e aceita interrupções e decisões de aprovação. Essa interface ainda é documentada como experimental; mantenha o Codex CLI atualizado e confira a compatibilidade da versão instalada.

## Proteção e aprovações

O JARVIS usa o sandbox `workspaceWrite` e limita a raiz gravável à pasta definida em JARVIS_PASTA. A rede fica desativada por padrão. A política `onRequest` deixa o Codex pedir autorização quando uma operação exige permissão adicional.

O hook opcional `hooks/trava.py` reforça a proteção de ações classificadas como sensíveis. A configuração está em `.codex/hooks.json`. Na primeira utilização, abra o Codex na pasta do projeto, use `/hooks` e revise/confie no hook do JARVIS antes de permitir sua execução. Hooks de projeto não devem ser confiados sem revisão. A trava é uma camada adicional, não substitui o sandbox do Codex nem a revisão do que será executado.

## Voz e transcrição

Sem ELEVENLABS_API_KEY, o JARVIS continua funcionando na tela, sem resposta falada.

Com a chave, o ElevenLabs gera a fala e também pode transcrever áudio. Para transcrição local, configure Whisper e WHISPER_URL; o modo auto tenta o Whisper primeiro e usa ElevenLabs como alternativa.

A lista de vozes continua em `vozes.json`. As preferências escolhidas na engrenagem ficam salvas em `.estado/preferencias.json`.

## Atalhos e pré-busca

A pasta `atalhos/` mantém os scripts originais. `gatilhos.json` permite executar consultas frequentes antes de enviar a pergunta ao Codex, reduzindo a ida e volta de ferramentas. Os atalhos lentos podem ser aquecidos na inicialização com JARVIS_AQUECER_ATALHOS.

## App de Mac (opcional)

A pasta `app/` mantém o empacotador original para macOS. Ele é independente da integração do Codex, mas não se aplica ao Windows.

## Arquivos principais

~~~
server.py            servidor HTTP/SSE, áudio e sessão Codex
hooks/trava.py       proteção opcional PreToolUse para Codex
.codex/hooks.json    configuração do hook de projeto
web/index.html       interface visual original (não alterada)
persona.example.md   instruções do JARVIS
.env.example         configuração do servidor e do Codex
vozes.json           vozes do ElevenLabs
gatilhos.json        gatilhos de pré-busca
atalhos/             scripts de resposta rápida
.estado/             logs e preferências locais (não vai para o git)
~~~

## Licença

MIT
