/* Primacy pages, part 2: hunt, wallet (credit), docs helpers. */
(function () {
  "use strict";
  const P = window.Primacy, CFG = P.CFG, C = P.chain, { el, $, $$, fmtGen, parseGen, now, fmtDate, fmtSpan, shortAddr, isAddr, isBountyId } = P;
  const pages = (P.pages = P.pages || {});
  const until = (ts) => el("span", { "data-until": String(ts), text: ts > now() ? fmtSpan(ts - now()) : "now" });

  function depositModal(short, after) {
    const m = P.modal([], { label: "Deposit credit" });
    const amt = el("input", { value: fmtGen(short, 18).replace(/,/g, ""), inputmode: "decimal" });
    m.set([el("h3", { text: "Add credit first" }), el("p", { class: "muted", text: "Bonds and rewards are paid from your Primacy credit. You are short by " + fmtGen(short) + " GEN." }),
      el("div", { class: "field" }, el("label", { text: "Amount to deposit (GEN)" }), amt),
      el("div", { class: "row" }, el("button", { class: "btn sun", onclick: async () => { const w = parseGen(amt.value); if (!w || w <= 0n) { P.toast("Enter a positive amount.", "warn"); return; } m.close(); try { await C.write("deposit_credit", [], { value: w, title: "Deposit " + fmtGen(w) + " GEN", success: "Credit added." }); if (after) after(); } catch (e) {} }, text: "Deposit" }), el("button", { class: "btn ghost", onclick: () => m.close(), text: "Cancel" }))]);
  }
  P.depositModal = depositModal;

  /* ====================================================================
     HUNT
     ==================================================================== */
  pages.hunt = function () {
    const q = new URLSearchParams(location.search);
    const inS = $("#h-sponsor"), inId = $("#h-id"), inTitle = $("#h-title"), inBody = $("#h-body"), inSalt = $("#h-salt"), hashOut = $("#h-hash"), errBox = $("#h-errors"), card = $("#h-bounty"), commitBtn = $("#h-commit");
    let b = null, fs = [], salt = P.crypto.randomSalt();
    inSalt.value = salt;
    if (isAddr(q.get("s") || "")) inS.value = q.get("s"); if (q.get("id")) inId.value = q.get("id");
    $("#h-salt-new").addEventListener("click", () => { salt = P.crypto.randomSalt(); inSalt.value = salt; updateHash(); });
    $("#h-me").addEventListener("click", () => { if (P.wallet.account) inS.value = P.wallet.account; });

    function blockReason(bb, ff, me) {
      const t = now();
      if (bb.status !== "open") return "This bounty is " + bb.status + ".";
      if (t >= bb.commitBy) return "The commit window has ended.";
      if (bb.heads >= bb.slots) return "Every reward slot is already filled.";
      if (bb.count >= 32) return "The queue is full (32 findings).";
      if (me && me === bb.sponsor) return "Sponsors cannot submit findings to their own bounty.";
      if (me && ff.filter((x) => x.hunter === me).length >= 4) return "You already have 4 findings in this bounty, which is the limit.";
      return "";
    }
    async function loadBounty() {
      errBox.replaceChildren();
      const s = inS.value.trim().toLowerCase(), id = inId.value.trim();
      if (!isAddr(s) || !isBountyId(id)) { card.replaceChildren(el("div", { class: "callout danger" }, el("p", { text: "Enter the sponsor address and the bounty id." }))); return; }
      card.replaceChildren(el("div", { class: "row" }, P.spinner("sm"), el("span", { class: "muted", text: "Reading the bounty" })));
      try { [b, fs] = await Promise.all([C.views.bounty(s, id), C.views.findings(s, id)]); }
      catch (e) { b = null; card.replaceChildren(el("div", { class: "callout danger" }, el("p", { text: C.cleanErr(e) + ". Check the sponsor and the id." }))); return; }
      P.watch.add(s, id);
      const me = P.wallet.account && P.wallet.account.toLowerCase(), why = blockReason(b, fs, me);
      card.replaceChildren(el("div", { class: "sticker sun" }, el("div", { class: "row between" }, el("h3", { class: "break", text: b.id }), P.chip(b.status)),
        el("p", { style: { whiteSpace: "pre-wrap", wordBreak: "break-word" }, text: b.scope }),
        el("div", { class: "meta-row" }, el("span", null, "Reward ", P.genAmt(b.reward)), el("span", null, "Bond ", P.genAmt(b.bond)), el("span", { text: "Slots " + b.heads + "/" + b.slots }), el("span", null, "Commits close in ", until(b.commitBy))),
        why ? el("div", { class: "callout warn", style: { marginBottom: 0 } }, el("p", { text: why })) : el("p", { class: "small", style: { margin: "10px 0 0", fontWeight: 700 }, text: "✓ You can commit a finding here. Read the scope carefully first." }),
        el("p", { class: "small", style: { margin: "8px 0 0" } }, el("a", { href: P.bountyUrl(b.sponsor, b.id), text: "Open the full bounty page" }))));
      updateHash();
    }
    $("#h-load").addEventListener("click", loadBounty);
    if (inS.value && inId.value) loadBounty();

    const body = () => inBody.value.replace(/\r\n?/g, "\n");
    function counters() { $("#h-title-n").textContent = [...inTitle.value].length + " / 120"; $("#h-body-n").textContent = [...body()].length + " / 1200"; }
    async function updateHash() {
      counters();
      const me = P.wallet.account;
      if (!me || !b) { hashOut.textContent = !me ? "Connect a wallet so the commitment can include your address." : "Load a bounty to compute the commitment."; return; }
      const bad = P.crypto.validateText("Title", inTitle.value, 120, false) || P.crypto.validateText("Body", body(), 1200, true);
      if (bad) { hashOut.textContent = bad; return; }
      hashOut.textContent = await P.crypto.commitDigest({ sponsor: b.sponsor, bountyId: b.id, hunter: me, salt, title: inTitle.value, body: body() });
    }
    [inTitle, inBody].forEach((n) => n.addEventListener("input", updateHash));
    P.wallet.on(() => { updateHash(); drawVault(); if (b) loadBounty(); });

    async function commitFlow(e) {
      if (!(await P.wallet.ready())) return false;
      const me = P.wallet.account.toLowerCase();
      if (me !== e.hunter) { P.toast("This finding belongs to " + shortAddr(e.hunter) + ". Switch your wallet to that account.", "warn"); return false; }
      let bb, ff;
      try { [bb, ff] = await Promise.all([C.views.bounty(e.sponsor, e.bountyId), C.views.findings(e.sponsor, e.bountyId)]); } catch (err) { P.toast(C.cleanErr(err), "err", "Could not read the bounty"); return false; }
      const why = blockReason(bb, ff, me); if (why) { P.toast(why, "warn", "Cannot commit"); return false; }
      const have = await C.views.credit(me);
      if (have < bb.bond) { depositModal(bb.bond - have, () => P.toast("Credit added. Press the commit button again.", "info")); return false; }
      try { await C.write("commit_finding", [e.sponsor, e.bountyId, e.commitment], { title: "Commit finding", hint: "This fixes your place in line. Your text stays hidden until you reveal it.", success: "Your place in line is fixed. Reveal the finding before its deadline." }); }
      catch (err) { return false; }
      let mine = null; try { mine = (await C.views.findings(e.sponsor, e.bountyId)).find((x) => x.commitment === e.commitment && x.hunter === me); } catch (err) {}
      P.vault.patch(e.id, { status: "committed", index: mine ? mine.index : null, revealBy: mine ? mine.revealBy : 0 });
      P.watch.add(e.sponsor, e.bountyId); drawVault();
      return true;
    }

    commitBtn.addEventListener("click", async () => {
      errBox.replaceChildren();
      const errs = [];
      if (!b) errs.push("Load a bounty first.");
      const bad = P.crypto.validateText("Title", inTitle.value, 120, false) || P.crypto.validateText("Body", body(), 1200, true); if (bad) errs.push(bad);
      if (errs.length) { errBox.append(el("div", { class: "callout danger" }, el("ul", null, errs.map((x) => el("li", { text: x }))))); return; }
      if (!(await P.wallet.ready())) return;
      const me = P.wallet.account.toLowerCase();
      commitBtn.classList.add("busy");
      try {
        const commitment = await P.crypto.commitDigest({ sponsor: b.sponsor, bountyId: b.id, hunter: me, salt, title: inTitle.value, body: body() });
        const e = { id: "", sponsor: b.sponsor, bountyId: b.id, hunter: me, salt, title: inTitle.value, body: body(), commitment, status: "draft", index: null, revealBy: 0, createdAt: now() };
        e.id = P.vault.id(e);
        if (!P.vault.put(e)) { errBox.append(el("div", { class: "callout danger" }, el("p", { text: "This browser refused to store the salt, so the commit was not sent. Enable site storage and try again." }))); return; }
        const ok = await commitFlow(e);
        if (ok) { inTitle.value = ""; inBody.value = ""; salt = P.crypto.randomSalt(); inSalt.value = salt; updateHash(); P.confetti(80); loadBounty(); $("#vault").scrollIntoView({ behavior: "smooth" }); }
      } finally { commitBtn.classList.remove("busy"); }
    });

    /* ---------- vault ---------- */
    async function revealEntry(e) {
      if (!(await P.wallet.ready())) return;
      if (P.wallet.account.toLowerCase() !== e.hunter) { P.toast("Switch your wallet to " + shortAddr(e.hunter) + " to reveal this finding.", "warn"); return; }
      let f;
      try {
        let idx = e.index;
        if (idx == null) { const all = await C.views.findings(e.sponsor, e.bountyId); const mine = all.find((x) => x.commitment === e.commitment); if (!mine) throw new Error("This commitment is not on chain yet."); idx = mine.index; P.vault.patch(e.id, { index: idx }); }
        f = await C.views.finding(e.sponsor, e.bountyId, idx);
      } catch (err) { P.toast(C.cleanErr(err), "err", "Could not read the finding"); return; }
      if (f.status !== "committed") { P.vault.patch(e.id, { status: f.status === "revealed" ? "revealed" : "done" }); P.toast("This finding is already " + f.status + ".", "info"); drawVault(); return; }
      if (now() >= f.revealBy) { P.toast("The reveal window has ended. Anyone can now void this commitment and its bond goes to the sponsor.", "err", "Too late"); return; }
      try { await C.write("reveal_finding", [e.sponsor, e.bountyId, BigInt(f.index), e.title, e.body, e.salt], { title: "Reveal finding #" + f.index, success: "Your finding is public and waiting in the queue." }); }
      catch (err) { return; }
      P.vault.patch(e.id, { status: "revealed" }); drawVault();
    }
    async function syncVault() {
      const me = P.wallet.account && P.wallet.account.toLowerCase();
      const list = P.vault.all().filter((e) => e.status === "committed" || e.status === "revealed");
      if (!list.length) { P.toast("Nothing to sync yet.", "info"); return; }
      P.toast("Checking " + list.length + " finding(s) on Studionet.", "info");
      for (const e of list) {
        try {
          let idx = e.index; if (idx == null) { const all = await C.views.findings(e.sponsor, e.bountyId); const m = all.find((x) => x.commitment === e.commitment); if (!m) continue; idx = m.index; }
          const f = await C.views.finding(e.sponsor, e.bountyId, idx);
          P.vault.patch(e.id, { index: idx, revealBy: f.revealBy, status: f.status === "committed" ? "committed" : f.status === "revealed" ? "revealed" : f.status });
        } catch (err) { /* keep local state */ }
      }
      drawVault(); P.toast("Vault is up to date.", "ok");
    }
    $("#vault-sync").addEventListener("click", syncVault);
    $("#vault-export").addEventListener("click", () => {
      const blob = new Blob([P.vault.exportJson()], { type: "application/json" }), a = el("a", { href: URL.createObjectURL(blob), download: "primacy-vault-" + new Date().toISOString().slice(0, 10) + ".json" });
      document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    });
    $("#vault-import").addEventListener("change", async (ev) => {
      const file = ev.target.files[0]; if (!file) return;
      try { const r = await P.vault.importJson(await file.text()); P.toast(r.added + " entr" + (r.added === 1 ? "y" : "ies") + " imported" + (r.skipped ? ", " + r.skipped + " skipped (invalid or already known)" : "") + ".", r.added ? "ok" : "warn"); drawVault(); }
      catch (err) { P.toast("That file is not a Primacy vault export.", "err"); }
      ev.target.value = "";
    });
    function drawVault() {
      const host = $("#vault-list"), me = P.wallet.account && P.wallet.account.toLowerCase();
      let all = P.vault.all().sort((a, c) => c.createdAt - a.createdAt), hidden = 0;
      if (me) { const mine = all.filter((e) => e.hunter === me); hidden = all.length - mine.length; all = mine; }
      host.replaceChildren();
      if (!all.length) host.append(el("div", { class: "panel empty" }, el("p", { text: me ? "No findings from this account yet. Your committed findings and their salts will appear here." : "Connect a wallet to see your findings, or import a backup." })));
      all.forEach((e) => {
        const t = now(), actions = el("div", { class: "row", style: { marginTop: "10px" } });
        if (e.status === "draft") actions.append(el("button", { class: "btn small", onclick: async () => { await commitFlow(e); }, text: "Commit now" }));
        if (e.status === "committed") actions.append(el("button", { class: "btn small mint", onclick: () => revealEntry(e), text: "Reveal now" }));
        actions.append(el("a", { class: "btn small ghost", href: P.bountyUrl(e.sponsor, e.bountyId), text: "Open bounty" }),
          el("button", { class: "btn small ghost", onclick: () => { const m = P.modal([], { label: "Delete" }); m.set([el("h3", { text: "Delete from this browser?" }), el("p", { class: "muted", text: e.status === "committed" ? "This finding is committed on chain. Without its salt and text you can never reveal it, and its bond will be forfeited." : "The saved text and salt will be removed." }), el("div", { class: "row" }, el("button", { class: "btn coral", onclick: () => { P.vault.remove(e.id); m.close(); drawVault(); }, text: "Delete" }), el("button", { class: "btn ghost", onclick: () => m.close(), text: "Keep it" }))]); }, text: "Delete" }));
        host.append(el("article", { class: "ticket s-" + (e.status === "committed" ? "committed" : e.status === "distinct" ? "distinct" : e.status === "duplicate" ? "duplicate" : e.status === "invalid" ? "invalid" : "") },
          el("div", { class: "t-head" }, el("span", { class: "t-no", text: e.index != null ? "#" + e.index : "·" }), el("h4", { text: e.title }), el("span", { class: "chip " + (e.status === "draft" ? "" : e.status), text: e.status === "draft" ? "not committed" : e.status })),
          el("div", { class: "meta-row" }, el("span", null, "Bounty ", el("a", { href: P.bountyUrl(e.sponsor, e.bountyId), text: e.bountyId })), el("span", { class: "mono", title: e.commitment, text: e.commitment.slice(0, 14) + "…" }),
            e.status === "committed" && e.revealBy ? el("span", null, t < e.revealBy ? ["Reveal in ", until(e.revealBy)] : "Reveal window ended") : null),
          actions));
      });
      if (hidden) host.append(el("p", { class: "small muted", text: hidden + " saved finding(s) belong to other addresses and are hidden." }));
    }
    drawVault(); setInterval(() => { /* countdowns live in data-until nodes */ $$("[data-until]").forEach((n) => { const l = Number(n.dataset.until) - now(); n.textContent = l > 0 ? fmtSpan(l) : "now"; }); }, 1000);
  };

  /* ====================================================================
     WALLET / CREDIT
     ==================================================================== */
  pages.wallet = function () {
    const off = $("#w-off"), on = $("#w-on");
    let busy = false;
    async function refresh() {
      if (!P.wallet.connected) { off.classList.remove("hide"); on.classList.add("hide"); return; }
      off.classList.add("hide"); on.classList.remove("hide");
      const a = P.wallet.account;
      $("#w-account").replaceChildren(el("span", { class: "avatar", style: P.avatarStyle(a) + ";display:inline-block;vertical-align:middle;margin-right:8px" }), P.addrChip(a, false));
      ["#w-credit", "#w-native"].forEach((s) => { $(s).textContent = "···"; $(s).classList.add("skeleton"); });
      const [credit, native, acc] = await Promise.all([C.views.credit(a).catch(() => null), C.views.nativeBalance(a), C.views.accounting().catch(() => null)]);
      $("#w-credit").classList.remove("skeleton"); $("#w-native").classList.remove("skeleton");
      $("#w-credit").replaceChildren(credit === null ? "Unavailable" : P.genAmt(credit));
      $("#w-native").replaceChildren(native === null ? "Unavailable" : P.genAmt(native));
      $("#w-withdraw").disabled = !(credit && credit > 0n);
      $("#w-low").classList.toggle("hide", !(native !== null && native < 10n ** 16n));
      const accEl = $("#w-acc");
      accEl.replaceChildren(acc ? el("dl", { class: "kv" }, el("dt", { text: "Credit held for all users" }), el("dd", null, P.genAmt(acc.credits)), el("dt", { text: "Locked in bounties and bonds" }), el("dd", null, P.genAmt(acc.locked)), el("dt", { text: "Contract balance" }), el("dd", null, P.genAmt(acc.balance)), el("dt", { text: "Books balance" }), el("dd", { text: acc.solvent ? "Yes. Balance covers every liability." : "No. Shortfall " + fmtGen(acc.shortfall) + " GEN" })) : el("p", { class: "muted", text: "Contract totals are unavailable right now." }));
      drawActivity();
    }
    function drawActivity() {
      const host = $("#w-activity"), me = P.wallet.account.toLowerCase();
      const mine = P.vault.all().filter((e) => e.hunter === me).sort((x, y) => y.createdAt - x.createdAt).slice(0, 8), watch = P.watch.list().filter((w) => w.s === me).slice(0, 8);
      host.replaceChildren();
      if (!mine.length && !watch.length) { host.append(el("p", { class: "muted", text: "Bounties you create and findings you commit from this browser will be listed here." })); return; }
      if (watch.length) host.append(el("h4", { text: "Bounties you sponsor" }), el("div", { class: "watch" }, watch.map((w) => el("a", { class: "item", href: P.bountyUrl(w.s, w.id) }, el("b", { text: w.id }), el("span", { class: "muted small", text: "Open" })))));
      if (mine.length) host.append(el("h4", { style: { marginTop: "16px" }, text: "Your findings" }), el("div", { class: "watch" }, mine.map((e) => el("a", { class: "item", href: P.bountyUrl(e.sponsor, e.bountyId) }, el("span", null, el("b", { text: e.title }), el("br"), el("span", { class: "small muted", text: "in " + e.bountyId })), el("span", { class: "chip " + (e.status === "draft" ? "" : e.status), text: e.status === "draft" ? "not committed" : e.status })))));
    }
    $$("[data-amt]").forEach((b) => b.addEventListener("click", () => { $("#w-amount").value = b.dataset.amt; }));
    $("#w-deposit").addEventListener("click", async () => {
      const w = parseGen($("#w-amount").value);
      if (!w || w <= 0n) { P.toast("Enter an amount greater than zero, for example 0.5", "warn"); return; }
      if (busy) return; busy = true;
      try { await C.write("deposit_credit", [], { value: w, title: "Deposit " + fmtGen(w) + " GEN", success: "The GEN is now your Primacy credit.", celebrate: true }); await refresh(); } catch (e) {} finally { busy = false; }
    });
    $("#w-withdraw").addEventListener("click", async () => {
      const m = P.modal([], { label: "Withdraw" });
      m.set([el("h3", { text: "Withdraw all credit?" }), el("p", { class: "muted", text: "Your whole available credit is sent to your wallet. Funds locked in bounties or bonds stay locked." }),
        el("div", { class: "row" }, el("button", { class: "btn", onclick: async () => { m.close(); try { await C.write("withdraw_credit", [], { title: "Withdraw credit", success: "Your credit was sent to your wallet.", celebrate: true }); await refresh(); } catch (e) {} }, text: "Withdraw" }), el("button", { class: "btn ghost", onclick: () => m.close(), text: "Cancel" }))]);
    });
    $("#w-faucet").addEventListener("click", async (ev) => {
      const btn = ev.currentTarget, a = P.wallet.account; if (!a) return;
      btn.classList.add("busy");
      try {
        const r = await fetch(CFG.chain.rpc, { method: "POST", headers: { "Content-Type": "application/json" }, body: '{"jsonrpc":"2.0","id":1,"method":"sim_fundAccount","params":["' + a + '",1000000000000000000]}' });
        const d = await r.json(); if (d.error) throw new Error(d.error.message || "The faucet refused the request");
        P.toast("1 test GEN is on its way to " + shortAddr(a) + ".", "ok", "Funded"); setTimeout(refresh, 1500);
      } catch (e) { P.toast(C.cleanErr(e), "err", "Could not fund the account"); } finally { btn.classList.remove("busy"); }
    });
    $("#w-connect").addEventListener("click", () => P.wallet.openPicker());
    P.wallet.on(refresh); refresh();
  };

  /* ====================================================================
     DOCS + REFERENCE (table of contents scroll-spy, copy buttons)
     ==================================================================== */
  function docs() {
    P.enhanceCode(document);
    const links = $$(".toc a[href^='#']"), map = new Map(links.map((a) => [a.getAttribute("href").slice(1), a]));
    const heads = $$(".prose h2[id], .prose h3[id], .prose .method[id]").filter((h) => map.has(h.id));
    if (!("IntersectionObserver" in window) || !heads.length) return;
    const io = new IntersectionObserver((entries) => {
      entries.forEach((en) => { if (en.isIntersecting) { links.forEach((l) => l.classList.remove("on")); const l = map.get(en.target.id); if (l) l.classList.add("on"); } });
    }, { rootMargin: "-90px 0px -70% 0px" });
    heads.forEach((h) => io.observe(h));
  }
  pages.docs = docs; pages.reference = docs;
})();
