"""Google Workspace local: OAuth de aplicativo desktop e escopos somente leitura."""
import base64
import datetime as dt
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

SCOPES = "openid email https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/calendar.readonly"


def _b64(data):
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _headers(message):
    return {str(item.get("name", "")).lower(): str(item.get("value", ""))
            for item in (message.get("payload") or {}).get("headers", [])}


def _event(item):
    start = item.get("start") or {}
    return {
        "id": str(item.get("id", "")),
        "title": str(item.get("summary") or "Evento sem título")[:180],
        "start": str(start.get("dateTime") or start.get("date") or ""),
        "all_day": bool(start.get("date") and not start.get("dateTime")),
        "location": str(item.get("location") or "")[:180],
    }


class GoogleWorkspace:
    """OAuth desktop com PKCE; tokens guardados localmente e acesso apenas para leitura."""

    def __init__(self, state_dir, client_id="", client_secret=""):
        self.state_dir = state_dir
        self.client_id = (client_id or "").strip()
        self.client_secret = (client_secret or "").strip()
        self.token_path = state_dir / "google_tokens.bin"
        self.lock = threading.RLock()
        self.auth_state = "idle"
        self.auth_message = ""
        self.auth_url = ""
        self._state = ""
        self._verifier = ""
        self._redirect = ""
        self._cache = None
        self._cache_at = 0.0

    @property
    def configured(self):
        return bool(self.client_id and self.client_secret)

    def _save(self, token):
        self.state_dir.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(token).encode("utf-8")
        if os.name == "nt":
            try:
                import win32crypt
                raw = b"JARVIS-DPAPI-1\n" + win32crypt.CryptProtectData(
                    raw, "JARVIS Google OAuth", None, None, None, 0
                )[1]
            except Exception as exc:
                raise RuntimeError("Não foi possível proteger o token Google com DPAPI.") from exc
        else:
            raw = b"JARVIS-JSON-1\n" + raw
        temporary = self.token_path.with_suffix(".tmp")
        temporary.write_bytes(raw)
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        temporary.replace(self.token_path)

    def _load(self):
        try:
            raw = self.token_path.read_bytes()
        except FileNotFoundError:
            return None
        if raw.startswith(b"JARVIS-DPAPI-1\n"):
            if os.name != "nt":
                raise RuntimeError("Token Google protegido por outra instalação do Windows.")
            import win32crypt
            raw = win32crypt.CryptUnprotectData(raw.split(b"\n", 1)[1], None, None, None, 0)[1]
        elif raw.startswith(b"JARVIS-JSON-1\n"):
            raw = raw.split(b"\n", 1)[1]
        else:
            raise RuntimeError("Formato de token Google desconhecido.")
        return json.loads(raw.decode("utf-8"))

    def start_authorization(self):
        if not self.configured:
            return {"status": "needs_credentials", "message": "Configure GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET no .env."}
        with self.lock:
            if self.auth_state == "waiting" and self.auth_url:
                return {"status": "waiting", "authorization_url": self.auth_url}
            state = secrets.token_urlsafe(32)
            verifier = _b64(secrets.token_bytes(48))
            challenge = _b64(hashlib.sha256(verifier.encode("ascii")).digest())
            owner = self

            class Callback(BaseHTTPRequestHandler):
                def log_message(self, *args):
                    pass

                def do_GET(self):
                    query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                    returned_state = (query.get("state") or [""])[0]
                    code = (query.get("code") or [""])[0]
                    error = (query.get("error") or [""])[0]
                    if returned_state != owner._state:
                        status, title, detail = 403, "Autorização recusada", "A validação de segurança não corresponde."
                        owner._finish("error", detail)
                    elif error:
                        status, title, detail = 400, "Autorização cancelada", "O Google retornou: " + error[:100]
                        owner._finish("error", detail)
                    elif not code:
                        status, title, detail = 400, "Código ausente", "O Google não retornou o código de autorização."
                        owner._finish("error", detail)
                    else:
                        try:
                            token = owner._exchange(code)
                            owner._save(token)
                            status, title, detail = 200, "Google conectado", "Gmail e Agenda autorizados em modo somente leitura. Você pode fechar esta janela."
                            owner._finish("connected", detail)
                        except Exception as exc:
                            status, title, detail = 400, "Falha na autorização", str(exc)[:220]
                            owner._finish("error", detail)
                    safe = detail.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    page = (
                        "<!doctype html><html lang='pt-BR'><meta charset='utf-8'>"
                        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                        "<title>JARVIS · Google</title><body style='margin:0;background:#06111a;color:#eafaff;"
                        "font:16px system-ui;display:grid;min-height:100vh;place-items:center'>"
                        "<main style='max-width:480px;padding:36px'><p style='color:#8cecff'>J.A.R.V.I.S.</p>"
                        "<h1>" + title + "</h1><p>" + safe + "</p></main></body></html>"
                    ).encode("utf-8")
                    self.send_response(status)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(page)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(page)

            callback = HTTPServer(("127.0.0.1", 0), Callback)
            callback.timeout = 600
            self._state, self._verifier = state, verifier
            self._redirect = "http://127.0.0.1:" + str(callback.server_address[1]) + "/"
            params = {
                "client_id": self.client_id, "redirect_uri": self._redirect,
                "response_type": "code", "scope": SCOPES, "state": state,
                "code_challenge": challenge, "code_challenge_method": "S256",
                "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true",
            }
            self.auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
            self.auth_state = "waiting"
            self.auth_message = "Aguardando autorização do Google."
            threading.Thread(target=self._serve, args=(callback,), daemon=True, name="jarvis-google-oauth").start()
            return {"status": "waiting", "authorization_url": self.auth_url}

    def _serve(self, callback):
        try:
            callback.handle_request()
            with self.lock:
                if self.auth_state == "waiting":
                    self.auth_state = "error"
                    self.auth_message = "A autorização expirou. Tente novamente."
        finally:
            callback.server_close()
            with self.lock:
                self._state = self._verifier = self._redirect = self.auth_url = ""

    def _finish(self, state, message):
        with self.lock:
            self.auth_state = state
            self.auth_message = message
            self._cache = None

    def _token_request(self, values):
        request = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=urllib.parse.urlencode(values).encode("ascii"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read(800).decode("utf-8", "replace")
            raise RuntimeError("Google OAuth HTTP " + str(exc.code) + ": " + detail[:220]) from exc

    def _exchange(self, code):
        token = self._token_request({
            "code": code, "client_id": self.client_id, "client_secret": self.client_secret,
            "redirect_uri": self._redirect, "grant_type": "authorization_code",
            "code_verifier": self._verifier,
        })
        if not token.get("refresh_token"):
            old = self._load() or {}
            if old.get("refresh_token"):
                token["refresh_token"] = old["refresh_token"]
            else:
                raise RuntimeError("Google não entregou refresh token. Revogue o acesso anterior do JARVIS e conecte novamente.")
        token["expires_at"] = int(time.time()) + int(token.get("expires_in", 3600)) - 60
        return token

    def _access(self):
        token = self._load()
        if not token:
            raise RuntimeError("Google ainda não foi conectado.")
        if int(token.get("expires_at", 0)) > int(time.time()) + 30:
            return token["access_token"]
        refresh = token.get("refresh_token")
        if not refresh:
            raise RuntimeError("Autorização Google expirada. Conecte novamente.")
        fresh = self._token_request({
            "client_id": self.client_id, "client_secret": self.client_secret,
            "refresh_token": refresh, "grant_type": "refresh_token",
        })
        token["access_token"] = fresh["access_token"]
        token["expires_at"] = int(time.time()) + int(fresh.get("expires_in", 3600)) - 60
        self._save(token)
        return token["access_token"]

    def _get(self, url, params=None):
        target = url + (("?" + urllib.parse.urlencode(params or {}, doseq=True)) if params else "")
        for attempt in range(2):
            request = urllib.request.Request(target, headers={
                "Authorization": "Bearer " + self._access(), "Accept": "application/json"
            })
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code == 401 and attempt == 0:
                    token = self._load() or {}
                    token["expires_at"] = 0
                    self._save(token)
                    continue
                detail = exc.read(800).decode("utf-8", "replace")
                raise RuntimeError("Google API HTTP " + str(exc.code) + ": " + detail[:220]) from exc
        raise RuntimeError("Não foi possível renovar a autorização Google.")

    def _emails(self):
        listing = self._get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            {"q": "is:unread", "maxResults": 5},
        )
        rows = []
        for item in (listing.get("messages") or [])[:5]:
            message = self._get(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/" + urllib.parse.quote(item["id"], safe=""),
                {"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
            )
            headers = _headers(message)
            rows.append({
                "id": str(item.get("id", "")),
                "from": headers.get("from", "Remetente desconhecido")[:140],
                "subject": headers.get("subject", "(sem assunto)")[:160],
                "date": headers.get("date", "")[:80],
                "snippet": str(message.get("snippet", ""))[:220],
            })
        return rows

    def _events(self):
        now = dt.datetime.now(dt.timezone.utc)
        until = now + dt.timedelta(days=7)
        response = self._get(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            {
                "timeMin": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
                "timeMax": until.isoformat(timespec="seconds").replace("+00:00", "Z"),
                "maxResults": 8, "singleEvents": "true", "orderBy": "startTime",
            },
        )
        return [_event(item) for item in (response.get("items") or [])[:8]]

    def dashboard(self, force=False):
        if not self.configured:
            return {"status": "needs_credentials", "message": "Configure GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET no .env.",
                    "account": "", "emails": [], "events": []}
        with self.lock:
            if self.auth_state == "waiting":
                return {"status": "waiting", "message": self.auth_message, "account": "", "emails": [], "events": []}
            if not force and self._cache is not None and time.time() - self._cache_at < 25:
                return self._cache
        try:
            if not self._load():
                result = {"status": "error" if self.auth_state == "error" else "not_connected",
                          "message": self.auth_message or "Conecte sua conta Google para liberar Gmail e Agenda.",
                          "account": "", "emails": [], "events": []}
            else:
                account = self._get("https://www.googleapis.com/oauth2/v2/userinfo").get("email", "")
                result = {"status": "connected", "message": "Google conectado em modo somente leitura.",
                          "account": account, "emails": self._emails(), "events": self._events()}
        except Exception as exc:
            message = str(exc)
            if "HTTP 403" in message:
                status = "api_not_enabled"
                message = "Google respondeu HTTP 403. Confira Gmail API, Google Calendar API e a conta de teste OAuth."
            elif "HTTP 401" in message or "expirada" in message.lower() or "refresh token" in message.lower():
                status = "authorization_required"
                message = "A autorização Google expirou ou foi revogada. Conecte novamente."
            else:
                status = "error"
                message = message[:220]
            result = {"status": status, "message": message, "account": "", "emails": [], "events": []}
        with self.lock:
            self._cache = result
            self._cache_at = time.time()
        return result

    def disconnect(self):
        with self.lock:
            try:
                self.token_path.unlink()
            except FileNotFoundError:
                pass
            self._cache = None
            self._cache_at = 0
            self.auth_state = "idle"
            self.auth_message = "Conta Google desconectada deste computador."
        return {"status": "not_connected", "message": self.auth_message}
