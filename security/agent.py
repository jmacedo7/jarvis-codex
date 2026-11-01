import threading
from pathlib import Path
from .bridge import MobileBridge
def iniciar(eventos,estado_dir,cfg):
    bridge=MobileBridge(cfg,estado_dir,eventos)
    if bridge.start(): print("JARVIS: ponte móvel criptografada conectada.")
    else: print("JARVIS: ponte móvel não configurada; execute python -m security.setup.")
    if str(cfg.get("face_enabled","1")).lower() not in ("1","true","yes","on"):
        if eventos: eventos.emitir({"tipo":"face_status","status":"disabled","name":None,"similarity":None})
        return bridge
    db=Path(__file__).resolve().parents[1]/".estado"/"security"/"faces.dpapi"
    if not db.exists():
        print('JARVIS: cadastre ao menos um familiar: python -m security.face_guard enroll "Nome".')
        if eventos: eventos.emitir({"tipo":"face_status","status":"not_enrolled","name":None,"similarity":None})
        return bridge
    if eventos: eventos.emitir({"tipo":"face_status","status":"starting","name":None,"similarity":None})
    def camera():
        try:
            from .face_guard import run
            def status(estado,nome=None,similaridade=None):
                if eventos: eventos.emitir({"tipo":"face_status","status":estado,"name":nome,"similarity":similaridade})
            run(lambda when: bridge.alert_unknown(when), on_status=status)
        except Exception as exc:
            print("JARVIS: reconhecimento facial não iniciou:",repr(exc))
            if eventos:
                eventos.emitir({"tipo":"face_status","status":"error","name":None,"similarity":None,"detail":str(exc)[:200]})
                eventos.emitir({"tipo":"aviso","texto":"Reconhecimento facial indisponível: "+str(exc)[:200]})
    threading.Thread(target=camera,name="jarvis-face-guard",daemon=True).start()
    return bridge
