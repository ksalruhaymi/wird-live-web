"""Apple App Store purchase verification (signed JWS + optional Server API)."""

from __future__ import annotations

import base64
import json
import logging
import time
from pathlib import Path
from typing import Any

import jwt
import requests
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding
from django.conf import settings

from apps.subscription.store_verification.catalog import (
    PRODUCT_KIND_CONSUMABLE,
    expected_product_id,
    minutes_from_product_id,
)
from apps.subscription.store_verification.types import (
    StoreVerificationError,
    VerifiedStorePurchase,
)

logger = logging.getLogger(__name__)

# Apple Root CA - G3 (public). Source: https://www.apple.com/certificateauthority/
_APPLE_ROOT_CA_G3_PEM = b"""-----BEGIN CERTIFICATE-----
MIICQzCCAcmgAwIBAgIILcX8iNLFS5UwCgYIKoZIzj0EAwMwZzEbMBkGA1UEAwwS
QXBwbGUgUm9vdCBDQSAtIEczMSYwJAYDVQQLDB1BcHBsZSBDZXJ0aWZpY2F0aW9u
IEF1dGhvcml0eTETMBEGA1UECgwKQXBwbGUgSW5jLjELMAkGA1UEBhMCVVMwHhcN
MTQwNDMwMTgxOTA2WhcNMzkwNDMwMTgxOTA2WjBnMRswGQYDVQQDDBJBcHBsZSBS
b290IENBIC0gRzMxJjAkBgNVBAsMHUFwcGxlIENlcnRpZmljYXRpb24gQXV0aG9y
aXR5MRMwEQYDVQQKDApBcHBsZSBJbmMuMQswCQYDVQQGEwJVUzB2MBAGByqGSM49
AgEGBSuBBAAiA2IABJjpLz1AcqTtkyJygRMc3RCV8cWjTnHcFBbZDuWmBSp3ZHtf
TjjTuxxEtX/1H7YyYl3J6YRbTzBPEVoA/VhYDKX1DyxNB0cTddqXl5dvMVztK517
IDvYuVTZXpmkOlEKMaNCMEAwHQYDVR0OBBYEFLuw3qFYM4iapIqZ3r6966/ayySr
MA8GA1UdEwEB/wQFMAMBAf8wDgYDVR0PAQH/BAQDAgEGMAoGCCqGSM49BAMDA2gA
MGUCMQCD6cHEFl4aXTQY2e3v9GwOAEZLuN+yRhHFD/3meoyhpmvOwgPUnPWTxnS4
at+qIxUCMG1mihDK1A3UT82NQz60imOlM27jbdoXt2QfyFMm+YhidDkLF1vLUagM
6BgD56KyKA==
-----END CERTIFICATE-----
"""

_APPLE_ROOT = x509.load_pem_x509_certificate(_APPLE_ROOT_CA_G3_PEM)

_PRODUCTION_API = "https://api.storekit.itunes.apple.com"
_SANDBOX_API = "https://api.storekit-sandbox.itunes.apple.com"


def _b64url_decode(segment: str) -> bytes:
    pad = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + pad)


def _load_certs_from_x5c(x5c: list[str]) -> list[x509.Certificate]:
    certs: list[x509.Certificate] = []
    for item in x5c:
        der = base64.b64decode(item)
        certs.append(x509.load_der_x509_certificate(der))
    return certs


def _verify_cert_signed(child: x509.Certificate, issuer: x509.Certificate) -> None:
    pub = issuer.public_key()
    hash_alg = child.signature_hash_algorithm or hashes.SHA256()
    try:
        if isinstance(pub, ec.EllipticCurvePublicKey):
            pub.verify(
                child.signature,
                child.tbs_certificate_bytes,
                ec.ECDSA(hash_alg),
            )
        else:
            pub.verify(
                child.signature,
                child.tbs_certificate_bytes,
                padding.PKCS1v15(),
                hash_alg,
            )
    except (InvalidSignature, TypeError, ValueError) as exc:
        raise StoreVerificationError("سلسلة شهادات Apple غير صالحة.") from exc


