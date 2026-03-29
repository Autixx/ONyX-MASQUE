# ONX Subscriptions and Billing

## Status

Draft v0.1

## Purpose

This document defines the billing and subscription layer for ONX.

The goal is not payment-provider integration first.

The goal is to define:

- who is entitled to use the network
- how many devices are allowed
- how subscription lifetime is represented
- how billing state affects bundle issuance
- how quota and suspension should be enforced

This document is an architecture note, not end-user documentation.

## Design Principle

Billing must not be embedded into the transport core.

Billing is an entitlement layer above:

- users
- subscriptions
- devices
- profile delivery

Billing must decide:

- whether access is allowed
- how many devices are allowed
- which service class is allowed
- whether the client may receive a new session bundle

Billing must not directly own:

- nodes
- links
- route policies
- balancers
- transport drivers

## Main Requirement

The minimal viable billing slice must support:

- lifetime subscriptions
- expiring subscriptions
- configurable device count per subscription
- manual extension
- manual suspension
- manual reactivation

That is enough for an early commercial control plane.

## Core Entities

### User

Represents the subscriber principal.

Suggested fields:

- `id`
- `email` or `login`
- `display_name`
- `status`
- `created_at`
- `updated_at`

Suggested statuses:

- `active`
- `blocked`
- `deleted`

### Plan

Represents a commercial service template.

Suggested fields:

- `id`
- `code`
- `name`
- `billing_mode`
- `default_device_limit`
- `default_profile_class`
- `traffic_quota_bytes` nullable
- `speed_limit_profile` nullable
- `enabled`
- `created_at`
- `updated_at`

Suggested `billing_mode` values:

- `recurring`
- `fixed_term`
- `lifetime`
- `trial`

### Subscription

Represents one entitlement instance assigned to a user.

Suggested fields:

- `id`
- `user_id`
- `plan_id`
- `status`
- `billing_mode`
- `device_limit`
- `starts_at`
- `expires_at` nullable
- `revoked_at` nullable
- `suspended_at` nullable
- `grace_until` nullable
- `metadata_json`
- `created_at`
- `updated_at`

Suggested statuses:

- `pending`
- `active`
- `grace`
- `suspended`
- `expired`
- `revoked`

### Device Entitlement

This is usually not a separate commercial entity.

The device limit should be evaluated from:

- subscription
- optional user override
- optional operator override

### Entitlement Snapshot

This is the normalized access decision used by the bundle issuer.

Suggested fields:

- `user_id`
- `subscription_id`
- `plan_code`
- `is_allowed`
- `device_limit`
- `active_device_count`
- `profile_class`
- `traffic_quota_bytes`
- `traffic_used_bytes`
- `speed_limit_profile`
- `reason`

## Lifetime Subscription Support

Lifetime support is straightforward.

Recommended representations:

- `billing_mode = lifetime`
- `expires_at = null`

The evaluation rule:

- a lifetime subscription is active until manually suspended or revoked

This is much cleaner than using fake far-future expiration dates.

## Device Count Logic

Device count must be configurable per subscription.

Priority order should be:

1. explicit subscription override
2. plan default
3. system default

Suggested evaluation:

- count only `active` devices
- ignore `revoked` devices
- optionally ignore stale inactive devices after timeout if policy allows auto-replacement

Recommended replacement modes:

- `deny_new`
- `replace_oldest_inactive`
- `replace_oldest_any`
- `operator_approval`

This replacement mode can live in:

- plan policy
- subscription override
- global config

## Manual Extension Model

For early operations, ONX must support simple manual extension without payment integration.

Minimum actions:

- add days
- set explicit expiration date
- convert to lifetime
- suspend
- unsuspend

This alone is enough to operate:

- test accounts
- reseller accounts
- manual renewals
- gifted lifetime access

## Bundle Issuance Decision

The billing/subscription layer must gate bundle issuance.

Before issuing a session bundle, ONX must verify:

- user exists and is active
- subscription exists
- subscription status allows access
- current time is within entitlement window
- device is registered and allowed
- active device count does not exceed limit
- traffic or abuse policy is not violated

If any check fails:

- do not issue bundle
- do not allow tunnel establishment

This is the enforcement point.

## Relationship with Device Identity

This document depends on:

- `ONX_DEVICE_IDENTITY_AND_PROFILE_DELIVERY.md`

Interaction model:

1. user authenticates
2. device proves identity
3. entitlement engine evaluates billing/subscription state
4. if allowed, ONX issues encrypted session bundle

The subscription system therefore controls practical access without exposing transport internals.

## Traffic Accounting

Traffic accounting should be optional in the first implementation.

Early support may be:

- transfer counters per user
- transfer counters per device
- transfer counters per session

Suggested entities:

### Usage Counter

Suggested fields:

- `id`
- `user_id`
- `subscription_id`
- `device_id` nullable
- `period_start`
- `period_end` nullable
- `rx_bytes`
- `tx_bytes`
- `updated_at`

### Session Usage

Suggested fields:

- `id`
- `session_id`
- `user_id`
- `device_id`
- `ingress_node_id`
- `started_at`
- `ended_at`
- `rx_bytes`
- `tx_bytes`

Traffic enforcement in v1 may stay advisory.

Hard quota enforcement can come later.

## Abuse and Suspension

The billing layer should also support commercial enforcement states.

Examples:

- payment overdue
- refund
- chargeback
- abuse complaint
- operator suspension

Suggested actions:

- `suspend subscription`
- `revoke device`
- `block bundle issuance`
- `limit profile class`

## Billing Provider Integration

This should be optional and layered.

Billing providers may later include:

- Stripe
- Telegram bot payments
- manual invoice sync
- custom reseller API

The provider integration should not mutate transport state directly.

It should produce events such as:

- `subscription_activated`
- `subscription_extended`
- `subscription_expired`
- `subscription_suspended`
- `subscription_revoked`

Those events update the ONX subscription tables.

## Suggested API Surface

Future groups:

- `/users`
- `/plans`
- `/subscriptions`
- `/devices`
- `/entitlements`
- `/usage`

Example endpoints:

- `POST /api/v1/users`
- `GET /api/v1/users/{id}`
- `POST /api/v1/plans`
- `GET /api/v1/plans`
- `POST /api/v1/subscriptions`
- `PATCH /api/v1/subscriptions/{id}`
- `POST /api/v1/subscriptions/{id}/extend`
- `POST /api/v1/subscriptions/{id}/suspend`
- `POST /api/v1/subscriptions/{id}/activate`
- `GET /api/v1/users/{id}/entitlement`

## Recommended First Implementation Slice

The first code slice should be small.

Implement:

1. `users`
2. `plans`
3. `subscriptions`
4. configurable `device_limit`
5. entitlement evaluation service
6. gate bundle issuance on entitlement result
7. manual extension and suspension

Do not start with:

- Stripe webhooks
- quota throttling
- invoice history
- taxation
- reseller accounting

## Practical Alpha Goal

The earliest commercially useful result is:

- operator creates user
- operator assigns plan
- operator can set lifetime or expiration date
- operator can set allowed device count
- client app can only obtain bundle when subscription is valid

That is enough for real-world early usage.
