"use strict";

const $ = (id) => document.getElementById(id);

// The ES/PT toggle switches the interface text (header, stats panel, trace). Inside the chat,
// replies, buttons, placeholders, outcome tags and errors follow the conversation language.
const STRINGS = {
  es: {
    title: "Epsilon Bank Asistente", toggle: "PT", toggle_title: "Ver em português",
    brand_sub: "Asistente de tarjetas y disputas", sandbox: "Sandbox simulado",
    sandbox_title: "Bloqueos, disputas y tickets se escriben en un sandbox simulado",
    new_chat: "Nueva conversación", chat_label: "Conversación con el asistente", trace: "Recorrido",
    message: "Mensaje", send: "Enviar", stats_label: "Estadísticas", tab_live: "En vivo", tab_offline: "Evaluación offline",
    live_note: "Conversaciones atendidas por este servicio desde su último arranque. Las acciones son simuladas en el sandbox.",
    k_conversations: "Conversaciones", k_tickets: "Tickets a humano", k_verified: "verificados",
    k_attention: "Tiempo de atención p50", k_system: "Latencia del sistema p50",
    h_outcomes: "Cómo terminaron", h_actions: "Acciones verificadas", a_cards: "Tarjetas bloqueadas",
    a_cases: "Disputas registradas", a_errors: "Errores de herramientas", h_tickets: "Tickets por cola y prioridad",
    h_intents: "Intención e idioma", h_cost: "Costo estimado del LLM", c_conv: "Por conversación",
    c_resolved: "Por resolución automática", h_recent: "Últimas conversaciones",
    offline_note: "Medición offline sobre mensajes sintéticos etiquetados (held-out). No es una medición en producción.",
    h_meaning: "Qué significa", d_accuracy: "Exactitud", d_accuracy_text: "la ruta elegida coincide con la etiqueta del caso.",
    d_critical: "Errores críticos",
    d_critical_text: "fallos que pueden costarle dinero al cliente, como una tarjeta robada que no va a emergencia o un reclamo de dinero marcado como fuera de alcance.",
    d_baseline_text: "reglas por palabras clave.", d_llm_text: "clasificador con reglas deterministas encima.",
    typing: "El asistente está escribiendo",
    ph_default: "Escribe tu mensaje…", ph_options: "Responde con las opciones de arriba",
    ph_describe: "Describe lo que necesitas…", ph_transaction: "Ej.: 45.90 USD el 12 de junio en Uber",
    ph_language: "Usa os botões / Usa los botones de arriba", ph_new: "Escribe para iniciar otra conversación…",
    err_agent_unavailable: "El servicio no está disponible en este momento. Intenta de nuevo en unos minutos.",
    err_not_found: "La conversación expiró. Escribe para iniciar una nueva.",
    err_generic: "No pude procesar esa respuesta. Intenta de nuevo.",
    active: (n) => `${n} en curso`,
    containment: (pct) => `Contención ${pct}%: terminaron sin transferir a humano. Contener no implica haber resuelto.`,
    no_data: "Sin datos todavía", no_cost: "no definido",
    assumption: (i, o) => `Supuesto: $${i} entrada y $${o} salida por millón de tokens. Solo LLM; no incluye infraestructura.`,
    recent_empty: "Aún no hay conversaciones terminadas.",
    offline_empty: "No hay resultados de evaluación disponibles.",
    offline_head: ["Modelo", "Idioma", "Exactitud", "Críticos"],
    offline_run: (cases, run) => `${cases} mensajes sintéticos etiquetados (ES/PT). Corrida ${run}.`,
    scenario: (date) => `Fecha del escenario ${date}`,
    outcomes: {
      resolved: "Resuelta automáticamente", escalated: "Escalada con ticket", human_no_ticket: "Requiere humano",
      abstained: "Fuera de alcance", failed: "No completada", other: "Otro",
    },
    intents: {
      emergency: "Emergencia", not_me: "No reconocido", charge_error: "Cobro equivocado",
      other: "Otra", unclassified: "Sin clasificar",
    },
    nodes: {
      validator_agent: "Idioma", validation_wait: "Identidad", request_wait: "Solicitud",
      triage_agent: "Triage", triage_wait: "Aclarar", card_emergency_agent: "Emergencia", charge_extract: "Extraer cargo",
      charge_find: "Buscar cargo", charge_details: "Detalles", charge_select: "Elegir cargo",
      charge_error: "Explicar cargo", charge_save: "Guardar", fraud_agent: "Fraude", escalation: "Escalamiento",
    },
    langs: { es: "Español", pt: "Português", "?": "Sin idioma" },
    queues: { fraud: "Fraude", cards: "Tarjetas", general: "General", disputes: "Disputas" },
  },
  pt: {
    title: "Epsilon Bank Assistente", toggle: "ES", toggle_title: "Ver en español",
    brand_sub: "Assistente de cartões e contestações", sandbox: "Sandbox simulado",
    sandbox_title: "Bloqueios, contestações e tickets são gravados em um sandbox simulado",
    new_chat: "Nova conversa", chat_label: "Conversa com o assistente", trace: "Percurso",
    message: "Mensagem", send: "Enviar", stats_label: "Estatísticas", tab_live: "Ao vivo", tab_offline: "Avaliação offline",
    live_note: "Conversas atendidas por este serviço desde a última inicialização. As ações são simuladas no sandbox.",
    k_conversations: "Conversas", k_tickets: "Tickets para humano", k_verified: "verificados",
    k_attention: "Tempo de atendimento p50", k_system: "Latência do sistema p50",
    h_outcomes: "Como terminaram", h_actions: "Ações verificadas", a_cards: "Cartões bloqueados",
    a_cases: "Contestações registradas", a_errors: "Erros de ferramentas", h_tickets: "Tickets por fila e prioridade",
    h_intents: "Intenção e idioma", h_cost: "Custo estimado do LLM", c_conv: "Por conversa",
    c_resolved: "Por resolução automática", h_recent: "Últimas conversas",
    offline_note: "Medição offline sobre mensagens sintéticas rotuladas (held-out). Não é uma medição em produção.",
    h_meaning: "O que significa", d_accuracy: "Acurácia", d_accuracy_text: "a rota escolhida coincide com o rótulo do caso.",
    d_critical: "Erros críticos",
    d_critical_text: "falhas que podem custar dinheiro ao cliente, como um cartão roubado que não vai para emergência ou uma reclamação de dinheiro marcada como fora do escopo.",
    d_baseline_text: "regras por palavras-chave.", d_llm_text: "classificador com regras determinísticas por cima.",
    typing: "O assistente está digitando",
    ph_default: "Escreva sua mensagem…", ph_options: "Responda com as opções acima",
    ph_describe: "Descreva o que você precisa…", ph_transaction: "Ex.: 45,90 USD em 12 de junho no Uber",
    ph_language: "Usa os botões / Usa los botones de arriba", ph_new: "Escreva para iniciar outra conversa…",
    err_agent_unavailable: "O serviço não está disponível no momento. Tente novamente em alguns minutos.",
    err_not_found: "A conversa expirou. Escreva para iniciar uma nova.",
    err_generic: "Não consegui processar essa resposta. Tente novamente.",
    active: (n) => `${n} em andamento`,
    containment: (pct) => `Contenção ${pct}%: terminaram sem transferir para humano. Conter não implica ter resolvido.`,
    no_data: "Sem dados ainda", no_cost: "não definido",
    assumption: (i, o) => `Suposição: $${i} entrada e $${o} saída por milhão de tokens. Apenas LLM; não inclui infraestrutura.`,
    recent_empty: "Ainda não há conversas encerradas.",
    offline_empty: "Não há resultados de avaliação disponíveis.",
    offline_head: ["Modelo", "Idioma", "Acurácia", "Críticos"],
    offline_run: (cases, run) => `${cases} mensagens sintéticas rotuladas (ES/PT). Execução ${run}.`,
    scenario: (date) => `Data do cenário ${date}`,
    outcomes: {
      resolved: "Resolvida automaticamente", escalated: "Encaminhada com protocolo", human_no_ticket: "Requer atendimento",
      abstained: "Fora do escopo", failed: "Não concluída", other: "Outro",
    },
    intents: {
      emergency: "Emergência", not_me: "Não reconhecida", charge_error: "Cobrança errada",
      other: "Outra", unclassified: "Sem classificação",
    },
    nodes: {
      validator_agent: "Idioma", validation_wait: "Identidade", request_wait: "Solicitação",
      triage_agent: "Triage", triage_wait: "Esclarecer", card_emergency_agent: "Emergência", charge_extract: "Extrair cobrança",
      charge_find: "Buscar cobrança", charge_details: "Detalhes", charge_select: "Escolher cobrança",
      charge_error: "Explicar cobrança", charge_save: "Salvar", fraud_agent: "Fraude", escalation: "Escalonamento",
    },
    langs: { es: "Español", pt: "Português", "?": "Sem idioma" },
    queues: { fraud: "Fraude", cards: "Cartões", general: "Geral", disputes: "Contestações" },
  },
};
const LANG_KEY = "ui-lang";

