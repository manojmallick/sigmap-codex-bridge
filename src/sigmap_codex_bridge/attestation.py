"""Versioned HMAC provenance attestations for retained JSON evidence."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Mapping


ATTESTATION_SCHEMA_VERSION = 1
ATTESTATION_ALGORITHM = "hmac-sha256"


class AttestationError(ValueError):
    """Raised when an attestation cannot be created or verified safely."""


def canonical_json(value: object) -> bytes:
    """Return the stable UTF-8 JSON representation covered by signatures."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise AttestationError(f"payload is not canonical JSON: {error}") from error


def payload_sha256(payload: object) -> str:
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def _checked_key(key: bytes) -> bytes:
    if len(key) < 32:
        raise AttestationError("HMAC key must contain at least 32 bytes")
    return key


def sign_attestation(
    payload: Mapping[str, object], *, key: bytes, key_id: str
) -> dict[str, object]:
    """Create a deterministic, versioned envelope around a JSON object."""

    if not key_id.strip():
        raise AttestationError("key_id must be non-empty")
    unsigned: dict[str, object] = {
        "attestation_schema_version": ATTESTATION_SCHEMA_VERSION,
        "algorithm": ATTESTATION_ALGORITHM,
        "key_id": key_id,
        "payload_sha256": payload_sha256(payload),
        "payload": dict(payload),
    }
    signature = hmac.new(
        _checked_key(key), canonical_json(unsigned), hashlib.sha256
    ).hexdigest()
    return {**unsigned, "signature": signature}


def verify_attestation(
    value: Mapping[str, object],
    *,
    key: bytes | None,
    require_signed: bool = True,
    expected_key_id: str | None = None,
    expected_payload_sha256: str | None = None,
) -> dict[str, object]:
    """Verify an envelope while returning its retained payload on failure."""

    signed = "signature" in value
    payload = value.get("payload") if signed else dict(value)
    result: dict[str, object] = {
        "valid": False,
        "signed": signed,
        "payload": payload,
    }
    if not signed:
        if require_signed:
            return {**result, "error": "signed attestation required"}
        return {**result, "valid": True, "error": None}
    required = {
        "attestation_schema_version",
        "algorithm",
        "key_id",
        "payload_sha256",
        "payload",
        "signature",
    }
    if set(value) != required:
        return {**result, "error": "attestation fields do not match schema v1"}
    if value.get("attestation_schema_version") != ATTESTATION_SCHEMA_VERSION:
        return {**result, "error": "unsupported attestation schema version"}
    if value.get("algorithm") != ATTESTATION_ALGORITHM:
        return {**result, "error": "unsupported attestation algorithm"}
    if not isinstance(payload, Mapping):
        return {**result, "error": "attestation payload must be an object"}
    key_id = value.get("key_id")
    if not isinstance(key_id, str) or not key_id:
        return {**result, "error": "invalid key identity"}
    if expected_key_id is not None and key_id != expected_key_id:
        return {**result, "error": "attestation key identity mismatch"}
    actual_payload_hash = payload_sha256(payload)
    if value.get("payload_sha256") != actual_payload_hash:
        return {**result, "error": "attestation payload hash mismatch"}
    if (
        expected_payload_sha256 is not None
        and actual_payload_hash != expected_payload_sha256
    ):
        return {**result, "error": "attestation subject mismatch"}
    if key is None:
        return {**result, "error": "verification key is required"}
    unsigned = {name: value[name] for name in required if name != "signature"}
    expected_signature = hmac.new(
        _checked_key(key), canonical_json(unsigned), hashlib.sha256
    ).hexdigest()
    signature = value.get("signature")
    if not isinstance(signature, str) or not hmac.compare_digest(
        signature, expected_signature
    ):
        return {**result, "error": "attestation signature mismatch"}
    return {
        **result,
        "valid": True,
        "error": None,
        "algorithm": ATTESTATION_ALGORITHM,
        "key_id": key_id,
        "payload_sha256": actual_payload_hash,
    }


def read_json_object(path: str | Path) -> dict[str, object]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AttestationError(f"cannot read JSON object {path}: {error}") from error
    if not isinstance(value, dict):
        raise AttestationError("attestation input must be a JSON object")
    return value


def read_key(path: str | Path) -> bytes:
    try:
        return _checked_key(Path(path).read_bytes())
    except OSError as error:
        raise AttestationError(f"cannot read key {path}: {error}") from error


def write_json(path: str | Path, value: Mapping[str, object]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise AttestationError(f"cannot write attestation {output}: {error}") from error
