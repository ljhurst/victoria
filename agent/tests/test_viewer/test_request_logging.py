from unittest.mock import patch

import pytest
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from victoria.core import observability
from victoria.viewer.request_logging import RequestLoggingMiddleware


async def _ok(request: Request):
    return PlainTextResponse("ok")


async def _missing(request: Request):
    raise HTTPException(status_code=404)


async def _boom(request: Request):
    raise RuntimeError("boom")


@pytest.fixture
def client():
    app = Starlette(
        routes=[
            Route("/healthz", _ok),
            Route("/page", _ok),
            Route("/missing", _missing),
            Route("/boom", _boom),
        ],
        middleware=[Middleware(RequestLoggingMiddleware)],
    )
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _lines(logger) -> list[tuple[str, dict]]:
    return [(c.args[0], c.kwargs) for c in logger.info.call_args_list + logger.error.call_args_list]


def test_logs_method_path_and_status(client):
    with patch.object(observability, "logger") as logger:
        client.get("/page")

    ((finished, fields),) = _lines(logger)
    assert finished == "stage finished"
    assert fields["stage"] == "request"
    assert fields["method"] == "GET"
    assert fields["path"] == "/page"
    assert fields["status"] == 200


def test_query_string_is_never_logged(client):
    with patch.object(observability, "logger") as logger:
        client.get("/page?code=secret-code&state=secret-state")

    assert "secret" not in str(logger.mock_calls)
    assert "code=" not in str(logger.mock_calls)


def test_handled_http_errors_log_their_status(client):
    with patch.object(observability, "logger") as logger:
        client.get("/missing")

    assert _lines(logger)[-1][1]["status"] == 404


def test_healthz_is_not_logged(client):
    with patch.object(observability, "logger") as logger:
        assert client.get("/healthz").status_code == 200

    assert _lines(logger) == []


def test_unhandled_exception_is_logged_as_a_failure(client):
    with patch.object(observability, "logger") as logger:
        assert client.get("/boom").status_code == 500

    (failed,) = logger.error.call_args_list
    assert failed.args == ("stage failed",)
    assert failed.kwargs["stage"] == "request"
    assert failed.kwargs["path"] == "/boom"
    assert failed.kwargs["error"] == "RuntimeError"
