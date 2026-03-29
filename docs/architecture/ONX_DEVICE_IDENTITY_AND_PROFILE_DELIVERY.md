# ONX Device Identity and Profile Delivery

## Status

Draft v0.1

## Purpose

This document defines how ONX should:

- bind access to registered devices
- limit the number of active devices per user or subscription
- issue encrypted client profile bundles
- avoid exposing full network topology to end users
- support desktop and mobile devices

This is an architecture note, not a user guide.

## Problem Statement

ONX must not rely on reusable plaintext tunnel configs distributed to users.

Reasons:

- a normal user may copy the config to another device
- a normal user may inspect or modify config fields manually
- a leaked config should not give long-term access
- the full node inventory and routing topology must stay on the control-plane side

At the same time, ONX does not try to defend against a fully compromised client device or deep reverse engineering.

The target is practical protection against ordinary end-user misuse.

## Design Goals

- Bind access to one registered device identity
- Allow configurable device limits per user or subscription
- Support desktop and mobile app registration flows
- Deliver only the minimum set of ingress candidates and protocol variants
- Avoid persistent plaintext configs as a user-facing artifact
- Make stolen profile files useless on unregistered devices
- Support revocation, rotation, and re-issue

## Non-Goals

- Prevent memory extraction on a fully compromised client
- Prevent runtime hook or reverse engineering attacks by a determined attacker
- Hide the first network hop from the local operating system
- Replace full MDM or enterprise endpoint management

## Core Model

The client must not receive the full topology.

Instead, ONX should work with three layers:

### 1. Bootstrap Trust

Shipped in the client application:

- bootstrap API domain names
- trust anchor or pinned control-plane public key
- protocol version

This layer is static or rarely changed.

### 2. Device Identity

Created on first install or first registration:

- app-generated device private key
- device public key registered in ONX
- device record with status and metadata

This is the main binding anchor.

### 3. Session Bundle

Issued online after user authentication and device verification:

- short-lived encrypted profile envelope
- only current ingress candidates and transport options
- no full topology inventory
- no backend-only policy internals

## Why Device Key Is Better Than Raw Hardware Fingerprint

Raw hardware fingerprints are weak as the primary trust anchor:

- some values are unavailable on modern mobile OSes
- some values are unstable across updates or reinstalls
- some values are easy to spoof
- privacy restrictions block access to many historical identifiers

Therefore the primary identity should be:

- application-generated device keypair

Hardware and OS traits should be treated only as:

- registration metadata
- risk signals
- device change heuristics

## Device Model

Suggested entities:

### User

Represents the account or subscriber principal.

### Subscription

Represents entitlement to service.

Suggested fields:

- `id`
- `user_id`
- `plan_id`
- `billing_mode`
- `expires_at`
- `device_limit`
- `status`

Notes:

- lifetime subscription is naturally represented by `billing_mode=lifetime` or `expires_at=null`
- `device_limit` must be configurable

### Device

Represents one registered client device.

Suggested fields:

- `id`
- `user_id`
- `subscription_id`
- `device_public_key`
- `platform`
- `device_label`
- `status`
- `first_registered_at`
- `last_seen_at`
- `revoked_at`
- `risk_state`

Suggested status values:

- `pending`
- `active`
- `revoked`
- `blocked`

### Device Metadata

Represents non-secret descriptive data.

Suggested fields:

- `device_id`
- `app_version`
- `os_name`
- `os_version`
- `device_model`
- `vendor_device_id`
- `app_instance_id`
- `attestation_type`
- `attestation_summary`
- `last_ip`
- `last_asn`

## Device Limit Policy

Device count must be configurable.

The controlling field should live at subscription or user-policy level:

- `device_limit`

Examples:

- `1` for strict single-device access
- `2` for phone + laptop
- `5` for family or multi-device plans
- `null` or very high value for unlimited plans

Recommended policy behavior:

- if `active_device_count < device_limit`, registration is allowed
- if `active_device_count >= device_limit`, registration is denied or requires explicit replacement

Recommended replacement modes:

- deny new device
- revoke oldest inactive device
- require user/operator approval

## Registration Flow

### First Registration

1. Client installs app
2. Client generates local device keypair
3. Client authenticates user
4. Client submits:
   - `device_public_key`
   - platform metadata
   - optional attestation payload
5. ONX checks subscription and device limit
6. ONX creates or activates device record
7. ONX returns signed registration result

### Routine Bundle Request

1. Client requests challenge
2. ONX returns nonce/challenge
3. Client signs challenge with device private key
4. ONX verifies:
   - user/session auth
   - device exists and is active
   - signature matches device public key
   - subscription is active
5. ONX issues encrypted session bundle

This makes a stolen bundle or copied file insufficient on another device.

## Session Bundle

