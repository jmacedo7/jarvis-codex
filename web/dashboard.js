(() => {
  const $=id=>document.getElementById(id);
  const boot=$("jarvis-boot"), status=$("boot-status"), sub=$("boot-sub"), ring=$("scan-progress"), meter=$("boot-meter-fill");
  let progress=3, unlocked=false, dashboardLoaded=false, knownNotifications=new Set();
  const setProgress=n=>{progress=Math.max(progress,Math.min(100,n));ring.style.strokeDashoffset=String(628-(628*progress/100));meter.style.width=progress+"%";};
  const showStatus=(title,detail,pct)=>{status.textContent=title;sub.textContent=detail;if(pct!=null)setProgress(pct);};
  function unlock(name){
    if(unlocked)return;unlocked=true;setProgress(100);showStatus("Identidade confirmada", "Bem-vindo de volta, "+(name||"Senhor")+". Preparando seu ambiente.",100);
    document.body.classList.add("jarvis-authenticated");
    setTimeout(()=>boot.classList.add("unlocked"),1150);
    toast("JARVIS ONLINE","Acesso liberado","Reconhecimento concluído. Seus módulos estão sendo sincronizados.");
    loadDashboard();
  }
  function face(e){
    if(unlocked)return;
    const detail=e.detail||"";
    if(e.status==="starting"){showStatus("Inicializando biometria","Carregando o modelo facial local e preparando a câmera.",8);}
    else if(e.status==="active"){showStatus("Câmera preparada","Centralize seu rosto no enquadramento para iniciar a verificação.",18);}
    else if(e.status==="no_face"){showStatus("Procurando seu rosto","Olhe diretamente para a câmera. A análise acontece neste computador.",34);}
    else if(e.status==="unknown"){showStatus("Analisando identidade","Rosto detectado. Comparando com o cadastro protegido.",66);}
    else if(e.status==="recognized"){unlock(e.name);}
    else if(e.status==="camera_error"){showStatus("Câmera indisponível",detail||"Verifique a conexão e feche outros aplicativos que estejam usando a webcam.",0);}
    else if(e.status==="error"){showStatus("Falha na biometria",detail||"Confira as dependências no ambiente .venv-security e reinicie o JARVIS.",0);}
    else if(e.status==="not_enrolled"){showStatus("Cadastro necessário","Nenhum rosto cadastrado. Execute o comando de cadastro facial no ambiente do JARVIS.",0);}
    else if(e.status==="disabled"){showStatus("Biometria desativada","Ative JARVIS_FACE_ENABLED=1 no arquivo .env e reinicie.",0);}
  }
  function toast(title,heading,body){
    const host=$("jarvis-toasts"),node=document.createElement("div");node.className="jarvis-toast";
    const small=document.createElement("small");small.textContent=title;
    const strong=document.createElement("strong");strong.textContent=heading;
    const p=document.createElement("p");p.textContent=body;
    node.append(small,strong,p);host.append(node);setTimeout(()=>{node.style.opacity="0";node.style.transform="translateX(20px)";setTimeout(()=>node.remove(),400);},6500);
  }
  function clock(){const now=new Date();$("dash-time").textContent=now.toLocaleTimeString("pt-BR",{hour:"2-digit",minute:"2-digit"});$("dash-date").textContent=now.toLocaleDateString("pt-BR",{weekday:"long",day:"2-digit",month:"long"});}
  async function loadDashboard(){
    clock();
    try{
      const r=await fetch("/api/painel",{cache:"no-store"});if(!r.ok)throw new Error("painel indisponível");
      const data=await r.json(),items=data.notifications||[];
      $("dash-notification-count").textContent=items.length+" recentes";
      const list=$("dash-notifications");list.replaceChildren();
      if(!items.length){$("dash-notifications-empty").hidden=false;}
      else{$("dash-notifications-empty").hidden=true;items.slice(0,5).forEach(n=>{const item=document.createElement("div");item.className="dash-notification";const strong=document.createElement("strong");strong.textContent=(n.app||"Celular")+" · "+(n.title||"Notificação");const text=document.createElement("span");text.textContent=n.text||"Nova notificação";item.append(strong,text);list.append(item);});}
      items.slice().reverse().forEach(n=>{const id=[n.received_at,n.app,n.title,n.text].join("|");if(knownNotifications.has(id))return;knownNotifications.add(id);if(dashboardLoaded)toast("NOTIFICAÇÃO DO CELULAR",(n.app||"Celular")+" · "+(n.title||"Nova notificação"),n.text||"Você recebeu uma notificação.");});dashboardLoaded=true;
    }catch(e){$("dash-notification-count").textContent="Sem conexão";}
  }
  function connect(){const source=new EventSource("/api/eventos");source.onmessage=ev=>{try{const e=JSON.parse(ev.data);if(e.tipo==="face_status")face(e);}catch(_){}};}
  clock();setInterval(clock,1000);connect();setTimeout(()=>{if(!unlocked)showStatus("Aguardando reconhecimento","A câmera está iniciando. Mantenha o rosto visível por alguns segundos.",12);},8000);
  setInterval(()=>{if(unlocked)loadDashboard();},30000);
  $("dash-email").textContent="Integração de e-mail não conectada";
  $("dash-events").textContent="Agenda não conectada";
  $("dash-weather").textContent="Configure uma cidade para consultar o clima";
})();