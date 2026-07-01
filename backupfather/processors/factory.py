"""Build the ordered processor chain (compress then encrypt) from settings."""

from __future__ import annotations

from backupfather.config import Compression, EncryptionMethod, Settings
from backupfather.processors.base import BackupProcessor
from backupfather.processors.compress import GzipCompressor, ZstdCompressor
from backupfather.processors.encrypt import AesEncryptor, GpgPublicKeyEncryptor


def build_processors(settings: Settings) -> list[BackupProcessor]:
    """Compression runs before encryption (compress plaintext, then encrypt)."""
    processors: list[BackupProcessor] = []

    if settings.compression is Compression.gzip:
        processors.append(GzipCompressor(level=settings.compression_level))
    elif settings.compression is Compression.zstd:
        processors.append(ZstdCompressor(level=settings.compression_level))
    # Compression.none -> no compressor.

    if settings.encryption_enabled:
        if settings.encryption_method is EncryptionMethod.gpg:
            processors.append(GpgPublicKeyEncryptor(recipient=settings.gpg_recipient))
        else:
            processors.append(AesEncryptor(passphrase=settings.aes_passphrase.get_secret_value()))

    return processors
