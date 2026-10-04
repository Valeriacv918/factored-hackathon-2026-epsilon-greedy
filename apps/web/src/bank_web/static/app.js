// Chat page. The server keeps all conversation state; this only shows replies
// and sends text or a button value. Agent text is always set with textContent.
const messages = document.getElementById("messages");
const options = document.getElementById("options");
const composer = document.getElementById("composer");
const input = document.getElementById("text");
const sendButton = document.getElementById("send");
const status = document.getElementById("status");

const STATUS = {
  auth: "Verificación de identidad",
  dispute: "Identidad verificada",
  done: "Conversación terminada",
};

function bubble(text, kind) {
  const el = document.createElement("div");
  el.className = `bubble bubble--${kind}`;
  el.textContent = text;
  messages.appendChild(el);
  messages.scrollTop = messages.scrollHeight;
  return el;
}

function typing() {
  const el = bubble("", "agent");
  el.innerHTML = '<span class="typing"><span></span><span></span><span></span></span>';
  return el;
}

function setComposer(enabled) {
  input.disabled = !enabled;
  sendButton.disabled = !enabled;
  if (enabled) input.focus();
}

function render(reply) {
  for (const text of reply.messages) bubble(text, "agent");
  status.textContent = STATUS[reply.phase] || "";

  options.replaceChildren();
  options.hidden = reply.input !== "buttons";
  for (const option of reply.options) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = option.label;
    button.addEventListener("click", () => send({ choice: option.value }, option.label));
    options.appendChild(button);
  }
  setComposer(reply.input === "text");
  if (reply.phase === "done") bubble("Puedes iniciar una nueva conversación.", "system");
}

async function post(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.detail || "Error de conexión.");
    error.status = response.status;
    throw error;
  }
  return data;
}

async function send(body, shownText) {
  bubble(shownText, "user");
  for (const button of options.querySelectorAll("button")) button.disabled = true;
  setComposer(false);
  const pending = typing();
  try {
    const reply = await post("/api/chat", body);
    pending.remove();
    render(reply);
  } catch (error) {
    pending.remove();
    bubble(typeof error.message === "string" ? error.message : "Error.", "error");
    if (error.status === 409) return start();
    // Let the user retry the same step.
    for (const button of options.querySelectorAll("button")) button.disabled = false;
    setComposer(options.hidden);
  }
}

async function start() {
  messages.replaceChildren();
  options.replaceChildren();
  options.hidden = true;
  setComposer(false);
  try {
    render(await post("/api/start"));
  } catch (error) {
    bubble("No se pudo iniciar la conversación. Recarga la página.", "error");
  }
}

composer.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text || input.disabled) return;
  input.value = "";
  send({ text }, text);
});

document.getElementById("reset").addEventListener("click", start);

start();
