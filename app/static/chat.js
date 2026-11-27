const form = document.querySelector("#question-form");
const question = document.querySelector("#question");
const submit = document.querySelector("#submit");
const result = document.querySelector("#result");
const sources = document.querySelector("#sources");
const list = document.querySelector("#source-list");

function showResult(message, state, citations = []) {
  const paragraph = document.createElement("p");
  paragraph.className = `response ${state}`;
  const ids = new Set(citations.map((source) => source.id));
  for (const part of message.split(/(\[\d+\])/)) {
    const id = Number(part.slice(1, -1));
    if (/^\[\d+\]$/.test(part) && ids.has(id)) {
      const link = document.createElement("a");
      link.className = "citation";
      link.href = `#source-${id}`;
      link.textContent = part;
      link.setAttribute("aria-label", `답변 출처 ${id}`);
      paragraph.append(link);
    } else {
      paragraph.append(part);
    }
  }
  result.replaceChildren(paragraph);
}

function renderSources(citations) {
  list.replaceChildren();
  sources.hidden = citations.length === 0;
  for (const source of citations) {
    const card = document.createElement("li");
    card.id = `source-${source.id}`;
    card.className = "source-card";
    const top = document.createElement("div");
    top.className = "source-top";
    const number = document.createElement("span");
    number.className = "source-number";
    number.textContent = `[${source.id}]`;
    const link = document.createElement("a");
    link.href = source.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = `${source.item_name} ↗`;
    top.append(number, link);

    const meta = document.createElement("span");
    meta.className = "source-meta";
    meta.textContent = [source.section, `편람 수정일 ${source.revision_date}`].filter(Boolean).join(" · ");
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "근거 발췌 보기";
    const excerpt = document.createElement("p");
    excerpt.className = "excerpt";
    excerpt.textContent = source.excerpt;
    details.append(summary, excerpt);
    card.append(top, meta, details);
    list.append(card);
  }
}

document.querySelectorAll(".suggestions button").forEach((button) => {
  button.addEventListener("click", () => {
    question.value = button.textContent.trim();
    question.focus();
  });
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (submit.disabled) return;
  const value = question.value.trim();
  renderSources([]);
  if (value.length < 2) {
    showResult("질문을 두 글자 이상 입력해 주세요.", "error");
    question.focus();
    return;
  }
  submit.disabled = true;
  showResult("편람에서 근거를 찾고 답변을 작성하고 있어요.", "pending");
  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: value }),
      signal: AbortSignal.timeout(120000),
    });
    const data = await response.json();
    if (!response.ok) {
      showResult(typeof data.detail === "string" ? data.detail : "질문을 확인해 주세요.", "error");
      return;
    }
    showResult(data.answer, data.status === "answered" ? "answered" : "unanswered", data.sources);
    renderSources(data.sources);
  } catch {
    showResult("서버에 연결할 수 없어요. 잠시 후 다시 시도해 주세요.", "error");
  } finally {
    submit.disabled = false;
  }
});

fetch("/api/config").then((response) => response.json()).then(({ mode }) => {
  if (mode === "local") {
    const label = document.querySelector("#mode");
    label.textContent = "로컬 검증 환경 · Apple 온디바이스 모델";
    label.hidden = false;
  }
}).catch(() => {});
