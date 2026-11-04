#!/usr/bin/env node
// Secret-fixture check for the publish driver (scripts/publish/driver.py).
//
//   node secret_check.mjs <rules file> < diff
//
// Reads a unified diff (git diff -U0) on stdin and prints "file:line rule" for every added line
// shaped like a credential. It never prints the matched text. Exit 0 = clean, 5 = hits (the same
// code tools/merge-batch.mjs pre-flight uses), 2 = it could not run (the driver then refuses).
//
// The credential shapes are the roadmap repo's own: the PATTERNS export of its
// tools/secret-rules.mjs, passed in as <rules file>. The generic rule and the scan below follow
// secretShapes() in tools/merge-batch.mjs, which that file does not export, so they are repeated
// here. If the roadmap repo changes them, update this file to match.
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const fail = (msg) => {
  console.error(`secret_check: ${msg}`);
  process.exit(2);
};

const rulesPath = process.argv[2];
if (!rulesPath) fail("usage: node secret_check.mjs <rules file> < diff");
let PATTERNS;
try {
  ({ PATTERNS } = await import(pathToFileURL(rulesPath).href));
} catch (e) {
  fail(`cannot load the rules file: ${e && e.message}`);
}
if (!PATTERNS || typeof PATTERNS !== "object" || !Object.keys(PATTERNS).length) fail("the rules file has no PATTERNS");

// Approximates gitleaks' generic-api-key rule, as in tools/merge-batch.mjs: a keyword, an operator,
// then a 10+ character value whose Shannon entropy is 3.5 or more. A value of only letters, `_`,
// `.` and `-`, or one holding a word (5+ letters of one case), is skipped.
const GENERIC =
  /(?:access|auth|api|credential|creds|key|passw(?:or)?d|secret|token)[ \t\w.-]{0,20}[\s'"]{0,3}(?:=|>|:{1,3}=|\|\||:|=>|\?=|,)[`'"\s=]{0,5}([\w.=-]{10,150}|[a-z0-9][a-z0-9+/]{11,}={0,3})(?=[`'"\s;]|\\[nr]|$)/gi;
const entropy = (s) => {
  const n = {};
  for (const c of s) n[c] = (n[c] || 0) + 1;
  return Object.values(n).reduce((e, k) => e - (k / s.length) * Math.log2(k / s.length), 0);
};
const generic = (v) => !/^[a-zA-Z_.-]+$|[a-z]{5}|[A-Z]{5}/.test(v) && entropy(v) >= 3.5;
let SHAPES;
try {
  SHAPES = Object.entries(PATTERNS).map(([rule, re]) => [rule, new RegExp(re, "g")]);
} catch (e) {
  fail(`a pattern does not compile: ${e && e.message}`);
}

// Credential shapes are matched across each run of added lines (a private key spans lines); the
// generic rule line by line, as gitleaks does.
function secretShapes(diff) {
  const hits = new Set();
  let file = "";
  let line = 0;
  let header = false;
  let block = [];
  const flush = () => {
    const first = line - block.length;
    const starts = [];
    let at = 0;
    for (const t of block) {
      starts.push(at);
      at += t.length + 1;
    }
    const text = block.join("\n");
    for (const [rule, re] of SHAPES) {
      let k = 0;
      for (const m of text.matchAll(re)) {
        while (k + 1 < starts.length && starts[k + 1] <= m.index) k++;
        hits.add(`${file}:${first + k} ${rule}`);
      }
    }
    block.forEach((t, k) => {
      if ([...t.matchAll(GENERIC)].some((m) => generic(m[1]))) hits.add(`${file}:${first + k} generic-api-key`);
    });
    block = [];
  };
  for (const l of diff.split("\n")) {
    if (!header && l.startsWith("+")) {
      block.push(l.slice(1));
      line++;
      continue;
    }
    flush();
    if (l.startsWith("diff --git ")) header = true;
    else if (header && l.startsWith("+++ ")) file = l.slice(4).replace(/^b\//, "");
    else if (l.startsWith("@@")) {
      header = false;
      line = Number(/\+(\d+)/.exec(l)[1]);
    }
  }
  flush();
  return [...hits];
}

const hits = secretShapes(readFileSync(0, "utf8"));
if (hits.length) {
  console.log(hits.join("\n"));
  process.exit(5);
}
