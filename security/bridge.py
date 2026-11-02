import base64, hashlib, json, os, threading, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
AAD = b"JARVIS-MOBILE-v1"
def _key(secret):
    if not secret or len(secret) < 24: raise ValueError("JARVIS_MOBILE_SECRET ausente ou muito curto")
    return hashlib.sha256(secret.encode("utf-8")).digest()
def encrypt(payload, secret):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12); raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    return "v1." + base64.urlsafe_b64encode(nonce + AESGCM(_key(secret)).encrypt(nonce, raw, AAD)).decode().rstrip("=")
def decrypt(token, secret):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not token.startswith("v1."): raise ValueError("Versão de mensagem desconhecida")
    encoded = token[3:]; raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    return json.loads(AESGCM(_key(secret)).decrypt(raw[:12], raw[12:], AAD).decode("utf-8"))
class MobileBridge:
    def __init__(self, cfg, state_dir, events=None):
        self.server=(cfg.get("ntfy_server") or "https://ntfy.sh").rstrip("/")
        self.inbox=cfg.get("ntfy_inbox","").strip(); self.alerts=cfg.get("ntfy_alerts","").strip()
        self.secret=cfg.get("mobile_secret",""); self.state_dir=Path(state_dir); self.events=events
        self.stop_event=threading.Event(); self.thread=None
        self.online=False; self.last_error=""; self.last_connected_at=0; self.last_message_at=0
        self.last_message_id=""; self.invalid_messages=0; self.lock=threading.RLock()
    @property
    def enabled(self): return bool(self.inbox and self.alerts and self.secret)
    def publish(self, topic, payload, title="JARVIS", priority="default"):
        if not self.enabled or not topic: return False
        body=encrypt(payload,self.secret).encode()
        req=urllib.request.Request(self.server+"/"+urllib.parse.quote(topic,safe=""),data=body,method="POST",
            headers={"Content-Type":"text/plain; charset=utf-8","Title":title,"Priority":priority,"Cache":"no"})
        with urllib.request.urlopen(req,timeout=15) as response: return 200 <= response.status < 300
    def alert_unknown(self, when=None):
        # Generic plaintext alert: no photo, name, face template, or personal details.
        body=("O JARVIS detectou uma pessoa não reconhecida. Horário: "+
              time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(when or time.time())))
        req=urllib.request.Request(self.server+"/"+urllib.parse.quote(self.alerts,safe=""),
            data=body.encode("utf-8"),method="POST",
            headers={"Content-Type":"text/plain; charset=utf-8","Title":"JARVIS - Pessoa nao reconhecida","Priority":"high","Cache":"no"})
        with urllib.request.urlopen(req,timeout=15) as response: return 200 <= response.status < 300
    def _set_status(self, online=None, error=None):
        with self.lock:
            was_online=self.online
            if online is not None: self.online=bool(online)
            if error is not None: self.last_error=str(error)[:180]
            if self.online and not was_online: self.last_connected_at=int(time.time())
            snapshot=self.status()
        if self.events: self.events.emitir({"tipo":"mobile_status","status":snapshot})

    def status(self):
        with self.lock:
            return {
                "configured": self.enabled, "connected": self.online,
                "status": "not_configured" if not self.enabled else ("connected" if self.online else ("error" if self.last_error else "waiting")),
                "last_error": self.last_error, "last_connected_at": self.last_connected_at,
                "last_message_at": self.last_message_at, "invalid_messages": self.invalid_messages,
            }

    def _save_health(self, payload):
        sessions = []
        for item in (payload.get("sleep_sessions") or [])[:10]:
            if not isinstance(item, dict): continue
            stages = []
            for stage in (item.get("stages") or [])[:16]:
                if not isinstance(stage, dict): continue
                try: stage_type = int(stage.get("type", 0))
                except (TypeError, ValueError): stage_type = 0
                stages.append({
                    "type": max(0, min(7, stage_type)),
                    "start": str(stage.get("start", ""))[:40],
                    "end": str(stage.get("end", ""))[:40],
                })
            try: duration = int(item.get("duration_minutes", 0) or 0)
            except (TypeError, ValueError): duration = 0
            sessions.append({
                "start": str(item.get("start", ""))[:40],
                "end": str(item.get("end", ""))[:40],
                "duration_minutes": max(0, min(24 * 60, duration)),
                "stages": stages,
            })
        record = {
            "source": "Samsung Health via Health Connect",
            "synced_at": int(time.time()),
            "steps_today": max(0, min(200000, int(payload.get("steps_today", 0) or 0))),
            "sleep_sessions": sessions,
        }
        self.state_dir.mkdir(parents=True, exist_ok=True)
        path = self.state_dir / "health_summary.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
        if self.events: self.events.emitir({"tipo":"health_update","synced_at":record["synced_at"]})

    def _save_notification(self,payload):
        self.state_dir.mkdir(parents=True,exist_ok=True); path=self.state_dir/"mobile_notifications.jsonl"
        record={"received_at":int(time.time()),"app":str(payload.get("app",""))[:100],"title":str(payload.get("title",""))[:200],
            "text":str(payload.get("text",""))[:1500],"package":str(payload.get("package",""))[:160],"posted_at":int(payload.get("posted_at",0) or 0)}
        with path.open("a",encoding="utf-8") as f: f.write(json.dumps(record,ensure_ascii=False)+"\n")
        lines=path.read_text(encoding="utf-8").splitlines()
        if len(lines)>200: path.write_text("\n".join(lines[-200:])+"\n",encoding="utf-8")
        with self.lock:
            self.last_message_at=int(time.time())
            self.last_error=""
        if self.events:
            summary=(record["app"]+": "+record["title"]+" — "+record["text"]).strip(" :—")
            self.events.emitir({"tipo":"mobile_notification","received_at":record["received_at"],"app":record["app"],"title":record["title"]})
            self.events.emitir({"tipo":"aviso","texto":"Notificação recebida do celular: "+summary[:500]})
    def _listen(self):
        started=int(time.time())
        while not self.stop_event.is_set():
            cursor=self.last_message_id or str(started)
            url=self.server+"/"+urllib.parse.quote(self.inbox,safe="")+"/json?"+urllib.parse.urlencode({"since":cursor})
            try:
                req=urllib.request.Request(url,headers={"Accept":"application/x-ndjson"})
                with urllib.request.urlopen(req,timeout=75) as response:
                    self._set_status(online=True,error="")
                    for line in response:
                        if self.stop_event.is_set(): break
                        try:
                            msg=json.loads(line.decode("utf-8"))
                            if msg.get("id"): self.last_message_id=str(msg["id"])
                            if msg.get("event")!="message": continue
                            payload=decrypt(msg.get("message",""),self.secret)
                            if payload.get("kind")=="notification": self._save_notification(payload)
                            elif payload.get("kind")=="health_sync": self._save_health(payload)
                        except Exception:
                            with self.lock: self.invalid_messages+=1
                            self._set_status(error="Mensagem recebida, mas não pôde ser validada. Confira o pareamento.")
                    self._set_status(online=False)
                    self.stop_event.wait(5)
            except urllib.error.HTTPError as exc:
                self._set_status(online=False,error="ntfy respondeu HTTP "+str(exc.code)+".")
                self.stop_event.wait(5)
            except Exception as exc:
                self._set_status(online=False,error="Falha na conexão ntfy: "+type(exc).__name__)
                self.stop_event.wait(5)
    def start(self):
        if not self.enabled: return False
        self.thread=threading.Thread(target=self._listen,name="jarvis-mobile-bridge",daemon=True); self.thread.start(); return True
    def stop(self): self.stop_event.set()
