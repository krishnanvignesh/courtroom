// ---------- Crisp 16x16 pixel-art SVG sprites ----------
const SPRITES = {
  gavel: `
    <svg viewBox="0 0 16 16" shape-rendering="crispEdges" aria-hidden="true">
      <rect x="6" y="2" width="6" height="4" fill="#d97706"/>
      <rect x="5" y="2" width="1" height="4" fill="#ffd23f"/>
      <rect x="12" y="2" width="1" height="4" fill="#92400e"/>
      <rect x="8" y="6" width="2" height="7" fill="#b45309"/>
      <rect x="4" y="13" width="8" height="2" fill="#78350f"/>
      <rect x="3" y="12" width="10" height="1" fill="#f59e0b"/>
    </svg>`,
  judge: `
    <svg viewBox="0 0 16 16" shape-rendering="crispEdges" aria-hidden="true">
      <rect x="4" y="2" width="8" height="3" fill="#e2e8f0"/>
      <rect x="3" y="4" width="2" height="4" fill="#cbd5e1"/>
      <rect x="11" y="4" width="2" height="4" fill="#cbd5e1"/>
      <rect x="5" y="4" width="6" height="5" fill="#fbbf92"/>
      <rect x="6" y="6" width="1" height="1" fill="#1e1b4b"/>
      <rect x="9" y="6" width="1" height="1" fill="#1e1b4b"/>
      <rect x="4" y="7" width="8" height="2" fill="#f8fafc"/>
      <rect x="3" y="9" width="10" height="6" fill="#4c1d95"/>
      <rect x="7" y="9" width="2" height="4" fill="#f8fafc"/>
      <rect x="5" y="9" width="2" height="2" fill="#c084fc"/>
      <rect x="9" y="9" width="2" height="2" fill="#c084fc"/>
    </svg>`,
  prosecutor: `
    <svg viewBox="0 0 16 16" shape-rendering="crispEdges" aria-hidden="true">
      <rect x="5" y="2" width="6" height="2" fill="#94a3b8"/>
      <rect x="4" y="3" width="2" height="2" fill="#cbd5e1"/>
      <rect x="5" y="4" width="6" height="5" fill="#fbbf92"/>
      <rect x="6" y="6" width="1" height="1" fill="#0f172a"/>
      <rect x="9" y="6" width="1" height="1" fill="#0f172a"/>
      <rect x="3" y="9" width="10" height="6" fill="#be123c"/>
      <rect x="7" y="9" width="2" height="5" fill="#fff1f2"/>
      <rect x="13" y="10" width="2" height="2" fill="#fbbf92"/>
    </svg>`,
  defender: `
    <svg viewBox="0 0 16 16" shape-rendering="crispEdges" aria-hidden="true">
      <rect x="4" y="2" width="8" height="3" fill="#1e293b"/>
      <rect x="3" y="4" width="2" height="2" fill="#334155"/>
      <rect x="5" y="4" width="6" height="5" fill="#fbbf92"/>
      <rect x="6" y="6" width="1" height="1" fill="#0f172a"/>
      <rect x="9" y="6" width="1" height="1" fill="#0f172a"/>
      <rect x="3" y="9" width="10" height="6" fill="#1d4ed8"/>
      <rect x="7" y="9" width="2" height="5" fill="#ff4d6d"/>
      <rect x="6" y="9" width="1" height="3" fill="#f8fafc"/>
      <rect x="9" y="9" width="1" height="3" fill="#f8fafc"/>
    </svg>`,
  bailiff: `
    <svg viewBox="0 0 16 16" shape-rendering="crispEdges" aria-hidden="true">
      <rect x="4" y="2" width="8" height="2" fill="#065f46"/>
      <rect x="3" y="4" width="10" height="1" fill="#ffd23f"/>
      <rect x="5" y="5" width="6" height="4" fill="#fbbf92"/>
      <rect x="6" y="6" width="4" height="2" fill="#0f172a"/>
      <rect x="7" y="6" width="1" height="1" fill="#2ee59d"/>
      <rect x="9" y="6" width="1" height="1" fill="#2ee59d"/>
      <rect x="3" y="9" width="10" height="6" fill="#047857"/>
      <rect x="10" y="10" width="2" height="2" fill="#ffd23f"/>
      <rect x="5" y="11" width="4" height="3" fill="#e2e8f0"/>
    </svg>`,
  scroll: `
    <svg viewBox="0 0 16 16" shape-rendering="crispEdges" aria-hidden="true">
      <rect x="3" y="2" width="10" height="2" fill="#d97706"/>
      <rect x="4" y="4" width="8" height="8" fill="#fef3c7"/>
      <rect x="5" y="5" width="6" height="1" fill="#78350f"/>
      <rect x="5" y="7" width="6" height="1" fill="#78350f"/>
      <rect x="5" y="9" width="4" height="1" fill="#78350f"/>
      <rect x="10" y="10" width="2" height="2" fill="#ff4d6d"/>
      <rect x="3" y="12" width="10" height="2" fill="#b45309"/>
    </svg>`,
};

document.querySelectorAll(".sprite[data-sprite]").forEach((el) => {
  const key = el.dataset.sprite;
  if (SPRITES[key]) el.innerHTML = SPRITES[key];
});