function loadLang() {
  try {
    const saved = localStorage.getItem(LANG_KEY);
    return Object.hasOwn(STRINGS, saved ?? "") ? saved : "es";
  } catch { return "es"; }
}

let uiLang = loadLang();
const t = (key) => STRINGS[uiLang][key];
const pick = (lang) => (lang === "pt" ? "pt" : "es");
const say = (lang, key) => STRINGS[pick(lang)][key]; // chat text: conversation language

let conversation = null; // { id, pending, done, language }
let busy = false;
let composerHint = { key: "ph_default", lang: null }; // lang null: follows the interface toggle
let lastTrace = [];
let lastMetrics = null;

// --- chat --------------------------------------------------------------------------------

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "style") node.style.cssText = value; // CSSOM: allowed by the CSP, unlike style attributes
    else node.setAttribute(key, value);
  }
  for (const child of children) if (child) node.append(child);
  return node;
}

function addMessage(who, text, extraClass = "") {
  const item = el("li", { class: `msg ${who} ${extraClass}`.trim() }, el("p", { text }));
  $("messages").append(item);
  item.scrollIntoView({ block: "end", behavior: "smooth" });
  return item;
}

function showTyping() {
  const item = el("li", { class: "msg agent", id: "typing" },
    el("span", { class: "typing", "aria-label": t("typing") }, el("i"), el("i"), el("i")));
  $("messages").append(item);
  item.scrollIntoView({ block: "end" });
}

