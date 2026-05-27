from __future__ import annotations

import logging
import os
from functools import lru_cache

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _infisical_client():
    """Lazily create and authenticate the Infisical SDK client.

    Uses Universal Auth with machine identity credentials.
    Called at most once per process lifetime.
    """
    from infisical_sdk import InfisicalSDKClient

    host = os.environ.get("INFISICAL_HOST", "https://app.infisical.com")
    client = InfisicalSDKClient(host=host, cache_ttl=300)

    # Try Universal Auth first
    client_id = os.environ.get("INFISICAL_CLIENT_ID")
    client_secret = os.environ.get("INFISICAL_CLIENT_SECRET")

    if client_id and client_secret:
        client.auth.universal_auth.login(
            client_id=client_id,
            client_secret=client_secret,
        )
        logger.info("Infisical: authenticated via Universal Auth")
    else:
        token = os.environ.get("INFISICAL_TOKEN")
        if token:
            client.auth.token_auth.login(token=token)
            logger.info("Infisical: authenticated via token")
        else:
            logger.warning(
                "Infisical: no credentials found. Set INFISICAL_CLIENT_ID + "
                "INFISICAL_CLIENT_SECRET for Universal Auth, or INFISICAL_TOKEN."
            )
            return None

    return client


@lru_cache(maxsize=128)
def get_secret(name: str) -> str | None:
    """Fetch a single secret from Infisical by name."""
    client = _infisical_client()
    if not client:
        return None

    project_id = os.environ.get("INFISICAL_PROJECT_ID")
    if not project_id:
        logger.warning("Infisical: INFISICAL_PROJECT_ID not set")
        return None

    env_slug = os.environ.get("INFISICAL_ENV", "dev")
    path = os.environ.get("INFISICAL_PATH", "/")

    try:
        resp = client.secrets.get_secret_by_name(
            secret_name=name,
            project_id=project_id,
            environment_slug=env_slug,
            secret_path=path,
        )
        return resp.secretValue
    except Exception as exc:
        logger.debug("Infisical: failed to fetch secret %s: %s", name, exc)
        return None


def list_secrets() -> dict[str, str]:
    """Fetch all secrets from Infisical and return as a flat dict."""
    client = _infisical_client()
    if not client:
        return {}

    project_id = os.environ.get("INFISICAL_PROJECT_ID")
    if not project_id:
        logger.warning("Infisical: INFISICAL_PROJECT_ID not set")
        return {}

    env_slug = os.environ.get("INFISICAL_ENV", "dev")
    path = os.environ.get("INFISICAL_PATH", "/")

    try:
        resp = client.secrets.list_secrets(
            project_id=project_id,
            environment_slug=env_slug,
            secret_path=path,
        )
        return {s.secretKey: s.secretValue for s in resp.secrets}
    except Exception as exc:
        logger.error("Infisical: failed to list secrets: %s", exc)
        return {}


def inject_secrets_into_env() -> int:
    """Fetch all secrets from Infisical and inject them as environment variables.

    Only sets env vars that are NOT already set, so local .env overrides
    or explicit exports take precedence.

    Returns the number of secrets injected.
    """
    secrets = list_secrets()
    injected = 0

    for key, value in secrets.items():
        if key not in os.environ and value:
            os.environ[key] = value
            injected += 1

    if injected:
        logger.info(
            "Infisical: injected %d secrets into environment (out of %d total)",
            injected,
            len(secrets),
        )
    return injected
