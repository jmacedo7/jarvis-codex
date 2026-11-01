import json,secrets
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    env=ROOT/".env"; text=env.read_text(encoding="utf-8") if env.exists() else ""
    values={}
    for line in text.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k,v=line.split("=",1); values[k.strip()]=v.strip().strip('"').strip("'")
    if values.get("JARVIS_NTFY_INBOX") and values.get("JARVIS_NTFY_ALERTS") and values.get("JARVIS_MOBILE_SECRET"):
        print("Configuração já existe. Não vou sobrescrever segredos."); return
    inbox="jarvis-in-"+secrets.token_urlsafe(24).replace("-","").replace("_","")
    alerts="jarvis-alert-"+secrets.token_urlsafe(24).replace("-","").replace("_","")
    secret=secrets.token_urlsafe(48)
    block="\n# JARVIS mobile companion (local secrets; never commit .env)\nJARVIS_NTFY_SERVER=https://ntfy.sh\nJARVIS_NTFY_INBOX="+inbox+"\nJARVIS_NTFY_ALERTS="+alerts+"\nJARVIS_MOBILE_SECRET="+secret+"\nJARVIS_FACE_ENABLED=1\n"
    kept=[line for line in text.splitlines() if not line.startswith(("JARVIS_NTFY_SERVER=","JARVIS_NTFY_INBOX=","JARVIS_NTFY_ALERTS=","JARVIS_MOBILE_SECRET=","JARVIS_FACE_ENABLED="))]
    env.write_text("\n".join(kept).rstrip()+block,encoding="utf-8")
    pairing={"server":"https://ntfy.sh","inbox_topic":inbox,"alerts_topic":alerts,"shared_secret":secret}
    state=ROOT/".estado"; state.mkdir(exist_ok=True)
    (state/"mobile_pairing.json").write_text(json.dumps(pairing,indent=2),encoding="utf-8")
    print("Pareamento salvo em .estado/mobile_pairing.json. NÃO compartilhe nem envie ao GitHub.")
    print("Servidor:",pairing["server"]); print("Tópico de entrada:",inbox); print("Tópico de alertas:",alerts)
if __name__=="__main__": main()
