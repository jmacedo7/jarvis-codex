(() => {
  const $ = (id) => document.getElementById(id);
  const boot = $("jarvis-boot");
  const status = $("boot-status");
  const sub = $("boot-sub");
  const ring = $("scan-progress");
  const meter = $("boot-meter-fill");
  let progress = 3;
  let unlocked = false;
  let dashboardLoaded = false;
  let knownNotifications = new Set();
  let speechTimer = null;
  let currentSpeechText = "";

  const setProgress = (n) => {
    progress = Math.max(progress, Math.min(100, n));
    if (ring) ring.style.strokeDashoffset = String(628 - (628 * progress / 100));
    if (meter) meter.style.width = progress + "%";
  };
  const showStatus = (title, detail, pct) => {
    if (status) status.textContent = title;
    if (sub) sub.textContent = detail;
    if (pct != null) setProgress(pct);
  };

  function unlock(name) {
    if (unlocked) return;
    unlocked = true;
    setProgress(100);
    showStatus("Identidade confirmada", "Bem-vindo, " + (name || "Senhor") + ". Preparando seu ambiente.", 100);
    document.body.classList.add("jarvis-authenticated");
    setTimeout(() => boot && boot.classList.add("unlocked"), 1150);
    loadDashboard();
    setTimeout(showGuideOnce, 2300);
  }

  function face(e) {
    if (unlocked) return;
    const detail = e.detail || "";
    if (e.status === "starting") {
      showStatus("Inicializando biometria", "Carregando o modelo facial local e preparando a câmera.", 8);
    } else if (e.status === "active") {
      showStatus("Câmera preparada", "Centralize seu rosto no enquadramento para iniciar a verificação.", 18);
    } else if (e.status === "no_face") {
      showStatus("Procurando seu rosto", "A verificação termina assim que sua identidade for confirmada.", 34);
    } else if (e.status === "unknown") {
      showStatus("Analisando identidade", "Rosto detectado. Comparando com o cadastro protegido.", 66);
    } else if (e.status === "recognized") {
      unlock(e.name);
    } else if (e.status === "disabled") {
      showStatus("Biometria desativada", "O JARVIS seguirá sem bloqueio facial, conforme a configuração.", 100);
      unlock("modo sem biometria");
    } else if (e.status === "camera_error") {
      showStatus("Câmera indisponível", detail || "Verifique a conexão e feche outros aplicativos que estejam usando a webcam.", 0);
    } else if (e.status === "error") {
      showStatus("Falha na biometria", detail || "Confira as dependências do ambiente Python e reinicie o JARVIS.", 0);
    } else if (e.status === "not_enrolled") {
      showStatus("Cadastro necessário", "Nenhum rosto cadastrado. Execute: python -m security.face_guard enroll \"Seu nome\".", 0);
    }
  }

  function toast(title, heading, body) {
    const host = $("jarvis-toasts");
    if (!host) return;
    const node = document.createElement("div");
    node.className = "jarvis-toast";
    const small = document.createElement("small");
    small.textContent = title;
    const strong = document.createElement("strong");
    strong.textContent = heading;
    const p = document.createElement("p");
    p.textContent = body;
    node.append(small, strong, p);
    host.append(node);
    setTimeout(() => {
      node.style.opacity = "0";
      node.style.transform = "translateX(20px)";
      setTimeout(() => node.remove(), 400);
    }, 6500);
  }

  const guideSteps = [
    {
      title: "Fale com o JARVIS",
      body: "Segure a barra de espaço enquanto fala. Solte quando terminar. O JARVIS transcreve e responde em voz alta."
    },
    {
      title: "Digite ou ajuste a voz",
      body: "Pressione T para digitar. Use a engrenagem no canto superior para escolher a voz e a velocidade; a escolha fica salva no .env desta instalação."
    },
    {
      title: "Confira seus módulos",
      body: "As notificações do celular aparecem quando a ponte Android está configurada. E-mail, agenda e clima permanecem como não conectados até configurar provedores."
    }
  ];
  let guideIndex = 0;

  function fecharGuia() {
    const panel = $("jarvis-guide");
    if (panel) panel.hidden = true;
    try { localStorage.setItem("jarvis.onboarding.v1", "done"); } catch (_) {}
  }

  function renderGuia() {
    const step = guideSteps[guideIndex];
    $("guide-step").textContent = "PASSO " + (guideIndex + 1) + " DE " + guideSteps.length;
    $("guide-title").textContent = step.title;
    $("guide-body").textContent = step.body;
    $("guide-advance").textContent = guideIndex === guideSteps.length - 1 ? "Concluir" : "Continuar";
  }

  function showGuideOnce() {
    let concluido = false;
    try { concluido = localStorage.getItem("jarvis.onboarding.v1") === "done"; } catch (_) {}
    if (concluido) return;
    const panel = $("jarvis-guide");
    if (!panel) return;
    guideIndex = 0;
    renderGuia();
    panel.hidden = false;
    $("guide-advance").onclick = () => {
      if (guideIndex >= guideSteps.length - 1) {
        fecharGuia();
        return;
      }
      guideIndex += 1;
      renderGuia();
    };
    $("guide-dismiss").onclick = fecharGuia;
  }

  function clock() {
    const now = new Date();
    if ($("dash-time")) $("dash-time").textContent = now.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    if ($("dash-date")) $("dash-date").textContent = now.toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "long" });
  }

  function mostrarIntegracao(id, integration, indisponivel) {
    const node = $(id);
    if (!node) return;
    node.textContent = integration && integration.connected ? "Conectado" : indisponivel;
  }

  async function loadDashboard() {
    clock();
    try {
      const response = await fetch("/api/painel", { cache: "no-store" });
      if (!response.ok) throw new Error("painel indisponível");
      const data = await response.json();
      const items = data.notifications || [];
      $("dash-notification-count").textContent = items.length + " recentes";
      const list = $("dash-notifications");
      list.replaceChildren();
      $("dash-notifications-empty").hidden = items.length > 0;
      items.slice(0, 5).forEach((notification) => {
        const item = document.createElement("div");
        item.className = "dash-notification";
        const title = document.createElement("strong");
        title.textContent = (notification.app || "Celular") + " · " + (notification.title || "Notificação");
        const text = document.createElement("span");
        text.textContent = notification.text || "Nova notificação";
        item.append(title, text);
        list.append(item);
      });
      items.slice().reverse().forEach((notification) => {
        const id = [notification.received_at, notification.app, notification.title, notification.text].join("|");
        if (knownNotifications.has(id)) return;
        knownNotifications.add(id);
        if (dashboardLoaded) {
          toast("NOTIFICAÇÃO DO CELULAR",
            (notification.app || "Celular") + " · " + (notification.title || "Nova notificação"),
            notification.text || "Você recebeu uma notificação.");
        }
      });
      dashboardLoaded = true;

      const integrations = data.integrations || {};
      mostrarIntegracao("dash-email", integrations.email, "Não conectada · configure uma conta de e-mail.");
      mostrarIntegracao("dash-events", integrations.calendar, "Não conectada · configure a agenda.");
      mostrarIntegracao("dash-weather", integrations.weather, "Não configurado · escolha uma cidade/provedor.");

      const report = (data.reports || [])[0];
      $("dash-report").textContent = report
        ? (report.title + " · " + report.created_at + (report.summary ? "\n" + report.summary : ""))
        : "Nenhum relatório salvo ainda. Diga “boa noite” para gerar o relatório do dia.";
    } catch (_) {
      if ($("dash-notification-count")) $("dash-notification-count").textContent = "Sem conexão";
    }
  }

  function mostrarFala(evento) {
    const card = $("dash-response-card");
    const texto = $("dash-response-text");
    const barra = $("dash-response-progress");
    const legenda = $("dash-response-status");
    if (!card || !texto || !barra) return;
    if (speechTimer) clearInterval(speechTimer);
    currentSpeechText = String(evento.text || "").trim();
    const palavras = currentSpeechText.split(/\s+/).filter(Boolean);
    card.hidden = false;
    texto.textContent = "";
    barra.style.width = "0%";
    legenda.textContent = evento.source === "ElevenLabs" ? "ElevenLabs · falando agora" : "Voz local · falando agora";
    if (!palavras.length) return;

    const totalMs = Math.max(700, Number(evento.duration || (palavras.length / 2.5)) * 1000);
    const passoMs = Math.max(35, totalMs / palavras.length);
    let indice = 0;
    speechTimer = setInterval(() => {
      indice = Math.min(palavras.length, indice + 1);
      texto.textContent = palavras.slice(0, indice).join(" ");
      barra.style.width = (indice / palavras.length * 100) + "%";
      if (indice >= palavras.length && speechTimer) {
        clearInterval(speechTimer);
        speechTimer = null;
      }
    }, passoMs);
  }

  function finalizarFala(evento) {
    if (speechTimer) {
      clearInterval(speechTimer);
      speechTimer = null;
    }
    const barra = $("dash-response-progress");
    const legenda = $("dash-response-status");
    if (barra) barra.style.width = "100%";
    if (legenda) legenda.textContent = evento && evento.failed ? "Fala interrompida" : "Resposta concluída · permanece no painel";
    if ($("dash-response-text") && currentSpeechText) $("dash-response-text").textContent = currentSpeechText;
  }

  function mostrarFerramenta(evento) {
    const host = $("dash-activity-list");
    if (!host || !evento.label) return;
    const chip = document.createElement("span");
    chip.className = "dash-activity-chip";
    chip.textContent = evento.label;
    host.append(chip);
    while (host.children.length > 8) host.removeChild(host.firstChild);
    $("dash-activity-card").hidden = false;
  }

  function connect() {
    const source = new EventSource("/api/eventos");
    source.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message.tipo === "face_status") face(message);
      } catch (_) {}
    };
    source.onerror = () => {
      if (!unlocked) showStatus("Reconectando segurança", "Aguardando o serviço local do JARVIS.", 0);
    };
  }

  window.addEventListener("jarvis:speech-start", (event) => mostrarFala(event.detail || {}));
  window.addEventListener("jarvis:speech-end", (event) => finalizarFala(event.detail || {}));
  window.addEventListener("jarvis:tool", (event) => mostrarFerramenta(event.detail || {}));

  clock();
  setInterval(clock, 1000);
  connect();
  setTimeout(() => {
    if (!unlocked) showStatus("Aguardando reconhecimento", "A câmera está iniciando. Mantenha o rosto visível por alguns segundos.", 12);
  }, 8000);
  setInterval(() => {
    if (unlocked) loadDashboard();
  }, 30000);

  $("dash-report").textContent = "Carregando relatórios…";
  $("dash-email").textContent = "Verificando integração…";
  $("dash-events").textContent = "Verificando integração…";
  $("dash-weather").textContent = "Verificando configuração…";
  $("dash-activity-card").hidden = true;
  $("dash-response-card").hidden = true;
})();
