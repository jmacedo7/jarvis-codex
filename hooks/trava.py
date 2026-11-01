#!/usr/bin/env python3
"""Guardrail PreToolUse do JARVIS para Codex.

Bloqueia ações destrutivas, publicações/envios e alterações fora da pasta
configurada até o dono confirmar. O sandbox nativo do Codex continua sendo
a fronteira principal de isolamento.
"""
import json
import os
import re
import sys
from pathlib import Path

MCP_ARRISCADO = re.compile(
    r"(send|enviar|envio|criar|create|salvar|save|update|atualizar|anotar|delete|excluir|trash|apagar|"
    r"publicar|publish|tirar_do_ar|arquivar|cancelar|editar|edit|upload|move|mover|share|reply|forward|"
    r"draft|label|spam|respond|transfer|provision|set_|add_|remove|apply|duplicate|generate|reencode|"
    r"schedule|rename|enable|disable|finish|start_|onboarding|import|write|copy|merge|comment|resolve)",
    re.I,
)
MCP_LEITURA = re.compile(
    r"(list|listar|get|ver|buscar|search|read|ficha|metricas|quem_sou|quadro|assinantes|"
    r"suggest|count|status|show|preview|who_am_i|find|info|help|query|fetch|download)",
    re.I,
)
BASH_ARRISCADO = [
    r"\brm\b", r"\bmv\b", r"\bsudo\b", r"\bkill(all)?\b", r"\bpkill\b",
    r"\bchmod\b", r"\bchown\b", r"\bgit\s+(push|reset|clean|checkout|rebase|commit|merge)\b",
    r"\bcurl\b.*\s-X\s*(POST|PUT|PATCH|DELETE)\b",
    r"\bcurl\b.*\s(-d|--data\S*|-F|--form|-T|--upload-file)\b",
    r"\bnpm\s+publish\b", r"\bvercel\b", r"\bsupabase\b.*\b(delete|reset|push)\b",
    r"\bgh\s+\w+\s+(create|delete|merge|edit|close|comment)\b", r"\bdd\b", r"\btee\b",
]

def dentro_da_pasta(caminho, pasta):
    if not caminho or not pasta:
        return False
    alvo = os.path.realpath(os.path.expandvars(os.path.expanduser(str(caminho))))
    raiz = os.path.realpath(os.path.expandvars(os.path.expanduser(str(pasta))))
    try:
        return os.path.commonpath([alvo, raiz]) == raiz
    except (ValueError, OSError):
        return False

def negar(motivo):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"TRAVA DO JARVIS: {motivo} precisa da confirmação do dono. "
                "Não tente outro caminho. Explique exatamente a ação e pergunte: Confirma?"
            ),
        }
    }, ensure_ascii=False))
    raise SystemExit(0)

ZERNIO_LEITURA = {"check", "status", "accounts", "yt-playlists", "tiktok-info", "li-orgs",
                  "posts", "post-get", "autos", "auto-get", "auto-logs"}


def zernio_arriscado(comando):
    m = re.search(r"zernio\.py\s+(\S+)(?:\s+(\S+))?", comando)
    if not m:
        return False
    sub, metodo = m.group(1), (m.group(2) or "").upper()
    if sub == "api":
        return metodo != "GET"
    return sub not in ZERNIO_LEITURA


def alvos_patch(comando):
    alvos = []
    for linha in str(comando).splitlines():
        m = re.match(r"\*\*\*\s+(?:Add|Update|Delete)\s+File:\s*(.+?)\s*$", linha)
        if m:
            alvos.append(m.group(1).strip())
        m = re.match(r"\*\*\*\s+Move\s+to:\s*(.+?)\s*$", linha)
        if m:
            alvos.append(m.group(1).strip())
    return alvos

def main():
    try:
        evento = json.load(sys.stdin)
    except (ValueError, TypeError):
        return
    if evento.get("hook_event_name") != "PreToolUse":
        return
    estado_env = os.environ.get("JARVIS_ESTADO")
    estado = Path(estado_env) if estado_env else None
    pasta = os.environ.get("JARVIS_PASTA") or evento.get("cwd", "")
    confirmado = bool(estado_env and estado and (estado / "confirmado").exists())
    if confirmado:
        return
    nome = str(evento.get("tool_name", ""))
    entrada = evento.get("tool_input") or {}
    if nome.startswith("mcp__"):
        acao = nome.split("__")[-1]
        if MCP_ARRISCADO.search(acao) or not MCP_LEITURA.search(acao):
            negar(f"a ação do conector '{acao}'")
        return
    if nome == "apply_patch":
        alvos = alvos_patch(entrada.get("command", ""))
        if not alvos:
            negar("uma alteração de arquivo cujo destino não foi identificado")
        for alvo in alvos:
            caminho = alvo if os.path.isabs(alvo) else os.path.join(evento.get("cwd", ""), alvo)
            if not dentro_da_pasta(caminho, pasta):
                negar("escrever fora da pasta de trabalho")
        return
    if nome == "Bash":
        comando = str(entrada.get("command", ""))
        if zernio_arriscado(comando):
            negar("publicar, agendar ou mudar algo nas redes sociais")
        if any(re.search(p, comando, re.I) for p in BASH_ARRISCADO):
            negar("esse comando de terminal")
        if re.search(r"(?<![0-9&<])>{1,2}\s*([^\s;&|]+)", comando):
            negar("redirecionar a saída para um arquivo")
        if re.search(r"\b(osascript|powershell\s+-enc|certutil\s+-decode)\b", comando, re.I):
            negar("esse comando de terminal")
        return

if __name__ == "__main__":
    main()