function hideTyping() { $("typing")?.remove(); }

function setComposer(enabled, key, lang = null) {
  $("composer-input").disabled = !enabled;
  $("composer-send").disabled = !enabled;
  if (key) {
    composerHint = { key, lang };
    $("composer-input").placeholder = STRINGS[lang ? pick(lang) : uiLang][key];
  }
  if (enabled) $("composer-input").focus();
}

function renderTrace(trace) {
  lastTrace = trace || [];
  const steps = [];
  for (const step of lastTrace) {
    const label = t("nodes")[step.node] || step.node;
    if (steps[steps.length - 1] !== label) steps.push(label);
  }
  $("trace").hidden = steps.length === 0;
  $("trace-steps").replaceChildren(...steps.map((label, i) =>
    el("li", { class: i === steps.length - 1 ? "last" : "", text: label })));
}

function renderQuestion(question) {
  if (question.resolved) renderOutcome({ ...question.resolved, language: question.language });
  const bubble = addMessage("agent", question.message || "");
  if (question.card) bubble.append(el("div", { class: "detail" }, el("span", { class: "card-chip", text: question.card })));
  if (question.transaction) {
    const tx = question.transaction;
    bubble.append(el("div", { class: "detail",
      text: [tx.date && String(tx.date).slice(0, 10), tx.amount && `${tx.amount} ${tx.currency || ""}`, tx.merchant]
        .filter(Boolean).join(" · ") }));
  }
  if (question.form) bubble.append(identityForm(question));
  if (question.options) bubble.append(optionButtons(question));
  if (question.input === "text") {
    setComposer(true, question.kind === "transaction_details" ? "ph_transaction" : "ph_describe", question.language);
  } else {
    setComposer(false, question.kind === "language" ? "ph_language" : "ph_options", question.language);
  }
}

