# ADR-0007: Job Target Locking

## Status
Accepted

## Context
ONX workers can run in parallel and recover stale leases. Without target-scoped locking,
different workers may execute conflicting jobs against the same entity (`node` or `link`).

## Decision
Introduce a persistent lock table `job_locks` keyed by `target_type:target_id`.

- lock acquisition happens during job claim (`pending -> running`)
- lock lease follows job lease (`lease_expires_at`)
- lock is released on terminal state or when retry is rescheduled
- new job enqueue is rejected when same target already has active `pending/running` job

## Consequences
Pros:

- prevents concurrent `apply/discover/bootstrap` operations on the same target
- safer multi-worker behavior
- deterministic operator feedback (`409 conflict` with existing job id)

Cons:

- adds one more table and lock lifecycle management logic
- requires careful cleanup on exceptional paths
