/* Primacy frontend configuration. Change the contract address here and nowhere else. */
window.PRIMACY = {
  contract: "0xf49Fca785788a2a3881c593F33B2E20113FD99e1",
  version: "0.1.0",
  deployTx: "0xdec3786346bc193a565722ce9ba28b9ccc4113edbb4b60baa3d0ddbe0aef8825",
  chain: {
    id: 61999,
    hex: "0xf22f",
    name: "GenLayer Studionet",
    rpc: "https://studio.genlayer.com/api",
    explorer: "https://explorer-studio.genlayer.com",
    txPath: "/tx/",
    symbol: "GEN",
    decimals: 18
  },
  links: {
    github: "https://github.com/reza9133/primacy/",
    x: "https://x.com/amirhp771",
    xHandle: "@amirhp771",
    genlayer: "https://www.genlayer.com",
    genlayerDocs: "https://docs.genlayer.com"
  },
  /* Real bounties created by the launch test run on the deployed contract. */
  examples: [
    { sponsor: "0x174fbcdecffc4ada6bd69470fcea8dce760eac3e", id: "MAIN", note: "Full run: commits, reveals, duplicates, a void and a close" },
    { sponsor: "0x174fbcdecffc4ada6bd69470fcea8dce760eac3e", id: "CANCEL1", note: "A bounty cancelled before anyone committed" },
    { sponsor: "0xa2543dcafa572ab922543333916d53da75b45417", id: "CANCEL1", note: "Same id under another sponsor, cancelled too" }
  ]
};
window.PRIMACY.explorerAddress = window.PRIMACY.chain.explorer + "/address/" + window.PRIMACY.contract;
