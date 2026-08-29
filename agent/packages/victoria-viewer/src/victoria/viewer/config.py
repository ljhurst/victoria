from functools import lru_cache

from aws_lambda_powertools.utilities import parameters
from pydantic import Field
from pydantic_settings import BaseSettings


class ViewerSettings(BaseSettings):
    wiki_bucket: str = Field(validation_alias="WIKI_BUCKET")
    lasso_issuer_url: str = Field(validation_alias="LASSO_ISSUER_URL")
    viewer_base_url: str = Field(validation_alias="VIEWER_BASE_URL")
    lasso_client_id: str = Field(default="victoria-viewer", validation_alias="LASSO_CLIENT_ID")

    # The OAuth resource indicator Lasso audience-binds tokens to. In prod
    # it's just viewer_base_url; local dev sets it to the deployed viewer URL
    # (the value actually registered in Lasso) while viewer_base_url stays
    # localhost for the redirect and cookie.
    resource_url: str | None = Field(default=None, validation_alias="VIEWER_RESOURCE_URL")

    # In Lambda, the signing key lives in SSM (SecureString); for local dev,
    # set VIEWER_SESSION_SECRET directly so there's no AWS call.
    session_secret_param: str | None = Field(
        default=None, validation_alias="VIEWER_SESSION_SECRET_SSM_PARAM"
    )
    session_secret: str | None = Field(default=None, validation_alias="VIEWER_SESSION_SECRET")

    @property
    def resource_indicator(self) -> str:
        return self.resource_url or self.viewer_base_url

    @property
    def redirect_uri(self) -> str:
        return f"{self.viewer_base_url.rstrip('/')}/auth/callback"

    @property
    def https_only(self) -> bool:
        return self.viewer_base_url.startswith("https://")


@lru_cache(maxsize=1)
def get_viewer_settings() -> ViewerSettings:
    return ViewerSettings()


@lru_cache(maxsize=1)
def get_session_secret() -> str:
    settings = get_viewer_settings()
    if settings.session_secret:
        return settings.session_secret
    if settings.session_secret_param:
        return parameters.get_parameter(settings.session_secret_param, decrypt=True)
    raise RuntimeError("set VIEWER_SESSION_SECRET or VIEWER_SESSION_SECRET_SSM_PARAM")
