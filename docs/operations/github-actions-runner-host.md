# GitHub Actions runner host operations

This document records the public, non-secret operating model for the shared
self-hosted GitHub Actions runner host. Live addresses, organization names,
runner names, credentials, private-key paths, and repository-specific output
must not be added here.

## Host model

The host has 8 vCPUs, 16 GiB of memory, a small root filesystem, four persistent
runner listeners, and one shared Docker daemon. All four listeners should remain
online. Listener availability and safe job concurrency are separate concerns:
an idle listener is inexpensive, while four jobs can independently fan out and
oversubscribe CPU, memory, and disk.

Administrative SSH uses a dedicated non-root account and public-key
authentication. Root and password login remain disabled. Resolve the address and
identity from the approved local inventory; never record either in this public
repository. Escalate with `sudo` only after login.

This maintenance change makes cleanup safe around active jobs. It does not yet
implement weighted heavy/light admission across organizations.

## Safe cleanup invariant

No destructive Docker, cache, temporary-directory, or workspace operation may
run while any `Runner.Worker` exists.

The maintenance sequence is:

1. Take the host-wide non-blocking maintenance lock.
2. Count `Runner.Worker` processes globally.
3. If any worker exists, log `cleanup deferred` and exit successfully.
4. Freeze all four runner systemd units through the cgroup freezer.
5. Verify all four units report `FreezerState=frozen`.
6. Count workers again and check for active Docker mounts of runner workspaces.
7. If either check is unsafe, thaw all units and exit without cleanup.
8. Run Docker and filesystem cleanup.
9. Thaw exactly the units marked by this maintenance attempt.

The scripts use a runtime marker plus three recovery paths: an exit trap,
`ExecStopPost`, and a one-minute recovery timer. Recovery is idempotent. A stale
marker never grants permission to clean; it only identifies units that must be
thawed.

## Disk policy

- Below 75% root-disk use: the two-minute disk guard observes only.
- At or above 75%: pressure cleanup is attempted. It is deferred without any
  prune when a job is active.
- At or above 90%: idle runner units are frozen, checked again, and stopped to
  prevent new work. Units with active workers are preserved.
- At or below 80%: only units stopped by the disk guard are restarted.

The thresholds have hysteresis so runners do not repeatedly stop and start near
one boundary. This policy favors a running job over reclaiming space. A future
admission controller is still required to drain continuously busy runners before
the disk reaches the emergency threshold.

## Effective components

```text
/usr/local/lib/zenta-ci-common
/usr/local/sbin/zenta-ci-disk-guard
/usr/local/sbin/zenta-ci-maintenance
/usr/local/sbin/zenta-ci-repair-workspaces
/usr/local/sbin/zenta-ci-recover-drain

zenta-ci-disk-guard.timer          every 2 minutes
zenta-ci-workspace-repair.timer    every 15 minutes
zenta-ci-maintenance.timer         daily
zenta-ci-recovery.timer            every minute
```

All three cleanup entry points share `/run/lock/zenta-ci-maintenance.lock`.

## Verification

During an active job, all of the following must be true:

```bash
sudo systemctl start zenta-ci-maintenance.service
sudo /usr/local/sbin/zenta-ci-maintenance pressure
sudo systemctl start zenta-ci-workspace-repair.service

sudo journalctl --since '5 minutes ago' --no-pager \
  -t zenta-ci-maintenance \
  -t zenta-ci-workspace-repair
```

The log must contain only `cleanup deferred` or `repair deferred`. It must not
contain Docker prune output.

Check that all listeners are running and no drain marker remains:

```bash
pgrep -a -x Runner.Listener
pgrep -a -x Runner.Worker || true
test ! -d /run/zenta-ci-maintenance-drain
systemctl --failed
```

When the host is idle, a normal maintenance run should log the following order:

```text
cleanup started: workers=0 listeners=frozen
cleanup completed: workers=0
```

Afterward, all four runner units must be active and have
`FreezerState=running`.

## Rollback

Each deployment must create a timestamped directory under
`/var/backups/zenta-ci/` before replacing a script or unit. Roll back only in an
idle maintenance window. Stop the four maintenance/recovery timers, restore the
recorded files, run `systemctl daemon-reload`, and then re-enable the original
timers. Never stop a runner service merely to perform cleanup while its worker is
active.

## Known limits

- This protects cleanup from active jobs but does not cap the number or weight of
  jobs accepted by four online listeners.
- The shared Docker socket remains a host-level trust boundary.
- Disk pressure can remain above 75% while jobs run because safety takes priority
  over pruning. A host-wide admission/drain controller is the next iteration.