def _verify_x5c_chain(certs: list[x509.Certificate]) -> x509.Certificate:
    if not certs:
        raise StoreVerificationError("شهادة توقيع Apple مفقودة.")
    # certs[0] = leaf (signs the JWS), then intermediate(s), root may be omitted.
    for i in range(len(certs) - 1):
        _verify_cert_signed(certs[i], certs[i + 1])
    # Last cert must be Apple Root CA - G3, or signed by it.
    last = certs[-1]
    if last.fingerprint(hashes.SHA256()) == _APPLE_ROOT.fingerprint(hashes.SHA256()):
        return certs[0]
    _verify_cert_signed(last, _APPLE_ROOT)
    return certs[0]


def decode_and_verify_signed_transaction(jws: str) -> dict[str, Any]:
    """Verify StoreKit 2 signed transaction JWS and return payload claims."""
    token = (jws or "").strip()
    parts = token.split(".")
    if len(parts) != 3:
        raise StoreVerificationError(
            "بيانات التحقق من Apple غير صالحة (توقّع JWS مطلوب)."
        )

    try:
        header = json.loads(_b64url_decode(parts[0]))
    except (json.JSONDecodeError, ValueError) as exc:
        raise StoreVerificationError("ترويسة توقيع Apple غير صالحة.") from exc

    x5c = header.get("x5c")
    if not isinstance(x5c, list) or not x5c:
        raise StoreVerificationError("شهادة توقيع Apple (x5c) مفقودة.")

    leaf = _verify_x5c_chain(_load_certs_from_x5c(x5c))
    public_key = leaf.public_key()
    try:
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["ES256"],
            options={
                "verify_aud": False,
                "require": ["productId", "transactionId", "bundleId"],
            },
        )
    except jwt.PyJWTError as exc:
        raise StoreVerificationError("فشل التحقق من توقيع عملية Apple.") from exc

    if not isinstance(claims, dict):
        raise StoreVerificationError("حمولة عملية Apple غير صالحة.")
    return claims


def _normalize_environment(raw: str) -> str:
    value = (raw or "").strip().lower()
    if value in {"sandbox", "xcode"}:
        return "sandbox"
    if value == "production":
        return "production"
    raise StoreVerificationError(f"بيئة Apple غير معروفة: {raw}")


def _apple_api_configured() -> bool:
    return bool(
        (getattr(settings, "APPLE_ISSUER_ID", "") or "").strip()
        and (getattr(settings, "APPLE_KEY_ID", "") or "").strip()
        and (
            (getattr(settings, "APPLE_PRIVATE_KEY_PATH", "") or "").strip()
            or (getattr(settings, "APPLE_PRIVATE_KEY", "") or "").strip()
        )
    )


def _load_apple_private_key() -> str:
    inline = (getattr(settings, "APPLE_PRIVATE_KEY", "") or "").strip()
    if inline:
        return inline.replace("\\n", "\n")
    path = (getattr(settings, "APPLE_PRIVATE_KEY_PATH", "") or "").strip()
    if not path:
        raise StoreVerificationError("مفتاح App Store Server API غير مضبوط.")
    return Path(path).read_text(encoding="utf-8")


def _app_store_server_token(*, bundle_id: str) -> str:
    now = int(time.time())
    payload = {
        "iss": settings.APPLE_ISSUER_ID.strip(),
        "iat": now,
        "exp": now + 1200,
        "aud": "appstoreconnect-v1",
        "bid": bundle_id,
    }
    headers = {"alg": "ES256", "kid": settings.APPLE_KEY_ID.strip(), "typ": "JWT"}
    return jwt.encode(payload, _load_apple_private_key(), algorithm="ES256", headers=headers)


def fetch_transaction_from_server_api(
    *,
    transaction_id: str,
    environment: str,
    bundle_id: str,
) -> dict[str, Any]:
    """Cross-check transaction via App Store Server API Get Transaction Info."""
    base = _SANDBOX_API if environment == "sandbox" else _PRODUCTION_API
    url = f"{base}/inApps/v1/transactions/{transaction_id}"
    token = _app_store_server_token(bundle_id=bundle_id)
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    if response.status_code == 404 and environment == "production":
        # Retry sandbox once (common during TestFlight / Sandbox).
        return fetch_transaction_from_server_api(
            transaction_id=transaction_id,
            environment="sandbox",
            bundle_id=bundle_id,
        )
    if response.status_code != 200:
        raise StoreVerificationError(
            f"فشل استعلام App Store Server API ({response.status_code})."
        )
    body = response.json()
    signed = body.get("signedTransactionInfo")
    if not isinstance(signed, str) or not signed.strip():
        raise StoreVerificationError("استجابة App Store Server API ناقصة.")
    return decode_and_verify_signed_transaction(signed)


