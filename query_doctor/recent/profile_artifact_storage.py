"""Raw-free storage lifecycle contract for Recent profile artifacts."""

from __future__ import annotations

from dataclasses import dataclass


PROFILE_ARTIFACT_STORAGE_KIND_FINGERPRINT_ONLY = "fingerprint_only"
PROFILE_ARTIFACT_LEGACY_STORAGE_KIND_LOCAL = "local"
PROFILE_ARTIFACT_STORAGE_KIND_OBJECT = "object"


@dataclass(frozen=True)
class ProfileArtifactStorageLifecycle:
    storage_kind: str
    stores_profile_bytes: bool
    deletion_required: bool
    deletion_supported: bool
    deletion_action: str

    def safe_payload(self) -> dict[str, object]:
        return {
            "storage_kind": self.storage_kind,
            "stores_profile_bytes": self.stores_profile_bytes,
            "deletion_required": self.deletion_required,
            "deletion_supported": self.deletion_supported,
            "deletion_action": self.deletion_action,
        }


FINGERPRINT_ONLY_LIFECYCLE = ProfileArtifactStorageLifecycle(
    storage_kind=PROFILE_ARTIFACT_STORAGE_KIND_FINGERPRINT_ONLY,
    stores_profile_bytes=False,
    deletion_required=False,
    deletion_supported=True,
    deletion_action="metadata_only",
)


def canonical_profile_artifact_storage_kind(value: object) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    if not text or text == PROFILE_ARTIFACT_LEGACY_STORAGE_KIND_LOCAL:
        return PROFILE_ARTIFACT_STORAGE_KIND_FINGERPRINT_ONLY
    return text[:64]


def profile_artifact_storage_lifecycle(
    storage_kind: object,
) -> ProfileArtifactStorageLifecycle | None:
    canonical = canonical_profile_artifact_storage_kind(storage_kind)
    if canonical == PROFILE_ARTIFACT_STORAGE_KIND_FINGERPRINT_ONLY:
        return FINGERPRINT_ONLY_LIFECYCLE
    return None


def profile_artifact_storage_metadata_allowed(*, storage_kind: object, storage_key: object) -> bool:
    lifecycle = profile_artifact_storage_lifecycle(storage_kind)
    if lifecycle is None:
        return False
    key = str(storage_key or "").strip()
    if not key:
        return False
    if "/" in key or "\\" in key or ":" in key:
        return False
    return lifecycle.storage_kind == PROFILE_ARTIFACT_STORAGE_KIND_FINGERPRINT_ONLY
