# M43 Raspberry Pi Runtime and Deployment Contract

Issue: #320
Milestone: M43 Raspberry Pi Market-Health Alert Service
Status: Design contract

## Purpose

This document defines the production runtime and deployment contract for the M43 Raspberry Pi Market-Health Alert Service.

## Production target

The production runtime is the Raspberry Pi running Debian/Linux.

Android/Termux is the development and control surface only. It may be used for SSH, GitHub CLI work, issue/PR management, inspection, and manual control. It must not be responsible for scheduled market-hours monitoring.

GitHub is the source of truth for code, issues, milestones, branches, PRs, CI results, and project history.

## Device responsibilities

Android/Termux:

- connects to the Pi through remote.it SSH
- runs GitHub CLI commands
- creates issues and PRs
- inspects logs and files over SSH
- receives Telegram notifications
- does not run the production timer
- does not host the production SQLite database
- does not send production alerts as the primary sender

Raspberry Pi/Debian:

- runs the M43 alert service
- runs market-health refreshes through existing Jerboa refresh paths
- writes local SQLite snapshots and alert history
- sends Telegram notifications directly
- runs under systemd timer/service control
- keeps logs and status evidence
- recovers cleanly after reboot

GitHub:

- stores the authoritative code and project history
- tracks M43 work through issues and milestones
- receives focused branches and PRs
- runs CI checks before squash merge
- preserves issue and PR audit history

A merged PR does not automatically mean the Pi is running the new code. The Pi must pull or deploy the tested commit.

## Service model

M43 v1 uses a systemd timer plus a run-once service.

It should not start as a forever-running daemon.

Expected run flow:

1. systemd timer starts the run-once service.
2. the service checks market-hours policy.
3. the service refreshes or loads required market-health artifacts.
4. the service writes a run record and held-symbol snapshots.
5. the service detects alert-worthy changes.
6. the service applies cooldown and duplicate suppression.
7. the service sends or logs Telegram alerts according to mode.
8. the service exits with a clear status code.

The timer may run every 15 minutes. The Python runner should decide whether the market is open or whether the run should be skipped.

## Deployment contract

Live file syncing is not the primary deployment workflow.

Normal production workflow:

1. create a focused M43 branch
2. make the change
3. run local checks where practical
4. push the branch
5. open a PR linked to the issue
6. wait for CI to pass
7. squash merge to main
8. delete the branch
9. pull the tested commit onto the Raspberry Pi
10. run a Pi smoke test before relying on production behavior

Expected Pi update pattern:

- cd into `/root/market-health-cli`
- fetch `origin/main`
- switch to `main`
- pull with fast-forward only

If a release-wrapper model is used, the wrapper target must also be rebuilt or repointed. A correct repo checkout and a correct installed runtime are separate states.

## Expected local paths

| Purpose | Recommended path |
|---|---|
| Repository checkout | `/root/market-health-cli` or documented equivalent |
| Cache directory | `~/.cache/jerboa/` |
| Alert SQLite database | `~/.cache/jerboa/market_health_alerts.v1.sqlite` |
| Config file | `~/.config/jerboa/market_health_alerts.toml` or repo-standard equivalent |
| Secrets file | local-only file under `~/.config/jerboa/` |
| systemd user units | `~/.config/systemd/user/` or installer-managed equivalent |
| Logs | journald plus SQLite run/system-event rows |

Secrets must never be committed to GitHub.

## Telegram contract

Telegram delivery should happen directly from the Raspberry Pi.

Expected modes:

- disabled
- dry-run
- test
- live

The bot token and chat ID must come from local secrets or environment outside Git.

## Testing contract

CI should prove deterministic logic and must not require live market data, Telegram network access, Schwab network access, or Android background behavior.

The Raspberry Pi should prove production behavior through scheduled dry-runs, snapshot freshness checks, Telegram test delivery, alert-noise review, database recoverability, and reboot recovery.

## Rollback contract

Rollback should be possible by disabling the timer or returning the Pi to a known-good commit.

Rollback should not delete the SQLite database by default. The database is audit evidence.

If a release-wrapper model is used, rollback must also restore the wrapper target to the known-good release directory.

## Non-goals for M43 v1

- no trade execution
- no broker orders
- no Android background automation
- no candidate/watchlist alerts in v1
- no recommendation-engine redesign
- no terminal-dashboard scraping
- no committed secrets
- no CI dependence on live market data

## Acceptance criteria status

- [x] Document supported production target: Debian/Raspberry Pi
- [x] Document Android/Termux role as development/control only
- [x] Document GitHub branch/PR/pull workflow
- [x] Document no live syncing as primary deployment
- [x] Document expected Pi paths for config, database, logs, and secrets
- [x] Document how the Pi pulls tested branches or main
- [x] Document rollback expectations
- [x] Add this to a dedicated docs file
