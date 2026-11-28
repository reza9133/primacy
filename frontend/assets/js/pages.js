/* Primacy pages, part 1: home, explore, bounty, create. */
(function () {
  "use strict";
  const P = window.Primacy, CFG = P.CFG, C = P.chain, { el, $, $$, big, fmtGen, parseGen, now, fmtDate, fmtSpan, shortAddr, isAddr, isBountyId } = P;
  const pages = (P.pages = P.pages || {});

  /* ---------- shared bits ---------- */
  function note(kind, title, text, ...actions) {
    return el("div", { class: "panel empty" }, kind === "load" ? P.spinner() : null, el("h3", { text: title }), text ? el("p", { text }) : null, actions.length ? el("div", { class: "row", style: { justifyContent: "center" } }, actions) : null);
  }
  function startTicker(onExpire) {
    if (P._tick) clearInterval(P._tick);
    P._tick = setInterval(() => {
      let expired = false;
      $$("[data-until]").forEach((n) => {
        const left = Number(n.dataset.until) - now();
        if (left <= 0) { if (!n.dataset.done) { n.dataset.done = "1"; expired = true; } n.textContent = "now"; } else n.textContent = fmtSpan(left);
      });
      if (expired && onExpire) onExpire();
    }, 1000);
  }
  const until = (ts) => el("span", { "data-until": String(ts), text: ts > now() ? fmtSpan(ts - now()) : "now" });
  const slotDots = (n, of) => el("div", { class: "slots", role: "img", "aria-label": n + " of " + of + " slots filled" }, Array.from({ length: of }, (_, i) => el("i", { class: i < n ? "on" : "" })));
  const stat = (label, node) => el("div", { class: "stat" }, el("b", null, node), el("span", { text: label }));
  const CLOSE_REASON = { all_slots_filled: "Every reward slot was filled", review_deadline: "The review deadline passed", commit_window_ended: "Commits ended and nothing was pending", cancelled_before_any_commit: "Cancelled by the sponsor before any commit" };
  const STATUS_NOTE = {
    committed: "Hash is on chain. The text stays hidden until the hunter reveals it.",
    revealed: "Published and waiting its turn in the queue.",
    distinct: "First report of this defect. The reward was paid and the bond refunded.",
    duplicate: "Reports a defect that an earlier accepted finding already covers. Bond refunded, no reward.",
    invalid: "Out of scope or not actionable. The bond went to the sponsor.",
    unresolved: "Validators could not decide, or the bounty closed first. Bond refunded.",
    void: "Not revealed in time. The bond went to the sponsor.",
    late: "The bounty filled its slots while this finding waited. Bond refunded."
  };
  P.STATUS_NOTE = STATUS_NOTE;
  function effCursor(b, fs) { let c = b.cursor; while (c < fs.length && fs[c].status !== "committed" && fs[c].status !== "revealed") c++; return c; }
  P.effCursor = effCursor;
  function commitOpen(b) { return b.status === "open" && now() < b.commitBy && b.heads < b.slots && b.count < 32; }
  P.commitOpen = commitOpen;

  /* ====================================================================
     HOME
     ==================================================================== */
  pages.home = function () {
    const box = $("#live"); if (!box) return;
    Promise.all([C.views.info(), C.views.accounting()]).then(([info, acc]) => {
      box.replaceChildren(
        el("div", { class: "row between" }, el("h3", { text: "Live from the contract" }), el("span", { class: "chip open" }, "● online")),
        el("div", { class: "grid g4", style: { marginTop: "14px" } },
          stat("Credit held for users", P.genAmt(acc.credits)), stat("Locked in bounties and bonds", P.genAmt(acc.locked)),
          stat("Contract balance", P.genAmt(acc.balance)), stat("Books balance", el("span", { text: acc.solvent ? "Yes, solvent" : "Shortfall" }))),
        el("p", { class: "small muted", style: { margin: "14px 0 0" } }, "Version " + info.version + ". Minimum reward " + fmtGen(info.min_reward_wei) + " GEN, up to " + info.max_slots + " slots, " + info.max_findings + " findings per bounty. Read straight from ", el("a", { href: CFG.explorerAddress, target: "_blank", rel: "noopener", text: shortAddr(CFG.contract) }), "."));
    }).catch((e) => { box.replaceChildren(el("h3", { text: "Live data is unavailable" }), el("p", { class: "muted", text: "Studionet did not answer (" + C.cleanErr(e) + "). The contract is still at " + CFG.contract + "." })); });
  };

  /* ====================================================================
     EXPLORE
     ==================================================================== */
  pages.explore = function () {
    const form = $("#find-form"), fs = $("#f-sponsor"), fi = $("#f-id"), err = $("#f-err");
    P.wallet.on(() => { const b = $("#f-me"); if (b) b.disabled = !P.wallet.connected; }); const meBtn = $("#f-me"); meBtn.disabled = !P.wallet.connected;
    meBtn.addEventListener("click", () => { if (P.wallet.account) fs.value = P.wallet.account; });
    form.addEventListener("submit", (e) => {
      e.preventDefault(); err.textContent = "";
      const s = fs.value.trim(), id = fi.value.trim();
      if (!isAddr(s)) { err.textContent = "The sponsor must be a 0x address with 40 hex characters."; fs.classList.add("bad"); return; } fs.classList.remove("bad");
      if (!isBountyId(id)) { err.textContent = "A bounty id uses 1 to 64 letters, digits, dots, dashes or underscores, and starts with a letter or digit."; fi.classList.add("bad"); return; } fi.classList.remove("bad");
      location.href = P.bountyUrl(s, id);
    });
    function drawWatch() {
      const host = $("#watch-list"), list = P.watch.list();
      host.replaceChildren();
      if (!list.length) { host.append(el("div", { class: "empty" }, el("p", { text: "Bounties you open, create or hunt in will be listed here." }))); return; }
      list.forEach((w) => host.append(el("div", { class: "row", style: { flexWrap: "nowrap" } },
        el("a", { class: "item grow", href: P.bountyUrl(w.s, w.id) }, el("span", null, el("b", { text: w.id }), " ", el("span", { class: "addr", text: shortAddr(w.s) })), el("span", { class: "muted small", text: "Open" })),
        el("button", { class: "btn ghost small", "aria-label": "Remove " + w.id, onclick: () => { P.watch.remove(w.s, w.id); drawWatch(); }, text: "Remove" }))));
    }
    drawWatch();
    const ex = $("#examples");
    CFG.examples.forEach((e) => {
      const status = el("span", { class: "chip skeleton", text: "loading" });
      ex.append(el("a", { class: "item", href: P.bountyUrl(e.sponsor, e.id) }, el("span", null, el("b", { text: e.id }), " ", el("span", { class: "addr", text: shortAddr(e.sponsor) }), el("br"), el("span", { class: "small muted", text: e.note })), status));
      C.views.bounty(e.sponsor, e.id).then((b) => { status.replaceWith(el("span", null, P.chip(b.status), " ", el("span", { class: "small muted", text: b.count + " findings" }))); })
        .catch(() => { status.className = "small muted"; status.textContent = "not found"; });
    });
  };

  /* ====================================================================
     BOUNTY DETAIL
     ==================================================================== */
  pages.bounty = function () {
    const root = $("#bounty-root");
    const q = new URLSearchParams(location.search), s = (q.get("s") || "").trim().toLowerCase(), id = (q.get("id") || "").trim();
    if (!isAddr(s) || !isBountyId(id)) { root.replaceChildren(note("err", "This bounty link is incomplete", "A bounty is identified by its sponsor address and its id.", el("a", { class: "btn", href: "explore.html", text: "Find a bounty" }))); return; }
    let b = null, fs = [];

    async function load(spin) {
      if (spin) root.replaceChildren(note("load", "Reading the bounty from Studionet", "Validators answer reads for free, this takes a moment."));
      try { [b, fs] = await Promise.all([C.views.bounty(s, id), C.views.findings(s, id)]); }
      catch (e) { root.replaceChildren(note("err", "Bounty not found", C.cleanErr(e) + ". Check the sponsor address and the id.", el("a", { class: "btn", href: "explore.html", text: "Back to bounties" }))); return; }
      P.watch.add(s, id); document.title = id + " · Primacy bounty"; draw();
    }
    async function act(fn, args, opts, after) {
      try { const r = await C.write(fn, args, opts); await load(false); if (after) after(r); } catch (e) { if (!e.silent) await load(false).catch(() => {}); }
    }

    function revealModal(f) {
      const entry = P.vault.all().find((x) => x.commitment === f.commitment && x.sponsor === b.sponsor && x.bountyId === b.id);
      const title = el("input", { value: entry ? entry.title : "", maxlength: 240 }), body = el("textarea", { rows: 6 }), salt = el("input", { value: entry ? entry.salt : "", class: "mono", maxlength: 64 });
      body.value = entry ? entry.body : "";
      const status = el("div", { class: "small", style: { margin: "10px 0" } }), go = el("button", { class: "btn", disabled: true, text: "Reveal finding" });
      const m = P.modal([], { wide: true, label: "Reveal finding" });
      let ok = false;
      async function check() {
        const err = P.crypto.validateText("Title", title.value, 120, false) || P.crypto.validateText("Body", body.value.replace(/\r\n?/g, "\n"), 1200, true) || (/^[A-Za-z0-9_-]{16,64}$/.test(salt.value) ? "" : "The salt is 16 to 64 letters, digits, dashes or underscores.");
        if (err) { ok = false; status.textContent = err; status.style.color = "#C2281B"; go.disabled = true; return; }
        const d = await P.crypto.commitDigest({ sponsor: b.sponsor, bountyId: b.id, hunter: f.hunter, salt: salt.value, title: title.value, body: body.value.replace(/\r\n?/g, "\n") });
        ok = d === f.commitment; status.textContent = ok ? "✓ This text matches the commitment on chain." : "This text does not match the commitment. It must be exactly what you committed, with the same salt.";
        status.style.color = ok ? "#0B7A5C" : "#C2281B"; go.disabled = !ok;
      }
      [title, body, salt].forEach((n) => n.addEventListener("input", check));
      go.addEventListener("click", async () => {
        m.close();
        const t = title.value, bd = body.value.replace(/\r\n?/g, "\n"), sl = salt.value;
        await act("reveal_finding", [b.sponsor, b.id, BigInt(f.index), t, bd, sl], { title: "Reveal finding #" + f.index, success: "Your finding is public and waiting in the queue." }, () => {
          const e = P.vault.all().find((x) => x.commitment === f.commitment); if (e) P.vault.patch(e.id, { status: "revealed" });
        });
      });
      m.set([el("h3", { text: "Reveal finding #" + f.index }),
        el("p", { class: "muted", text: entry ? "Your text was found in this browser's vault. Check it and reveal." : "Paste the exact title, body and salt you committed with." }),
        el("div", { class: "field" }, el("label", { text: "Title" }), title), el("div", { class: "field" }, el("label", { text: "Body" }), body), el("div", { class: "field" }, el("label", { text: "Salt" }), salt),
        status, el("div", { class: "row" }, go, el("button", { class: "btn ghost", onclick: () => m.close(), text: "Cancel" }))]);
      check();
    }

    function ticket(f, cursor) {
      const t = now(), me = P.wallet.account && P.wallet.account.toLowerCase();
      const head = el("div", { class: "t-head" }, el("span", { class: "t-no", text: "#" + f.index }),
        el("h4", { text: f.title || (f.status === "committed" ? "Hidden until revealed" : "Untitled") }), P.chip(f.status), P.addrChip(f.hunter));
      const kids = [head];
      if (f.status === "distinct") kids.push(el("span", { class: "first", text: "FIRST FINDER" }));
      if (f.body) kids.push(el("pre", { text: f.body }));
      kids.push(el("p", { class: "small", style: { margin: "4px 0 8px" }, text: STATUS_NOTE[f.status] || "" }));
      if (f.status === "duplicate" && f.duplicateOf >= 0) kids.push(el("p", { class: "small" }, el("b", { text: "Same defect as " }), el("a", { href: "#f" + f.duplicateOf, text: "finding #" + f.duplicateOf })));
      if (f.inScope || f.confidence) kids.push(el("div", { class: "meta-row" }, el("span", { text: "In scope: " + (f.inScope || "n/a") }), el("span", { text: "Actionable: " + (f.actionable || "n/a") }), el("span", { text: "Validator confidence: " + f.confidence + "%" })));
      if (f.rationale) kids.push(el("p", { class: "small muted", style: { margin: "6px 0 0" } }, el("b", { text: "Validators said: " }), f.rationale));
      const meta = el("div", { class: "meta-row", style: { marginTop: "8px" } }, el("span", { text: "Committed " + fmtDate(f.committedAt) }),
        f.revealedAt ? el("span", { text: "Revealed " + fmtDate(f.revealedAt) }) : null, f.decidedAt ? el("span", { text: "Decided " + fmtDate(f.decidedAt) }) : null,
        el("span", null, "Bond ", P.genAmt(f.bond || 0n), " ", f.bondState === "locked" ? "locked" : f.bondState === "refunded" ? "refunded" : f.bondState === "forfeited_to_sponsor" ? "forfeited" : ""),
        f.reward > 0n ? el("span", null, "Reward ", P.genAmt(f.reward)) : null,
        f.attempts || f.failures ? el("span", { text: "Attempts " + f.attempts + ", failures " + f.failures }) : null,
        f.status === "revealed" && f.retryAt > t ? el("span", null, "Retry in ", until(f.retryAt)) : null);
      kids.push(meta);
      const actions = el("div", { class: "row", style: { marginTop: "12px" } });
      if (f.status === "committed") {
        if (t < f.revealBy) { kids.push(el("p", { class: "small", style: { marginTop: "8px" } }, "Reveal deadline in ", until(f.revealBy), ".")); if (me === f.hunter) actions.append(el("button", { class: "btn small mint", onclick: () => revealModal(f), text: "Reveal this finding" })); }
        else actions.append(el("button", { class: "btn small coral", onclick: () => act("void_unrevealed", [b.sponsor, b.id, BigInt(f.index)], { title: "Void finding #" + f.index, success: "The unrevealed commitment is void. Its bond went to the sponsor." }), text: "Void it (reveal window ended)" }));
      }
      if (f.status === "revealed" && f.index === cursor && b.status === "open") kids.push(el("p", { class: "small", style: { marginTop: "8px", fontWeight: 700 }, text: "Next in line for review." }));
      if (actions.children.length) kids.push(actions);
      return el("article", { class: "ticket s-" + f.status, id: "f" + f.index }, kids);
    }

    function draw() {
      const t = now(), cursor = effCursor(b, fs), me = P.wallet.account && P.wallet.account.toLowerCase(), isSponsor = me === b.sponsor;
      const open = b.status === "open";
      const phase = !open ? (b.status === "cancelled" ? "Cancelled" : "Closed") : t < b.commitBy ? (b.heads >= b.slots ? "All slots filled" : "Accepting commits") : "Commit window ended, reviewing";
      const header = el("section", { class: "page-head wrap" },
        el("div", { class: "row" }, P.chip(b.status), el("span", { class: "muted", text: phase })),
        el("h1", { class: "break", style: { fontSize: "clamp(2rem,4.5vw,3.2rem)", marginTop: "10px" }, text: b.id }),
        el("div", { class: "row" }, el("span", { class: "muted", text: "Sponsored by" }), P.addrChip(b.sponsor), isSponsor ? el("span", { class: "chip open", text: "you" }) : null,
          el("button", { class: "btn small ghost", onclick: () => P.copy(location.href, "Link copied"), text: "Copy link" }),
          el("button", { class: "btn small ghost", onclick: () => load(true), text: "Refresh" })));
      const scope = el("div", { class: "sticker sun" }, el("h3", { text: "What counts as a finding" }), el("p", { style: { margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-word" }, text: b.scope }));
      const stats = el("div", { class: "grid g4" },
        el("div", { class: "panel" }, stat("Reward per slot", P.genAmt(b.reward))), el("div", { class: "panel" }, stat("Bond per finding", P.genAmt(b.bond))),
        el("div", { class: "panel" }, el("div", { class: "stat" }, el("b", { text: b.heads + " / " + b.slots }), el("span", { text: "Slots filled" }), slotDots(b.heads, b.slots))),
        el("div", { class: "panel" }, stat("Reward still in escrow", P.genAmt(b.escrow))));
      const tl = [["Created", b.createdAt, true], ["Commits close", b.commitBy, false], ["Review deadline", b.reviewBy, false]];
      if (b.closedAt) tl.push([b.status === "cancelled" ? "Cancelled" : "Closed", b.closedAt, true, CLOSE_REASON[b.closeReason] || b.closeReason]);
      const line = el("div", { class: "timeline" }, tl.map(([label, ts, always, extra]) => {
        const past = always || ts <= t; return el("div", { class: "tl " + (past ? "past" : "") },
          el("b", { text: label }), el("span", { class: "muted small", text: fmtDate(ts) }), !past && open ? el("span", { class: "small" }, "  in ", until(ts)) : null, extra ? el("div", { class: "small muted", text: extra }) : null); }),
        el("div", { class: "tl" }, el("b", { text: "Reveal window" }), el("span", { class: "muted small", text: fmtSpan(b.revealWindow) + " after each commit" })));

      /* actions */
      const acts = el("div", { class: "stack" });
      if (commitOpen(b)) {
        acts.append(isSponsor ? el("p", { class: "muted", text: "Sponsors cannot submit findings to their own bounty." })
          : el("div", null, el("a", { class: "btn mint", href: "hunt.html?s=" + b.sponsor + "&id=" + encodeURIComponent(b.id), text: "Submit a finding" }), el("p", { class: "small muted", style: { marginTop: "8px" } }, "Commits close in ", until(b.commitBy), ". A bond of ", P.genAmt(b.bond), " is locked until the finding is decided.")));
      } else if (open) acts.append(el("p", { class: "muted", text: b.heads >= b.slots ? "Every slot is filled." : b.count >= 32 ? "The queue is full (32 findings)." : "The commit window has ended." }));
      if (open) {
        const f = fs[cursor];
        if (cursor < fs.length && t < b.reviewBy) {
          if (f.status === "revealed") {
            const wait = f.retryAt > t;
            acts.append(el("div", null,
              el("button", { class: "btn" + (wait ? "" : " sun"), disabled: wait, onclick: () => act("adjudicate", [b.sponsor, b.id], { title: "Review finding #" + f.index, hint: "Validators are reading the finding and comparing it with accepted ones. This usually takes one to three minutes.", success: "The finding was decided.", celebrate: false }, () => { const nf = fs[f.index]; if (nf && nf.status === "distinct") P.confetti(); }), text: "Review finding #" + f.index + " now" }),
              el("p", { class: "small muted", style: { marginTop: "8px" } }, wait ? ["The previous attempt was inconclusive. You can try again in ", until(f.retryAt), "."] : "Anyone can start the review. Validators decide, the contract pays.")));
          } else if (f.status === "committed") acts.append(el("p", { class: "muted" }, "Finding #" + f.index + " is next but still hidden. ", t < f.revealBy ? ["Its hunter has ", until(f.revealBy), " left to reveal."] : "Its reveal window ended, so anyone can void it below."));
        }
        const canClose = t >= b.reviewBy || (t >= b.commitBy && cursor >= fs.length);
        if (canClose) acts.append(el("div", null, el("button", { class: "btn white", onclick: () => act("close_bounty", [b.sponsor, b.id], { title: "Close bounty", success: "The bounty is closed and unused reward went back to the sponsor." }), text: "Close this bounty" }), el("p", { class: "small muted", style: { marginTop: "8px" }, text: "Returns unused reward to the sponsor and settles any leftover bonds." })));
        if (isSponsor && b.count === 0) acts.append(el("div", null, el("button", { class: "btn coral", onclick: () => act("cancel_bounty", [b.id], { title: "Cancel bounty", success: "Cancelled. Your escrow is back in your credit." }), text: "Cancel bounty" }), el("p", { class: "small muted", style: { marginTop: "8px" }, text: "Possible only while nobody has committed." })));
      }
      if (!acts.children.length) acts.append(el("p", { class: "muted", text: "Nothing left to do here." }));

      const queue = el("div", { class: "queue-list" }, fs.length ? fs.map((f) => ticket(f, cursor)) : [el("div", { class: "panel empty" }, el("p", { text: "No one has committed a finding yet." }))]);

      root.replaceChildren(header, el("div", { class: "wrap stack" }, scope, stats,
        el("div", { class: "grid g2", style: { alignItems: "start" } }, el("div", { class: "sticker" }, el("h3", { text: "What you can do" }), acts), el("div", { class: "panel" }, el("h3", { text: "Timeline" }), line)),
        el("div", null, el("div", { class: "row between" }, el("h2", { text: "The queue" }), el("span", { class: "muted", text: b.count + " finding" + (b.count === 1 ? "" : "s") + ", decided strictly in commit order" })), queue)));
    }
    P.wallet.on(() => { if (b) draw(); });
    startTicker(() => { if (b) draw(); });
    load(true);
  };

  /* ====================================================================
     CREATE
     ==================================================================== */
  pages.create = function () {
    const f = { id: $("#c-id"), scope: $("#c-scope"), reward: $("#c-reward"), slots: $("#c-slots"), bond: $("#c-bond"), commit: $("#c-commit"), reveal: $("#c-reveal"), tail: $("#c-tail") };
    const errBox = $("#c-errors"), sum = $("#c-summary"), credit = $("#c-credit"), submit = $("#c-submit");
    const MIN_REWARD = 10n ** 14n, MIN_BOND = 10n ** 12n;
    let have = null;
    const cleanScope = () => f.scope.value.replace(/\s+/g, " ").trim();
    $("#c-bond-auto").addEventListener("click", () => { const r = parseGen(f.reward.value); if (r) f.bond.value = fmtGen(r / 10n, 18).replace(/,/g, ""); recalc(); });
    function values() {
      const e = [], reward = parseGen(f.reward.value), bond = parseGen(f.bond.value), slots = Number(f.slots.value), scope = cleanScope();
      if (!isBountyId(f.id.value.trim())) e.push("Bounty id: 1 to 64 letters, digits, dots, dashes or underscores, starting with a letter or digit.");
      if (scope.length < 20 || scope.length > 800) e.push("Scope: write 20 to 800 characters (now " + scope.length + ").");
      if (reward === null || reward < MIN_REWARD) e.push("Reward per slot: at least 0.0001 GEN.");
      if (bond === null || bond < MIN_BOND) e.push("Bond: at least 0.000001 GEN.");
      else if (reward !== null && bond > reward) e.push("Bond cannot be larger than the reward.");
      return { e, reward, bond, slots, scope, id: f.id.value.trim() };
    }
    function recalc() {
      $("#c-scope-n").textContent = cleanScope().length + " / 800";
      const v = values(), total = v.reward !== null ? v.reward * BigInt(v.slots) : null;
      sum.replaceChildren(
        el("dl", { class: "kv" },
          el("dt", { text: "Locked from your credit" }), el("dd", null, total !== null ? P.genAmt(total) : "n/a", total !== null ? el("span", { class: "muted small", text: "  (" + fmtGen(v.reward) + " × " + v.slots + ")" }) : null),
          el("dt", { text: "Commits close" }), el("dd", { text: fmtDate(now() + Number(f.commit.value)) }),
          el("dt", { text: "Reveal window" }), el("dd", { text: fmtSpan(Number(f.reveal.value)) + " after each commit" }),
          el("dt", { text: "Review deadline" }), el("dd", { text: fmtDate(now() + Number(f.commit.value) + Number(f.reveal.value) + Number(f.tail.value)) })));
      const need = total || 0n;
      if (!P.wallet.connected) credit.replaceChildren(el("p", { class: "muted", text: "Connect a wallet to check your credit." }));
      else if (have === null) credit.replaceChildren(el("span", { class: "spin-dots" }, el("i"), el("i"), el("i")));
      else {
        const short = need > have ? need - have : 0n;
        credit.replaceChildren(el("p", null, "Your credit: ", P.genAmt(have)), short > 0n ? el("div", { class: "callout warn" }, el("p", null, "You need ", P.genAmt(short), " more credit to lock this reward. Deposit it first, then create the bounty."),
          el("button", { class: "btn small sun", type: "button", onclick: () => deposit(short), text: "Deposit " + fmtGen(short) + " GEN" })) : need > 0n ? el("p", { class: "small", style: { color: "#0B7A5C", fontWeight: 700 }, text: "✓ Enough credit to open this bounty." }) : null);
      }
    }
    async function refreshCredit() { if (!P.wallet.connected) { have = null; recalc(); return; } try { have = await C.views.credit(P.wallet.account); } catch (e) { have = null; } recalc(); }
    async function deposit(amount) {
      try { await C.write("deposit_credit", [], { value: amount, title: "Deposit " + fmtGen(amount) + " GEN", success: "The GEN is now your Primacy credit." }); } catch (e) { return; }
      refreshCredit();
    }
    Object.values(f).forEach((n) => n.addEventListener("input", recalc)); Object.values(f).forEach((n) => n.addEventListener("change", recalc));
    P.wallet.on(refreshCredit); refreshCredit(); recalc(); setInterval(recalc, 30000);

    $("#c-form").addEventListener("submit", async (ev) => {
      ev.preventDefault(); errBox.replaceChildren();
      const v = values();
      if (v.e.length) { errBox.append(el("div", { class: "callout danger" }, el("strong", { text: "Fix these first" }), el("ul", null, v.e.map((x) => el("li", { text: x }))))); errBox.scrollIntoView({ behavior: "smooth", block: "center" }); return; }
      if (!(await P.wallet.ready())) return;
      const me = P.wallet.account.toLowerCase(), total = v.reward * BigInt(v.slots);
      submit.classList.add("busy");
      try {
        let exists = false; try { await C.views.bounty(me, v.id); exists = true; } catch (e) { exists = false; }
        if (exists) { errBox.append(el("div", { class: "callout danger" }, el("p", { text: "You already have a bounty with this id. Pick another id." }))); return; }
        const credit = await C.views.credit(me);
        if (credit < total) { have = credit; recalc(); errBox.append(el("div", { class: "callout warn" }, el("p", { text: "Your credit is too low. Deposit the missing amount shown above, then create the bounty." }))); return; }
        const commitBy = now() + Number(f.commit.value), reveal = Number(f.reveal.value), reviewBy = commitBy + reveal + Number(f.tail.value);
        await C.write("create_bounty", [v.id, v.scope, v.reward, BigInt(v.slots), v.bond, BigInt(commitBy), BigInt(reveal), BigInt(reviewBy)], { title: "Create bounty " + v.id, success: "Your bounty is open." });
        P.watch.add(me, v.id); P.confetti();
        const url = new URL(P.bountyUrl(me, v.id), location.href).href;
        $("#c-form").classList.add("hide");
        $("#c-done").classList.remove("hide");
        $("#c-done-link").href = P.bountyUrl(me, v.id);
        $("#c-done-copy").onclick = () => P.copy(url, "Bounty link copied");
      } catch (e) { /* the transaction dialog already explained what happened */ }
      finally { submit.classList.remove("busy"); }
    });
  };
})();
