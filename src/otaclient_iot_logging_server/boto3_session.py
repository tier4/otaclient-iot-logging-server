# Copyright 2022 TIER IV, INC. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from __future__ import annotations

import json
import logging
import ssl
import subprocess
from http import HTTPStatus
from pathlib import Path
from typing import Any, Dict, Optional

import urllib3
from awscrt.http import HttpClientConnection, HttpRequest
from awscrt.io import (
    ClientBootstrap,
    ClientTlsContext,
    DefaultHostResolver,
    EventLoopGroup,
    Pkcs11Lib,
    TlsContextOptions,
)
from boto3 import Session
from botocore.credentials import DeferredRefreshableCredentials
from botocore.session import get_session as get_botocore_session

from otaclient_iot_logging_server._utils import parse_pkcs11_uri
from otaclient_iot_logging_server.greengrass_config import (
    IoTSessionConfig,
    PKCS11Config,
)

logger = logging.getLogger(__name__)

_AWSCRT_TIMEOUT_SEC = 10

#
# ------ certificate loading helpers ------ #
#


def _load_pkcs11_cert(
    pkcs11_lib: str,
    slot_id: str,
    private_key_label: str,
    user_pin: Optional[str] = None,
) -> bytes:
    """Load certificate from a pkcs11 interface(backed by a TPM2.0 chip).

    This function requires opensc and libtpm2-pkcs11-1 to be installed,
        and a properly setup and working TPM2.0 chip.
    """
    # fmt: off
    _cmd = [
        "/usr/bin/pkcs11-tool",
        "--module", pkcs11_lib,
        "--type", "cert",
        "--slot", slot_id,
        "--label", private_key_label,
        "--read-object",
    ]
    if user_pin:
        _cmd.extend(["--pin", user_pin])
    # fmt: on
    return subprocess.check_output(_cmd)


def _convert_to_pem(_data: bytes) -> bytes:
    """Unconditionally convert input cert to PEM format."""
    if _data.startswith(b"-----BEGIN CERTIFICATE-----"):
        return _data
    # the input _data represents a DER format cert
    return ssl.DER_cert_to_PEM_cert(_data).encode()


def _load_certificate(cert_path: str, pkcs11_cfg: Optional[PKCS11Config]) -> bytes:
    """
    NOTE: Only PEM format cert is supported.
    """
    if cert_path.startswith("pkcs11"):
        assert pkcs11_cfg, (
            "certificate is provided by pkcs11, but no pkcs11_cfg is not available"
        )

        _parsed_cert_uri = parse_pkcs11_uri(cert_path)
        # NOTE: the cert pull from pkcs11 interface is in DER format
        return _convert_to_pem(
            _load_pkcs11_cert(
                pkcs11_lib=pkcs11_cfg.pkcs11_lib,
                slot_id=pkcs11_cfg.slot_id,
                private_key_label=_parsed_cert_uri["object"],
                user_pin=pkcs11_cfg.user_pin,
            )
        )
    return _convert_to_pem(Path(cert_path).read_bytes())


#
# ------ credential fetching ------ #
#
# AWS IoT Core Credential Provider API:
#   https://docs.aws.amazon.com/iot/latest/developerguide/authorizing-direct-aws.html


def _parse_credentials_response(
    response_status: int,
    response_body: bytes,
    credential_url: str,
) -> Dict[str, Any]:
    """Parse credential provider response, raising on non-200 status."""
    if response_status != HTTPStatus.OK:
        logger.error(
            "Failed to get credentials from %s: status=%s, body=%s",
            credential_url,
            response_status,
            response_body.decode(),
        )
        raise ValueError(
            f"Error getting credentials from IoT credential provider: "
            f"status={response_status}"
        )
    credentials = json.loads(response_body.decode())["credentials"]
    return {
        "access_key": credentials["accessKeyId"],
        "secret_key": credentials["secretAccessKey"],
        "token": credentials["sessionToken"],
        "expiry_time": credentials["expiration"],
    }


def _fetch_iot_credentials(
    endpoint: str,
    role_alias: str,
    thing_name: str,
    cert_path: str,
    key_path: str,
) -> Dict[str, Any]:
    """Fetch IAM credentials from AWS IoT Core Credential Provider via mTLS.

    Uses urllib3 with client certificate file paths directly.

    Args:
        endpoint: AWS IoT credential provider endpoint FQDN.
        role_alias: IoT Role Alias name.
        thing_name: IoT Thing Name.
        cert_path: Path to the client certificate PEM file.
        key_path: Path to the private key file.

    Returns:
        Credentials dict with access_key, secret_key, token, expiry_time.
    """
    url = f"https://{endpoint}/role-aliases/{role_alias}/credentials"
    http = urllib3.PoolManager(cert_file=cert_path, key_file=key_path)
    response = http.request(
        "GET",
        url,
        headers={"x-amzn-iot-thingname": thing_name},
    )
    return _parse_credentials_response(response.status, response.data, url)