function optionButtons(question) {
  const box = el("div", { class: "options" });
  for (const option of question.options) {
    const kind = question.kind === "select_card" && option.value === null ? "card"
      : option.value === "human" ? "human" : option.value === "yes" ? "go" : "";
    const button = el("button", { type: "button", class: kind, text: option.label });
    button.addEventListener("click", () => {
      if (busy || box.classList.contains("used")) return;
      box.classList.add("used");
      button.classList.add("chosen");
      if (question.kind === "language" && ["es", "pt"].includes(option.value)) {
        conversation.language = option.value;
      }
      addMessage("user", option.label);
      send({ index: option.index });
    });
    box.append(button);
  }
  return box;
}

function identityForm(question) {
  const form = el("form", { class: "identity", autocomplete: "off" });
  for (const field of question.form) {
    const input = el("input", { name: field.name, type: field.type, required: "", maxlength: "100",
      autocomplete: "off", spellcheck: "false" });
    if (field.type === "date") input.max = new Date().toISOString().slice(0, 10);
    form.append(el("label", {}, document.createTextNode(field.label), input));
  }
  const error = el("span", { class: "err", role: "alert" });
  const submit = el("button", { class: "primary", type: "submit",
    text: question.language === "pt" ? "Verificar identidade" : "Verificar identidad" });
  form.append(el("div", { class: "row" }, submit,
    el("span", { class: "lock", text: question.language === "pt"
      ? "Seus dados vão direto para a verificação; nenhum modelo de IA os vê."
      : "Tus datos van directo a la verificación; ningún modelo de IA los ve." })), error);
  form.addEventListener("input", () => { error.textContent = ""; });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (busy) return;
    const fields = {};
    for (const field of question.form) fields[field.name] = form.elements[field.name].value.trim();
    if (Object.values(fields).some((v) => !v)) {
      error.textContent = question.language === "pt" ? "Preencha todos os campos." : "Completa todos los campos.";
      return;
    }
    // Identity factors leave the page with this request; nothing keeps them on screen.
    form.replaceChildren(el("span", { class: "lock", text: question.language === "pt"
      ? "Formulário enviado. Os dados não ficam salvos nesta página." : "Formulario enviado. Los datos no quedan guardados en esta página." }));
    addMessage("user", question.language === "pt" ? "Dados de identidade enviados" : "Datos de identidad enviados", "masked");
    send({ fields });
  });
  setTimeout(() => form.elements[0]?.focus(), 50);
  return form;
}

function renderOutcome(result) {
  const bubble = addMessage("agent", result.response || "", `done ${result.group}`);
  bubble.append(el("span", { class: `outcome-tag ${result.group}`,
    text: say(result.language, "outcomes")[result.group] || result.outcome }));
}

function renderDone(result) {
  renderOutcome(result);
  setComposer(true, "ph_new", result.language);
}

function handle(result) {
  conversation = { id: result.thread_id, pending: result.question || null, done: result.status === "done",
    language: result.question?.language || result.language || conversation?.language || "es" };
  renderTrace(result.trace);
  if (result.status === "waiting") renderQuestion(result.question);
  else renderDone(result);
  refreshMetrics();
}

const ERRORS = { agent_unavailable: "err_agent_unavailable", not_found: "err_not_found" };

async function post(url, body) {
  const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body), credentials: "same-origin" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw Object.assign(new Error(data.error || "error"), { code: data.error, status: response.status });
  return data;
}

async function send(answer) {
  busy = true;
  setComposer(false);
  showTyping();
  try {
    const result = conversation && !conversation.done
      ? await post(`/api/conversations/${encodeURIComponent(conversation.id)}/resume`, answer)
      : await post("/api/conversations", answer);
    hideTyping();
    handle(result);
  } catch (err) {
    hideTyping();
    addMessage("agent", say(conversation?.language, ERRORS[err.code] || "err_generic"), "done failed");
    if (err.code === "not_found" || err.code === "agent_unavailable") conversation = null;
    setComposer(true);
  } finally {
    busy = false;
  }
}