// ---------- Topbar scroll border ----------
const nav = document.getElementById("nav");
const syncNav = () => nav && nav.classList.toggle("scrolled", window.scrollY > 8);
window.addEventListener("scroll", syncNav, { passive: true });
syncNav();

// ---------- Interactive arcade courtroom trial ----------
const SCRIPT = [
  {
    actor: "prosecutor",
    speaker: "PROSECUTOR",
    color: "var(--red)",
    callout: "OBJECTION!",
    hp: "78%",
    cost: "$0.00",
    text: "In-memory counter breaks behind 4 Gunicorn workers. Prove shared state!",
  },
  {
    actor: "defender",
    speaker: "DEFENDER",
    color: "var(--blue)",
    callout: "HOLD IT!",
    hp: "64%",
    cost: "$0.02",
    text: "Also, this plan builds 3 backends when only Redis exists. Cut the bloat!",
  },
  {
    actor: "bailiff",
    speaker: "BAILIFF (PYTHON)",
    color: "var(--green)",
    callout: "VERIFIED!",
    hp: "86%",
    cost: "$0.02",
    text: "[VERIFIED] settings.REDIS_URL at config/settings.py L41. [UNVERIFIED] E4 dropped.",
  },
  {
    actor: "judge",
    speaker: "JUDGE (BLINDED)",
    color: "var(--purple)",
    callout: "APPROVED!",
    hp: "100%",
    cost: "$0.04",
    text: "Approved with conditions: use Redis directly. Allowed files locked.",
  },
  {
    actor: "bailiff",
    speaker: "REPLAY GATE",
    color: "var(--yellow)",
    callout: "GATE FAIL!",
    hp: "35%",
    cost: "$0.00",
    text: "Agent edited src/billing/webhooks.py outside blast_radius. Blocked at $0.00!",
  },
];

const screen = document.getElementById("gameScreen");
const dlgName = document.getElementById("dlgName");
const dlgText = document.getElementById("dlgText");
const hpBar = document.getElementById("hpBar");
const costVal = document.getElementById("costVal");
const objection = document.getElementById("objection");
const actors = Array.from(document.querySelectorAll(".actor[data-actor]"));
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

let beatIndex = 0;
let typeTimer = null;
let autoTimer = null;
let calloutTimer = null;

function showBeat(index) {
  if (!screen) return;
  clearTimeout(typeTimer);
  clearTimeout(autoTimer);
  clearTimeout(calloutTimer);

  const beat = SCRIPT[index % SCRIPT.length];
  actors.forEach((a) => a.classList.toggle("speaking", a.dataset.actor === beat.actor));
  dlgName.textContent = beat.speaker;
  dlgName.style.background = beat.color;
  hpBar.style.width = beat.hp;
  costVal.textContent = beat.cost;

  objection.textContent = beat.callout;
  objection.classList.add("show");
  calloutTimer = setTimeout(() => objection.classList.remove("show"), 950);

  if (reducedMotion) {
    dlgText.textContent = beat.text;
    return;
  }

  dlgText.textContent = "";
  let pos = 0;
  const tick = () => {
    pos += 2;
    dlgText.textContent = beat.text.slice(0, pos);
    if (pos < beat.text.length) {
      typeTimer = setTimeout(tick, 22);
    } else {
      autoTimer = setTimeout(nextBeat, 2600);
    }
  };
  tick();
}

function nextBeat() {
  beatIndex = (beatIndex + 1) % SCRIPT.length;
  showBeat(beatIndex);
}

if (screen) {
  screen.addEventListener("click", nextBeat);
  showBeat(0);
}

// ---------- Case File cartridges ----------
document.querySelectorAll(".cart[data-tab]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const target = btn.dataset.tab;
    document.querySelectorAll(".cart[data-tab]").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".case[data-panel]").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    const panel = document.querySelector(`.case[data-panel="${target}"]`);
    if (panel) panel.classList.add("active");
  });
});

// ---------- Quick-start mini-tabs ----------
document.querySelectorAll(".mini-tab[data-mini]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const target = btn.dataset.mini;
    document.querySelectorAll(".mini-tab[data-mini]").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".mini-panel[data-mini-panel]").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    const panel = document.querySelector(`.mini-panel[data-mini-panel="${target}"]`);
    if (panel) panel.classList.add("active");
  });
});

// ---------- Copy buttons ----------
document.querySelectorAll(".copy").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const pre = btn.parentElement && btn.parentElement.querySelector("pre");
    if (!pre) return;
    try {
      await navigator.clipboard.writeText(pre.innerText);
      btn.textContent = "COPIED!";
      btn.classList.add("done");
      setTimeout(() => {
        btn.textContent = "COPY";
        btn.classList.remove("done");
      }, 1500);
    } catch {
      btn.textContent = "SELECT";
    }
  });
});

// ---------- Arcade CONTINUE? countdown ----------
const countdown = document.getElementById("countdown");
if (countdown && !reducedMotion) {
  let count = 9;
  setInterval(() => {
    count = count > 0 ? count - 1 : 9;
    countdown.textContent = String(count);
  }, 1000);
}