def _fetch_iot_credentials_pkcs11(
    endpoint: str,
    role_alias: str,
    thing_name: str,
    cert_pem: bytes,
    pkcs11_cfg: PKCS11Config,
    private_key_label: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch IAM credentials using PKCS#11 for private key operations via awscrt.

    awscrt is required here because urllib3 does not support PKCS#11.

    Args:
        endpoint: AWS IoT credential provider endpoint FQDN.
        role_alias: IoT Role Alias name.
        thing_name: IoT Thing Name.
        cert_pem: Client certificate in PEM format (bytes).
        pkcs11_cfg: PKCS#11 configuration.
        private_key_label: Label of the private key in the PKCS#11 store.

    Returns:
        Credentials dict with access_key, secret_key, token, expiry_time.
    """
    tls_ctx_opt = TlsContextOptions.create_client_with_mtls_pkcs11(
        pkcs11_lib=Pkcs11Lib(file=pkcs11_cfg.pkcs11_lib),
        user_pin=pkcs11_cfg.user_pin,
        slot_id=int(pkcs11_cfg.slot_id),
        token_label=None,  # type: ignore[arg-type]
        private_key_label=private_key_label,  # type: ignore[arg-type]
        cert_file_path=None,  # type: ignore[arg-type]
        cert_file_contents=cert_pem,
    )

    path = f"/role-aliases/{role_alias}/credentials"
    url = f"https://{endpoint}{path}"

    event_loop_group = EventLoopGroup()
    host_resolver = DefaultHostResolver(event_loop_group)
    bootstrap = ClientBootstrap(event_loop_group, host_resolver)

    tls_ctx = ClientTlsContext(tls_ctx_opt)
    tls_conn_opt = tls_ctx.new_connection_options()
    tls_conn_opt.set_server_name(endpoint)

    connection = HttpClientConnection.new(
        host_name=endpoint,
        port=443,
        bootstrap=bootstrap,
        tls_connection_options=tls_conn_opt,
    ).result(_AWSCRT_TIMEOUT_SEC)

    request = HttpRequest("GET", path)
    request.headers.add("host", endpoint)
    request.headers.add("x-amzn-iot-thingname", thing_name)

    response_status_code: int = 0
    response_body = bytearray()

    def on_response(
        _http_stream: Any, status_code: int, _headers: Any, **_kwargs: Any
    ) -> None:
        nonlocal response_status_code
        response_status_code = status_code

    def on_body(_http_stream: Any, chunk: bytes, **_kwargs: Any) -> None:
        response_body.extend(chunk)

    stream = connection.request(request, on_response, on_body)
    stream.activate()
    stream.completion_future.result(_AWSCRT_TIMEOUT_SEC)

    return _parse_credentials_response(response_status_code, bytes(response_body), url)


#
# ------ session creating helpers ------ #
#


def _create_boto3_session(region: str, refresh_func: Any) -> Session:
    """Create a boto3 Session with auto-refreshing credentials.

    Args:
        region: AWS region name.
        refresh_func: Callable that returns credentials dict.

    Returns:
        boto3 Session with refreshable credentials.
    """
    botocore_session = get_botocore_session()
    botocore_session._credentials = DeferredRefreshableCredentials(  # type: ignore[attr-defined]
        method="custom-iot-core-credential-provider",
        refresh_using=refresh_func,
    )
    botocore_session.set_config_variable("region", region)

    return Session(botocore_session=botocore_session)


def _get_session(config: IoTSessionConfig) -> Session:
    """Get a session that using plain privkey."""

    def _refresh():
        return _fetch_iot_credentials(
            endpoint=config.aws_credential_provider_endpoint,
            role_alias=config.aws_role_alias,
            thing_name=config.thing_name,
            cert_path=config.certificate_path,
            key_path=config.private_key_path,
        )

    return _create_boto3_session(config.region, _refresh)


def _get_session_pkcs11(config: IoTSessionConfig) -> Session:
    """Get a session backed by privkey provided by pkcs11."""
    assert (pkcs11_cfg := config.pkcs11_config), (
        "privkey is provided by pkcs11, but pkcs11_config is not available"
    )

    cert_pem = _load_certificate(config.certificate_path, config.pkcs11_config)
    _parsed_key_uri = parse_pkcs11_uri(config.private_key_path)

    def _refresh():
        return _fetch_iot_credentials_pkcs11(
            endpoint=config.aws_credential_provider_endpoint,
            role_alias=config.aws_role_alias,
            thing_name=config.thing_name,
            cert_pem=cert_pem,
            pkcs11_cfg=pkcs11_cfg,
            private_key_label=_parsed_key_uri.get("object"),
        )

    return _create_boto3_session(config.region, _refresh)


# API


def get_session(config: IoTSessionConfig) -> Session:
    """Get a boto3 session with givin IoTSessionConfig.

    The behavior changes according to whether privkey is provided by
        pkcs11 or by plain file, indicating with URI.
    """
    if config.private_key_path.startswith("pkcs11"):
        return _get_session_pkcs11(config)
    return _get_session(config)
