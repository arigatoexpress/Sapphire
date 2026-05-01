#!/usr/bin/env node
/**
 * Sapphire ↔ 0G Storage bridge.
 *
 * Invoked by lib/og/storage.py as a subprocess. Takes a JSON command on
 * argv[2] and emits a single JSON line on stdout.
 *
 * Commands:
 *   upload   {"path": "/abs/path"}                    → {"rootHash":"0x...", "txHash":"0x..."}
 *   uploadMem {"data": "<utf8 string>"}               → {"rootHash":"0x...", "txHash":"0x..."}
 *   download {"rootHash":"0x...", "outputPath":"..."} → {"ok": true, "verified": true}
 *
 * Reads from env:
 *   OG_PRIVATE_KEY           required for upload (32-byte hex, 0x-prefixed or not)
 *   OG_RPC_URL               required (e.g. https://evmrpc-testnet.0g.ai)
 *   OG_INDEXER_URL           required (e.g. https://indexer-storage-testnet-turbo.0g.ai)
 *
 * Errors are reported as `{"error": "..."}` on stdout with exit code 1.
 * stderr is reserved for human-readable progress; never read by the parent.
 */

import process from "node:process";

const RPC_URL = process.env.OG_RPC_URL;
const INDEXER_URL = process.env.OG_INDEXER_URL;
const PRIVATE_KEY = process.env.OG_PRIVATE_KEY;

function fail(msg) {
  process.stdout.write(JSON.stringify({ error: String(msg) }) + "\n");
  process.exit(1);
}

function ok(payload) {
  process.stdout.write(JSON.stringify(payload) + "\n");
  process.exit(0);
}

const [, , subcommand, jsonArg] = process.argv;
if (!subcommand) fail("usage: og_storage.mjs <upload|uploadMem|download> <json>");

let args;
try {
  args = JSON.parse(jsonArg ?? "{}");
} catch (e) {
  fail(`bad json arg: ${e.message}`);
}

if (!RPC_URL || !INDEXER_URL) fail("OG_RPC_URL and OG_INDEXER_URL must be set");

let ZgFile, MemData, Indexer, ethers;
try {
  ({ ZgFile, MemData, Indexer } = await import("@0gfoundation/0g-ts-sdk"));
  ethers = await import("ethers");
} catch (e) {
  fail(
    `0G TS SDK not installed in lib/og/_ts. Run: cd lib/og/_ts && npm install. (${e.message})`,
  );
}

async function makeSigner() {
  if (!PRIVATE_KEY) fail("OG_PRIVATE_KEY must be set for write operations");
  const provider = new ethers.JsonRpcProvider(RPC_URL);
  const key = PRIVATE_KEY.startsWith("0x") ? PRIVATE_KEY : "0x" + PRIVATE_KEY;
  return new ethers.Wallet(key, provider);
}

const indexer = new Indexer(INDEXER_URL);

if (subcommand === "upload") {
  if (!args.path) fail("upload requires {path}");
  const signer = await makeSigner();
  let file;
  try {
    file = await ZgFile.fromFilePath(args.path);
    const [tree, treeErr] = await file.merkleTree();
    if (treeErr) fail(`merkleTree: ${treeErr}`);
    const rootHash = tree?.rootHash();
    const [tx, uploadErr] = await indexer.upload(file, RPC_URL, signer);
    if (uploadErr) fail(`upload: ${uploadErr}`);
    const txHash = tx && (tx.txHash || (tx.txHashes && tx.txHashes[0])) || "";
    ok({ rootHash, txHash });
  } finally {
    if (file) await file.close().catch(() => {});
  }
}

if (subcommand === "uploadMem") {
  if (typeof args.data !== "string") fail("uploadMem requires {data: string}");
  const signer = await makeSigner();
  const bytes = new TextEncoder().encode(args.data);
  const memData = new MemData(bytes);
  const [tree, treeErr] = await memData.merkleTree();
  if (treeErr) fail(`merkleTree: ${treeErr}`);
  const rootHash = tree?.rootHash();
  const [tx, uploadErr] = await indexer.upload(memData, RPC_URL, signer);
  if (uploadErr) fail(`upload: ${uploadErr}`);
  const txHash = (tx && (tx.txHash || (tx.txHashes && tx.txHashes[0]))) || "";
  ok({ rootHash, txHash });
}

if (subcommand === "download") {
  if (!args.rootHash || !args.outputPath) fail("download requires {rootHash, outputPath}");
  const verify = args.verify !== false;
  const err = await indexer.download(args.rootHash, args.outputPath, verify);
  if (err) fail(`download: ${err}`);
  ok({ ok: true, verified: verify });
}

fail(`unknown subcommand: ${subcommand}`);
