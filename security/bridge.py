import base64, hashlib, json, os, threading, time, urllib.parse, urllib.request
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
    @property
    def enabled(self): return bool(self.inbox and self.alerts and self.secret)
    def publish(self, topic, payload, title="JARVIS", priority="default"):
        if not self.enabled or not topic: return False
        body=encrypt(payload,self.secret).encode()
        req=urllib.request.Request(self.server+"/"+urllib.parse.quote(topic,safe=""),data=body,method="POST",
            headers={"Content-Type":"text/plain; charset=utf-8","Title":title,"Priority":priority,"Cache":"no"})
        with urllib.request.urlopen(req,timeout=15) as response: return 200 <= response.status < 300
    def alert_unknown(self, when=None):
        return self.publish(self.alerts,{"kind":"security_alert","event":"unknown_person","time":when or int(time.time()),"device":"JARVIS-PC"},
            "JARVIS • Pessoa não reconhecida","high")
    def _save_notification(self,payload):
        self.state_dir.mkdir(parents=True,exist_ok=True); path=self.state_dir/"mobile_notifications.jsonl"
        record={"received_at":int(time.time()),"app":str(payload.get("app",""))[:100],"title":str(payload.get("title",""))[:200],
            "text":str(payload.get("text",""))[:1500],"package":str(payload.get("package",""))[:160],"posted_at":int(payload.get("posted_at",0) or 0)}
        with path.open("a",encoding="utf-8") as f: f.write(json.dumps(record,ensure_ascii=False)+"\n")
        lines=path.read_text(encoding="utf-8").splitlines()
        if len(lines)>200: path.write_text("\n".join(lines[-200:])+"\n",encoding="utf-8")
        if self.events:
            summary=(record["app"]+": "+record["title"]+" — "+record["text"]).strip(" :—")
            self.events.emitir({"tipo":"aviso","texto":"Notificação recebida do celular: "+summary[:500]})
    def _listen(self):
        url=self.server+"/"+urllib.parse.quote(self.inbox,safe="")+"/json"
        while not self.stop_event.is_set():
            try:
                req=urllib.request.Request(url,headers={"Accept":"application/x-ndjson"})
                with urllib.request.urlopen(req,timeout=75) as response:
                    for line in response:
                        if self.stop_event.is_set(): break
                        try:
                            msg=json.loads(line.decode("utf-8"))
                            if msg.get("event")!="message": continue
                            payload=decrypt(msg.get("message",""),self.secret)
                            if payload.get("kind")=="notification": self._save_notification(payload)
                        except Exception: continue
            except Exception: self.stop_event.wait(5)
    def start(self):
        if not self.enabled: return False
        self.thread=threading.Thread(target=self._listen,name="jarvis-mobile-bridge",daemon=True); self.thread.start(); return True
    def stop(self): self.stop_event.set()
