const api = document.body.dataset.api;
const byId = (id) => document.getElementById(id);
const selector = byId("conversation");
let stream;
let submitting = false;
let pendingSubmission;
let refreshVersion = 0;

function append(parent, tag, content) {
  const item = document.createElement(tag);
  if (content !== undefined) item.textContent = content;
  parent.append(item);
  return item;
}

async function request(url, data) {
  const response = await fetch(url, data === undefined ? {} : {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]").value,
    },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    let code = response.status;
    if (response.headers.get("Content-Type")?.includes("application/json")) {
      code = (await response.json()).error?.code ?? code;
    }
    throw new Error(String(code));
  }
  return response.json();
}

function endpoint(thread, resource) {
  return `${api}${encodeURIComponent(thread)}/${resource}/`;
}

function errorDetails(error) {
  return [
    error.code ?? error.error_code,
    error.stage && `Stage: ${error.stage}`,
    error.provider_status && `HTTP ${error.provider_status}`,
    error.provider_code,
    error.validation_codes?.length && `Validation: ${error.validation_codes.join(", ")}`,
    ...(error.validation_issues ?? []).map((issue) =>
      `${issue.loc.join(".") || "(root)"}: ${issue.type}, expected ${issue.expected_type}, received ${issue.received_type}`),
    error.finish_reason && `Finish: ${error.finish_reason}`,
  ].filter(Boolean);
}

async function refresh(thread) {
  const version = ++refreshVersion;
  const [chat, execution] = await Promise.all([
    request(endpoint(thread, "messages")),
    request(endpoint(thread, "execution")),
  ]);
  if (selector.value !== thread || version !== refreshVersion) return;
  const history = byId("history");
  history.replaceChildren();
  for (const message of chat.messages) append(history, "li", `${message.role}: ${message.content}`);
  byId("status").textContent = execution.status.replaceAll("_", " ");
  const plan = byId("plan");
  plan.replaceChildren();
  if (execution.plan) {
    append(plan, "p", execution.plan.goal);
    for (const task of execution.plan.tasks) {
      const block = append(plan, "details");
      append(block, "summary", `${task.task_id} · ${task.agent} · ${task.status}`);
      if (task.depends_on.length) append(block, "p", `Depends on ${task.depends_on.join(", ")}`);
      if (task.error) append(block, "p", errorDetails(task.error).join(" · "));
      if (task.output) {
        append(block, "pre", JSON.stringify(task.output, null, 2));
        for (const source of task.output.sources ?? []) {
          try {
            const url = new URL(source.url);
            if (url.protocol === "https:" || url.protocol === "http:") {
              const link = append(append(block, "div"), "a", source.title || source.url);
              link.href = url.href;
              link.target = "_blank";
              link.rel = "noopener noreferrer";
            }
          } catch {
            // Ignore malformed citation links.
          }
        }
      }
    }
  }
  for (const issue of execution.errors) append(plan, "p", issue.code);
  const approvals = byId("approval");
  approvals.replaceChildren();
  for (const item of execution.pending_approvals) {
    append(approvals, "p", item.summary ?? item.capability);
    const review = item.review ?? item.inputs;
    if (review) append(approvals, "pre", JSON.stringify(review, null, 2));
    for (const approved of [true, false]) {
      const button = append(approvals, "button", approved ? "Approve" : "Reject");
      button.addEventListener("click", () => action(async () => {
        await request(endpoint(thread, "approval"), {
          approval_id: item.approval_id,
          execution_id: item.execution_id,
          approved,
        });
        await refresh(thread);
      }));
    }
  }
}

async function action(run) {
  try {
    byId("feedback").textContent = "";
    await run();
  } catch (error) {
    byId("feedback").textContent = error.message;
  }
}

async function select(thread) {
  stream?.close();
  byId("events").replaceChildren();
  if (!thread) return;
  sessionStorage.setItem("agentixSupervisorThread", thread);
  const source = new EventSource(endpoint(thread, "events"));
  stream = source;
  source.onmessage = ({ data }) => {
    if (stream !== source) return;
    const event = JSON.parse(data);
    const list = byId("events");
    append(list, "li", [event.type, event.task_id, event.status, ...errorDetails(event.data ?? {})].filter(Boolean).join(" · "));
    if (list.children.length > 100) list.firstElementChild.remove();
    if (["plan_validated", "task_scheduled", "agent_completed", "agent_failed",
         "task_blocked", "approval_requested", "execution_completed", "execution_failed"].includes(event.type)) {
      action(() => refresh(thread));
    } else if (event.type === "conversation_started") {
      byId("status").textContent = "running";
    }
  };
  await refresh(thread);
}

async function load(preferred = sessionStorage.getItem("agentixSupervisorThread")) {
  const { conversations } = await request(api);
  selector.replaceChildren();
  if (!conversations.length) append(selector, "option", "No conversations").value = "";
  for (const { thread, created_at } of conversations) {
    append(selector, "option", new Date(created_at).toLocaleString()).value = thread;
  }
  if (conversations.some(({ thread }) => thread === preferred)) selector.value = preferred;
  await select(selector.value);
}

selector.addEventListener("change", () => action(() => select(selector.value)));
byId("new").addEventListener("click", () => action(async () => {
  const { thread } = await request(api, {});
  await load(thread);
}));
byId("composer").addEventListener("submit", (event) => {
  event.preventDefault();
  if (submitting) return;
  action(async () => {
    submitting = true;
    const button = event.target.querySelector("button");
    button.disabled = true;
    try {
      if (!selector.value) {
        const { thread } = await request(api, {});
        await load(thread);
      }
      const thread = selector.value;
      const message = byId("message").value;
      const project = byId("project")?.value;
      const payload = { message };
      if (project) payload.project_id = Number(project);
      const fingerprint = JSON.stringify([thread, payload]);
      if (pendingSubmission?.fingerprint !== fingerprint) {
        pendingSubmission = { fingerprint, request_id: crypto.randomUUID() };
      }
      await request(endpoint(thread, "messages"), { ...payload, request_id: pendingSubmission.request_id });
      pendingSubmission = undefined;
      byId("message").value = "";
      await refresh(thread);
    } finally {
      submitting = false;
      button.disabled = false;
    }
  });
});
action(load);
