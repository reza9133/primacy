# Primacy frontend

A multi-page, static website for the Primacy contract on GenLayer Studionet. No server and no build step are needed to run it.

| | |
|---|---|
| Contract | `0xf49Fca785788a2a3881c593F33B2E20113FD99e1` |
| Network | GenLayer Studionet, chain id 61999, RPC `https://studio.genlayer.com/api` |
| Explorer | https://explorer-studio.genlayer.com/address/0xf49Fca785788a2a3881c593F33B2E20113FD99e1 |
| Repository | https://github.com/reza9133/primacy/ |
| Author on X | https://x.com/amirhp771 |

## Pages

| File | Purpose |
|---|---|
| `index.html` | Landing page with live contract totals |
| `explore.html` | Open a bounty by sponsor and id, your list, live examples |
| `bounty.html` | Bounty detail: scope, timeline, queue, reveal, review, void, close, cancel |
| `create.html` | Create a bounty |
| `hunt.html` | Commit a finding, local vault with reveal, sync, export and import |
| `wallet.html` | My credit: deposit, withdraw, test GEN, contract accounting |
| `demo.html` | Interactive guided demo (simulation, no wallet needed) |
| `docs.html` | Full documentation |
| `reference.html` | Contract API reference |

## Run locally

```bash
cd frontend
python3 -m http.server 8080
# open http://localhost:8080
```

Serve over `http://localhost` or `https`. Wallet extensions do not inject into `file://` pages.

## Wallets

Wallets are discovered with EIP-6963 (`eip6963:announceProvider` / `eip6963:requestProvider`), with `window.ethereum` as a labelled fallback. Connect uses `eth_requestAccounts`. Disconnect drops the session, removes the provider listeners, forgets the remembered wallet and asks the wallet to revoke access with `wallet_revokePermissions` where supported. When the wallet is not on Studionet the site shows a banner and a dialog, then calls `wallet_switchEthereumChain` and falls back to `wallet_addEthereumChain`.

## Configuration

Everything that may change is in `assets/js/config.js`: the contract address, chain parameters, links and the example bounties. The explorer transaction link is `explorer + txPath + hash`; change `txPath` if the explorer uses another pattern.

## Layout

```
frontend/
  *.html                  pages
  favicon.svg
  assets/css/style.css    all styles
  assets/js/config.js     contract address, chain, links
  assets/js/core.js       helpers, layout, EIP-6963 wallet
  assets/js/chain.js      reads, writes, tx tracker, commitment hash, vault
  assets/js/pages.js      home, explore, bounty, create
  assets/js/pages2.js     hunt, credit, docs helpers
  assets/js/demo.js       interactive demo
  assets/js/genlayer-sdk.js   bundled genlayer-js (built from tools/)
  assets/brand/           Primacy logo files and GenLayer media kit assets
  assets/fonts/           self-hosted Bricolage Grotesque, Instrument Sans, Red Hat Mono
  tools/                  rebuilds the SDK bundle
```

## Rebuild the SDK bundle

```bash
cd frontend/tools
npm install
npm run build
```

## Deploy to GitHub Pages

`.github/workflows/pages.yml` publishes the `frontend` folder. In the repository settings choose Pages, then Source: GitHub Actions, and push to `main`.

## Notes

* Commitment hashing in `chain.js` is the same algorithm as `scripts/primacy_commit.py` and was verified to produce identical digests.
* Text from the chain (scopes, titles, bodies, rationales) is always rendered as plain text, never as HTML.
* The vault (salts and finding text) is kept in this browser's local storage. Use Export to back it up.
* Brand assets for GenLayer come from the official media kit. Follow its usage guidelines.