The bundle should be a short-lived encrypted envelope.

It should contain only what the client needs right now.

### Bundle Contents

- `bundle_id`
- `profile_id`
- `user_id`
- `device_id`
- `issued_at`
- `expires_at`
- `transport_candidates`
- `routing_token`
- `policy_hints`
- `server_signature` or AEAD integrity

### Transport Candidates

Each candidate should contain only:

- transport type
- priority
- endpoint reference
- runtime config payload
- optional fallback weight

Typical bundle size should be:

- `2-5` ingress candidates
- `1-3` transport options per candidate

Practical result:

- about `4-12` runtime transport blocks

Not the full mesh inventory.

### What Must Not Be Included

- full node list
- backend relay inventory
- egress inventory
- full balancer internals
- internal topology graph
- all available routes and policy rules

## Storage and Encryption Strategy

The client application should not expose reusable plaintext config files as a normal export path.

Recommended approach:

- store profile envelopes encrypted at rest
- decrypt only inside application runtime
- pass runtime payload directly to the tunnel/proxy engine
- avoid writing user-readable configs when possible

Recommended cryptographic shape:

- versioned profile container
- AEAD encryption
- key identifier
- issued time
- expiry time
- integrity protection

Suitable approaches:

- `XChaCha20-Poly1305`
- `AES-256-GCM`

The exact format can be:

- JSON envelope
- CBOR envelope
- protobuf envelope

The important rule is:

- versioned
- signed or AEAD-authenticated
- short-lived

## Mobile Device Support

Yes, mobile devices must be supported.

MAC address must not be used as the primary identity on smartphones:

- it is often randomized
- it may be inaccessible to applications
- it is not stable enough for trust decisions

### Recommended Mobile Identity Stack

Primary:

- app-generated device keypair stored in secure OS keystore

Secondary signals:

- vendor or app-scoped device identifier
- device model
- OS version
- app version
- push token or installation token only as telemetry, not trust anchor

Optional stronger attestation:

- Android Play Integrity API
- Android hardware-backed Key Attestation where available
- Apple App Attest
- Apple DeviceCheck as weaker fallback

### Platform Notes

#### Android

Good candidates:

- app-generated keypair in Android Keystore
- Play Integrity verdict
- Key Attestation certificate chain
- app-set or installation-scoped identifier

Avoid using as trust root:

- MAC
- IMEI
- serial number
- advertising identifier

#### iOS

Good candidates:

- app-generated keypair in Secure Enclave or Keychain-backed storage
- App Attest
- DeviceCheck
- `identifierForVendor` only as supporting metadata, not trust root

Avoid using as trust root:

- MAC
- advertising identifier
- private device identifiers

## Risk Controls

ONX should score device risk based on:

- impossible travel or abrupt geolocation change
- sudden ASN change
- app version below minimum
- failed signature verification
- attestation failure
- too many registration attempts
- too many concurrent active sessions

Possible actions:

- deny bundle issuance
- require re-registration
- soft-block and require manual review
- revoke device

## Revocation Model

ONX should support:

- revoke one device
- revoke all user devices
- rotate bundle signing/encryption keys
- rotate per-device trust state

After revocation:

- new session bundles must not be issued
- existing short-lived bundles expire naturally

## Config Visibility Policy

For ordinary users, the intended policy is:

- no downloadable plaintext tunnel config
- no visible backend IP inventory
- no visible topology graph
- no reusable profile export by default

The client may still know the first hop at runtime because it must open a real network connection.

That limitation is acceptable.

The design goal is not perfect secrecy on the endpoint.

The design goal is controlled delivery and anti-copy protection for ordinary usage.

## Suggested API Groups

Future API surface may include:

- `/auth`
- `/devices`
- `/subscriptions`
- `/profiles`
- `/bundles`
- `/attestation`

Example flows:

- `POST /api/v1/devices/register`
- `POST /api/v1/devices/challenge`
- `POST /api/v1/devices/verify`
- `POST /api/v1/bundles/issue`
- `POST /api/v1/bundles/rebind`
- `POST /api/v1/devices/{id}/revoke`

## Integration with Existing ONX Routing

This identity and delivery layer should sit above the current ONX routing core.

It should decide:

- whether a device may receive access
- which ingress candidates may be issued
- which transport variants may be issued
- how many devices are allowed

It should not replace:

- nodes
- links
- route policies
- balancers
- topology planner

Those remain control-plane internals.

## Immediate Implementation Recommendation

When this work starts, the first slice should be:

1. `users`
2. `subscriptions`
3. `devices`
4. configurable `device_limit`
5. app-generated device key registration
6. signed challenge flow
7. encrypted short-lived bundle issuance

Only after that should the project add:

- billing provider integration
- payment events
- more advanced mobile attestation policy
- self-service device replacement UI
