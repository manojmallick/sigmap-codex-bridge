# Provenance attestations and threat model

Version 1 attestations wrap one JSON object in a canonical, signed envelope. The
supported algorithm is `hmac-sha256`; keys must contain at least 32 bytes. The key
identifier is signed metadata, not a secret.

```bash
sigmap-bridge provenance sign report.json report.attestation.json \
  --key-file /secure/path/release.key --key-id release-2026 --json

sigmap-bridge provenance verify report.attestation.json \
  --key-file /secure/path/release.key \
  --expected-key-id release-2026 \
  --expected-payload-sha256 EXPECTED_SHA256 --json
```

The signature covers the schema version, algorithm, key identity, canonical payload,
and canonical payload SHA-256. Verification rejects changed payloads, changed signed
metadata, unsupported algorithms or versions, unexpected keys or subjects, malformed
envelopes, and unsigned values when a signature is required. Verification returns the
retained payload even on failure so invalid provenance does not hide raw evidence.

## Threat boundaries

| Threat | Behavior |
|---|---|
| File or metadata tampering | Detected by payload hash and HMAC verification. |
| Wrong key or algorithm | Fails closed. |
| Unsigned input | Fails when `require_signed=True`; may be explicitly accepted as legacy input otherwise. |
| Replay | A signature alone cannot detect replay. Verifiers must pin the expected payload SHA-256 and key identity, and apply their own experiment/time policy. |
| Key compromise | Anyone holding the shared HMAC key can forge attestations. Rotate the key identity, revoke the old key operationally, and re-attest trusted payloads. |
| Non-repudiation | Not provided. HMAC is symmetric; every verifier holding the key can also sign. |
| Host compromise | Not prevented. An attacker controlling the process or key file can sign arbitrary data. |
| Confidentiality | Not provided. Payloads remain readable JSON. |

Keep keys outside the repository, restrict filesystem access, distribute them through
an independent secret channel, and never print them in CI logs. Public-key signatures
are a possible future schema with a different algorithm identifier; they are not
silently substituted into v1.
