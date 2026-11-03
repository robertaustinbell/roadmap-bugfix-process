# Scheduling

The Open Code Review pipeline runs as two scheduled jobs. Everything else in the loop is started by the Coordinator (see [process.md](process.md) and [roles.md](roles.md)).

| Job | Every | AI? | Does |
|---|---|---|---|
| OCR pipeline mechanics | 15 min | no | scans while a round is open, keeps the publish driver running, sends stall notices ([`scripts/ocr/mech.py`](../scripts/ocr/mech.py)) |
| OCR pipeline agent | 30 min, only when there is work | yes | triage, fixes, independent reviews, issues, private reports ([agents/ocr-pipeline-agent.md](../agents/ocr-pipeline-agent.md)) |

Neither job opens a round. Scanning starts only when the Coordinator runs `st.py round open`, after the restart rule is met (every previous-round PR addressed by the maintainer; see [publishing.md](publishing.md#the-restart-rule)). When the usage limit hits, the mechanics job closes the round's scanning. There is no timed retry.

The publish driver is a long-running process, not a scheduled job. The mechanics job launches it when it is not running.

## Gating the agent job

The agent job is expensive, so it runs only when [`scripts/ocr/monitor.py`](../scripts/ocr/monitor.py) says there is work. The monitor prints `idle` or a `work part=... stage=... bucket=... fp=...` line:

- The line changes when the active part enters an agent stage, when fix-folder review or state files change, and every 3 hours while a part stays in an agent stage. The 3-hour bucket is the retry after a tick that failed part way.
- While a run holds `agent.lock`, the monitor repeats its last line, so a second run never overlaps the first.
- `idle` means: paused, `agent_hold` set, or no part in `scanned`/`reviewing`. The agent replies `idle` and stops.

## Option 1: Hermes Agent cron

This is what the working setup uses. See [schedules/hermes-cron-example.json](../schedules/hermes-cron-example.json) for both job definitions.

1. Put the scripts where Hermes cron looks for them (the `scripts` folder in your Hermes home, `$HERMES_HOME/scripts/`). Copy or symlink `scripts/ocr/mech.py` as `ocr_pipeline_mech.py` and `scripts/ocr/monitor.py` as `ocr_pipeline_monitor.py`.
2. Cron scripts get no arguments, so give them a config file: `ocr-pipeline.json` next to the script (or set `OCR_PIPELINE_CONFIG` in the gateway's environment). Example in [scripts/ocr/README.md](../scripts/ocr/README.md).
3. Mechanics job: `no_agent: true`, `script: ocr_pipeline_mech.py`, every 15 minutes, delivered to wherever you want notices. Its stdout is the notice; empty stdout sends nothing.
4. Agent job: `monitor_script: ocr_pipeline_monitor.py`, every 30 minutes, a prompt that says "read and follow agents/ocr-pipeline-agent.md". The monitor output is injected into the prompt. Deliver the agent's reply locally (it is a short log line) and send failures to your notice target.
5. Pin the agent job's model. An unpinned job follows the default model at fire time, which may be cheaper or unavailable.
6. Fire one agent tick by hand and check in the log that it ran on the intended model.

Pitfalls:

- Hermes cron refuses a script whose text contains the word "restart" or a raw `os.kill` call (a gateway-lifecycle guard). The provided scripts avoid both; keep it that way when you edit them.
- A no-agent script that exits non-zero alerts every tick. The scripts exit 0 and log errors to `mech.log`.
- Do not run the mechanics script by hand "to check it" when it prints its notices. It records each notice as sent before printing, and on Hermes only the cron run's stdout is delivered, so a manual run swallows the notice. If you must, clear it afterwards with `st.py set <part> pings '{}'`. With `NOTIFY_CMD` set, this does not apply.
- A monitor-gated job only wakes when the monitor output changes. A failed tick leaves the output unchanged; the 3-hour bucket is what makes it try again.
- To run the agent stage now, use `hermes cron run <job id>`. It blocks, so run it with a short timeout or in the background.

## Option 2: plain cron or launchd (no Hermes)

See [schedules/crontab-example.txt](../schedules/crontab-example.txt) and [schedules/README.md](../schedules/README.md) (which also has a launchd example for macOS).

- The mechanics script runs as is. Set `NOTIFY_CMD` so notices reach you instead of cron's mail.
- For the agent job, use `monitor.py --gate`: it exits 0 only when the line is not `idle` and differs from the last time the gate passed. Chain your agent CLI after it with `&&` and pass the monitor line plus [agents/ocr-pipeline-agent.md](../agents/ocr-pipeline-agent.md) as the prompt.
- Give the agent CLI the same tools the instructions assume: shell, git, gh (read-only for triage workers), file editing, and a way to start up to 4 sub-agents. If your CLI cannot start sub-agents, run the groups one after another in the same session and expect longer ticks.

## Pausing

| Want | Do |
|---|---|
| stop everything | pause both jobs, or `st.py top paused true` (also stops the driver keepalive) |
| scans continue, no triage | `st.py top agent_hold true` |
| finish the current part, then stop | `st.py stage <next part> held` |
| stop publishing | `touch <ROUND_DIR>/stop-driver` (the mechanics job will not relaunch a driver while it exists) |
| no new scans | `st.py round close` |

Undo each the same way (`false`, `queued`, delete `stop-driver`).
