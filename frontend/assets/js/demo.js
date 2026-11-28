/* Primacy interactive demo: a local simulation of the whole lifecycle. No wallet, no network.
   Commitments shown here are real SHA-256 digests computed with the same function the site uses. */
(function () {
  "use strict";
  const P = window.Primacy, { el, $ } = P;
  const pages = (P.pages = P.pages || {});

  const CAST = { sia: { name: "Sia", role: "Sponsor", addr: "0x5144aa01b3c0de2f7a6e8d90c1b2a3f4e5d6c7b8" }, ana: { name: "Ana", role: "Hunter", addr: "0xa11a7e5d1c0b9f8e7d6c5b4a39281706f5e4d3c2" }, ben: { name: "Ben", role: "Hunter", addr: "0xbe4e5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d" }, cy: { name: "Cy", role: "Hunter", addr: "0xc0c0ffee12345678abcdef0123456789abcdef01" } };
  const SPONSOR = CAST.sia.addr, BID = "quickstart-v1";
  const FIND = {
    ana: { title: "Quickstart step 3 uses the wrong port", body: "Step 3 tells readers to open http://localhost:8080, but the server in step 2 listens on port 4000, so the page never loads.", salt: "ana-demo-salt-0001" },
    ben: { title: "Dev server port in the Quickstart is incorrect", body: "The Quickstart sends people to localhost:8080 after starting the server, which actually runs on 4000. The link in step 3 is dead.", salt: "ben-demo-salt-0002" },
    cy: { title: "Homepage hero image looks blurry", body: "The big picture on the marketing homepage is low resolution on my phone and should be replaced.", salt: "cy-demo-salt-0003" }
  };
  const M = 1000; /* one GEN = 1000 milli-GEN in this simulation, so nothing is ever a float */
  const REWARD = 500, BOND = 50, SLOTS = 2;
  const g = (m) => String(+(m / M).toFixed(3));
  const digests = {};

  const fresh = () => ({
    acts: { sia: { credit: 0, locked: 0, wallet: 10000 }, ana: { credit: 0, locked: 0, wallet: 1000 }, ben: { credit: 0, locked: 0, wallet: 1000 }, cy: { credit: 0, locked: 0, wallet: 1000 } },
    bounty: null, queue: [], hot: [], validators: null, log: ""
  });

  /* each step mutates a state and says what changed */
  const STEPS = [
    { t: "Meet the cast", hot: [], text: "Sia runs the Quickstart guide for a product and wants its mistakes found. Ana, Ben and Cy are bug hunters. Each has some GEN in their wallet. Nothing has happened on chain yet.", fn() {} },
    { t: "Sia deposits credit", hot: ["sia"], text: "Everything in Primacy is paid from your own credit. Sia deposits 2 GEN with deposit_credit. Only Sia can ever move it.", fn(s) { s.acts.sia.wallet -= 2000; s.acts.sia.credit += 2000; } },
    { t: "Sia opens a bounty", hot: ["sia"], text: "create_bounty sets the scope, a reward of 0.5 GEN per slot, 2 slots and a bond of 0.05 GEN per finding. The 1 GEN reward is locked at once, so hunters know it is real. The scope is the text validators will judge against.", fn(s) { s.acts.sia.credit -= REWARD * SLOTS; s.acts.sia.locked += REWARD * SLOTS; s.bounty = { id: BID, scope: "Factual mistakes in the Quickstart guide: wrong values, dead links, broken commands. Design opinions are out of scope.", status: "open", heads: 0, escrow: REWARD * SLOTS }; } },
    { t: "Hunters fund their bonds", hot: ["ana", "ben", "cy"], text: "To commit a finding, a hunter needs credit for the bond. The bond is refunded unless the finding is invalid or never revealed, so spam costs something.", fn(s) { ["ana", "ben", "cy"].forEach((k) => { s.acts[k].wallet -= 200; s.acts[k].credit += 200; }); } },
    { t: "Ana commits first", hot: ["ana"], text: "Ana hashes her finding together with a secret salt and her own address, then calls commit_finding with only the hash. The bond locks and she takes place number 0 in line. Nobody can read her finding yet.", commit: "ana", fn(s) { const a = s.acts.ana; a.credit -= BOND; a.locked += BOND; s.queue.push({ who: "ana", status: "committed", title: null }); } },
    { t: "Ben and Cy commit next", hot: ["ben", "cy"], text: "Ben spotted the same mistake later. Cy found something unrelated. Both commit hashes and take places 1 and 2. Even someone watching the chain cannot overtake Ana: the order of commits is the priority.", commit: "ben,cy", fn(s) { ["ben", "cy"].forEach((k) => { s.acts[k].credit -= BOND; s.acts[k].locked += BOND; s.queue.push({ who: k, status: "committed", title: null }); }); } },
    { t: "Everyone reveals", hot: ["ana", "ben", "cy"], text: "Within the reveal window each hunter publishes the title, body and salt. The contract hashes them again. Only text that matches the earlier hash is accepted. Now the findings are public and waiting in the queue.", fn(s) { s.queue.forEach((q) => { q.status = "revealed"; q.title = FIND[q.who].title; q.body = FIND[q.who].body; }); } },
    { t: "Validators judge finding 0", hot: [], text: "Anyone calls adjudicate. Five validators each read the scope and the finding and answer a small fixed form. The contract only accepts the result if they agree on the classification. This finding is in scope, specific, and nothing earlier exists to duplicate.", validators: { id: 0, yes: 5, json: { in_scope: "yes", actionable: "yes", duplicate_of: "none", confidence: 94, rationale: "Names the exact step and the real port mismatch." } }, fn(s) { s.queue[0].status = "distinct"; } },
    { t: "Ana is paid", hot: ["ana"], text: "The outcome is distinct, so contract code pays Ana the 0.5 GEN reward and refunds her bond. The model never chose an amount or a recipient. It only filled in the form.", fn(s) { s.acts.ana.credit += REWARD + BOND; s.acts.ana.locked -= BOND; s.bounty.escrow -= REWARD; s.acts.sia.locked -= REWARD; s.bounty.heads = 1; } },
    { t: "Finding 1 is a duplicate", hot: ["ben"], text: "Next in line is Ben. His wording is different, but he describes the same defect in the same place. The validators agree it duplicates the accepted finding H1, which is Ana's. Ben gets his bond back and no reward.", validators: { id: 1, yes: 5, json: { in_scope: "yes", actionable: "yes", duplicate_of: "H1", confidence: 91, rationale: "Same wrong port in the same Quickstart step." } }, fn(s) { const q = s.queue[1]; q.status = "duplicate"; q.of = 0; s.acts.ben.credit += BOND; s.acts.ben.locked -= BOND; } },
    { t: "Finding 2 is out of scope", hot: ["cy", "sia"], text: "Cy reported a blurry image, but the scope covers factual mistakes in the guide. With high confidence the validators call it invalid, so Cy's bond is forfeited to Sia.", validators: { id: 2, yes: 5, json: { in_scope: "no", actionable: "unclear", duplicate_of: "none", confidence: 92, rationale: "A visual preference, not a factual error in the guide." } }, fn(s) { const q = s.queue[2]; q.status = "invalid"; s.acts.cy.locked -= BOND; s.acts.sia.credit += BOND; } },
    { t: "Anyone closes the bounty", hot: ["sia"], text: "Commits are over and nothing is pending, so anyone can call close_bounty. The unused 0.5 GEN slot returns to Sia's credit. If all slots had filled, the bounty would have closed by itself.", fn(s) { s.acts.sia.locked -= s.bounty.escrow; s.acts.sia.credit += s.bounty.escrow; s.bounty.escrow = 0; s.bounty.status = "closed"; } },
    { t: "Everyone withdraws", hot: ["sia", "ana", "ben", "cy"], text: "withdraw_credit sends a person's whole credit back to their own wallet, and nowhere else. Ana ends 0.5 GEN up, Ben is even, Cy lost his bond, and Sia paid for exactly one real fix.", fn(s) { Object.keys(s.acts).forEach((k) => { s.acts[k].wallet += s.acts[k].credit; s.acts[k].credit = 0; }); } }
  ];

  pages.demo = async function () {
    const stage = $("#stage"), narr = $("#narr");
    /* real digests for the commit steps */
    for (const k of ["ana", "ben", "cy"]) digests[k] = await P.crypto.commitDigest({ sponsor: SPONSOR, bountyId: BID, hunter: CAST[k].addr, salt: FIND[k].salt, title: FIND[k].title, body: FIND[k].body });
    let at = 0, timer = null, playing = false;
    const stateAt = (n) => { const s = fresh(); for (let i = 0; i <= n; i++) STEPS[i].fn(s); return s; };

    function renderStage(s, step) {
      const actors = el("div", { class: "actors" }, Object.keys(CAST).map((k) => {
        const a = s.acts[k];
        return el("div", { class: "actor" + (step.hot.includes(k) ? " hot" : "") }, el("b", null, el("span", { class: "av", style: P.avatarStyle(CAST[k].addr) }), CAST[k].name),
          el("span", { class: "small muted", text: CAST[k].role }),
          el("dl", null, el("dt", { text: "wallet" }), el("dd", { text: g(a.wallet) }), el("dt", { text: "credit" }), el("dd", { text: g(a.credit) }), el("dt", { text: "locked" }), el("dd", { text: g(a.locked) })));
      }));
      const kids = [actors];
      if (s.bounty) kids.push(el("div", { class: "demo-bounty" }, el("div", { class: "row between" }, el("b", { text: "Bounty " + s.bounty.id }), el("span", { class: "chip " + s.bounty.status, text: s.bounty.status })),
        el("p", { class: "small", style: { margin: "6px 0" }, text: s.bounty.scope }), el("div", { class: "meta-row" }, el("span", { text: "Reward " + g(REWARD) + " GEN per slot" }), el("span", { text: "Bond " + g(BOND) + " GEN" }), el("span", { text: "Slots " + s.bounty.heads + "/" + SLOTS }), el("span", { text: "Escrow " + g(s.bounty.escrow) + " GEN" }))));
      if (s.queue.length) {
        kids.push(el("div", { class: "label", text: "The queue, in commit order" }), el("div", { class: "demo-queue" }, s.queue.map((q, i) => el("div", { class: "dq s-" + q.status },
          el("span", { class: "n", text: i }),
          el("div", null, el("b", { text: q.title || "Hidden until revealed" }), el("p", null, q.title ? (q.status === "duplicate" ? "Duplicate of #" + q.of + ". " : "") + CAST[q.who].name : [CAST[q.who].name + " committed ", el("code", { text: digests[q.who].slice(0, 18) + "…" })])),
          el("span", { class: "chip " + q.status, text: q.status })))));
      }
      if (step.validators) {
        const v = step.validators;
        kids.push(el("div", { style: { marginTop: "16px" } }, el("div", { class: "label", text: "Validators on finding #" + v.id }),
          el("div", { class: "vals" }, Array.from({ length: 5 }, (_, i) => el("span", { class: "v " + (i < v.yes ? "yes" : ""), text: "V" + (i + 1) })), el("span", { class: "small", text: v.yes + " of 5 agree" })),
          el("pre", { class: "json", text: JSON.stringify(v.json, null, 2) })));
      }
      if (step.commit) {
        kids.push(el("div", { style: { marginTop: "14px" } }, el("div", { class: "label", text: "What goes on chain" }),
          step.commit.split(",").map((k) => el("p", { class: "small", style: { margin: "2px 0" } }, CAST[k].name + ": ", el("code", { class: "break", text: digests[k] })))));
      }
      stage.replaceChildren(...kids);
    }
    function render() {
      const step = STEPS[at], s = stateAt(at);
      renderStage(s, step);
      narr.replaceChildren(
        el("div", { class: "step-no", text: "Step " + (at + 1) + " of " + STEPS.length }), el("h3", { text: step.t }), el("p", { text: step.text }),
        el("div", { class: "ctrl" },
          el("button", { class: "btn small ghost", onclick: () => go(at - 1, true), disabled: at === 0, text: "Back" }),
          el("button", { class: "btn small " + (playing ? "white" : "sun"), onclick: toggle, text: playing ? "Pause" : at === STEPS.length - 1 ? "Replay" : "Play" }),
          el("button", { class: "btn small", onclick: () => go(at + 1, true), disabled: at === STEPS.length - 1, text: "Next" })),
        el("div", { class: "dots", role: "tablist" }, STEPS.map((x, i) => el("button", { class: i === at ? "cur" : i < at ? "on" : "", "aria-label": "Step " + (i + 1) + ": " + x.t, onclick: () => go(i, true) }))),
        at === STEPS.length - 1 ? el("div", { class: "row", style: { marginTop: "18px" } }, el("a", { class: "btn mint", href: "explore.html", text: "Try it for real" }), el("a", { class: "btn white", href: "docs.html", text: "Read the docs" })) : null);
    }
    function go(n, manual) {
      at = Math.max(0, Math.min(STEPS.length - 1, n));
      if (manual && playing) stop();
      render();
      if (at === STEPS.length - 1) { stop(); render(); P.confetti(70); }
    }
    function stop() { playing = false; clearInterval(timer); timer = null; }
    function toggle() {
      if (playing) { stop(); render(); return; }
      if (at === STEPS.length - 1) at = 0;
      playing = true; render();
      timer = setInterval(() => { if (at < STEPS.length - 1) go(at + 1, false); else stop(); }, 6000);
    }
    render();
  };
})();
