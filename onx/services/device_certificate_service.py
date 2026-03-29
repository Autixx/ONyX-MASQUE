from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from onx.core.config import get_settings
from onx.db.models.device import Device
from onx.db.models.device_certificate import DeviceCertificate
from onx.services.client_device_service import client_device_service


class DeviceCertificateService:
    def __init__(self) -> None:
        self._settings = get_settings()

    def get_current_for_device(self, db: Session, *, device_id: str) -> DeviceCertificate | None:
        now = datetime.now(timezone.utc)
        return db.scalar(
            select(DeviceCertificate)
            .where(
                DeviceCertificate.device_id == device_id,
                DeviceCertificate.revoked_at.is_(None),
                DeviceCertificate.not_after > now,
            )
            .order_by(DeviceCertificate.created_at.desc())
        )

    def list_for_device(self, db: Session, *, device_id: str) -> list[DeviceCertificate]:
        return list(
            db.scalars(
                select(DeviceCertificate)
                .where(DeviceCertificate.device_id == device_id)
                .order_by(DeviceCertificate.created_at.desc())
            ).all()
        )

    def issue_for_device(
        self,
        db: Session,
        *,
        device: Device,
        csr_pem: str,
    ) -> DeviceCertificate:
        client_device_service.assert_recently_verified(device)
        csr = self._load_csr(csr_pem)
        existing = self.get_current_for_device(db, device_id=device.id)
        if (
            existing is not None
            and self._seconds_until(existing.not_after) > self._settings.lust_client_cert_renew_before_seconds
            and self._certificate_matches_csr(existing, csr)
        ):
            return existing

        ca_key, ca_cert = self._ensure_ca()
        now = datetime.now(timezone.utc)
        not_before = now - timedelta(minutes=5)
        not_after = now + timedelta(seconds=self._settings.lust_client_cert_ttl_seconds)
        serial_number = x509.random_serial_number()

        subject = x509.Name(
            [
                x509.NameAttribute(NameOID.COMMON_NAME, f"device:{device.id}"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ONyX LuST"),
            ]
        )
        builder = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(ca_cert.subject)
            .public_key(csr.public_key())
            .serial_number(serial_number)
            .not_valid_before(not_before)
            .not_valid_after(not_after)
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]),
                critical=False,
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(csr.public_key()),
                critical=False,
            )
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
                critical=False,
            )
        )
        san = self._extract_subject_alt_name(csr)
        if san is not None:
            builder = builder.add_extension(san, critical=False)
        certificate = builder.sign(private_key=ca_key, algorithm=hashes.SHA256())
        certificate_pem = certificate.public_bytes(serialization.Encoding.PEM).decode("utf-8")
        fingerprint = certificate.fingerprint(hashes.SHA256()).hex()
        subject_text = certificate.subject.rfc4514_string()

        self.revoke_for_device(db, device_id=device.id, commit=False)
        row = DeviceCertificate(
            device_id=device.id,
            serial_number_hex=format(serial_number, "x"),
            fingerprint_sha256=fingerprint,
            subject_text=subject_text,
            certificate_pem=certificate_pem,
            not_before=not_before,
            not_after=not_after,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def revoke_for_device(self, db: Session, *, device_id: str, commit: bool = True) -> int:
        now = datetime.now(timezone.utc)
        rows = list(
            db.scalars(
                select(DeviceCertificate).where(
                    DeviceCertificate.device_id == device_id,
                    DeviceCertificate.revoked_at.is_(None),
                )
            ).all()
        )
        for row in rows:
            row.revoked_at = now
            db.add(row)
        if commit:
            db.commit()
        return len(rows)

    def ca_certificate_pem(self) -> str:
        _, cert = self._ensure_ca()
        return cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")

    @staticmethod
    def serialize_certificate(certificate: DeviceCertificate) -> dict:
        return {
            "id": certificate.id,
            "device_id": certificate.device_id,
            "serial_number_hex": certificate.serial_number_hex,
            "fingerprint_sha256": certificate.fingerprint_sha256,
            "subject_text": certificate.subject_text,
            "certificate_pem": certificate.certificate_pem,
            "not_before": certificate.not_before,
            "not_after": certificate.not_after,
            "revoked_at": certificate.revoked_at,
            "created_at": certificate.created_at,
            "updated_at": certificate.updated_at,
        }

    def _ensure_ca(self) -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
        pki_dir = Path(self._settings.lust_pki_dir).expanduser().resolve()
        pki_dir.mkdir(parents=True, exist_ok=True)
        key_path = pki_dir / "lust-client-ca.key.pem"
        cert_path = pki_dir / "lust-client-ca.cert.pem"
        if key_path.exists() and cert_path.exists():
            key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
            cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
            return key, cert

        key = ec.generate_private_key(ec.SECP256R1())
        subject = x509.Name(
            [
                x509.NameAttribute(NameOID.COMMON_NAME, "ONyX LuST Client CA"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ONyX"),
            ]
        )
        now = datetime.now(timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_encipherment=False,
                    content_commitment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
                critical=False,
            )
            .sign(private_key=key, algorithm=hashes.SHA256())
        )
        key_path.write_bytes(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        return key, cert

    @staticmethod
    def _load_csr(csr_pem: str) -> x509.CertificateSigningRequest:
        try:
            csr = x509.load_pem_x509_csr(csr_pem.encode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid CSR.") from exc
        if hasattr(csr, "is_signature_valid") and not csr.is_signature_valid:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="CSR signature is invalid.")
        return csr

    @staticmethod
    def _extract_subject_alt_name(csr: x509.CertificateSigningRequest) -> x509.SubjectAlternativeName | None:
        try:
            return csr.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        except x509.ExtensionNotFound:
            return None

    @staticmethod
    def _certificate_matches_csr(existing: DeviceCertificate, csr: x509.CertificateSigningRequest) -> bool:
        try:
            certificate = x509.load_pem_x509_certificate(existing.certificate_pem.encode("utf-8"))
        except Exception:  # noqa: BLE001
            return False
        existing_spki = certificate.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        csr_spki = csr.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return existing_spki == csr_spki

    @staticmethod
    def _seconds_until(value: datetime | None) -> int:
        if value is None:
            return 0
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return int((value - datetime.now(timezone.utc)).total_seconds())


device_certificate_service = DeviceCertificateService()
