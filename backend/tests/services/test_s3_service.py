"""Tests for S3Service against the test S3 storage."""

import pytest
from flask import Flask

from app.exceptions import InvalidOperationException
from app.services.container import ServiceContainer


class TestS3ServiceDownloadFile:
    """Tests for S3Service.download_file()."""

    def test_download_file_missing_key_names_the_key(
        self, app: Flask, container: ServiceContainer
    ) -> None:
        """A missing object fails with an error that names its key."""
        s3_key = "tests/s3-service/missing-object.bin"
        service = container.s3_service()

        with pytest.raises(InvalidOperationException) as exc_info:
            service.download_file(s3_key)

        assert exc_info.value.cause == f"file not found: {s3_key}"
