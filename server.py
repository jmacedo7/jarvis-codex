#!/usr/bin/env python3
"""JARVIS: assistente de voz conectado ao Codex App Server.

Você segura a barra de espaço e fala. O áudio vira texto (Whisper local ou
ElevenLabs Scribe), o texto vai para uma conversa persistente do Codex, e a
resposta volta falada pelo ElevenLabs. A interface HTTP/SSE permanece separada
do motor de IA.

Só usa a biblioteca padrão do Python (3.9+). Rodar:  python3 server.py
"""
import json
import os
import queue
import random
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
WEB = RAIZ / "web"
ESTADO = RAIZ / ".estado"


# ---------------------------------------------------------------- configuração

def ler_env(caminho):
    valores = {}
    try:
        for linha in Path(caminho).expanduser().read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            k, v = linha.split("=", 1)
            valores[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return valores


def carregar_config():
    # Ordem: variável de ambiente > .env do projeto > ~/.config/vortex-marketing/.env
    base = ler_env("~/.config/vortex-marketing/.env")
    base.update(ler_env(RAIZ / ".env"))
    base.update({k: v for k, v in os.environ.items() if k.startswith(("JARVIS_", "ELEVENLABS_", "WHISPER_"))})
    pasta = Path(base.get("JARVIS_PASTA") or Path.home()).expanduser()
    return {
        "pasta": pasta,
        "porta": int(base.get("JARVIS_PORTA", "8790")),
        "modelo": base.get("JARVIS_MODELO", ""),
        "esforco": base.get("JARVIS_ESFORCO", "low"),
        # leve: mantém o contexto inicial enxuto; completo: usa diretamente a pasta de trabalho.
        # O Codex recebe o diretório de trabalho em cada turno e respeita AGENTS.md.
        "contexto": base.get("JARVIS_CONTEXTO", "leve"),
        "persona": base.get("JARVIS_PERSONA", "persona.md"),
        "eleven_key": base.get("ELEVENLABS_API_KEY", ""),
        "voz": base.get("JARVIS_VOZ", "xHUwLsLfyqiYOIVTzLRW"),
        "modelo_voz": base.get("JARVIS_MODELO_VOZ", "eleven_multilingual_v2"),
        "velocidade_voz": float(base.get("JARVIS_VELOCIDADE_VOZ", "1.0")),
        "transcricao": base.get("JARVIS_TRANSCRICAO", "auto"),
        "whisper_url": base.get("WHISPER_URL", "http://127.0.0.1:8178").rstrip("/"),
        "codex_bin": base.get("JARVIS_CODEX_BIN", "codex"),
        "aprovacao": base.get("JARVIS_APROVACAO", "on-request"),
        "rede": base.get("JARVIS_REDE", "0") == "1",
        "aquecer": base.get("JARVIS_AQUECER", "1") == "1",
        "aquecer_atalhos": base.get("JARVIS_AQUECER_ATALHOS", ""),
        "ntfy_server": base.get("JARVIS_NTFY_SERVER", "https://ntfy.sh"),
        "ntfy_inbox": base.get("JARVIS_NTFY_INBOX", ""),
        "ntfy_alerts": base.get("JARVIS_NTFY_ALERTS", ""),
        "mobile_secret": base.get("JARVIS_MOBILE_SECRET", ""),
        "face_enabled": base.get("JARVIS_FACE_ENABLED", "1"),
    }


CFG = carregar_config()
PREFS = ESTADO / "preferencias.json"  # o que se escolhe na engrenagem vale mais que o .env


def carregar_vozes():
    try:
        return json.loads((RAIZ / "vozes.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return []


def carregar_preferencias():
    try:
        p = json.loads(PREFS.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return
    if p.get("voz"):
        CFG["voz"] = p["voz"]
    if p.get("velocidade"):
        CFG["velocidade_voz"] = float(p["velocidade"])


def salvar_preferencias():
    ESTADO.mkdir(exist_ok=True)
    PREFS.write_text(json.dumps({"voz": CFG["voz"], "velocidade": CFG["velocidade_voz"]}), encoding="utf-8")


VOZES = carregar_vozes()
carregar_preferencias()
AMOSTRA = "Às suas ordens, Senhor. É assim que eu vou falar com o senhor daqui pra frente."


def persona():
    """Carrega a personalidade do vault do Obsidian ou, como fallback, do projeto."""
    configurado = Path(CFG.get("persona") or "JARVIS/persona.md").expanduser()
    candidatos = [configurado] if configurado.is_absolute() else [
        CFG["pasta"] / configurado,
        RAIZ / configurado,
    ]
    candidatos.extend([RAIZ / "persona.md", RAIZ / "persona.example.md"])
    vistos = set()
    for arquivo in candidatos:
        try:
            resolvido = arquivo.resolve()
            if resolvido in vistos:
                continue
            vistos.add(resolvido)
            if resolvido.is_file():
                return resolvido.read_text(encoding="utf-8")
        except OSError:
            continue
    return ""


# ------------------------------------------------------------ eventos pra tela

class Eventos:
    """Fila de eventos que a página recebe por Server-Sent Events."""

    def __init__(self):
        self.ouvintes = []
        self.lock = threading.Lock()
        self.ultimo_estado = {"tipo": "estado", "estado": "iniciando"}

    def emitir(self, evento):
        if evento.get("tipo") == "estado":
            self.ultimo_estado = evento
        with self.lock:
            for q in list(self.ouvintes):
                q.put(evento)

    def assinar(self):
        q = queue.Queue()
        with self.lock:
            self.ouvintes.append(q)
        q.put(self.ultimo_estado)
        return q

    def sair(self, q):
        with self.lock:
            if q in self.ouvintes:
                self.ouvintes.remove(q)


EVENTOS = Eventos()


def log(registro):
    ESTADO.mkdir(exist_ok=True)
    registro["quando"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(ESTADO / "log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")


# --------------------------------------------------- rótulos do que ele está usando

NOMES_SERVIDOR = {
    "geracorte": "GeraCorte",
    "geragrupos": "GeraGrupos",
    "panda-video": "Panda Video",
    "google_calendar": "Agenda",
    "gmail": "Gmail",
    "google_drive": "Drive",
}


INTERNAS = {"ToolSearch", "TodoWrite", "BashOutput", "KillShell", "ListMcpResourcesTool", "ReadMcpResourceTool"}


def rotulo_ferramenta(nome, entrada):
    entrada = entrada or {}
    if nome in INTERNAS:
        return None
    if nome.startswith("mcp__"):
        servidor = nome.split("__")[1]
        for chave, rot in NOMES_SERVIDOR.items():
            if chave.lower() in servidor.lower():
                return rot
        return re.sub(r"^[a-z0-9]+_ai_", "", servidor, flags=re.I).replace("_", " ")
    if nome == "Bash":
        cmd = entrada.get("command", "")
        if re.search(r"zernio\.py|redes_resumo|isca_resumo", cmd):
            return "Redes sociais"
        if "supabase" in cmd or "psql" in cmd:
            return "Banco de dados"
        if "Memória" in cmd or "/memory" in cmd:
            return "Memória"
        if "TaskNotes" in cmd:
            return "Kanban"
        if re.match(r"\s*(grep|rg|find|cat|head|tail|ls)\b", cmd):
            return "Lendo o vault"
        return "Terminal"
    caminho = str(entrada.get("file_path") or entrada.get("path") or entrada.get("pattern") or "")
    if nome in ("Write", "Edit", "MultiEdit"):
        if "TaskNotes" in caminho:
            return "Kanban"
        return "Escrevendo nota"
    if nome in ("Read", "Grep", "Glob", "LS"):
        if "Memória" in caminho or "memory" in caminho:
            return "Memória"
        if "TaskNotes" in caminho:
            return "Kanban"
        return "Lendo o vault"
    if nome == "Skill":
        return "Skill " + str(entrada.get("skill", ""))
    if nome in ("WebSearch", "WebFetch"):
        return "Internet"
    if nome in ("Task", "Agent"):
        return "Agente"
    return nome


# ------------------------------------------------------------ sessão do Codex

# O App Server mantém uma thread viva e transmite eventos JSONL pelo stdio.
# A interface HTTP/SSE e todos os recursos de áudio continuam no server.py.

LEMBRETE = ("\n\n[modo JARVIS: seja direto, preciso e natural em português do Brasil. "
            "Perguntas simples devem ser respondidas sem ferramentas. Se precisar trabalhar, "
            "avise em uma frase curta antes de agir. Resposta falada: no máximo 2 frases curtas, "
            "até 30 palavras. Trate o dono por Senhor.]")
ESPERA_AVISO = 0.3


class TurnoCodex:
    """Uma solicitação ativa no Codex App Server."""

    def __init__(self, ao_avisar=None):
        self.fila = queue.Queue()
        self.entregue = False
        self.avisou = False
        self.ao_avisar = ao_avisar
        self.agendado = False
        self.trava = threading.Lock()
        self.marcas = {"envio": time.time()}

    def marcar(self, nome):
        self.marcas.setdefault(nome, round(time.time() - self.marcas["envio"], 2))

    def entregar(self, resultado):
        if not self.entregue:
            self.entregue = True
            self.fila.put(resultado)

    def avisar(self, frase=None):
        with self.trava:
            if self.avisou or self.entregue or not self.ao_avisar:
                return
            self.avisou = True
        self.ao_avisar(frase)

    def pedir_aviso(self, frase=None):
        with self.trava:
            if self.avisou or self.agendado:
                return
            self.agendado = True
        relogio = threading.Timer(ESPERA_AVISO, self.avisar, args=(frase,))
        relogio.daemon = True
        relogio.start()


class SessaoCodex:
    """Cliente JSON-RPC do Codex App Server via stdin/stdout."""

    def __init__(self):
        self.proc = None
        self.lock = threading.Lock()
        self.escrita_lock = threading.Lock()
        self.rpc_lock = threading.Lock()
        self.rpc_pendentes = {}
        self.proximo_id = 0
        self.turno = None
        self.livre = threading.Event()
        self.livre.set()
        self.ferramentas_turno = []
        self.thread_id = None
        self.turn_id = None
        self.texto_turno = ""
        self.aprovacoes = []
        self.aprovacao_lock = threading.Lock()

    def pasta_de_abertura(self):
        # O processo começa na raiz do JARVIS para carregar a configuração dos hooks.
        return RAIZ

    def comando(self):
        executavel = CFG.get("codex_bin") or "codex"
        encontrado = shutil.which(executavel) or shutil.which(executavel + ".cmd")
        executavel = encontrado or executavel
        args = [executavel, "app-server", "--listen", "stdio://"]
        if os.name == "nt" and str(executavel).lower().endswith((".cmd", ".bat")):
            linha = subprocess.list2cmdline(args)
            return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", linha]
        return args

    def _enviar(self, mensagem):
        if not self.vivo():
            raise RuntimeError("O processo do Codex não está em execução.")
        with self.escrita_lock:
            self.proc.stdin.write(json.dumps(mensagem, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()

    def _rpc(self, metodo, parametros=None, limite=25):
        with self.rpc_lock:
            self.proximo_id += 1
            rid = self.proximo_id
            slot = {"evento": threading.Event()}
            self.rpc_pendentes[rid] = slot
        mensagem = {"id": rid, "method": metodo, "params": parametros or {}}
        try:
            self._enviar(mensagem)
        except Exception:
            with self.rpc_lock:
                self.rpc_pendentes.pop(rid, None)
            raise
        if not slot["evento"].wait(limite):
            with self.rpc_lock:
                self.rpc_pendentes.pop(rid, None)
            raise TimeoutError(f"O Codex não respondeu ao método {metodo}.")
        if slot.get("erro"):
            raise RuntimeError(slot["erro"].get("message", str(slot["erro"])))
        return slot.get("resultado") or {}

    def iniciar(self):
        if self.vivo():
            return
        ESTADO.mkdir(exist_ok=True)
        env = os.environ.copy()
        env["JARVIS_ESTADO"] = str(ESTADO)
        env["JARVIS_PASTA"] = str(CFG["pasta"])
        env["JARVIS_ROOT"] = str(RAIZ)
        self.livre.set()
        self.thread_id = None
        self.turn_id = None
        self.texto_turno = ""
        self.aprovacoes = []
        self.rpc_pendentes = {}

        self.proc = subprocess.Popen(
            self.comando(), cwd=str(self.pasta_de_abertura()), env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, encoding="utf-8",
        )
        threading.Thread(target=self._ler_saida, args=(self.proc,), daemon=True).start()
        threading.Thread(target=self._ler_erros, args=(self.proc,), daemon=True).start()

        try:
            inicializacao = self._rpc("initialize", {
                "clientInfo": {
                    "name": "jarvis-codex",
                    "title": "JARVIS",
                    "version": "1.0.0",
                }
            }, limite=30)
            self._enviar({"method": "initialized", "params": {}})

            parametros = {
                "cwd": str(RAIZ),
                "approvalPolicy": CFG["aprovacao"],
                "sandbox": "workspace-write",
            }
            if CFG["modelo"]:
                parametros["model"] = CFG["modelo"]
            thread = self._rpc("thread/start", parametros, limite=60)
            self.thread_id = (thread.get("thread") or {}).get("id")
            if not self.thread_id:
                raise RuntimeError("O Codex não retornou o identificador da conversa.")
            log({"evento": "codex_init", "modelo": CFG["modelo"] or "padrão",
                 "thread": self.thread_id, "sandbox": "workspace-write",
                 "aprovacao": CFG["aprovacao"], "plataforma": inicializacao.get("platformOs")})
        except Exception:
            self.parar()
            raise

    def parar(self):
        proc = self.proc
        self.proc = None
        self.thread_id = None
        self.turn_id = None
        self.aprovacoes = []
        self.livre.set()
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            except OSError:
                pass

    def vivo(self):
        return self.proc is not None and self.proc.poll() is None

    def tem_aprovacao(self):
        with self.aprovacao_lock:
            return bool(self.aprovacoes)

    def resolver_aprovacao(self, aprovar):
        with self.aprovacao_lock:
            if not self.aprovacoes:
                return False
            pendente = self.aprovacoes.pop(0)
        decisao = "accept" if aprovar else "decline"
        self._enviar({"id": pendente["id"], "result": {"decision": decisao}})
        log({"evento": "codex_aprovacao", "decisao": decisao,
             "metodo": pendente["metodo"],
             "comando": str(pendente.get("params", {}).get("command", ""))[:200]})
        return True

    def interromper(self):
        if not self.vivo() or not self.thread_id or not self.turn_id:
            return False
        try:
            self._enviar({
                "id": "jarvis-interrupt-" + uuid.uuid4().hex[:8],
                "method": "turn/interrupt",
                "params": {"threadId": self.thread_id, "turnId": self.turn_id},
            })
            return True
        except (BrokenPipeError, OSError, RuntimeError):
            return False

    def _texto_item(self, item):
        if not isinstance(item, dict):
            return ""
        partes = []
        texto = item.get("text")
        if isinstance(texto, str):
            partes.append(texto)
        for bloco in item.get("content", []) or []:
            if isinstance(bloco, dict):
                valor = bloco.get("text") or bloco.get("output_text")
                if isinstance(valor, str):
                    partes.append(valor)
        return "\n".join(p for p in partes if p).strip()

    def _rotular_item(self, item):
        tipo = item.get("type", "")
        if tipo == "commandExecution":
            comando = item.get("command", "")
            rotulo = rotulo_ferramenta("Bash", {"command": comando})
            self.ferramentas_turno.append("Bash " + str(comando)[:160])
            return rotulo or "Terminal"
        if tipo == "fileChange":
            self.ferramentas_turno.append("apply_patch")
            return "Arquivos"
        if tipo == "mcpToolCall":
            nome = item.get("tool") or item.get("toolName") or item.get("name") or "MCP"
            entrada = item.get("arguments") or item.get("input") or {}
            self.ferramentas_turno.append(str(nome) + " " + json.dumps(entrada, ensure_ascii=False)[:160])
            return rotulo_ferramenta(str(nome), entrada) or "Conector"
        if tipo in ("webSearch", "webFetch"):
            return "Internet"
        return None

    def _solicitar_aprovacao(self, mensagem):
        metodo = mensagem.get("method", "")
        parametros = mensagem.get("params") or {}
        pendente = {"id": mensagem.get("id"), "metodo": metodo, "params": parametros}
        with self.aprovacao_lock:
            self.aprovacoes.append(pendente)
        if metodo == "item/commandExecution/requestApproval":
            comando = parametros.get("command") or parametros.get("reason") or "execução de comando"
            aviso = "O Codex solicita autorização: " + str(comando)[:180] + ". Diga confirma ou cancela."
        else:
            aviso = "O Codex solicita aprovação para alterar arquivos. Diga confirma ou cancela."
        EVENTOS.emitir({"tipo": "aviso", "texto": aviso})
        if self.turno:
            self.turno.marcar("aprovacao_s")

    def _ler_saida(self, proc):
        for linha in proc.stdout:
            try:
                mensagem = json.loads(linha)
            except (ValueError, TypeError):
                continue

            if "id" in mensagem and "method" not in mensagem:
                with self.rpc_lock:
                    slot = self.rpc_pendentes.pop(mensagem.get("id"), None)
                if slot:
                    slot["resultado"] = mensagem.get("result")
                    slot["erro"] = mensagem.get("error")
                    slot["evento"].set()
                continue

            metodo = mensagem.get("method", "")
            parametros = mensagem.get("params") or {}

            if metodo in ("item/commandExecution/requestApproval", "item/fileChange/requestApproval"):
                self._solicitar_aprovacao(mensagem)
                continue

            if metodo == "item/agentMessage/delta":
                delta = parametros.get("delta") or parametros.get("text") or ""
                if isinstance(delta, str):
                    self.texto_turno += delta
                    if self.turno:
                        self.turno.marcar("1a_mensagem_s")
                continue

            if metodo == "item/started":
                item = parametros.get("item") or {}
                if self.turno and item.get("type") in ("commandExecution", "mcpToolCall", "fileChange"):
                    self.turno.marcar("ferramenta_s")
                    self.turno.pedir_aviso()
                rotulo = self._rotular_item(item)
                if rotulo:
                    EVENTOS.emitir({"tipo": "ferramenta", "rotulo": rotulo})
                continue

            if metodo == "item/completed":
                item = parametros.get("item") or {}
                if item.get("type") == "agentMessage" and not self.texto_turno.strip():
                    self.texto_turno = self._texto_item(item)
                continue

            if metodo == "turn/completed":
                turno = parametros.get("turn") or {}
                status = turno.get("status", "completed")
                resposta = self.texto_turno.strip() or self._texto_item(turno)
                if status == "interrupted":
                    resultado = {"result": "", "interrompido": True}
                elif status == "failed":
                    erro = (turno.get("error") or {}).get("message") or "O Codex não conseguiu concluir a solicitação."
                    resultado = {"result": erro, "is_error": True}
                else:
                    resultado = {"result": resposta or "Feito."}
                if self.turno:
                    self.turno.entregar(resultado)
                self.turn_id = None
                self.livre.set()
                continue

            if metodo == "error":
                erro = parametros.get("error") or {}
                if self.turno:
                    self.turno.entregar({"result": erro.get("message", "Erro no Codex."), "is_error": True})
                self.livre.set()
                continue

            if metodo == "warning":
                log({"evento": "codex_aviso", "mensagem": parametros.get("message", "")})

        erro = "A sessão do Codex foi encerrada."
        with self.rpc_lock:
            pendentes = list(self.rpc_pendentes.values())
            self.rpc_pendentes.clear()
        for slot in pendentes:
            slot["erro"] = {"message": erro}
            slot["evento"].set()
        if self.turno:
            self.turno.entregar({"result": erro, "is_error": True})
        self.livre.set()

    def _ler_erros(self, proc):
        ESTADO.mkdir(exist_ok=True)
        with open(ESTADO / "codex-erros.log", "a", encoding="utf-8") as arquivo:
            for linha in proc.stderr:
                arquivo.write(linha)
                arquivo.flush()

    def _prompt(self, texto):
        instrucoes = persona()
        modo = (
            "Contexto enxuto: use a pasta de trabalho indicada e leia apenas as instruções AGENTS.md "
            "ou documentação que forem relevantes para a tarefa."
            if CFG["contexto"] == "leve"
            else "Contexto completo: antes de agir, consulte AGENTS.md e as instruções relevantes da pasta de trabalho."
        )
        nota = (
            "\n\n## Pasta de trabalho do usuário\n"
            "A pasta de trabalho é " + str(CFG["pasta"]) + ". "
            "Trabalhe nela, usando caminhos absolutos quando necessário. " + modo +
            "\nNão altere os arquivos do JARVIS, salvo pedido explícito."
        )
        return (
            "Instruções permanentes do JARVIS (aplicam-se a esta conversa):\n"
            + instrucoes + nota + "\n\nMensagem do usuário:\n" + texto + LEMBRETE
        )

    def perguntar(self, texto, limite=300, ao_avisar=None, aviso_apos=None):
        with self.lock:
            if not self.vivo():
                self.iniciar()
            espera = time.time()
            self.livre.wait(timeout=20)
            turno = TurnoCodex(ao_avisar)
            turno.marcas["esperou_rodada_s"] = round(time.time() - espera, 2)
            self.turno = turno
            self.texto_turno = ""
            self.livre.clear()
            self.ferramentas_turno = []

            sandbox = {
                "type": "workspaceWrite",
                "writableRoots": [str(CFG["pasta"])],
                "networkAccess": CFG["rede"],
            }
            parametros = {
                "threadId": self.thread_id,
                "input": [{"type": "text", "text": self._prompt(texto)}],
                "cwd": str(CFG["pasta"]),
                "approvalPolicy": CFG["aprovacao"],
                "sandboxPolicy": sandbox,
            }
            if CFG["modelo"]:
                parametros["model"] = CFG["modelo"]
            if CFG["esforco"]:
                parametros["effort"] = CFG["esforco"]

            try:
                iniciado = self._rpc("turn/start", parametros, limite=40)
                self.turn_id = (iniciado.get("turn") or {}).get("id")
                if not self.turn_id:
                    raise RuntimeError("O Codex não confirmou o início da tarefa.")
            except Exception as erro:
                self.livre.set()
                return {"result": str(erro), "is_error": True}

            if aviso_apos:
                relogio = threading.Timer(aviso_apos, turno.avisar)
                relogio.daemon = True
                relogio.start()
            try:
                return turno.fila.get(timeout=limite)
            except queue.Empty:
                self.interromper()
                self.parar()
                return {"is_error": True, "result": "Senhor, o Codex demorou demais. Reiniciei a sessão; pode repetir?"}


SESSAO = SessaoCodex()


# ---------------------------------------------------------------- transcrição

def multipart(campos, nome_arquivo, conteudo, mime, campo_arquivo="file"):
    limite = uuid.uuid4().hex
    partes = []
    for k, v in campos.items():
        partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    partes.append(
        f'--{limite}\r\nContent-Disposition: form-data; name="{campo_arquivo}"; filename="{nome_arquivo}"\r\n'
        f"Content-Type: {mime}\r\n\r\n".encode() + conteudo + b"\r\n"
    )
    partes.append(f"--{limite}--\r\n".encode())
    return b"".join(partes), f"multipart/form-data; boundary={limite}"


def para_wav(audio, mime):
    ext = ".mp4" if "mp4" in mime else ".ogg" if "ogg" in mime else ".webm"
    with tempfile.TemporaryDirectory() as tmp:
        entrada = Path(tmp) / ("fala" + ext)
        saida = Path(tmp) / "fala.wav"
        entrada.write_bytes(audio)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(entrada), "-ar", "16000", "-ac", "1", str(saida)],
            check=True,
        )
        return saida.read_bytes()


def transcrever_whisper(audio, mime):
    wav = para_wav(audio, mime)
    corpo, tipo = multipart({"response_format": "json", "temperature": "0.0"}, "fala.wav", wav, "audio/wav")
    req = urllib.request.Request(CFG["whisper_url"] + "/inference", data=corpo, headers={"Content-Type": tipo})
    with urllib.request.urlopen(req, timeout=25) as r:  # passou disso, usa o ElevenLabs
        return json.loads(r.read().decode("utf-8")).get("text", "")


def transcrever_scribe(audio, mime):
    corpo, tipo = multipart({"model_id": "scribe_v1", "language_code": "por"}, "fala.webm", audio, mime)
    req = urllib.request.Request(
        "https://api.elevenlabs.io/v1/speech-to-text", data=corpo,
        headers={"Content-Type": tipo, "xi-api-key": CFG["eleven_key"]},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8")).get("text", "")


# Frases que o whisper "inventa" quando o áudio é quase só silêncio (vêm de legendas de vídeo).
ALUCINACOES = [
    re.compile(p) for p in (
        r"^legendas? (por|pela|de)\b", r"\bruberti\b", r"\bamara org\b",
        r"\bobrigad[oa] por assistir", r"\binscreva se\b",
    )
]


def transcrever(audio, mime):
    modo = CFG["transcricao"]
    texto = ""
    if modo in ("auto", "whisper"):
        try:
            texto = transcrever_whisper(audio, mime)
        except Exception as erro:  # whisper fora do ar
            if modo == "whisper":
                raise
            log({"evento": "whisper_falhou", "erro": str(erro)})
            texto = transcrever_scribe(audio, mime)
    else:
        texto = transcrever_scribe(audio, mime)
    texto = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", texto)  # [BLANK_AUDIO], (música)
    texto = " ".join(texto.split())
    limpo = " ".join(normalizar(texto))
    if len(limpo.replace(" ", "")) < 2 or any(p.search(limpo) for p in ALUCINACOES):  # "ok" confirma a trava
        log({"evento": "transcricao_descartada", "texto": texto})
        return ""
    return texto


# ---------------------------------------------------------------- confirmação

def normalizar(texto):
    sem_acento = unicodedata.normalize("NFD", texto.lower())
    sem_acento = "".join(c for c in sem_acento if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]", " ", sem_acento).split()


AFIRMACOES = {"sim", "confirma", "confirmo", "confirmado", "pode", "manda", "isso", "ok", "okay",
              "fechado", "vai", "faz", "beleza", "claro", "positivo", "certo", "bora"}


def eh_confirmacao(texto):
    palavras = normalizar(texto)
    return 0 < len(palavras) <= 6 and palavras[0] in AFIRMACOES and "nao" not in palavras


def pediu_confirmacao(resposta):
    return "confirma" in " ".join(normalizar(resposta[-80:]))


# ------------------------------------------------------------------ resposta falada

def limpar_para_fala(texto):
    texto = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", texto)  # [link](url) -> link
    texto = re.sub(r"https?://\S+", "", texto)
    texto = re.sub(r"[*_#`>|]", "", texto)
    texto = re.sub(r"^\s*[-•]\s*", "", texto, flags=re.M)
    texto = " ".join(texto.split())
    return texto[:700]


class Fala:
    """Gera a voz uma vez só (ElevenLabs) e entrega aos pedaços pra quem pedir."""

    todas = {}

    def __init__(self, texto, voz=None, velocidade=None):
        self.pedacos = bytearray()
        self.pronto = False
        self.erro = None
        self.cond = threading.Condition()
        self.voz = voz or CFG["voz"]
        self.velocidade = velocidade if velocidade is not None else CFG["velocidade_voz"]
        threading.Thread(target=self._gerar, args=(texto,), daemon=True).start()

    def esperar(self, limite=60):
        with self.cond:
            fim = time.time() + limite
            while not self.pronto and time.time() < fim:
                self.cond.wait(timeout=1)
        return bytes(self.pedacos) if self.pronto and not self.erro else b""

    def _gerar(self, texto):
        url = (f"https://api.elevenlabs.io/v1/text-to-speech/{self.voz}/stream"
               "?output_format=mp3_44100_128")
        pedido = {"text": texto, "model_id": CFG["modelo_voz"]}
        if self.velocidade != 1.0:
            pedido["voice_settings"] = {"speed": self.velocidade}
        corpo = json.dumps(pedido).encode()
        req = urllib.request.Request(url, data=corpo, headers={
            "xi-api-key": CFG["eleven_key"], "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                while True:
                    pedaco = r.read(4096)
                    if not pedaco:
                        break
                    with self.cond:
                        self.pedacos.extend(pedaco)
                        self.cond.notify_all()
        except urllib.error.HTTPError as erro:
            self.erro = erro.code
            log({"evento": "voz_falhou", "codigo": erro.code, "detalhe": erro.read()[:300].decode("utf-8", "ignore")})
        except Exception as erro:
            self.erro = repr(erro)
            log({"evento": "voz_falhou", "detalhe": repr(erro)})
        finally:
            with self.cond:
                self.pronto = True
                self.cond.notify_all()

    def ler(self):
        pos = 0
        while True:
            with self.cond:
                while pos >= len(self.pedacos) and not self.pronto:
                    self.cond.wait(timeout=30)
                novo = bytes(self.pedacos[pos:])
                acabou = self.pronto
            pos += len(novo)
            if novo:
                yield novo
            if acabou and pos >= len(self.pedacos):
                return

    fixas = {}  # frases prontas: geradas uma vez quando o JARVIS abre

    @classmethod
    def fixa(cls, texto):
        chave = f"{CFG['voz']}|{CFG['velocidade_voz']}|{texto}"
        id_fala = "f" + uuid.uuid5(uuid.NAMESPACE_URL, chave).hex[:11]
        if id_fala not in cls.fixas:
            cls.fixas[id_fala] = cls(texto)
        return id_fala

    @classmethod
    def criar(cls, texto):
        id_fala = uuid.uuid4().hex[:12]
        cls.todas[id_fala] = cls(texto)
        for antigo in list(cls.todas)[:-20]:  # guarda só as últimas 20
            cls.todas.pop(antigo, None)
        return id_fala


# Ditas quando ele vai trabalhar e não escreveu o próprio aviso.
AVISOS_PRONTOS = ["Um instante, Senhor.", "Deixa comigo, Senhor.", "Verificando, Senhor.",
                  "Já volto com isso, Senhor.", "Consultando, Senhor."]


# ---------------------------------------------------------------- pré-busca
# Pergunta que bate com um gatilho de gatilhos.json já sai com o dado buscado:
# o atalho roda enquanto a pergunta vai para o Codex, que só precisa responder.

def carregar_gatilhos():
    try:
        return json.loads((RAIZ / "gatilhos.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return []


GATILHOS = carregar_gatilhos()


def periodo_falado(texto):
    t = " ".join(normalizar(texto))
    if re.search(r"\b(semana|ultimos dias|7 dias|sete dias)\b", t):
        return ["--ultimos", "7"]
    if re.search(r"\b(mes|30 dias|trinta dias)\b", t):
        return ["--ultimos", "30"]
    if re.search(r"\bontem\b", t):
        return ["--dia", "ontem"]
    return ["--dia", "hoje"]


def prebusca(texto):
    palavras = set(normalizar(texto))
    comandos = []
    for g in GATILHOS:
        alvos = {" ".join(normalizar(p)) for p in g.get("palavras", [])}
        if palavras & alvos:
            cmd = [sys.executable, str(RAIZ / "atalhos" / g["comando"][0])] + g["comando"][1:]
            if g.get("periodo"):
                cmd += periodo_falado(texto)
            comandos.append((g["nome"], cmd))
    if not comandos:
        return ""

    def rodar(item):
        nome, cmd = item
        try:
            r = subprocess.run(cmd, cwd=str(RAIZ), capture_output=True, text=True, timeout=8)
            return f"{nome}: {r.stdout.strip()}" if r.returncode == 0 and r.stdout.strip() else ""
        except Exception:
            return ""

    with ThreadPoolExecutor(max_workers=len(comandos)) as grupo:
        linhas = [l for l in grupo.map(rodar, comandos) if l]
    if not linhas:
        return ""
    return ("\n\n[dados que o JARVIS já buscou agora pra esta pergunta. Responda direto com eles, "
            "sem rodar comando e sem aviso. Só rode algo se faltar o que ele pediu:]\n" + "\n".join(linhas))


class Turno:
    ocupado = threading.Lock()
    aguardando_confirmacao = False
    interrompido = False  # você apertou espaço no meio: esse pedido não fala mais nada


def interromper():
    if not Turno.ocupado.locked():
        return False
    Turno.interrompido = True
    SESSAO.interromper()
    log({"evento": "interrompido"})
    return True


def processar(audio=None, mime="audio/webm", texto=None):
    # Uma aprovação nativa do Codex é respondida pelo próximo comando de voz ou texto.
    if SESSAO.tem_aprovacao():
        try:
            if audio is not None:
                EVENTOS.emitir({"tipo": "estado", "estado": "transcrevendo"})
                texto = transcrever(audio, mime)
            texto = (texto or "").strip()
            if not texto:
                EVENTOS.emitir({"tipo": "aviso", "texto": "Não consegui entender. Diga confirma ou cancela."})
                return
            EVENTOS.emitir({"tipo": "voce", "texto": texto})
            palavras = normalizar(texto)
            if eh_confirmacao(texto):
                SESSAO.resolver_aprovacao(True)
                EVENTOS.emitir({"tipo": "aviso", "texto": "Autorização enviada ao Codex."})
            elif palavras and palavras[0] in {"cancela", "cancelar", "nao", "negativo", "desiste"}:
                SESSAO.resolver_aprovacao(False)
                EVENTOS.emitir({"tipo": "aviso", "texto": "Solicitação recusada."})
            else:
                EVENTOS.emitir({"tipo": "aviso", "texto": "O Codex aguarda confirmação. Diga confirma ou cancela."})
        except Exception as erro:
            EVENTOS.emitir({"tipo": "aviso", "texto": f"Não consegui responder à aprovação: {erro}"})
        return

    # Se o pedido anterior foi interrompido, ele libera em instantes: espera um pouco.
    if not Turno.ocupado.acquire(timeout=10 if Turno.interrompido else 0.01):
        EVENTOS.emitir({"tipo": "aviso", "texto": "Ainda estou no pedido anterior, Senhor."})
        return
    token = ESTADO / "confirmado"
    inicio = time.time()
    registro = {"evento": "turno"}
    try:
        if audio is not None:
            EVENTOS.emitir({"tipo": "estado", "estado": "transcrevendo"})
            texto = transcrever(audio, mime)
            registro["transcricao_s"] = round(time.time() - inicio, 2)
            if Turno.interrompido:
                registro["interrompido"] = True
                return
        texto = (texto or "").strip()
        if not texto:
            EVENTOS.emitir({"tipo": "aviso", "texto": "Não consegui ouvir. Segure o espaço e fale de novo."})
            EVENTOS.emitir({"tipo": "estado", "estado": "parado"})
            return
        EVENTOS.emitir({"tipo": "voce", "texto": texto})
        registro["voce"] = texto

        # A trava só abre quando ele pediu "Confirma?" e você respondeu que sim.
        if Turno.aguardando_confirmacao and eh_confirmacao(texto):
            ESTADO.mkdir(exist_ok=True)
            token.write_text(str(time.time()))
            registro["confirmou"] = True

        EVENTOS.emitir({"tipo": "estado", "estado": "pensando"})
        t_codex = time.time()

        def avisar(frase=None):
            # "Um instante, Senhor." sai na hora, enquanto ele trabalha.
            if Turno.interrompido:
                return
            frase = limpar_para_fala(frase or "")[:160]
            pronta = not frase
            if pronta:
                frase = random.choice(AVISOS_PRONTOS)
            registro["aviso"] = frase + (" (pronta)" if pronta else "")
            registro["aviso_s"] = round(time.time() - inicio, 2)
            if CFG["eleven_key"]:
                id_fala = Fala.fixa(frase) if pronta else Fala.criar(frase)
                EVENTOS.emitir({"tipo": "fala", "texto": frase, "audio": f"/api/voz/{id_fala}"})

        t_busca = time.time()
        dados = prebusca(texto)
        if dados:
            registro["prebusca_s"] = round(time.time() - t_busca, 2)
        r = SESSAO.perguntar(texto + dados, ao_avisar=avisar, aviso_apos=2.5 if dados else None)
        registro["codex_s"] = round(time.time() - t_codex, 2)
        registro["cedo"] = bool(r.get("cedo"))
        if SESSAO.turno:
            registro["etapas"] = {k: v for k, v in SESSAO.turno.marcas.items() if k != "envio"}
        if Turno.interrompido or r.get("interrompido"):
            registro["interrompido"] = True
            return
        registro["ferramentas"] = SESSAO.ferramentas_turno
        resposta = limpar_para_fala(r.get("result") or "") or "Feito."
        if r.get("is_error"):
            registro["erro"] = r.get("result")
        Turno.aguardando_confirmacao = pediu_confirmacao(resposta)

        audio_url = f"/api/voz/{Fala.criar(resposta)}" if CFG["eleven_key"] else ""
        registro["resposta"] = resposta
        registro["total_s"] = round(time.time() - inicio, 2)
        EVENTOS.emitir({
            "tipo": "resposta", "texto": resposta, "audio": audio_url,
            "segundos": registro["total_s"], "confirmar": Turno.aguardando_confirmacao,
        })
        EVENTOS.emitir({"tipo": "estado", "estado": "parado"})
    except Exception as erro:
        registro["erro"] = repr(erro)
        EVENTOS.emitir({"tipo": "aviso", "texto": f"Deu erro: {erro}"})
        EVENTOS.emitir({"tipo": "estado", "estado": "parado"})
    finally:
        if token.exists():
            token.unlink()
        log(registro)
        Turno.interrompido = False
        Turno.ocupado.release()


def config_atual():
    return {"voz": CFG["voz"], "velocidade": CFG["velocidade_voz"], "vozes": VOZES}


def gravar_avisos_prontos():
    """Deixa as frases prontas ("Um instante, Senhor.") gravadas na voz escolhida."""
    if CFG["eleven_key"]:
        for frase in AVISOS_PRONTOS:
            Fala.fixa(frase)


def aquecer_atalhos():
    """Roda atalhos lentos quando abre (ex.: o resumo da isca de ontem), pra resposta sair na hora."""
    for comando in filter(None, (c.strip() for c in CFG["aquecer_atalhos"].split(";"))):
        partes = shlex.split(comando)
        try:
            subprocess.run([sys.executable, str(RAIZ / "atalhos" / partes[0])] + partes[1:],
                           cwd=str(RAIZ), capture_output=True, timeout=180)
            log({"evento": "atalho_aquecido", "comando": comando})
        except Exception as erro:
            log({"evento": "atalho_falhou", "comando": comando, "erro": repr(erro)})


def aquecer():
    """Primeira chamada ao abrir: conecta as ferramentas e deixa o Codex pronto."""
    threading.Thread(target=aquecer_atalhos, daemon=True).start()
    EVENTOS.emitir({"tipo": "estado", "estado": "aquecendo"})
    try:
        SESSAO.iniciar()
        gravar_avisos_prontos()
        if CFG["aquecer"]:
            with Turno.ocupado:
                SESSAO.perguntar("(Mensagem automática de início. Não use ferramentas. Responda só: Pronto.)", limite=120)
    finally:
        EVENTOS.emitir({"tipo": "estado", "estado": "parado"})


# ---------------------------------------------------------------------- HTTP

TIPOS = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon"}


class Servidor(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def responder(self, codigo, corpo=b"", tipo="application/json"):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        caminho = self.path.split("?")[0]
        if caminho == "/api/eventos":
            return self.eventos()
        if caminho == "/api/config":
            return self.responder(200, json.dumps(config_atual(), ensure_ascii=False).encode())
        if caminho.startswith("/api/amostra/"):
            return self.amostra(caminho.rsplit("/", 1)[-1])
        if caminho.startswith("/api/voz/"):
            return self.voz(caminho.rsplit("/", 1)[-1])
        if caminho == "/api/saude":
            corpo = json.dumps({"codex": SESSAO.vivo(), "pasta": str(CFG["pasta"]), "modelo": CFG["modelo"],
                                "telas": len(EVENTOS.ouvintes)})
            return self.responder(200, corpo.encode())
        arquivo = (WEB / ("index.html" if caminho == "/" else caminho.lstrip("/"))).resolve()
        if WEB.resolve() not in arquivo.parents and arquivo != WEB.resolve() / "index.html":
            return self.responder(404, b"{}")
        if not arquivo.is_file():
            return self.responder(404, b"{}")
        self.responder(200, arquivo.read_bytes(), TIPOS.get(arquivo.suffix, "application/octet-stream"))

    def do_POST(self):
        tamanho = int(self.headers.get("Content-Length", "0"))
        corpo = self.rfile.read(tamanho) if tamanho else b""
        if self.path == "/api/interromper":
            return self.responder(200, json.dumps({"interrompeu": interromper()}).encode())
        if self.path in ("/api/audio", "/api/texto") and Turno.ocupado.locked() and not Turno.interrompido and not SESSAO.tem_aprovacao():
            return self.responder(409, b'{"ocupado":true}')  # a tela avisa e espera
        if self.path == "/api/audio":
            if len(corpo) < 2000:  # toque rápido no espaço, sem fala
                return self.responder(200, b'{"ok":false}')
            mime = self.headers.get("Content-Type", "audio/webm")
            threading.Thread(target=processar, kwargs={"audio": corpo, "mime": mime}, daemon=True).start()
            return self.responder(202, b'{"ok":true}')
        if self.path == "/api/texto":
            texto = json.loads(corpo or b"{}").get("texto", "")
            threading.Thread(target=processar, kwargs={"texto": texto}, daemon=True).start()
            return self.responder(202, b'{"ok":true}')
        if self.path == "/api/diag":  # a tela avisa se a voz tocou ou falhou
            try:
                dados = json.loads(corpo or b"{}")
            except ValueError:
                dados = {}
            log({"evento": "tela", "tipo": str(dados.get("evento", ""))[:40],
                 "detalhe": str(dados.get("detalhe", ""))[:300]})
            return self.responder(200, b'{"ok":true}')
        if self.path == "/api/config":
            pedido = json.loads(corpo or b"{}")
            ids = {v["id"] for v in VOZES}
            if pedido.get("voz") in ids:
                CFG["voz"] = pedido["voz"]
            if pedido.get("velocidade") is not None:
                CFG["velocidade_voz"] = round(min(1.2, max(0.7, float(pedido["velocidade"]))), 2)
            salvar_preferencias()
            log({"evento": "config", "voz": CFG["voz"], "velocidade": CFG["velocidade_voz"]})
            threading.Thread(target=gravar_avisos_prontos, daemon=True).start()
            return self.responder(200, json.dumps(config_atual(), ensure_ascii=False).encode())
        if self.path == "/api/reiniciar":
            SESSAO.parar()
            Turno.aguardando_confirmacao = False
            threading.Thread(target=aquecer, daemon=True).start()
            return self.responder(200, b'{"ok":true}')
        self.responder(404, b"{}")

    def eventos(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        q = EVENTOS.assinar()
        try:
            while True:
                try:
                    evento = q.get(timeout=15)
                    dados = "data: " + json.dumps(evento, ensure_ascii=False) + "\n\n"
                except queue.Empty:
                    dados = ": ping\n\n"
                self.wfile.write(dados.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            EVENTOS.sair(q)

    def amostra(self, voz):
        if voz not in {v["id"] for v in VOZES} or not CFG["eleven_key"]:
            return self.responder(404, b"{}")
        arquivo = ESTADO / "amostras" / f"{voz}-{CFG['velocidade_voz']}.mp3"
        if not arquivo.exists():
            dados = Fala(AMOSTRA, voz=voz).esperar()
            if not dados:
                return self.responder(502, b"{}")
            arquivo.parent.mkdir(parents=True, exist_ok=True)
            arquivo.write_bytes(dados)
        self.responder(200, arquivo.read_bytes(), "audio/mpeg")

    def voz(self, id_fala):
        fala = Fala.todas.get(id_fala) or Fala.fixas.get(id_fala)
        if not fala:
            return self.responder(404, b"{}")
        if fala.pronto and fala.erro:
            return self.responder(502, b"{}")
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Cache-Control", "no-store")
        if fala.pronto:
            self.send_header("Content-Length", str(len(fala.pedacos)))
        self.end_headers()
        try:
            for pedaco in fala.ler():
                self.wfile.write(pedaco)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


def completar_path():
    """Quando abre pelo app (fora do terminal), o PATH vem curto. Procura nos lugares de costume."""
    atual = os.environ.get("PATH", "").split(os.pathsep)
    for pasta in ("~/.npm-global/bin", "~/.local/bin", "~/.codex/bin", "/opt/homebrew/bin",
                  "/usr/local/bin", "/opt/homebrew/opt/ffmpeg-full/bin"):
        pasta = os.path.expanduser(pasta)
        if os.name == "nt":
            npm_global = os.path.join(os.environ.get("APPDATA", ""), "npm")
            if npm_global and os.path.isdir(npm_global) and npm_global not in atual:
                atual.append(npm_global)
        if os.path.isdir(pasta) and pasta not in atual:
            atual.append(pasta)
    os.environ["PATH"] = os.pathsep.join(atual)


def main():
    completar_path()
    if not CFG["pasta"].is_dir():
        sys.exit(f"JARVIS_PASTA não existe: {CFG['pasta']}")
    if not (shutil.which(CFG["codex_bin"]) or shutil.which(CFG["codex_bin"] + ".cmd")):
        sys.exit("Não achei o Codex CLI (comando codex). Instale e faça login: https://developers.openai.com/codex/cli")
    if not CFG["eleven_key"]:
        print("Aviso: sem ELEVENLABS_API_KEY. Ele vai responder só em texto na tela.")
    servidor = ThreadingHTTPServer(("127.0.0.1", CFG["porta"]), Servidor)
    servidor.daemon_threads = True
    url = f"http://localhost:{CFG['porta']}"
    print(f"JARVIS no ar em {url}  (pasta: {CFG['pasta']})")

    try:
        from security.agent import iniciar as iniciar_seguranca
        ponte_seguranca = iniciar_seguranca(EVENTOS, ESTADO, CFG)
    except Exception as erro:
        ponte_seguranca = None
        print("JARVIS: módulo de segurança não iniciou:", repr(erro))

    def encerrar(*_):
        SESSAO.parar()
        if ponte_seguranca:
            ponte_seguranca.stop()
        os._exit(0)

    signal.signal(signal.SIGTERM, encerrar)
    threading.Thread(target=aquecer, daemon=True).start()
    if "--sem-abrir" not in sys.argv:
        webbrowser.open(url)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        SESSAO.parar()


if __name__ == "__main__":
    main()
