import os

import pytest


@pytest.fixture(autouse=True)
def aws_credentials():
    """Dummy credentials so botocore's signing step succeeds before moto
    intercepts the request — moto needs *some* credentials present, real
    ones aren't required since no request ever reaches AWS."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    os.environ.setdefault("WIKI_BUCKET", "victoria-test")
