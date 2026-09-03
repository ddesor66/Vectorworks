"""Offline RSA/SHA-256 verification and network-license binding (Python 3.9)."""
import base64
import hashlib
import hmac
import json
import re

PRODUCT = "PD-TOOLS"
SCHEMA = 1
MAX_LICENSE_BYTES = 16384
SHA256_DER_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


def canonical_payload(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def fingerprint(license_id):
    if not isinstance(license_id, str) or not license_id.strip():
        raise ValueError("Vectorworks liefert keine gueltige Lizenzkennung.")
    return hashlib.sha256(license_id.strip().encode("utf-8")).hexdigest()


def entry_checksum_valid(source, expected):
    """Validate an entry script independent of checkout line endings.

    Git keeps text files with LF but Windows checkouts commonly use CRLF.  The
    executable Python content is identical in both representations, so accept
    only the raw file or its strictly newline-normalized equivalents.
    """
    if not isinstance(source, bytes) or not isinstance(expected, str):
        return False
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        return False
    normalized_lf = source.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    normalized_crlf = normalized_lf.replace(b"\n", b"\r\n")
    digests = (
        hashlib.sha256(source).hexdigest(),
        hashlib.sha256(normalized_lf).hexdigest(),
        hashlib.sha256(normalized_crlf).hexdigest(),
    )
    return any(hmac.compare_digest(expected, digest) for digest in digests)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Doppeltes Feld in der PD-Netzwerkfreigabe.")
        result[key] = value
    return result


def read_document(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_LICENSE_BYTES:
        raise ValueError("PD-Netzwerkfreigabe hat eine ungueltige Dateigroesse.")
    document = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    if not isinstance(document, dict) or set(document) != {"payload", "signature"}:
        raise ValueError("Ungueltiges Format der PD-Netzwerkfreigabe.")
    if not isinstance(document["payload"], dict) or not isinstance(document["signature"], str):
        raise ValueError("Unvollstaendige PD-Netzwerkfreigabe.")
    return document


def signature_valid(payload, signature, modulus, exponent):
    """Strict full-block EMSA-PKCS1-v1_5 verification; no private key in runtime."""
    if not isinstance(signature, str) or not isinstance(payload, dict):
        return False
    if type(modulus) is not int or modulus.bit_length() < 2048 or exponent != 65537:
        return False
    try:
        sig = base64.b64decode(signature.encode("ascii"), validate=True)
        size = (modulus.bit_length() + 7) // 8
        if len(sig) != size:
            return False
        number = int.from_bytes(sig, "big")
        if not 0 < number < modulus:
            return False
        actual = pow(number, exponent, modulus).to_bytes(size, "big")
        digest = SHA256_DER_PREFIX + hashlib.sha256(canonical_payload(payload)).digest()
        padding = size - len(digest) - 3
        if padding < 8:
            return False
        expected = b"\x00\x01" + b"\xff" * padding + b"\x00" + digest
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, UnicodeError, OverflowError):
        return False


def validate_payload(payload, license_id, serial_series):
    expected_fields = {"schema", "product", "binding", "license_id_sha256",
                       "serial_series", "vectorworks_major"}
    if set(payload) != expected_fields or type(payload.get("schema")) is not int:
        raise ValueError("Ungueltiges Freigabeschema.")
    if payload["schema"] != SCHEMA or payload["product"] != PRODUCT:
        raise ValueError("Die Freigabe gilt nicht fuer diese PD-Tools.")
    if payload["binding"] != "vectorworks-network-license-id-sha256":
        raise ValueError("Keine Vectorworks-Netzwerkfreigabe.")
    if type(payload["vectorworks_major"]) is not int or payload["vectorworks_major"] != 2026:
        raise ValueError("Die Freigabe gilt nicht fuer Vectorworks 2026.")
    if payload["serial_series"] != "G" or serial_series != "G":
        raise ValueError("Die PD-Tools benoetigen die freigegebene G-Netzwerklizenz.")
    allowed = payload["license_id_sha256"]
    if not isinstance(allowed, str) or not re.fullmatch(r"[0-9a-f]{64}", allowed):
        raise ValueError("Ungueltige Pruefkennung in der Freigabe.")
    if not hmac.compare_digest(allowed, fingerprint(license_id)):
        raise ValueError("Diese Vectorworks-Netzwerklizenz ist fuer die PD-Tools nicht freigegeben.")


def validate_document(raw, license_id, serial_series, modulus, exponent):
    document = read_document(raw)
    if not signature_valid(document["payload"], document["signature"], modulus, exponent):
        raise ValueError("Die Signatur der PD-Netzwerkfreigabe ist ungueltig.")
    validate_payload(document["payload"], license_id, serial_series)
    return True
