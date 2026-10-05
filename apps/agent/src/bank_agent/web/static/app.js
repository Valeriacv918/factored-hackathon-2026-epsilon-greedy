"use strict";

const $ = (id) => document.getElementById(id);
const OUTCOMES = {
  resolved: "Resuelta automáticamente", escalated: "Escalada con ticket", human_no_ticket: "Requiere humano",
  abstained: "Fuera de alcance", failed: "No completada", other: "Otro",
};
const INTENTS = {
  emergency: "Emergencia", not_me: "No reconocido", charge_error: "Cobro equivocado",
  other: "Otra", unclassified: "Sin clasificar",
};
const NODES = {
  validator_agent: "Idioma", validation_wait: "Identidad", request_wait: "Solicitud", triage_agent: "Triage",
  triage_wait: "Aclarar", card_emergency_agent: "Emergencia", charge_extract: "Extraer cargo",
  charge_find: "Buscar cargo", charge_details: "Detalles", charge_select: "Elegir cargo",
  charge_error: "Explicar cargo", charge_save: "Guardar", fraud_agent: "Fraude", escalation: "Escalamiento",
};
const LANGS = { es: "Español", pt: "Português", "?": "Sin idioma" };

let conversation = null; // { id, pending, done }
let busy = false;

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
    el("span", { class: "typing", "aria-label": "El asistente está escribiendo" }, el("i"), el("i"), el("i")));
  $("messages").append(item);
  item.scrollIntoView({ block: "end" });
}

function hideTyping() { $("typing")?.remove(); }

function setComposer(enabled, placeholder) {
  $("composer-input").disabled = !enabled;
  $("composer-send").disabled = !enabled;
  if (placeholder) $("composer-input").placeholder = placeholder;
  if (enabled) $("composer-input").focus();
}

function renderTrace(trace) {
  const steps = [];
  for (const step of trace || []) {
    const label = NODES[step.node] || step.node;
    if (steps[steps.length - 1] !== label) steps.push(label);
  }
  $("trace").hidden = steps.length === 0;
  $("trace-steps").replaceChildren(...steps.map((label, i) =>
    el("li", { class: i === steps.length - 1 ? "last" : "", text: label })));
}

function renderQuestion(question) {
  const bubble = addMessage("agent", question.message || "");
  if (question.card) bubble.append(el("div", { class: "detail" }, el("span", { class: "card-chip", text: question.card })));
  if (question.transaction) {
    const t = question.transaction;
    bubble.append(el("div", { class: "detail",
      text: [t.date && String(t.date).slice(0, 10), t.amount && `${t.amount} ${t.currency || ""}`, t.merchant]
        .filter(Boolean).join(" · ") }));
  }
  if (question.form) bubble.append(identityForm(question));
  if (question.options) bubble.append(optionButtons(question));
  if (question.input === "text") {
    setComposer(true, question.kind === "transaction_details"
      ? "Ej.: 45.90 USD el 12 de junio en Uber" : "Describe lo que necesitas…");
  } else {
    setComposer(false, "Responde con las opciones de arriba");
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

function renderDone(result) {
  const bubble = addMessage("agent", result.response || "", `done ${result.group}`);
  bubble.append(el("span", { class: `outcome-tag ${result.group}`, text: OUTCOMES[result.group] || result.outcome }));
  setComposer(true, "Escribe para iniciar otra conversación…");
}

function handle(result) {
  conversation = { id: result.thread_id, pending: result.question || null, done: result.status === "done" };
  renderTrace(result.trace);
  if (result.status === "waiting") renderQuestion(result.question);
  else renderDone(result);
  refreshMetrics();
}

const ERRORS = {
  agent_unavailable: "El servicio no está disponible en este momento. Intenta de nuevo en unos minutos.",
  not_found: "La conversación expiró. Escribe para iniciar una nueva.",
};

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
    addMessage("agent", ERRORS[err.code] || "No pude procesar esa respuesta. Intenta de nuevo.", "done failed");
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
  setComposer(true, "Me robaron la billetera…");
});

// --- stats -------------------------------------------------------------------------------

function ms(value) {
  if (value === null || value === undefined) return "—";
  if (value < 1000) return `${Math.round(value)} ms`;
  if (value < 60000) return `${(value / 1000).toFixed(1)} s`;
  return `${(value / 60000).toFixed(1)} min`;
}

