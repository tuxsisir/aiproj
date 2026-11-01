// CivicDesk landing: living building, cursor spotlight, "Ask your bylaws" demo, scroll reveals.
(() => {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const pick = (list) => list[Math.floor(Math.random() * list.length)];

  // ---------- Cursor spotlight on the blueprint hero ----------
  const hero = document.querySelector("[data-hero]");
  if (hero && !reduceMotion) {
    hero.addEventListener("pointermove", (e) => {
      const r = hero.getBoundingClientRect();
      hero.style.setProperty("--mx", `${e.clientX - r.left}px`);
      hero.style.setProperty("--my", `${e.clientY - r.top}px`);
    });
  }

  // ---------- Living building ----------
  const stage = document.querySelector("[data-building]");
  if (stage) {
    const svgNS = "http://www.w3.org/2000/svg";
    const group = stage.querySelector("#windows");
    const VIEW_W = 420, VIEW_H = 520, COLS = 5, FLOORS = 9;
    const windows = [];
    for (let f = 0; f < FLOORS; f++) {
      for (let c = 0; c < COLS; c++) {
        const x = 90 + c * 52, y = 104 + f * 38;
        const rect = document.createElementNS(svgNS, "rect");
        Object.entries({ x, y, width: 32, height: 24, rx: 2, class: "win" }).forEach(([k, v]) => rect.setAttribute(k, v));
        group.appendChild(rect);
        windows.push({ rect, x: x + 16, y: y + 12, unit: `${FLOORS - f}0${c + 1}` });
      }
    }
    // Some lights on from the start.
    windows.forEach((w) => Math.random() < 0.32 && w.rect.classList.add("lit"));

    const events = [
      { k: "Email inbox", t: (u) => `Unit ${u} leak thread forwarded → summarized, urgency high`, ai: true },
      { k: "Bylaw 3(4)", t: (u) => `Noise docket logged for unit ${u} · manager notified` },
      { k: "Council vote", t: () => "4 of 5 ballots in · majority reached" },
      { k: "Ask the bylaws", t: () => "“Visitor parking?” → 24 hours max · p.12", ai: true },
      { k: "s.135 notice", t: (u) => `Sent to owner of ${u} · 14-day clock started` },
      { k: "Documents", t: () => "2024 AGM minutes summarized by topic", ai: true },
      { k: "Approval", t: () => "New treasurer approved · welcome email sent" },
    ];
    const layer = stage.querySelector("[data-events]");
    let eventIndex = 0;

    const spawn = () => {
      const w = pick(windows);
      const ev = events[eventIndex++ % events.length];
      const cls = ev.ai ? "ai" : "lit";
      w.rect.classList.remove("lit", "ai");
      w.rect.classList.add(cls);
      const card = document.createElement("div");
      card.className = `event-card${ev.ai ? " ai" : ""}`;
      const left = (w.x / VIEW_W) * 100, top = (w.y / VIEW_H) * 100;
      const onLeft = w.x >= VIEW_W / 2;
      card.style.left = `${left}%`;
      card.style.top = `${top}%`;
      // `translate` (not `transform`) so the enter/exit animations don't clobber the offset.
      card.style.translate = `${onLeft ? "calc(-100% - 18px)" : "18px"} -50%`;
      card.innerHTML = `<div class="k">${ev.k}</div><div>${ev.t(w.unit)}</div>`;
      layer.appendChild(card);
      setTimeout(() => card.remove(), 4200);
      setTimeout(() => w.rect.classList.remove("ai"), 4200);
    };

    if (!reduceMotion) {
      setInterval(() => pick(windows).rect.classList.toggle("lit"), 650);
      setTimeout(spawn, 1600);
      setInterval(spawn, 2900);
    }
  }

  // ---------- "Ask your bylaws" demo ----------
  const demo = document.querySelector("[data-ask-demo]");
  if (demo) {
    const qa = [
      {
        q: "Can I rent my unit as a short-term rental?",
        a: [
          ["No. Rentals must be for a term of at least 30 days", "Bylaws p.18"],
          [", and the owner must file a Form K before the tenant moves in", "Bylaws p.19"],
          [". Short-term rental fines can be up to $1,000 per day.", "Bylaws p.31"],
        ],
      },
      {
        q: "What are the rules for visitor parking?",
        a: [
          ["Visitors may use the marked stalls for up to 24 hours", "Rules p.4"],
          [". Longer stays need a pass from the strata manager", "Rules p.4"],
          [", and unauthorized vehicles may be towed at the owner's expense.", "Bylaws p.12"],
        ],
      },
      {
        q: "How many pets can I have?",
        a: [
          ["Up to two pets per strata lot: one dog or one cat, plus caged birds or fish", "Bylaws p.9"],
          [". Dogs must be leashed on common property.", "Bylaws p.9"],
        ],
      },
    ];
    const qEl = demo.querySelector("[data-q]");
    const stateEl = demo.querySelector("[data-state]");
    const aEl = demo.querySelector("[data-a]");
    const chips = [...demo.querySelectorAll("[data-chip]")];
    let run = 0;

    const render = (item) => {
      aEl.innerHTML = item.a.map(([text, cite]) => `${text}<span class="cite">${cite}</span>`).join("");
    };

    const play = async (i) => {
      const token = ++run;
      const item = qa[i];
      chips.forEach((c, n) => c.classList.toggle("active", n === i));
      aEl.innerHTML = "";
      aEl.style.opacity = 0;
      stateEl.hidden = true;
      if (reduceMotion) { qEl.textContent = item.q; render(item); aEl.style.opacity = 1; return; }
      qEl.textContent = "";
      for (const ch of item.q) {
        if (token !== run) return;
        qEl.textContent += ch;
        await sleep(32);
      }
      stateEl.hidden = false;
      await sleep(1500);
      if (token !== run) return;
      stateEl.hidden = true;
      render(item);
      aEl.style.transition = "opacity 0.5s";
      aEl.style.opacity = 1;
      await sleep(6000);
      if (token === run) play((i + 1) % qa.length);
    };

    chips.forEach((chip, i) => chip.addEventListener("click", () => play(i)));
    // Start when the demo scrolls into view.
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) { io.disconnect(); play(0); }
    }, { threshold: 0.4 });
    io.observe(demo);
  }

  // ---------- Scroll reveal ----------
  const revealables = document.querySelectorAll("[data-reveal], [data-reveal-group]");
  const ro = new IntersectionObserver((entries) => {
    entries.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("is-visible"); ro.unobserve(e.target); } });
  }, { threshold: 0.15 });
  revealables.forEach((el) => ro.observe(el));
})();
