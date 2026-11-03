# Schedules

Examples for running the OCR pipeline's two jobs. What the jobs do and how they are gated: [docs/scheduling.md](../docs/scheduling.md).

| File | For |
|---|---|
| [hermes-cron-example.json](hermes-cron-example.json) | Hermes Agent cron: a no-AI mechanics job every 15 min and a monitor-gated agent job every 30 min |
| [crontab-example.txt](crontab-example.txt) | plain cron on macOS or Linux |
| launchd (below) | macOS without cron |

All of them are sanitized from a working setup. Replace every `<...>` placeholder and review before use. None of them opens a scan round; the Coordinator does that with `st.py round open`.

## Before you schedule anything

1. Write `ocr-pipeline.json` ([scripts/ocr/README.md](../scripts/ocr/README.md)) and run `python3 scripts/ocr/st.py show`.
2. Run `python3 scripts/ocr/monitor.py` once and check it prints `idle` or a `work ...` line.
3. Decide where notices go. On Hermes, the mechanics job's stdout is the notice. Elsewhere, set `NOTIFY_CMD` to a script that reads the text on stdin and sends it (mail, chat webhook, a desktop notification).
4. For the agent job, pin the model, and make sure the agent can run shell commands, git, gh and edit files.

## launchd (macOS)

Save as `~/Library/LaunchAgents/org.example.ocr-mech.plist`, replace the placeholders, then `launchctl load` it. Make a second plist for the agent job that runs a small wrapper script (monitor gate, then your agent CLI, as in the crontab example) with `StartInterval` 1800.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>org.example.ocr-mech</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>-I</string>
    <string>REPO_PATH/scripts/ocr/mech.py</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>DIRS_WITH_GIT_GH_NODE_OCR:/usr/bin:/bin</string>
  </dict>
  <key>StartInterval</key><integer>900</integer>
  <key>StandardOutPath</key><string>LOG_DIR/ocr-mech.out</string>
  <key>StandardErrorPath</key><string>LOG_DIR/ocr-mech.err</string>
</dict>
</plist>
```

Other settings come from `loop.env` in the kit root, which every script reads; launchd only needs `PATH`.

launchd does not run a job while the Mac sleeps; it runs a missed interval once on wake. The scripts keep the machine awake only while a scan or suite is running (`KEEP_AWAKE`).

## What not to do

- Do not add a schedule that opens rounds or retries scans on a timer. Rounds follow the restart rule in [docs/process.md](../docs/process.md).
- Do not run two publish drivers. The mechanics job keeps exactly one running.
- Do not put a merge step anywhere. The loop never merges.
