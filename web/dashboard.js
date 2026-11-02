(() => {
  const $=id=>document.getElementById(id);
  let unlocked=false,loaded=false,clockTimer=null;
  const seen=new Set();
  function pill(id,label,mode){const node=$(id);if(!node)return;node.textContent=label;node.dataset.mode=mode||"neutral";}
  function toast(title,body){const host=$("jarvis-toasts");if(!host)return;const node=document.createElement("div"),h=document.createElement("b"),p=document.createElement("span");node.className="orb-toast";h.textContent=title;p.textContent=body;node.append(h,p);host.append(node);setTimeout(()=>node.remove(),6500);}
  function updateClock(){const now=new Date();$("dash-time").textContent=now.toLocaleTimeString("pt-BR",{hour:"2-digit",minute:"2-digit",second:"2-digit"});$("dash-date").textContent=now.toLocaleDateString("pt-BR",{weekday:"long",day:"2-digit",month:"long"});}
  function face(e){
    if(unlocked)return;
    const detail=e.detail||"",boot=$("jarvis-boot");
    const show=(title,sub)=>{if($("boot-status"))$("boot-status").textContent=title;if($("boot-sub"))$("boot-sub").textContent=sub;};
    if(e.status==="starting")show("INICIALIZANDO BIOMETRIA","Carregando o modelo facial e preparando a câmera.");
    else if(e.status==="active")show("CÂMERA PREPARADA","Centralize seu rosto para iniciar a verificação.");
    else if(e.status==="no_face")show("PROCURANDO SEU ROSTO","Aguardando a primeira correspondência.");
    else if(e.status==="unknown")show("ANALISANDO IDENTIDADE","Comparando com o cadastro local protegido.");
    else if(e.status==="camera_error")show("CÂMERA INDISPONÍVEL",detail||"Verifique a webcam e tente novamente.");
    else if(e.status==="not_enrolled")show("CADASTRO NECESSÁRIO","Cadastre seu rosto antes de usar o bloqueio biométrico.");
    else if(e.status==="error")show("FALHA NA BIOMETRIA",detail||"Confira as dependências de segurança.");
    else if(e.status==="recognized"||e.status==="disabled"){
      unlocked=true;document.body.classList.add("jarvis-authenticated");
      if(boot)setTimeout(()=>boot.classList.add("unlocked"),700);
      loadDashboard();
    }
  }
  function renderRows(host,items,type){
    host.replaceChildren();
    if(!items||!items.length){const empty=document.createElement("div");empty.className="orb-empty";empty.textContent=type==="email"?"Nenhum e-mail não lido.":"Nenhum compromisso nos próximos sete dias.";host.append(empty);return;}
    items.forEach(x=>{
      const row=document.createElement("div"),title=document.createElement("b"),meta=document.createElement("small");
      row.className="orb-item";title.textContent=type==="email"?(x.subject||"(sem assunto)"):(x.title||"Evento");
      meta.textContent=type==="email"?(x.from||"Remetente desconhecido"):(x.start?new Date(x.start).toLocaleString("pt-BR",{dateStyle:"short",timeStyle:x.all_day?undefined:"short"}):"Horário não informado");
      row.append(title,meta);if(type==="email"&&x.snippet){const detail=document.createElement("span");detail.textContent=x.snippet;row.append(detail);}host.append(row);
    });
  }
  function updateGoogle(data){
    const g=data.google||{},connected=g.status==="connected",waiting=g.status==="waiting";
    pill("dash-email-state",connected?"CONECTADO":waiting?"AGUARDANDO":"OFFLINE",connected?"good":waiting?"pending":g.status==="error"||g.status==="api_not_enabled"||g.status==="authorization_required"?"bad":"neutral");
    pill("dash-calendar-state",connected?"CONECTADA":waiting?"AGUARDANDO":"OFFLINE",connected?"good":waiting?"pending":g.status==="error"||g.status==="api_not_enabled"||g.status==="authorization_required"?"bad":"neutral");
    $("dash-email-note").textContent=g.account?"Conta: "+g.account+" · somente leitura":(g.message||"Conta Google não conectada.");
    $("dash-calendar-note").textContent=connected?"Agenda principal · próximos sete dias":(g.message||"Próximos sete dias.");
    $("dash-google-connect").disabled=waiting||g.status==="needs_credentials";
    $("dash-google-connect").textContent=waiting?"AGUARDANDO…":g.status==="needs_credentials"?"CREDENCIAIS PENDENTES":connected?"ATUALIZAR":"CONECTAR GOOGLE";
    $("dash-google-disconnect").hidden=!connected;
    renderRows($("dash-email-list"),data.emails||[],"email");
    renderRows($("dash-calendar-list"),data.events||[],"calendar");
  }
  function updateHealth(data){
    const h=data.health||{},sessions=h.sleep_sessions||[],last=sessions[0];
    if(h.status==="synced"){
      pill("dash-sleep-state","SINCRONIZADO","good");
      if(last){
        const mins=Number(last.duration_minutes||0),hours=Math.floor(mins/60),rest=mins%60;
        $("dash-sleep-duration").textContent=hours+"h "+String(rest).padStart(2,"0")+"m";
        if(last.start&&last.end)$("dash-sleep-meta").textContent=new Date(last.start).toLocaleDateString("pt-BR")+" · "+new Date(last.start).toLocaleTimeString("pt-BR",{hour:"2-digit",minute:"2-digit"})+"–"+new Date(last.end).toLocaleTimeString("pt-BR",{hour:"2-digit",minute:"2-digit"});
        else $("dash-sleep-meta").textContent="Última sessão de sono recebida.";
        const stages=Array.isArray(last.stages)?last.stages:[];
        const counts={1:0,2:0,3:0,4:0,5:0,6:0,7:0};
        stages.forEach(stage=>{const type=Number(stage.type);if(counts[type]!==undefined&&stage.start&&stage.end)counts[type]+=Math.max(0,(new Date(stage.end)-new Date(stage.start))/60000);});
        const names={4:"Leve",5:"Profundo",6:"REM",1:"Acordado"};
        $("dash-sleep-stages").replaceChildren();
        Object.keys(names).forEach(key=>{if(!counts[key])return;const item=document.createElement("span");item.textContent=names[key]+" "+Math.round(counts[key])+"m";$("dash-sleep-stages").append(item);});
      }else{
        $("dash-sleep-duration").textContent="Sem registro";
        $("dash-sleep-meta").textContent="Nenhuma sessão de sono foi recebida nos últimos dez dias.";
        $("dash-sleep-stages").replaceChildren();
      }
      $("dash-sleep-steps").textContent=Number(h.steps_today||0).toLocaleString("pt-BR");
      $("dash-sleep-synced").textContent="Última sincronização: "+new Date(h.synced_at*1000).toLocaleString("pt-BR");
    }else{
      pill("dash-sleep-state","AGUARDANDO","neutral");
      $("dash-sleep-duration").textContent="--h --m";
      $("dash-sleep-meta").textContent="Abra o JARVIS Companion, autorize Sono e Passos e toque em Sincronizar.";
      $("dash-sleep-stages").replaceChildren();
      $("dash-sleep-steps").textContent="—";
      $("dash-sleep-synced").textContent="Nenhum dado de saúde foi enviado para este computador.";
    }
  }
  function updateNotifications(data){
    const items=data.notifications||[],mobile=((data.integrations||{}).mobile)||{};
    pill("dash-mobile-state",mobile.connected?"CONECTADO":mobile.status==="error"?"COM ERRO":mobile.status==="not_configured"?"NÃO CONFIGURADO":"AGUARDANDO",mobile.connected?"good":mobile.status==="error"?"bad":"neutral");
    $("dash-notification-count").textContent=String(items.length);
    const drawer=$("dash-mobile-list");drawer.replaceChildren();
    if(!items.length){const empty=document.createElement("p");empty.className="orb-empty";empty.textContent="Nenhuma notificação recente.";drawer.append(empty);}
    items.slice(0,12).forEach(x=>{const item=document.createElement("div"),title=document.createElement("b"),body=document.createElement("span");item.className="orb-item";title.textContent=(x.app||"Celular")+" · "+(x.title||"Notificação");body.textContent=x.text||"";item.append(title,body);drawer.append(item);});
    items.slice().reverse().forEach(x=>{const key=[x.received_at,x.app,x.title,x.text].join("|");if(seen.has(key))return;seen.add(key);if(loaded)toast((x.app||"Celular")+" · "+(x.title||"Notificação"),x.text||"Nova notificação recebida.");});
    $("dash-system-state").textContent="ONLINE";
  }
  async function loadDashboard(){
    try{
      const response=await fetch("/api/painel",{cache:"no-store"});if(!response.ok)throw new Error("painel indisponível");
      const data=await response.json();updateGoogle(data);updateHealth(data);updateNotifications(data);loaded=true;
    }catch(_){$("dash-system-state").textContent="SEM CONEXÃO";}
  }
  async function connectGoogle(){
    const button=$("dash-google-connect");button.disabled=true;
    const popup=window.open("about:blank","jarvis-google-auth","popup,width=540,height=720");
    try{
      const response=await fetch("/api/google/connect",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
      const result=await response.json();
      if(result.authorization_url&&popup)popup.location=result.authorization_url;else if(popup)popup.close();
      if(!response.ok)toast("Google",result.message||"Configure as credenciais OAuth.");
      else toast("Google","Conclua a autorização na janela aberta.");
      await loadDashboard();
    }catch(_){if(popup)popup.close();toast("Google","Não foi possível iniciar a autorização.");}
    finally{button.disabled=false;setTimeout(loadDashboard,1200);}
  }
  async function disconnectGoogle(){
    if(!confirm("Desconectar Gmail e Agenda deste computador?"))return;
    try{await fetch("/api/google/disconnect",{method:"POST"});await loadDashboard();toast("Google","Conta desconectada.");}
    catch(_){toast("Google","Não foi possível desconectar.");}
  }
  async function fetchWeather(){
    const city=$("dash-weather-city").value.trim();if(!city){$("dash-weather-condition").textContent="Digite uma cidade para consultar.";return;}
    $("dash-weather-search").disabled=true;$("dash-weather-state").textContent="CONSULTANDO";
    try{
      const r=await fetch("/api/clima?cidade="+encodeURIComponent(city),{cache:"no-store"}),data=await r.json();
      if(!r.ok||!data.ok)throw new Error(data.message||"Não foi possível consultar o clima.");
      const w=data.weather;$("dash-weather-state").textContent="ATUALIZADO";
      $("dash-weather-temp").textContent=Math.round(Number(w.temperature))+"°";
      $("dash-weather-condition").textContent=w.condition||"Condição indisponível";
      $("dash-weather-meta").textContent=(w.city||city)+(w.region?", "+w.region:"")+" · sensação "+Math.round(Number(w.feels_like))+"° · umidade "+w.humidity+"% · vento "+w.wind+" km/h";
      $("dash-weather-days").textContent=(w.daily||[]).map(x=>new Date(x.date+"T12:00:00").toLocaleDateString("pt-BR",{weekday:"short"})+": "+Math.round(x.min)+"° / "+Math.round(x.max)+"° · chuva "+x.rain+"%").join("   ");
      try{localStorage.setItem("jarvis.weather-city",city);}catch(_){}
    }catch(error){$("dash-weather-state").textContent="SEM DADOS";$("dash-weather-condition").textContent=error.message||"Falha ao consultar."; }
    finally{$("dash-weather-search").disabled=false;}
  }
  function wire(){
    $("dash-google-connect").addEventListener("click",connectGoogle);
    $("dash-google-disconnect").addEventListener("click",disconnectGoogle);
    $("dash-weather-search").addEventListener("click",fetchWeather);
    $("dash-weather-city").addEventListener("keydown",e=>{if(e.key==="Enter")fetchWeather();});
    $("dash-notification-toggle").addEventListener("click",()=>$("dash-mobile-drawer").hidden=!$("dash-mobile-drawer").hidden);
    try{const city=localStorage.getItem("jarvis.weather-city")||"";$("dash-weather-city").value=city;if(city)fetchWeather();}catch(_){}
  }
  const stream=new EventSource("/api/eventos");
  stream.onmessage=e=>{try{const msg=JSON.parse(e.data);if(msg.tipo==="face_status")face(msg);else if(["mobile_notification","mobile_status","health_update"].includes(msg.tipo))loadDashboard();}catch(_){}};
  stream.onerror=()=>{if(!unlocked)$("dash-system-state").textContent="RECONECTANDO";};
  window.addEventListener("jarvis:speech-start",e=>{if(unlocked)toast("JARVIS está falando",String((e.detail||{}).text||"").slice(0,120));});
  clockTimer=setInterval(updateClock,1000);updateClock();wire();
  setInterval(()=>{if(unlocked)loadDashboard();},20000);
  $("dash-system-state").textContent="AGUARDANDO";
})();