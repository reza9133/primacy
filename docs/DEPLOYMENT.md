# Deploying Primacy to GenLayer Studionet

## Before you deploy

1. Everything passes locally: `python scripts/run_report.py --no-live`.
2. The committed ABI is current. `run_report.py` compares `artifacts/primacy.abi.json` with the schema generated
   from the contract and fails on drift. To regenerate it after a contract change, run
   `genvm-lint schema contracts/primacy.py --output artifacts/primacy.abi.json`.
3. Optional but recommended: a live run, `python scripts/run_report.py --skip-tests --fast`
   (see [LIVE_E2E.md](LIVE_E2E.md)).

## Deploy

```bash
python scripts/deploy.py
```

With no key set, the script creates a throwaway account and asks Studionet to fund it. To deploy from an account you
control:

```bash
export PRIMACY_DEPLOYER_KEY=0xYOUR_PRIVATE_KEY
python scripts/deploy.py
```

| Option | Meaning |
|---|---|
| `--rpc URL` | Endpoint. Also `PRIMACY_RPC_URL`. Default `https://studio.genlayer.com/api` |
| `--network NAME` | Label for the output file name. Default `studionet` |
| `--timeout SECONDS` | How long to wait for the deployment. Default 600 |
| `--out DIR` | Directory for the record. Default `deployments/` |

The script waits for the deployment to be decided, verifies that `get_info` answers, and writes
`deployments/<network>.json`:

```json
{
  "network": "studionet",
  "rpc": "https://studio.genlayer.com/api",
  "contract": "0x…",
  "transaction": "0x…",
  "deployer": "0x…",
  "contract_sha256": "…",
  "version": "0.1.0",
  "deployed_utc": "…"
}
```

`contract_sha256` is the hash of `contracts/primacy.py` at deployment time, so you can later prove which source a
deployed address runs.

Exit status: 0 deployed and verified, 1 the deployment or verification failed, 2 it could not start (missing
dependency, unreachable endpoint, or no funded account).

## About the deployer

The contract has no owner, no administrator and no constructor arguments. The deploying account has no special
rights afterwards. There is no upgrade path: a new version is a new contract at a new address. Existing bounties
stay on the old one.

## Using the deployed contract

* Read methods need no funds. Write methods need an account with GEN for fees.
* To sponsor a bounty: `deposit_credit()` with value, then `create_bounty(...)`. The three deadlines are absolute
  Unix timestamps in seconds; see the constraints in the README.
* To hunt: build a commitment with `scripts/primacy_commit.py`, `deposit_credit()` at least the bond, then
  `commit_finding`, and later `reveal_finding`.
* Anyone may drive a bounty forward with `adjudicate`, `void_unrevealed` and `close_bounty`.
* Always fund the contract with `deposit_credit()`. A plain transfer to the contract address is not credited.

### Choosing sponsor parameters

| Parameter | Guidance |
|---|---|
| `bond_wei` | 5–10 % of `reward_wei` or more. A trivial bond lets one party fill the 32-finding queue cheaply. |
| `commit_by` | As short as the audience allows. It bounds how long the queue can be filled. |
| `reveal_window` | Long enough for a hunter to notice the commit confirmed and reveal; an hour or more on a busy network. |
| `review_by` | Leaves time for adjudication of up to 32 findings, including cooldowns after inconclusive answers. A few days is typical. |
| `scope_text` | Say what is in scope and what is explicitly out. Validators judge against exactly this text. |

## Troubleshooting

| Symptom | Cause |
|---|---|
| `could not fund a throwaway deployer` | The endpoint does not offer `sim_fundAccount` (or is not a Studio endpoint). Set `PRIMACY_DEPLOYER_KEY` to a funded account. |
| `missing dependency` | Run `pip install -r requirements.txt` |
| `deployment did not produce a contract` | The contract failed to initialize; the message includes the validators' output. Run the linter: `genvm-lint check contracts/primacy.py` |
| `get_info failed` after a successful deployment | The network has not finished indexing the new contract. Wait a few seconds and read `get_info` yourself with the address from the message. |
