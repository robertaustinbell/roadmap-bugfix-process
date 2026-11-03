# OCR pipeline scripts

Sanitized from a working implementation; review before running. All three need only Python 3 (standard library), `git`, and for scanning the `ocr` CLI. They pass `python3 -m py_compile`.

| Script | Run by | Does |
|---|---|---|
| `st.py` | humans, the agent, the Coordinator | the only way to edit `state.json` (`show`, `init`, `stage`, `notify`, `set`, `top`, `round open|close`) |
| `mech.py` | scheduler, every 15 min | one mechanics tick: scans while a round is open, keeps the publish driver running, sends notices. Also `mech.py scan-part <name>` and `mech.py list` |
| `monitor.py` | scheduler, before the agent job | prints `idle` or a `work ...` line; `--gate` for plain cron |

How they fit together: [docs/open-code-review-pipeline.md](../../docs/open-code-review-pipeline.md) and [docs/scheduling.md](../../docs/scheduling.md).

## Configuration

Each setting is read from an environment variable, else from a JSON file: `$OCR_PIPELINE_CONFIG`, else `ocr-pipeline.json` next to the script. Scheduled scripts on Hermes cannot take arguments, so the JSON file is the easy route there.

```json
{
  "OCR_BASE_DIR": "/path/to/ocr-work",
  "OCR_PIPELINE_DIR": "/path/to/ocr-work/pipeline",
  "ROADMAP_WORKTREE": "/path/to/roadmap-ocr-worktree",
  "UPSTREAM_REMOTE": "upstream",
  "UPSTREAM_BRANCH": "main",
  "OCR_BIN": "ocr",
  "KEEP_AWAKE": "caffeinate -ims",
  "ROUND_DIR": "/path/to/publish-round",
  "FIXES_DIR": "/path/to/fixes",
  "NOTIFY_CMD": "/path/to/your-notify-script"
}
```

| Key | Needed by | Notes |
|---|---|---|
| `OCR_BASE_DIR` | all | holds `parts/` and `results/` |
| `OCR_PIPELINE_DIR` | all | default `OCR_BASE_DIR/pipeline` |
| `ROADMAP_WORKTREE` | mech | detached worktree with an `upstream` remote pointing at the maintainer's repo |
| `ROUND_DIR`, `FIXES_DIR`, `PUBLISH_DRIVER` | mech | optional; set them to have the tick keep the publish driver running |
| `FIXES_DIR` | monitor | its review/state files are part of the fingerprint |
| `NOTIFY_CMD` | mech | gets each notice on stdin. Unset: notices go to stdout (Hermes cron delivers stdout) |
| `KEEP_AWAKE` | mech | command prefix that stops sleep during a scan; empty string to disable |

The publish driver reads its own settings from the environment (see [../publish/README.md](../publish/README.md)). When the mechanics job launches it, it inherits the job's environment, not the JSON file.

## First run

```sh
# 1. a worktree for scans (never your working checkout)
git -C /path/to/roadmap worktree add --detach /path/to/roadmap-ocr-worktree upstream/main

# 2. part lists: one repo path per line, ~33-67 files each
mkdir -p /path/to/ocr-work/parts
(cd /path/to/roadmap-ocr-worktree && ocr scan --preview)   # copy the "Will review" list, split it into parts/NN-name.txt

# 3. state
python3 scripts/ocr/st.py init
python3 scripts/ocr/st.py show

# 4. check ocr itself
ocr llm test        # must pass the connection and the tool-call round trip
```

Then set up the two jobs ([docs/scheduling.md](../../docs/scheduling.md)) and let the Coordinator open a round: `python3 scripts/ocr/st.py round open`.

## Files the scripts write

- `results/<part>.{json,log,session,done}`: scan output, progress log, resume id, clean-finish marker.
- `pipeline/state.json`, `.mech.lock`: state and its lock.
- `pipeline/mech.log`: every launch, finish, usage stop, notice and error.
- `pipeline/scan-<part>.out`: the background scan runner's own output.
- `pipeline/.monitor-last`, `.monitor-gate-last`: monitor bookkeeping.
- The agent writes `pipeline/agent.lock`, `agent.log` and `NN-REPORT.md`.

## Changes from the working version

- Paths, the notice channel and account details are configuration, not constants.
- The scan runner was a shell script; it is now `mech.py scan-part`, with the same rules: skip files missing on the checked-out commit, resume a saved session, stop the whole process group on the first usage-limit error, drop a session with no finished files, write `.done` only on a clean finish.
- The driver keepalive uses the driver's own pid file instead of matching process names (name matching found the sleep-prevention wrapper first), and leaves a driver alone while `stop-driver` or `_done-round` exists.
- `st.py` refuses an ambiguous part prefix instead of taking the first match, and gained `init` and `top`.
- `monitor.py --gate` was added for schedulers that cannot compare output between runs.
