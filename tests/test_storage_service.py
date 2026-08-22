import pytest

from app.services.storage_service import StorageService, StorageServiceError


class Bucket:
    def __init__(self, response: object = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[tuple[str, int]] = []

    def create_signed_url(self, path: str, ttl: int) -> object:
        self.calls.append((path, ttl))
        if self.error:
            raise self.error
        return self.response


class Storage:
    def __init__(self, bucket: Bucket) -> None:
        self.bucket = bucket
        self.names: list[str] = []

    def from_(self, name: str) -> Bucket:
        self.names.append(name)
        return self.bucket


class Client:
    def __init__(self, bucket: Bucket) -> None:
        self.storage = Storage(bucket)


async def test_storage_extracts_private_signed_url() -> None:
    bucket = Bucket({"signedURL": "https://storage.test/signed"})
    service = StorageService(Client(bucket), "private-assets", 900)
    assert await service.create_signed_url("resume/file.pdf") == "https://storage.test/signed"
    assert bucket.calls == [("resume/file.pdf", 900)]


@pytest.mark.parametrize("response", [{}, {"signedURL": ""}, None])
async def test_storage_rejects_malformed_response(response: object) -> None:
    with pytest.raises(StorageServiceError, match="storage_signed_url_failed"):
        await StorageService(Client(Bucket(response)), "bucket", 900).create_signed_url("x")


async def test_storage_hides_provider_exception() -> None:
    with pytest.raises(StorageServiceError, match="storage_signed_url_failed") as error:
        await StorageService(
            Client(Bucket(error=RuntimeError("secret provider body"))), "bucket", 900
        ).create_signed_url("x")
    assert "secret" not in str(error.value)