$("composer").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = $("composer-input");
  const text = input.value.trim();
  if (!text || busy) return;
  input.value = "";
  addMessage("user", text);
  if (conversation && !conversation.done && conversation.pending?.input === "text") send({ text });
  else { conversation = null; send({ message: text }); }
});

$("composer-input").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    $("composer").requestSubmit();
  }
});

$("new-chat").addEventListener("click", () => {
  if (busy) return;
  conversation = null;
  const intro = $("messages").querySelector(".intro");
  $("messages").replaceChildren(intro);
  renderTrace([]);
  setComposer(true, "ph_default");
});

// --- interface language ------------------------------------------------------------------

function applyLang() {
  document.documentElement.lang = uiLang;
  document.title = t("title");
  for (const node of document.querySelectorAll("[data-i18n]")) node.textContent = t(node.dataset.i18n);
  for (const node of document.querySelectorAll("[data-i18n-title]")) node.title = t(node.dataset.i18nTitle);
  for (const node of document.querySelectorAll("[data-i18n-aria-label]")) {
    node.setAttribute("aria-label", t(node.dataset.i18nAriaLabel));
  }
  const toggle = $("ui-lang");
  toggle.textContent = t("toggle");
  toggle.title = t("toggle_title");
  toggle.setAttribute("aria-label", t("toggle_title"));
  $("composer-input").placeholder = STRINGS[composerHint.lang ? pick(composerHint.lang) : uiLang][composerHint.key];
  renderTrace(lastTrace);
  if (lastMetrics) renderMetrics(lastMetrics);
}

$("ui-lang").addEventListener("click", () => {
  uiLang = uiLang === "es" ? "pt" : "es";
  try { localStorage.setItem(LANG_KEY, uiLang); } catch { /* the choice lasts this page view */ }
  applyLang();
});

// --- stats -------------------------------------------------------------------------------

function ms(value) {
  if (value === null || value === undefined) return "—";
  if (value < 1000) return `${Math.round(value)} ms`;
  if (value < 60000) return `${(value / 1000).toFixed(1)} s`;
  return `${(value / 60000).toFixed(1)} min`;
}

function usd(value) {
  if (value === null || value === undefined) return t("no_cost");
  return value < 0.01 ? `$${value.toFixed(5)}` : `$${value.toFixed(3)}`;
}

function chips(target, counts, labels = {}, classFor = () => "") {
  const entries = Object.entries(counts || {}).sort((a, b) => b[1] - a[1]);
  $(target).replaceChildren(...(entries.length ? entries.map(([key, n]) =>
    el("span", { class: classFor(key) }, document.createTextNode(labels[key] || key), el("b", { text: String(n) })))
    : [el("span", { class: "empty", text: t("no_data") })]));
}

