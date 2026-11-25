#!/usr/bin/env python3
"""Local rehearsal network for scripts/live_e2e.py.

This starts the open-source `glsim` simulator and adds the one thing it lacks for this contract:
the value attached to a transaction is passed through to the contract, so deposit_credit works.

It is a rehearsal tool. It runs the same contract code and answers the same JSON-RPC calls, but it has
no real validators, no real language model and no real money. Results from it say that the
end-to-end script logic is sound; they say nothing about Studionet itself.

Usage:
    python scripts/sim_network.py --port 4101
"""

from __future__ import annotations

import argparse
import sys


def install_value_passthrough() -> None:
    from glsim import engine as engine_module
    from glsim import server as server_module

    pending = {"value": 0}
    original_decode = server_module.decode_raw_transaction

    def decode_and_remember(raw_hex):
        decoded = original_decode(raw_hex)
        pending["value"] = int(decoded.get("value", 0) or 0)
        return decoded

    server_module.decode_raw_transaction = decode_and_remember

    original_call = engine_module.SimEngine.call_from_calldata

    def call_with_value(self, contract_address, calldata_bytes, sender=None):
        self.vm.value = pending["value"]
        try:
            return original_call(self, contract_address, calldata_bytes, sender)
        finally:
            self.vm.value = 0
            pending["value"] = 0

    engine_module.SimEngine.call_from_calldata = call_with_value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Local GenLayer rehearsal network (glsim + attached value).")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4101)
    parser.add_argument("--validators", type=int, default=5)
    parser.add_argument("--chain-id", type=int, default=61999)
    parser.add_argument("--seed", default=None)
    args = parser.parse_args(argv)

    try:
        install_value_passthrough()
        from glsim.server import create_app, run_server
    except ImportError as exc:  # pragma: no cover - environment problem
        sys.stderr.write(f"glsim is not installed ({exc}); run: pip install -r requirements.txt\n")
        return 2

    app = create_app(
        num_validators=args.validators,
        max_rotations=3,
        chain_id=args.chain_id,
        llm_provider=None,
        use_browser=False,
        verbose=False,
        seed=args.seed,
    )
    run_server(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
