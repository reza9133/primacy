/* Primacy core: helpers, UI kit, shared layout, EIP-6963 wallet. No dependencies. */
(function () {
  "use strict";
  const CFG = window.PRIMACY;
  const P = (window.Primacy = window.Primacy || {});
  P.CFG = CFG;

  /* ---------------- tiny DOM kit ---------------- */
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  function el(tag, props, ...kids) {
    const n = document.createElement(tag);
    if (props) for (const k in props) {
      const v = props[k];
      if (v == null || v === false) continue;
      if (k === "class") n.className = v;
      else if (k === "text") n.textContent = v;
      else if (k === "html") n.innerHTML = v; /* only ever used with trusted, static strings */
      else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v);
      else if (k === "style" && typeof v === "object") Object.assign(n.style, v);
      else n.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) {
      if (kid == null || kid === false) continue;
      n.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    }
    return n;
  }
  P.$ = $; P.$$ = $$; P.el = el;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  P.sleep = sleep;

  /* ---------------- storage ---------------- */
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch (e) { return false; } },
    del(k) { try { localStorage.removeItem(k); } catch (e) {} }
  };
  P.store = store;

  /* ---------------- numbers, units, time ---------------- */
  const WEI = 10n ** 18n;
  function big(v) {
    if (typeof v === "bigint") return v;
    if (typeof v === "number") return BigInt(Math.trunc(v));
    if (typeof v === "string" && /^-?\d+$/.test(v.trim())) return BigInt(v.trim());
    return 0n;
  }
  function fmtGen(wei, max) {
    max = max == null ? 6 : max;
    const w = big(wei);
    const neg = w < 0n; const a = neg ? -w : w;
    const whole = a / WEI;
    let frac = (a % WEI).toString().padStart(18, "0").slice(0, max).replace(/0+$/, "");
    if (a > 0n && whole === 0n && frac === "") return (neg ? "-" : "") + "<" + (1 / 10 ** max).toFixed(max);
    return (neg ? "-" : "") + whole.toLocaleString("en-US") + (frac ? "." + frac : "");
  }
  function parseGen(str) {
    const s = String(str == null ? "" : str).trim().replace(",", ".");
    if (!/^\d+(\.\d{1,18})?$/.test(s)) return null;
    const [w, f = ""] = s.split(".");
    return BigInt(w) * WEI + BigInt(f.padEnd(18, "0"));
  }
  const now = () => Math.floor(Date.now() / 1000);
  function fmtDate(ts) {
    ts = Number(ts);
    if (!ts) return "n/a";
    return new Date(ts * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  }
  function fmtSpan(sec) {
    sec = Math.max(0, Math.round(Number(sec)));
    const d = Math.floor(sec / 86400), h = Math.floor((sec % 86400) / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
    if (d) return d + "d " + h + "h";
    if (h) return h + "h " + m + "m";
    if (m) return m + "m " + (s ? s + "s" : "");
    return s + "s";
  }
  const shortAddr = (a) => (a ? a.slice(0, 6) + "…" + a.slice(-4) : "");
  const isAddr = (a) => /^0x[0-9a-fA-F]{40}$/.test(String(a || ""));
  const isBountyId = (s) => /^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/.test(String(s || ""));
  Object.assign(P, { big, fmtGen, parseGen, now, fmtDate, fmtSpan, shortAddr, isAddr, isBountyId, WEI });

  async function copy(text, msg) {
    try { await navigator.clipboard.writeText(text); }
    catch (e) {
      const t = el("textarea", { style: { position: "fixed", opacity: 0 } }); t.value = text; document.body.append(t); t.select();
      try { document.execCommand("copy"); } catch (e2) {} t.remove();
    }
    toast(msg || "Copied to clipboard", "ok");
  }
  P.copy = copy;

  /* ---------------- toasts ---------------- */
  let toastBox;
  function toast(msg, kind, title, ms) {
    if (!toastBox) { toastBox = el("div", { class: "toasts", "aria-live": "polite" }); document.body.append(toastBox); }
    const icon = { ok: "✓", err: "!", warn: "!", info: "i" }[kind || "ok"] || "✓";
    const t = el("div", { class: "toast " + (kind || "ok"), role: "status" },
      el("span", { class: "ico", text: icon }),
      el("div", null, title ? el("b", { text: title }) : null, el("span", { text: msg })),
      el("button", { "aria-label": "Dismiss", text: "×", onclick: () => t.remove() }));
    toastBox.append(t);
    setTimeout(() => t.remove(), ms || (kind === "err" ? 8000 : 4500));
    return t;
  }
  P.toast = toast;

  /* ---------------- modal ---------------- */
  function modal(content, opts) {
    opts = opts || {};
    const prev = document.activeElement;
    const box = el("div", { class: "modal" + (opts.wide ? " wide" : ""), role: "dialog", "aria-modal": "true", "aria-label": opts.label || "Dialog" });
    const ov = el("div", { class: "overlay" }, box);
    const api = {
      el: box,
      close() { ov.remove(); document.removeEventListener("keydown", onKey); if (prev && prev.focus) prev.focus(); if (opts.onClose) opts.onClose(); },
      set(c) { box.replaceChildren(); if (opts.closable !== false) box.append(el("button", { class: "x", "aria-label": "Close", text: "×", onclick: api.close })); box.append(...[].concat(c)); }
    };
    function onKey(e) { if (e.key === "Escape" && opts.closable !== false) api.close(); }
    document.addEventListener("keydown", onKey);
    ov.addEventListener("mousedown", (e) => { if (e.target === ov && opts.closable !== false) api.close(); });
    api.set(content);
    document.body.append(ov);
    const f = box.querySelector("button, input, a"); if (f) f.focus();
    return api;
  }
  P.modal = modal;

  /* ---------------- confetti ---------------- */
  function confetti(n) {
    if (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const c = el("canvas", { class: "confetti", "aria-hidden": "true" });
    document.body.append(c);
    const ctx = c.getContext("2d"); if (!ctx) { c.remove(); return; }
    const dpr = window.devicePixelRatio || 1; const W = (c.width = innerWidth * dpr), H = (c.height = innerHeight * dpr);
    const colors = ["#FFC933", "#110FFF", "#FF6A5C", "#14C79A", "#9A7BFF", "#4CC3FF"];
    const ps = Array.from({ length: n || 140 }, () => ({
      x: W / 2 + (Math.random() - .5) * W * .3, y: H * .35, vx: (Math.random() - .5) * 16 * dpr, vy: (-Math.random() * 14 - 4) * dpr,
      w: (6 + Math.random() * 7) * dpr, h: (4 + Math.random() * 5) * dpr, r: Math.random() * 6, vr: (Math.random() - .5) * .4, c: colors[(Math.random() * colors.length) | 0]
    }));
    let f = 0;
    (function tick() {
      ctx.clearRect(0, 0, W, H);
      ps.forEach((p) => { p.vy += .35 * dpr; p.x += p.vx; p.y += p.vy; p.r += p.vr; ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.r); ctx.fillStyle = p.c; ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h); ctx.restore(); });
      if (++f < 150) requestAnimationFrame(tick); else c.remove();
    })();
  }
  P.confetti = confetti;

  /* ---------------- misc UI helpers ---------------- */
  P.explorerAddr = (a) => CFG.chain.explorer + "/address/" + a;
  P.explorerTx = (h) => CFG.chain.explorer + (CFG.chain.txPath || "/tx/") + h;
  function addrChip(a, short) {
    return el("a", { class: "addr", href: P.explorerAddr(a), target: "_blank", rel: "noopener", title: a, text: short === false ? a : shortAddr(a) });
  }
  function genAmt(wei, max) {
    return el("span", { class: "gen" }, el("img", { src: "assets/brand/gen-token.svg", alt: "", width: 16, height: 16 }), fmtGen(wei, max), " GEN");
  }
  function chip(status) { return el("span", { class: "chip " + status, text: status }); }
  function spinner(size) { return el("span", { class: "spin-orbit" + (size ? " " + size : ""), role: "status", "aria-label": "Loading" }, el("i"), el("i"), el("i")); }
  function avatarStyle(addr) {
    const h = parseInt((addr || "0x0").slice(2, 8), 16) || 0, h2 = parseInt((addr || "0x0").slice(-6), 16) || 0;
    return "background:linear-gradient(135deg,hsl(" + (h % 360) + " 85% 62%),hsl(" + (h2 % 360) + " 85% 55%))";
  }
  Object.assign(P, { addrChip, genAmt, chip, spinner, avatarStyle });

  /* =====================================================================
     Wallet: EIP-6963 discovery, connect, disconnect, network switch
     ===================================================================== */
  const W = (P.wallet = {
    found: new Map(),   /* uuid -> { info, provider } */
    active: null,       /* { info, provider } */
    account: null,
    chainId: null,      /* number */
    subs: new Set(),
    on(fn) { W.subs.add(fn); return () => W.subs.delete(fn); },
    emit() { W.subs.forEach((f) => { try { f(W); } catch (e) { console.error(e); } }); },
    get connected() { return !!(W.active && W.account); },
    get onChain() { return W.chainId === CFG.chain.id; }
  });
  const KEY = "primacy.wallet.v1";
  let handlers = null;

  function announce(e) {
    const d = e && e.detail;
    if (!d || !d.info || !d.provider || !d.info.uuid) return;
    W.found.set(d.info.uuid, { info: d.info, provider: d.provider });
    W.emit();
  }
  W.discover = function () {
    window.addEventListener("eip6963:announceProvider", announce);
    window.dispatchEvent(new Event("eip6963:requestProvider"));
  };
  /* Wallets that predate EIP-6963 only expose window.ethereum. Offer it as a fallback. */
  W.list = function () {
    const out = Array.from(W.found.values());
    if (!out.length && window.ethereum) {
      out.push({ info: { uuid: "legacy", name: window.ethereum.isMetaMask ? "MetaMask" : "Browser wallet", icon: "", rdns: "legacy.injected" }, provider: window.ethereum });
    }
    return out;
  };
  const hexToNum = (h) => (typeof h === "string" ? parseInt(h, 16) : Number(h));

  function detach() {
    if (handlers && W.active) {
      const p = W.active.provider;
      const off = p.removeListener || p.off;
      if (off) { try { off.call(p, "accountsChanged", handlers.acc); off.call(p, "chainChanged", handlers.chain); off.call(p, "disconnect", handlers.disc); } catch (e) {} }
    }
    handlers = null;
  }
  function attach(entry, account, chainId) {
    detach();
    W.active = entry; W.account = account; W.chainId = chainId;
    handlers = {
      acc: (accs) => { if (!accs || !accs.length) softClear(); else { W.account = accs[0]; P.chain && P.chain.resetSigner && P.chain.resetSigner(); W.emit(); } },
      chain: (id) => { W.chainId = hexToNum(id); W.emit(); },
      disc: () => softClear()
    };
    const p = entry.provider; if (p.on) { p.on("accountsChanged", handlers.acc); p.on("chainChanged", handlers.chain); p.on("disconnect", handlers.disc); }
    store.set(KEY, entry.info.rdns || entry.info.uuid);
    P.chain && P.chain.resetSigner && P.chain.resetSigner();
    W.emit();
  }
  function softClear() {
    detach(); W.active = null; W.account = null; W.chainId = null; P.chain && P.chain.resetSigner && P.chain.resetSigner(); W.emit();
  }

  W.connect = async function (entry) {
    const p = entry.provider;
    let accounts;
    try { accounts = await p.request({ method: "eth_requestAccounts" }); }
    catch (e) { throw new Error(e && e.code === 4001 ? "You closed the wallet request." : (e && e.message) || "Wallet connection failed"); }
    if (!accounts || !accounts.length) throw new Error("The wallet returned no accounts.");
    let chainId = null;
    try { chainId = hexToNum(await p.request({ method: "eth_chainId" })); } catch (e) {}
    attach(entry, accounts[0], chainId);
    if (!W.onChain) await W.promptSwitch(true);
    return W.account;
  };

  /* Real disconnect: drop listeners and state, forget the wallet, and ask the wallet to revoke site access. */
  W.disconnect = async function () {
    const entry = W.active;
    softClear(); store.del(KEY);
    if (entry) { try { await entry.provider.request({ method: "wallet_revokePermissions", params: [{ eth_accounts: {} }] }); } catch (e) { /* not every wallet supports it */ } }
    toast("Your wallet is disconnected from Primacy.", "info", "Disconnected");
  };

  W.switchChain = async function () {
    if (!W.active) throw new Error("Connect a wallet first.");
    const p = W.active.provider, c = CFG.chain;
    try {
      await p.request({ method: "wallet_switchEthereumChain", params: [{ chainId: c.hex }] });
    } catch (e) {
      const unknown = e && (e.code === 4902 || e.code === -32603 || /unrecognized chain|not been added|unknown chain|add.*chain/i.test(e.message || ""));
      if (!unknown) throw e;
      await p.request({ method: "wallet_addEthereumChain", params: [{
        chainId: c.hex, chainName: c.name, rpcUrls: [c.rpc], blockExplorerUrls: [c.explorer],
        nativeCurrency: { name: "GEN Token", symbol: c.symbol, decimals: c.decimals } }] });
    }
    try { W.chainId = hexToNum(await p.request({ method: "eth_chainId" })); } catch (e) {}
    W.emit();
  };

  /* Shows a message explaining the switch, then asks the wallet to do it. */
  W.promptSwitch = function (auto) {
    return new Promise((resolve) => {
      let working = false;
      const m = modal([], { label: "Switch network", onClose: () => resolve(W.onChain) });
      const body = () => {
        const wrong = W.chainId ? "chain " + W.chainId : "an unknown network";
        m.set([
          el("h3", { text: "Switch to " + CFG.chain.name }),
          el("p", { class: "muted", text: "Your wallet is on " + wrong + ". Primacy runs on " + CFG.chain.name + " (chain id " + CFG.chain.id + "), so transactions can only be sent from there." }),
          el("div", { class: "tx-note", text: working ? "Check your wallet and approve the network switch." : "Your wallet will ask you to approve the switch. If the network is missing, it will offer to add it first." }),
          el("div", { class: "row", style: { marginTop: "18px" } },
            el("button", { class: "btn" + (working ? " busy" : ""), onclick: go, text: working ? "Waiting for your wallet" : "Switch network" }),
            el("button", { class: "btn ghost", onclick: () => m.close(), text: "Not now" }))
        ]);
      };
      async function go() {
        working = true; body();
        try { await W.switchChain(); toast("You are now on " + CFG.chain.name + ".", "ok", "Network switched"); m.close(); }
        catch (e) { working = false; body(); toast(e && e.code === 4001 ? "The switch was declined. You can retry from the yellow banner." : ((e && e.message) || "Could not switch network"), "warn", "Still on the wrong network"); }
      }
      body();
      if (auto) setTimeout(go, 350);
    });
  };

  W.openPicker = function () {
    const list = W.list();
    const body = [el("h3", { text: "Connect a wallet" }),
      el("p", { class: "muted", text: "Pick one of the wallets found in this browser. Primacy discovers them with EIP-6963, so each wallet announces itself." })];
    const m = modal([], { label: "Connect wallet" });
    const listEl = el("div", { class: "wallet-list" });
    if (!list.length) {
      listEl.append(el("div", { class: "empty" }, el("div", { class: "ph", text: "🦊", style: { fontSize: "2rem" } }),
        el("p", { text: "No wallet was found in this browser." }),
        el("p", { class: "small muted" }, "Install an EIP-6963 wallet such as ", el("a", { href: "https://metamask.io/download/", target: "_blank", rel: "noopener", text: "MetaMask" }), " or ", el("a", { href: "https://rabby.io", target: "_blank", rel: "noopener", text: "Rabby" }), ", then reload this page.")));
    }
    list.forEach((entry) => {
      const icon = entry.info.icon && /^data:image\//.test(entry.info.icon) ? el("img", { src: entry.info.icon, alt: "" }) : el("span", { class: "ph", text: "👛" });
      const b = el("button", { class: "wallet-opt", onclick: async () => {
        b.classList.add("busy"); b.disabled = true;
        try { await W.connect(entry); m.close(); toast(shortAddr(W.account) + " is connected.", "ok", "Wallet connected"); }
        catch (e) { b.classList.remove("busy"); b.disabled = false; toast(e.message, "err", "Could not connect"); }
      } }, icon, el("span", null, entry.info.name, el("small", { text: entry.info.rdns || "" })));
      listEl.append(b);
    });
    m.set([...body, listEl, el("p", { class: "small muted", text: "Primacy never sees your keys. Every transaction is confirmed inside your wallet." })]);
  };

  /* Restore the previous session quietly (no popup) if the wallet still allows this site. */
  W.restore = async function () {
    const saved = store.get(KEY, null); if (!saved) return;
    await sleep(350);
    const entry = W.list().find((e) => (e.info.rdns || e.info.uuid) === saved);
    if (!entry) return;
    try {
      const accs = await entry.provider.request({ method: "eth_accounts" });
      if (accs && accs.length) { attach(entry, accs[0], hexToNum(await entry.provider.request({ method: "eth_chainId" }))); }
      else store.del(KEY);
    } catch (e) { /* ignore */ }
  };

  /* A write needs: connected + right network. Returns true when ready. */
  W.ready = async function () {
    if (!W.connected) { W.openPicker(); return false; }
    if (!W.onChain) { const ok = await W.promptSwitch(false); return !!ok && W.onChain; }
    return true;
  };

  /* =====================================================================
     Shared layout: header, network banner, footer
     ===================================================================== */
  const NAV = [["index.html", "Home", "home"], ["explore.html", "Bounties", "explore"], ["create.html", "Create", "create"], ["hunt.html", "Hunt", "hunt"], ["wallet.html", "My credit", "wallet"], ["demo.html", "Demo", "demo"], ["docs.html", "Docs", "docs"]];

  function buildHeader(page) {
    const host = $("#app-header"); if (!host) return;
    const nav = el("nav", { class: "nav", id: "nav", "aria-label": "Main" }, NAV.map(([href, label, key]) =>
      el("a", { href, text: label, "aria-current": key === page || (page === "reference" && key === "docs") || (page === "bounty" && key === "explore") ? "page" : null })));
    const right = el("div", { class: "head-right" });
    const burger = el("button", { class: "burger", "aria-label": "Menu", "aria-controls": "nav", "aria-expanded": "false", onclick: () => { const o = nav.classList.toggle("open"); burger.setAttribute("aria-expanded", o); } }, el("span"), el("span"), el("span"));
    const header = el("header", { class: "site-header" }, el("div", { class: "wrap" },
      el("a", { class: "brand", href: "index.html", "aria-label": "Primacy home" }, el("img", { src: "assets/brand/primacy-logo.svg", alt: "Primacy", width: 120, height: 34 })),
      nav, right, burger));
    const banner = el("div", { class: "net-banner hide", id: "net-banner", role: "alert" });
    host.replaceWith(header, banner);

    let menuOpen = false;
    document.addEventListener("click", (e) => { if (menuOpen && !e.target.closest(".acct")) { menuOpen = false; render(); } });
    function render() {
      right.replaceChildren();
      if (!W.connected) {
        right.append(el("button", { class: "btn small", onclick: () => W.openPicker(), text: "Connect wallet" }));
        banner.classList.add("hide"); return;
      }
      const ok = W.onChain;
      right.append(el("button", { class: "net-pill " + (ok ? "ok" : "bad"), title: ok ? CFG.chain.name : "Switch to " + CFG.chain.name, onclick: () => { if (!ok) W.promptSwitch(false); } },
        el("i"), el("span", { class: "lbl", text: ok ? "Studionet" : "Wrong network" })));
      const acct = el("div", { class: "acct" });
      const btn = el("button", { class: "acct-btn", "aria-haspopup": "menu", "aria-expanded": String(menuOpen), onclick: (e) => { e.stopPropagation(); menuOpen = !menuOpen; render(); } },
        el("span", { class: "avatar", style: avatarStyle(W.account) }), el("span", { class: "nm", text: shortAddr(W.account) }));
      acct.append(btn);
      if (menuOpen) {
        acct.append(el("div", { class: "menu", role: "menu" },
          el("div", { class: "who", text: (W.active.info.name || "Wallet") + " connected" }),
          el("button", { role: "menuitem", onclick: () => { copy(W.account, "Address copied"); } }, "Copy address"),
          el("a", { role: "menuitem", href: P.explorerAddr(W.account), target: "_blank", rel: "noopener" }, "View on explorer"),
          el("a", { role: "menuitem", href: "wallet.html" }, "My credit"),
          ok ? null : el("button", { role: "menuitem", onclick: () => { menuOpen = false; render(); W.promptSwitch(false); } }, "Switch to Studionet"),
          el("div", { class: "sep" }),
          el("button", { role: "menuitem", class: "danger", onclick: () => { menuOpen = false; W.disconnect(); } }, "Disconnect")));
      }
      right.append(acct);
      if (!ok) {
        banner.classList.remove("hide");
        banner.replaceChildren(el("div", { class: "wrap" },
          el("strong", { text: "Wrong network." }),
          el("span", { class: "grow", text: "Your wallet is on " + (W.chainId ? "chain " + W.chainId : "another network") + ". Switch to " + CFG.chain.name + " (chain id " + CFG.chain.id + ") to send transactions." }),
          el("button", { class: "btn small", onclick: () => W.promptSwitch(false), text: "Switch network" })));
      } else banner.classList.add("hide");
    }
    W.on(render); render();
  }

  function buildFooter() {
    const host = $("#app-footer"); if (!host) return;
    const L = CFG.links;
    const col = (title, links) => el("div", null, el("h4", { text: title }), links.map(([t, h, ext]) => el("a", { href: h, text: t, target: ext ? "_blank" : null, rel: ext ? "noopener" : null })));
    host.replaceWith(el("footer", { class: "site-footer" }, el("div", { class: "wrap" },
      el("div", { class: "foot-grid" },
        el("div", null,
          el("a", { class: "brand", href: "index.html" }, el("img", { src: "assets/brand/primacy-logo-white.svg", alt: "Primacy", width: 120, height: 34 })),
          el("p", { style: { marginTop: "14px", maxWidth: "30ch" }, text: "First-finder rewards with duplicate judgement by GenLayer validators." }),
          el("div", { class: "foot-gl" }, el("span", { text: "Built on" }), el("a", { href: L.genlayer, target: "_blank", rel: "noopener", "aria-label": "GenLayer" }, el("img", { src: "assets/brand/genlayer-logo-white.svg", alt: "GenLayer", height: 22 })))),
        col("Use Primacy", [["Browse bounties", "explore.html"], ["Create a bounty", "create.html"], ["Hunt for findings", "hunt.html"], ["My credit", "wallet.html"], ["Interactive demo", "demo.html"]]),
        col("Learn", [["Documentation", "docs.html"], ["Contract reference", "reference.html"], ["How decisions are made", "docs.html#decisions"], ["FAQ", "docs.html#faq"], ["GenLayer docs", L.genlayerDocs, 1]]),
        col("Project", [["GitHub", L.github, 1], ["X " + L.xHandle, L.x, 1], ["Contract on explorer", CFG.explorerAddress, 1], ["Deployment transaction", P.explorerTx(CFG.deployTx), 1]])),
      el("div", { class: "foot-bottom" },
        el("span", null, "Primacy v" + CFG.version + " on " + CFG.chain.name + ". Test network, test funds."),
        el("span", null, "Contract ", el("a", { class: "addr", style: { display: "inline-block", color: "#15143B" }, href: CFG.explorerAddress, target: "_blank", rel: "noopener", text: shortAddr(CFG.contract) }))))));
  }

  /* first-visit loader (created by script, so a broken script can never leave a blank page) */
  function loader() {
    if (sessionStorage.getItem("primacy.seen")) return;
    try { sessionStorage.setItem("primacy.seen", "1"); } catch (e) { return; }
    const l = el("div", { class: "page-loader", "aria-hidden": "true" }, el("span", { class: "spin-orbit lg" }, el("i"), el("i"), el("i")));
    document.body.append(l);
    const done = () => { l.classList.add("gone"); setTimeout(() => l.remove(), 500); };
    setTimeout(done, 650);
  }

  /* copy buttons on code blocks (docs) */
  P.enhanceCode = function (root) {
    $$("pre", root).forEach((pre) => {
      if (pre.querySelector(".copy-btn")) return;
      pre.append(el("button", { class: "copy-btn", type: "button", text: "Copy", onclick: (e) => { const code = pre.querySelector("code"); copy((code || pre).textContent, "Code copied"); e.target.textContent = "Copied"; setTimeout(() => (e.target.textContent = "Copy"), 1400); } }));
    });
  };

  P.boot = function (fn) {
    const run = () => {
      const page = document.body.dataset.page || "";
      loader();
      buildHeader(page); buildFooter();
      W.discover(); W.restore();
      if (fn) fn(page);
    };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run); else run();
  };
})();
