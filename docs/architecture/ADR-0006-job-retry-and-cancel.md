# ADR-0006: Job Retry and Cancellation Policy

## Status
Accepted

## Context
ONX jobs are executed by background workers and may fail because of network or remote runtime issues.
Without retry/cancel controls, transient errors cause operator noise and long-running tasks cannot be stopped safely.

## Decision
Introduce explicit retry and cancellation controls at the job model level:

- job fields:
  - `max_attempts`
  - `retry_delay_seconds`
  - `next_run_at`
  - `cancel_requested`
  - `cancelled_at`
- new terminal states:
  - `cancelled`
  - `dead`
- worker behavior:
  - on execution error, reschedule as `pending` when attempts remain
  - move to `dead` when attempts are exhausted
  - support cooperative cancellation through `/api/v1/jobs/{id}/cancel`

## Consequences
Pros:

- transient failures recover automatically
- operators can interrupt risky operations without killing worker processes
- retries are auditable via event logs

Cons:

- higher state-machine complexity for job lifecycle
- cancellation is cooperative and depends on heartbeat/progress checkpoints

## Notes
Future enhancement:

- add per-job backoff strategy and jitter
- add force-cancel for stuck jobs after lease expiration