def verify_apple_purchase(
    *,
    minutes: int,
    purchase_token: str,
    store_product_id: str = "",
    transaction_reference: str = "",
    expected_environment: str,
) -> VerifiedStorePurchase:
    """
    Verify an Apple consumable minute-package purchase.

    Requires the StoreKit signed transaction JWS in ``purchase_token``.
    When App Store Server API credentials are configured, also fetches the
    transaction from Apple to confirm status / revocation.
    """
    token = (purchase_token or "").strip()
    if not token:
        raise StoreVerificationError(
            "بيانات التحقق من App Store مطلوبة (signed transaction)."
        )

    claims = decode_and_verify_signed_transaction(token)
    if _apple_api_configured():
        try:
            env_hint = _normalize_environment(str(claims.get("environment") or "Sandbox"))
            claims = fetch_transaction_from_server_api(
                transaction_id=str(claims.get("transactionId") or "").strip(),
                environment=env_hint,
                bundle_id=str(claims.get("bundleId") or settings.APPLE_BUNDLE_ID),
            )
        except StoreVerificationError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("App Store Server API cross-check failed: %s", exc)
            raise StoreVerificationError(
                "تعذّر التحقق عبر App Store Server API."
            ) from exc

    bundle_id = str(claims.get("bundleId") or "").strip()
    expected_bundle = (getattr(settings, "APPLE_BUNDLE_ID", "") or "com.kslabs.wirdlive").strip()
    if bundle_id != expected_bundle:
        raise StoreVerificationError("معرّف حزمة Apple غير مطابق للتطبيق.")

    product_id = str(claims.get("productId") or "").strip()
    expected = expected_product_id(minutes=minutes, payment_method="app_store")
    client_sku = (store_product_id or "").strip()
    if product_id != expected:
        raise StoreVerificationError("معرّف منتج Apple لا يطابق باقة الدقائق.")
    if client_sku and client_sku != product_id:
        raise StoreVerificationError("معرّف منتج Apple المرسل لا يطابق عملية المتجر.")

    parsed_minutes = minutes_from_product_id(product_id)
    if parsed_minutes != int(minutes):
        raise StoreVerificationError("عدد دقائق منتج Apple لا يطابق الباقة.")

    tx_type = str(claims.get("type") or "").strip()
    if tx_type and tx_type != "Consumable":
        raise StoreVerificationError(
            "نوع منتج Apple يجب أن يكون Consumable لباقات الدقائق."
        )

    environment = _normalize_environment(str(claims.get("environment") or ""))
    if environment != expected_environment:
        raise StoreVerificationError(
            f"بيئة شراء Apple ({environment}) لا تطابق بيئة الخادم ({expected_environment})."
        )

    if claims.get("revocationDate"):
        raise StoreVerificationError("عملية شراء Apple ملغاة أو مستردة.")

    transaction_id = str(claims.get("transactionId") or "").strip()
    if not transaction_id:
        raise StoreVerificationError("معرّف عملية Apple مفقود.")

    client_tx = (transaction_reference or "").strip()
    if client_tx and client_tx not in {
        transaction_id,
        str(claims.get("originalTransactionId") or "").strip(),
    }:
        logger.info(
            "Apple client transaction_reference differs from verified id "
            "(client=%s verified=%s)",
            client_tx,
            transaction_id,
        )

    return VerifiedStorePurchase(
        payment_method="app_store",
        product_id=product_id,
        transaction_id=transaction_id,
        environment=environment,
        product_kind=PRODUCT_KIND_CONSUMABLE,
        package_or_bundle_id=bundle_id,
        minutes=int(minutes),
        raw=claims,
    )