function renderLive(live) {
  const OUTCOMES = t("outcomes"), INTENTS = t("intents");
  $("k-conversations").textContent = live.conversations;
  $("k-active").textContent = live.active ? t("active")(live.active) : "";
  $("k-tickets").textContent = live.tickets.total;
  $("k-attention").textContent = ms(live.latency_ms.attention_p50);
  $("k-attention-p95").textContent = live.latency_ms.attention_p95 != null ? `p95 ${ms(live.latency_ms.attention_p95)}` : "";
  $("k-system").textContent = ms(live.latency_ms.system_p50);
  $("k-system-p95").textContent = live.latency_ms.system_p95 != null ? `p95 ${ms(live.latency_ms.system_p95)}` : "";

  const total = live.conversations || 0;
  $("outcome-bar").replaceChildren(...Object.entries(live.outcomes).filter(([, n]) => n > 0)
    .map(([group, n]) => el("span", { class: `g-${group}`, style: `width:${(n / total) * 100}%`, title: `${OUTCOMES[group]}: ${n}` })));
  $("outcome-legend").replaceChildren(...Object.entries(live.outcomes).filter(([g, n]) => n > 0 || g !== "other")
    .map(([group, n]) => el("li", {}, el("i", { class: `g-${group}` }), document.createTextNode(OUTCOMES[group]),
      el("b", { text: String(n) }))));
  $("containment").textContent = live.containment === null ? ""
    : t("containment")((live.containment * 100).toFixed(0));

  $("a-cards").textContent = live.actions.cards_blocked;
  $("a-cases").textContent = live.actions.cases_filed;
  $("a-errors").textContent = live.tool_errors;
  chips("tickets-queue", live.tickets.by_queue, t("queues"));
  chips("tickets-priority", live.tickets.by_priority, {}, (p) => p.toLowerCase());

  const intents = Object.entries(live.intents).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...intents.map(([, n]) => n));
  $("intents").replaceChildren(...intents.map(([intent, n]) => el("div", { class: "bar" },
    el("span", { text: INTENTS[intent] || intent }),
    el("span", { class: "track" }, el("span", { class: "fill", style: `width:${(n / max) * 100}%` })),
    el("b", { text: String(n) }))));
  const languages = Object.fromEntries(Object.entries(live.by_language).map(([lang, v]) => [lang, v.conversations]));
  chips("languages", languages, t("langs"));

  $("c-conv").textContent = usd(live.cost_usd.per_conversation);
  $("c-resolved").textContent = usd(live.cost_usd.per_resolved);
  const price = live.cost_usd.price_per_mtok;
  $("c-assumption").textContent = t("assumption")(price.input, price.output);

  $("recent").replaceChildren(...(live.recent.length ? live.recent.map((r) => el("li", {},
    el("span", { class: `dot g-${r.group}` }),
    el("span", { text: `${INTENTS[r.intent] || INTENTS.unclassified} · ${OUTCOMES[r.group]}${r.ticket ? " · ticket" : ""}` }),
    el("span", { class: "t", text: `${(r.language || "").toUpperCase()} ${ms(r.attention_ms)}` })))
    : [el("li", { text: t("recent_empty") })]));
}

function renderOffline(offline) {
  if (!offline) {
    $("offline-table").replaceChildren(el("p", { class: "note", text: t("offline_empty") }));
    return;
  }
  const head = el("tr", {}, ...t("offline_head").map((h) => el("th", { text: h })));
  const rows = offline.results.map((r) => el("tr", { class: r.model },
    el("td", { text: r.model === "llm" ? "LLM" : "Baseline" }),
    el("td", { text: r.language.toUpperCase() }),
    el("td", { class: "num", text: `${r.correct}/${r.cases} (${(r.accuracy * 100).toFixed(0)}%)` }),
    el("td", { class: `num ${r.critical ? "crit" : "ok0"}`, text: String(r.critical) })));
  $("offline-table").replaceChildren(el("table", { class: "otable" }, el("thead", {}, head), el("tbody", {}, ...rows)));
  $("offline-run").textContent = t("offline_run")(offline.cases, offline.run);
}

function renderMetrics(data) {
  renderLive(data.live);
  renderOffline(data.offline);
  if (data.scenario_date) {
    $("scenario-date").hidden = false;
    $("scenario-date").textContent = t("scenario")(data.scenario_date);
  }
}

let refreshing = false;
async function refreshMetrics() {
  if (refreshing) return;
  refreshing = true;
  try {
    const response = await fetch("/api/metrics", { credentials: "same-origin" });
    if (!response.ok) return;
    lastMetrics = await response.json();
    renderMetrics(lastMetrics);
  } catch { /* the panel keeps its last numbers */ } finally {
    refreshing = false;
  }
}

for (const tab of document.querySelectorAll('[role="tab"]')) {
  tab.addEventListener("click", () => {
    for (const other of document.querySelectorAll('[role="tab"]')) {
      const selected = other === tab;
      other.setAttribute("aria-selected", String(selected));
      $(other.getAttribute("aria-controls")).hidden = !selected;
    }
  });
}

applyLang();
refreshMetrics();
setInterval(refreshMetrics, 5000);
setComposer(true);
