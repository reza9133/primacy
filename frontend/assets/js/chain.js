/* Primacy chain layer: contract reads/writes through genlayer-js, transaction tracker,
   commitment hashing (identical to the contract and scripts/primacy_commit.py), hunter vault, watchlist. */
(function () {
  "use strict";
  const P = window.Primacy, CFG = P.CFG, { el, big, store } = P;
  const C = (P.chain = {});

  /* ---------------- clients ---------------- */
  const SDK = () => { if (!window.GenLayerSDK) throw new Error("The GenLayer SDK did not load. Reload the page."); return window.GenLayerSDK; };
  let reader = null, signer = null, signerKey = "";
  const getReader = () => reader || (reader = SDK().createClient({ chain: SDK().studionet }));
  C.resetSigner = () => { signer = null; signerKey = ""; };
  function getSigner() {
    const W = P.wallet;
    if (!W.connected) throw new Error("Connect a wallet first.");
    const key = W.active.info.uuid + ":" + W.account;
    if (!signer || signerKey !== key) { signer = SDK().createClient({ chain: SDK().studionet, account: W.account, provider: W.active.provider }); signerKey = key; }
    return signer;
  }

  /* ---------------- errors ---------------- */
  const errText = (e) => (e && (e.shortMessage || e.message || e.details)) || String(e || "Unknown error");
  C.cleanErr = function (e) {
    if (e && (e.code === 4001 || e.code === "ACTION_REJECTED" || /user (rejected|denied)|rejected the request/i.test(errText(e)))) return "You rejected the request in your wallet.";
    const m = errText(e), x = /\[EXPECTED\]\s*([^\n"\\]+)/.exec(m);
    if (x) return x[1].trim();
    return m.length > 300 ? m.slice(0, 300) + "…" : m;
  };

  /* ---------------- reads ---------------- */
  async function read(fn, args) {
    let last;
    for (let i = 0; i < 3; i++) {
      try { return await getReader().readContract({ address: CFG.contract, functionName: fn, args: args || [] }); }
      catch (e) { last = e; if (/\[EXPECTED\]/.test(errText(e))) break; await P.sleep(900 * (i + 1)); }
    }
    throw last;
  }
  const N = (v) => Number(v), B = big;
  function normBounty(d) {
    return { key: d.key, id: d.bounty_id, sponsor: String(d.sponsor).toLowerCase(), scope: d.scope, reward: B(d.reward_wei), bond: B(d.bond_wei), slots: N(d.slots),
      commitBy: N(d.commit_by), revealWindow: N(d.reveal_window), reviewBy: N(d.review_by), createdAt: N(d.created_at), closedAt: N(d.closed_at),
      escrow: B(d.escrow), heads: N(d.heads), count: N(d.finding_count), cursor: N(d.cursor), status: d.status, closeReason: d.close_reason };
  }
  function normFinding(d) {
    return { index: N(d.index), hunter: String(d.hunter).toLowerCase(), commitment: d.commitment, title: d.title, body: d.body, status: d.status,
      committedAt: N(d.committed_at), revealBy: N(d.reveal_by), revealedAt: N(d.revealed_at), decidedAt: N(d.decided_at), bond: B(d.bond_wei), bondState: d.bond_state,
      reward: B(d.reward_wei), duplicateOf: N(d.duplicate_of), inScope: d.in_scope, actionable: d.actionable, confidence: N(d.confidence), rationale: d.rationale,
      reason: d.reason, attempts: N(d.attempts), failures: N(d.failures), retryAt: N(d.retry_at) };
  }
  C.views = {
    info: () => read("get_info"),
    accounting: async () => { const d = await read("get_accounting"); return { credits: B(d.total_credits), locked: B(d.total_locked), liabilities: B(d.accounted_liabilities), balance: B(d.contract_balance), unallocated: B(d.unallocated_balance), shortfall: B(d.balance_shortfall), solvent: !!d.solvent }; },
    credit: async (a) => B(await read("get_credit", [a])),
    bounty: async (s, id) => normBounty(await read("get_bounty", [s, id])),
    findings: async (s, id) => (await read("get_findings", [s, id])).map(normFinding),
    finding: async (s, id, i) => normFinding(await read("get_finding", [s, id, BigInt(i)])),
    nativeBalance: async (a) => { try { return BigInt(await getReader().request({ method: "eth_getBalance", params: [a, "latest"] })); } catch (e) { return null; } }
  };

  /* ---------------- writes ---------------- */
  const DECIDED = new Set(["ACCEPTED", "UNDETERMINED", "LEADER_TIMEOUT", "VALIDATORS_TIMEOUT", "CANCELED", "FINALIZED"]);
  const BAD = new Set(["UNDETERMINED", "LEADER_TIMEOUT", "VALIDATORS_TIMEOUT", "CANCELED"]);
  const STATUS_TEXT = { PENDING: "Waiting in the queue", ACTIVATED: "Waiting in the queue", PROPOSING: "A leader validator is running the call", COMMITTING: "Validators are voting", REVEALING: "Votes are being revealed", ACCEPTED: "Consensus reached", FINALIZED: "Finalized", UNDETERMINED: "Validators could not agree", LEADER_TIMEOUT: "The leader timed out", VALIDATORS_TIMEOUT: "Validators timed out", CANCELED: "Canceled" };

  /* Studionet can require fee estimates. Ask the node, and pass them only when the policy is on. */
  async function feeOptions(client, fn, args, value) {
    let enabled = false;
    try { const cfg = await client.request({ method: "sim_getFeeConfig", params: [] }); enabled = !!(cfg && cfg.enabled); } catch (e) { enabled = false; }
    if (!enabled) return undefined;
    let est = null;
    if (fn === "withdraw_credit" && client.estimateTransactionFeesForWrite) {
      try { est = await client.estimateTransactionFeesForWrite({ address: CFG.contract, functionName: fn, args, value, account: client.account }); } catch (e) { est = null; }
    }
    if (!est) est = await client.estimateTransactionFees();
    return { distribution: est.distribution, feeValue: est.feeValue, messageAllocations: est.messageAllocations };
  }

  /* Same reading of a receipt as scripts/live_e2e.py: consensus status first, then the leader's execution result. */
  C.interpret = function (tx) {
    const status = tx.statusName || tx.status_name || String(tx.status);
    if (BAD.has(status)) return { ok: false, status, detail: "Consensus ended as " + status + ". Nothing was changed. Wait a moment and try again." };
    const cd = tx.consensus_data || tx.consensusData || {};
    let lr = cd.leader_receipt; if (Array.isArray(lr)) lr = lr[0]; lr = lr || {};
    const result = lr.result && typeof lr.result === "object" ? lr.result : {};
    const genvm = lr.genvm_result && typeof lr.genvm_result === "object" ? lr.genvm_result : {};
    const exec = tx.txExecutionResultName || "";
    const errored = lr.execution_result === "ERROR" || result.status === "rollback" || result.status === "contract_error" || exec === "FINISHED_WITH_ERROR";
    if (errored) {
      const raw = [result.payload, genvm.stderr].filter(Boolean).map((x) => (typeof x === "string" ? x : JSON.stringify(x))).join(" ");
      const m = /\[EXPECTED\]\s*([^\n"\\]+)/.exec(raw);
      return { ok: false, status, detail: (m ? m[1].trim() : raw.trim()) || "The contract rejected the call." };
    }
    return { ok: true, status, detail: "" };
  };

  /* ---------------- transaction tracker (modal) ---------------- */
  function tracker(title, hint) {
    const steps = [{ k: "wallet", t: "Confirm in your wallet" }, { k: "send", t: "Sent to Studionet" }, { k: "consensus", t: "Validators reach consensus" }, { k: "result", t: "Contract result" }];
    const st = { wallet: "idle", send: "idle", consensus: "idle", result: "idle" }, sub = {};
    let mode = "run", hash = null, msg = "", finished = false, closed = false;
    const m = P.modal([], { closable: false, label: title, onClose: () => { closed = true; } });
    function render() {
      const hero = mode === "ok" ? el("div", { class: "tx-hero" }, el("div", { class: "ico", style: { width: "64px", height: "64px", fontSize: "2rem", display: "grid", placeItems: "center", background: "var(--mint)", border: "2px solid var(--ink)", borderRadius: "50%" }, text: "✓" }))
        : mode === "fail" ? el("div", { class: "tx-hero" }, el("div", { style: { width: "64px", height: "64px", fontSize: "2rem", fontWeight: 800, display: "grid", placeItems: "center", background: "var(--coral)", border: "2px solid var(--ink)", borderRadius: "50%" }, text: "!" }))
        : el("div", { class: "tx-hero" }, P.spinner("lg"));
      const list = el("ol", { class: "steps" }, steps.map((s) => el("li", { class: st[s.k] === "idle" ? "" : st[s.k] }, el("span", { class: "dot" }),
        el("span", null, s.t, sub[s.k] ? el("small", { text: sub[s.k] }) : null, s.k === "consensus" && st.consensus === "active" ? el("span", { class: "spin-validators", style: { marginTop: "8px" }, "aria-hidden": "true" }, el("i"), el("i"), el("i"), el("i"), el("i")) : null))));
      m.set([el("h3", { text: mode === "ok" ? "Done" : mode === "fail" ? "That did not go through" : title }), hero, list,
        mode === "run" && hint ? el("div", { class: "tx-note", text: hint }) : null,
        mode === "fail" ? el("div", { class: "tx-fail", text: msg }) : null,
        mode === "ok" && msg ? el("p", { class: "muted", text: msg }) : null,
        el("div", { class: "row between", style: { marginTop: "18px" } },
          hash ? el("a", { class: "small", href: P.explorerTx(hash), target: "_blank", rel: "noopener", text: "View transaction " + P.shortAddr(hash) }) : el("span"),
          el("button", { class: "btn small" + (mode === "run" ? " ghost" : ""), onclick: () => m.close(), text: mode === "run" ? "Hide" : "Close" }))]);
      const x = m.el.querySelector(".x"); if (x) x.remove();
    }
    render();
    return {
      step(k, state, text) { st[k] = state; if (text !== undefined) sub[k] = text; render(); },
      status(name) { sub.consensus = STATUS_TEXT[name] || name; render(); },
      hash(h) { hash = h; render(); },
      ok(text) { finished = true; mode = "ok"; msg = text || ""; st.result = "done"; render(); if (closed) P.toast(text || "Transaction confirmed", "ok", title); },
      fail(text) { finished = true; mode = "fail"; msg = text; if (st.wallet === "active") st.wallet = "fail"; else if (st.consensus === "active") st.consensus = "fail"; else st.result = "fail"; render(); if (closed) P.toast(text, "err", title); },
      close() { m.close(); }, get finished() { return finished; }
    };
  }

  /* write(fn, args, { value, title, hint }) -> { hash, tx } ; throws a readable Error on any failure */
  C.write = async function (fn, args, opts) {
    opts = opts || {};
    if (!(await P.wallet.ready())) throw Object.assign(new Error("Wallet is not ready"), { silent: true });
    const tr = tracker(opts.title || fn, opts.hint);
    try {
      const client = getSigner();
      tr.step("wallet", "active");
      const fees = await feeOptions(client, fn, args, opts.value);
      const req = { address: CFG.contract, functionName: fn, args: args || [], value: opts.value || 0n };
      if (fees) req.fees = fees;
      const hash = await client.writeContract(req);
      tr.hash(hash); tr.step("wallet", "done"); tr.step("send", "done"); tr.step("consensus", "active", "Waiting for the network");
      const deadline = Date.now() + 20 * 60 * 1000; let misses = 0, last = "", tx = null;
      while (Date.now() < deadline) {
        let cur = null;
        try { cur = await client.getTransaction({ hash }); } catch (e) { if (++misses > 40) throw new Error("The network cannot find this transaction yet. Check the explorer for its status."); }
        if (cur) {
          const s = cur.statusName || cur.status_name || String(cur.status);
          if (s !== last) { last = s; tr.status(s); }
          if (DECIDED.has(s)) { tx = cur; break; }
        }
        await P.sleep(2500);
      }
      if (!tx) throw new Error("Validators are taking longer than expected. The transaction may still complete; check the explorer.");
      tr.step("consensus", "done", STATUS_TEXT[last] || last);
      const res = C.interpret(tx);
      if (!res.ok) { tr.step("result", "fail"); throw Object.assign(new Error(res.detail), { hash, shown: true }); }
      tr.ok(opts.success);
      if (opts.celebrate) P.confetti();
      return { hash, tx };
    } catch (e) {
      if (!tr.finished) tr.fail(C.cleanErr(e));
      throw e;
    }
  };

  /* ---------------- commitments ---------------- */
  const enc = new TextEncoder();
  const fieldBytes = (s) => { const b = enc.encode(s); return [enc.encode(b.length + ":"), b, enc.encode(";")]; };
  function forbidden(c) {
    return c < 32 || (c >= 127 && c <= 159) || (c >= 0xD800 && c <= 0xDFFF) || (c >= 0x200B && c <= 0x200F) || (c >= 0x2028 && c <= 0x202E) || (c >= 0x2060 && c <= 0x206F) || c === 0xFEFF || (c >= 0xFFF9 && c <= 0xFFFF);
  }
  /* Mirror of the contract's exact-text rule. Returns an error string, or "" when the text is acceptable. */
  function validateText(label, value, limit, multiline) {
    if (!value) return label + " cannot be empty.";
    if ([...value].length > limit) return label + " is longer than " + limit + " characters.";
    if (value !== value.trim()) return label + " must not start or end with a space or blank line.";
    for (const ch of value) {
      const c = ch.codePointAt(0);
      if (c === 9 || c === 10) { if (multiline) continue; return label + " must be a single line."; }
      if (forbidden(c)) return label + " contains a hidden or control character (U+" + c.toString(16).toUpperCase().padStart(4, "0") + ").";
    }
    return "";
  }
  async function commitDigest(o) {
    const parts = ["primacy/v1", o.sponsor.toLowerCase() + ":" + o.bountyId, o.hunter.toLowerCase(), o.salt, o.title, o.body];
    const chunks = parts.flatMap(fieldBytes);
    const total = chunks.reduce((n, c) => n + c.length, 0), buf = new Uint8Array(total);
    let at = 0; chunks.forEach((c) => { buf.set(c, at); at += c.length; });
    const h = new Uint8Array(await crypto.subtle.digest("SHA-256", buf));
    return "0x" + Array.from(h, (x) => x.toString(16).padStart(2, "0")).join("");
  }
  function randomSalt() { const a = new Uint8Array(16); crypto.getRandomValues(a); return Array.from(a, (x) => x.toString(16).padStart(2, "0")).join(""); }
  P.crypto = { commitDigest, validateText, randomSalt };

  /* ---------------- hunter vault (this browser only) ---------------- */
  const VKEY = "primacy.vault.v1", WKEY = "primacy.watch.v1";
  const vault = (P.vault = {
    all() { const v = store.get(VKEY, []); return Array.isArray(v) ? v : []; },
    id(e) { return [e.sponsor.toLowerCase(), e.bountyId, e.hunter.toLowerCase(), e.commitment.slice(2, 14)].join(":"); },
    put(e) { const list = vault.all().filter((x) => x.id !== e.id); list.push(e); return store.set(VKEY, list); },
    patch(id, patch) { const list = vault.all(); const i = list.findIndex((x) => x.id === id); if (i < 0) return; list[i] = Object.assign({}, list[i], patch); store.set(VKEY, list); },
    remove(id) { store.set(VKEY, vault.all().filter((x) => x.id !== id)); },
    exportJson() { return JSON.stringify({ app: "primacy", version: 1, exportedAt: new Date().toISOString(), entries: vault.all() }, null, 2); },
    async importJson(text) {
      const data = JSON.parse(text); const entries = Array.isArray(data) ? data : data.entries;
      if (!Array.isArray(entries)) throw new Error("This file does not contain vault entries.");
      let added = 0, skipped = 0;
      for (const e of entries) {
        try {
          if (!P.isAddr(e.sponsor) || !P.isAddr(e.hunter) || !P.isBountyId(e.bountyId) || typeof e.salt !== "string" || typeof e.title !== "string" || typeof e.body !== "string") throw 0;
          const d = await commitDigest(e); if (d !== e.commitment) throw 0;
          const entry = { id: "", sponsor: e.sponsor.toLowerCase(), bountyId: e.bountyId, hunter: e.hunter.toLowerCase(), salt: e.salt, title: e.title, body: e.body, commitment: d, status: ["draft", "committed", "revealed"].includes(e.status) ? e.status : "draft", index: Number.isInteger(e.index) ? e.index : null, revealBy: Number(e.revealBy) || 0, createdAt: Number(e.createdAt) || P.now() };
          entry.id = vault.id(entry);
          const old = vault.all().find((x) => x.id === entry.id);
          if (old && old.status !== "draft") { skipped++; continue; }
          vault.put(entry); added++;
        } catch (err) { skipped++; }
      }
      return { added, skipped };
    }
  });
  const watch = (P.watch = {
    list() { const v = store.get(WKEY, []); return Array.isArray(v) ? v : []; },
    add(s, id) { s = s.toLowerCase(); const l = watch.list().filter((x) => !(x.s === s && x.id === id)); l.unshift({ s, id, at: P.now() }); store.set(WKEY, l.slice(0, 30)); },
    remove(s, id) { store.set(WKEY, watch.list().filter((x) => !(x.s === s.toLowerCase() && x.id === id))); }
  });
  P.bountyUrl = (s, id) => "bounty.html?s=" + encodeURIComponent(s) + "&id=" + encodeURIComponent(id);
})();