function usd(value) {
  if (value === null || value === undefined) return "no definido";
  return value < 0.01 ? `$${value.toFixed(5)}` : `$${value.toFixed(3)}`;
}

function chips(target, counts, labels = {}, classFor = () => "") {
  const entries = Object.entries(counts || {}).sort((a, b) => b[1] - a[1]);
  $(target).replaceChildren(...(entries.length ? entries.map(([key, n]) =>
    el("span", { class: classFor(key) }, document.createTextNode(labels[key] || key), el("b", { text: String(n) })))
    : [el("span", { class: "empty", text: "Sin datos todavía" })]));
}

function renderLive(live) {
  $("k-conversations").textContent = live.conversations;
  $("k-active").textContent = live.active ? `${live.active} en curso` : "";
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
    : `Contención ${(live.containment * 100).toFixed(0)}%: terminaron sin transferir a humano. Contener no implica haber resuelto.`;

  $("a-cards").textContent = live.actions.cards_blocked;
  $("a-cases").textContent = live.actions.cases_filed;
  $("a-errors").textContent = live.tool_errors;
  chips("tickets-queue", live.tickets.by_queue, { fraud: "Fraude", cards: "Tarjetas", general: "General", disputes: "Disputas" });
  chips("tickets-priority", live.tickets.by_priority, {}, (p) => p.toLowerCase());

  const intents = Object.entries(live.intents).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...intents.map(([, n]) => n));
  $("intents").replaceChildren(...intents.map(([intent, n]) => el("div", { class: "bar" },
    el("span", { text: INTENTS[intent] || intent }),
    el("span", { class: "track" }, el("span", { class: "fill", style: `width:${(n / max) * 100}%` })),
    el("b", { text: String(n) }))));
  const languages = Object.fromEntries(Object.entries(live.by_language).map(([lang, v]) => [lang, v.conversations]));
  chips("languages", languages, LANGS);

  $("c-conv").textContent = usd(live.cost_usd.per_conversation);
  $("c-resolved").textContent = usd(live.cost_usd.per_resolved);
  const price = live.cost_usd.price_per_mtok;
  $("c-assumption").textContent = `Supuesto: $${price.input} entrada y $${price.output} salida por millón de tokens. Solo LLM; no incluye infraestructura.`;

  $("recent").replaceChildren(...(live.recent.length ? live.recent.map((r) => el("li", {},
    el("span", { class: `dot g-${r.group}` }),
    el("span", { text: `${INTENTS[r.intent] || INTENTS.unclassified} · ${OUTCOMES[r.group]}${r.ticket ? " · ticket" : ""}` }),
    el("span", { class: "t", text: `${(r.language || "").toUpperCase()} ${ms(r.attention_ms)}` })))
    : [el("li", { text: "Aún no hay conversaciones terminadas." })]));
}

function renderOffline(offline) {
  if (!offline) {
    $("offline-table").replaceChildren(el("p", { class: "note", text: "No hay resultados de evaluación disponibles." }));
    return;
  }
  const head = el("tr", {}, ...["Modelo", "Idioma", "Exactitud", "Críticos"].map((h) => el("th", { text: h })));
  const rows = offline.results.map((r) => el("tr", { class: r.model },
    el("td", { text: r.model === "llm" ? "LLM" : "Baseline" }),
    el("td", { text: r.language.toUpperCase() }),
    el("td", { class: "num", text: `${r.correct}/${r.cases} (${(r.accuracy * 100).toFixed(0)}%)` }),
    el("td", { class: `num ${r.critical ? "crit" : "ok0"}`, text: String(r.critical) })));
  $("offline-table").replaceChildren(el("table", { class: "otable" }, el("thead", {}, head), el("tbody", {}, ...rows)));
  $("offline-run").textContent = `${offline.cases} mensajes sintéticos etiquetados (ES/PT). Corrida ${offline.run}.`;
}

let refreshing = false;
async function refreshMetrics() {
  if (refreshing) return;
  refreshing = true;
  try {
    const response = await fetch("/api/metrics", { credentials: "same-origin" });
    if (!response.ok) return;
    const data = await response.json();
    renderLive(data.live);
    renderOffline(data.offline);
    if (data.scenario_date) {
      $("scenario-date").hidden = false;
      $("scenario-date").textContent = `Fecha del escenario ${data.scenario_date}`;
    }
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

refreshMetrics();
setInterval(refreshMetrics, 5000);
setComposer(true);
