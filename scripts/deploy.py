#!/usr/bin/env python3
"""Deploy contracts/primacy.py to GenLayer Studionet and record the address.

    python scripts/deploy.py                          # throwaway deployer, funded by the network
    PRIMACY_DEPLOYER_KEY=0x... python scripts/deploy.py   # deploy from your own account

The contract has no owner and no constructor arguments, so the deploying account has no special rights.
The address and transaction are written to deployments/<network>.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT_RPC = "https://studio.genlayer.com/api"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Deploy Primacy to GenLayer Studionet.")
    parser.add_argument("--rpc", default=os.environ.get("PRIMACY_RPC_URL", DEFAULT_RPC))
    parser.add_argument("--network", default="studionet", help="label used for the output file name")
    parser.add_argument("--timeout", type=int, default=600, help="seconds to wait for the deployment")
    parser.add_argument("--out", default=str(ROOT / "deployments"))
    args = parser.parse_args(argv)

    try:
        import dataclasses

        import requests
        from genlayer_py import create_account, create_client
        from genlayer_py.chains import studionet
        from web3 import Web3
    except ImportError as exc:
        print(f"missing dependency ({exc}); run: pip install -r requirements.txt", file=sys.stderr)
        return 2

    chain = dataclasses.replace(studionet, rpc_urls={"default": {"http": [args.rpc]}})

    key = os.environ.get("PRIMACY_DEPLOYER_KEY", "").strip()
    account = create_account(key) if key else create_account()
    # read_contract uses the client's default account, so the client is built with it.
    client = create_client(chain=chain, endpoint=args.rpc, account=account)
    if not key:
        try:
            reply = requests.post(args.rpc, json={"jsonrpc": "2.0", "id": 1, "method": "sim_fundAccount",
                                                   "params": [account.address, 10**18]}, timeout=40).json()
            if reply.get("error") or "result" not in reply:
                raise RuntimeError(reply.get("error") or f"unexpected reply {str(reply)[:120]}")
        except Exception as exc:
            print(f"could not fund a throwaway deployer ({exc}); set PRIMACY_DEPLOYER_KEY to a funded account", file=sys.stderr)
            return 2

    code = (ROOT / "contracts" / "primacy.py").read_text(encoding="utf-8")
    print(f"deploying from {account.address} to {args.rpc}")
    try:
        kwargs = {}
        try:
            cfg = requests.post(args.rpc, json={"jsonrpc": "2.0", "id": 9, "method": "sim_getFeeConfig", "params": []}, timeout=20).json().get("result")
            if isinstance(cfg, dict) and cfg.get("enabled"):
                est = client.estimate_transaction_fees()
                kwargs["fees"] = {"distribution": est["distribution"], "feeValue": est.get("feeValue") or est.get("fee_value")}
        except Exception:
            pass
        tx_hash = client.deploy_contract(code=code, account=account, args=[], **kwargs)
        tx_hash = tx_hash if isinstance(tx_hash, str) else "0x" + bytes(tx_hash).hex()
        receipt = client.wait_for_transaction_receipt(
            transaction_hash=tx_hash, wait_until="decided", interval=3000,
            retries=max(2, args.timeout // 3),
        )
    except Exception as exc:
        print(f"deployment failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    data = receipt.get("data") if isinstance(receipt.get("data"), dict) else {}
    address = data.get("contract_address") or receipt.get("to_address")
    leader = ((receipt.get("consensus_data") or {}).get("leader_receipt") or [{}])
    leader = leader[0] if isinstance(leader, list) and leader else {}
    if not address or int(address, 16) == 0 or leader.get("execution_result") == "ERROR":
        print(f"deployment did not produce a contract (status {receipt.get('status_name')}): "
              f"{json.dumps(leader.get('genvm_result', {}))[:400]}", file=sys.stderr)
        return 1
    address = Web3.to_checksum_address(address)

    # Prove the deployed code answers.
    time.sleep(1)
    try:
        info = client.read_contract(address=address, function_name="get_info", args=[])
    except Exception as exc:
        print(f"the contract was deployed at {address} but get_info failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    if not isinstance(info, dict):
        info = {}

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "network": args.network,
        "rpc": args.rpc,
        "contract": address,
        "transaction": tx_hash,
        "deployer": account.address,
        "contract_sha256": hashlib.sha256(code.encode()).hexdigest(),
        "version": info.get("version"),
        "deployed_utc": datetime.now(timezone.utc).isoformat(),
    }
    target = out_dir / f"{args.network}.json"
    target.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"Primacy {info.get('version')} deployed at {address}")
    print(f"record written to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
