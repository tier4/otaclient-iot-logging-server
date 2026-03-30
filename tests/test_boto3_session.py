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
import ssl
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from awscrt.exceptions import AwsCrtError
from awscrt.io import ClientTlsContext, Pkcs11Lib, TlsContextOptions
from pytest_mock import MockerFixture

import otaclient_iot_logging_server.boto3_session
from otaclient_iot_logging_server._utils import parse_pkcs11_uri
from otaclient_iot_logging_server.boto3_session import (  # type: ignore
    _build_tls_context_from_path,
    _convert_to_pem,
    _create_boto3_session,
    _fetch_iot_credentials,
    _fetch_iot_credentials_via_awscrt,
    _parse_credentials_response,
    get_session,
)
from otaclient_iot_logging_server.greengrass_config import (
    IoTSessionConfig,
    PKCS11Config,
)
from tests.conftest import TEST_DATA_DPATH

MODULE = otaclient_iot_logging_server.boto3_session.__name__

SAMPLE_CERT_PEM_FPATH = TEST_DATA_DPATH / "sample_cert.pem"
SAMPLE_CERT_DER_FPATH = TEST_DATA_DPATH / "sample_cert.der"


@pytest.mark.parametrize(
    "_in, _expected",
    [
        (
            pem_cert := SAMPLE_CERT_PEM_FPATH.read_bytes(),
            pem_cert,
        ),
        (SAMPLE_CERT_DER_FPATH.read_bytes(), pem_cert),
    ],
)
def test__convert_to_pem(_in: bytes, _expected: bytes):
    assert _convert_to_pem(_in) == _expected


_MOCKED_CERT = b"mocked_certs"
_PKCS11_PRIVKEY_URI = "pkcs11:object=greengrass_privkey;type=private"
_PARSED_PKCS11_PRIVKEY_URI = parse_pkcs11_uri(_PKCS11_PRIVKEY_URI)


@pytest.mark.parametrize(
    "_config, _expected_fetch_target, _expected_call",
    [
        # test#1: boto3 session without pkcs11
        (
            test1_cfg := IoTSessionConfig(
                account_id="test_account",
                ca_path="test_capath",
                private_key_path="test_privkey_path",
                certificate_path="test_cert_path",
                thing_name="test_thing_name",
                profile="test_profile",
                region="test_region",
                aws_credential_provider_endpoint="test_cred_endpoint",
            ),
            "_fetch_iot_credentials",
            {
                "endpoint": test1_cfg.aws_credential_provider_endpoint,
                "role_alias": test1_cfg.aws_role_alias,
                "thing_name": test1_cfg.thing_name,
                "cert_path": test1_cfg.certificate_path,
                "key_path": test1_cfg.private_key_path,
            },
        ),
        # test#2: boto3 session with pkcs11
        (
            test2_cfg := IoTSessionConfig(
                account_id="test_account",
                ca_path="test_capath",
                private_key_path=_PKCS11_PRIVKEY_URI,
                certificate_path="test_cert_path",
                thing_name="test_thing_name",
                profile="test_profile",
                region="test_region",
                aws_credential_provider_endpoint="test_cred_endpoint",
                pkcs11_config=(
                    test2_pkcs11_cfg := PKCS11Config(
                        pkcs11_lib="tpm2-pkcs11_lib",
                        slot_id="1",
                        user_pin="userpin",
                    )
                ),
            ),
            "_fetch_iot_credentials_pkcs11",
            {
                "endpoint": test2_cfg.aws_credential_provider_endpoint,
                "role_alias": test2_cfg.aws_role_alias,
                "thing_name": test2_cfg.thing_name,
                "cert_pem": _MOCKED_CERT,
                "pkcs11_cfg": test2_pkcs11_cfg,
                "private_key_label": _PARSED_PKCS11_PRIVKEY_URI["object"],
            },
        ),
    ],
)
def test_get_session(
    _config: IoTSessionConfig,
    _expected_fetch_target: str,
    _expected_call: dict[str, Any],
    mocker: MockerFixture,
):
    """
    Confirm with specific input IoTSessionConfig, we get the expected
    credential fetch function being called with correct arguments.
    """
    # ------ setup test ------ #
    _mock_credentials = {
        "access_key": "test_access_key",
        "secret_key": "test_secret_key",
        "token": "test_token",
        "expiry_time": "2099-01-01T00:00:00Z",
    }
    _fetch_mock = mocker.patch(
        f"{MODULE}.{_expected_fetch_target}",
        return_value=_mock_credentials,
    )
    mocker.patch(
        f"{MODULE}._load_certificate", mocker.MagicMock(return_value=_MOCKED_CERT)
    )
    # ------ execution ------ #
    session = get_session(_config)
    # Call the refresh function directly to verify the arguments
    _refresh_func = session._session._credentials._refresh_using  # type: ignore
    _refresh_func()
    # ------ check result ------ #
    _fetch_mock.assert_called_once_with(**_expected_call)


class TestFetchIoTCredentials:
    """Tests for _fetch_iot_credentials (awscrt-based)."""

    def _mock_awscrt(self, mocker: MockerFixture):
        """Mock _fetch_iot_credentials_via_awscrt to return controlled responses."""
        mock_response = {
            "access_key": "AKIAIOSFODNN7EXAMPLE",
            "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "token": "FwoGZXIvYXdzEBY...",
            "expiry_time": "2099-01-01T00:00:00Z",
        }
        mock = mocker.patch(
            f"{MODULE}._fetch_iot_credentials_via_awscrt",
            return_value=mock_response,
        )
        return mock

    def test_success(self, mocker: MockerFixture, tmp_path):
        """Verify successful credential fetching returns correct format."""
        mock = self._mock_awscrt(mocker)
        mock_build = mocker.patch(f"{MODULE}._build_tls_context_from_path")

        result = _fetch_iot_credentials(
            endpoint="example.credentials.iot.ap-northeast-1.amazonaws.com",
            role_alias="test-role-alias",
            thing_name="test-thing",
            cert_path=str(tmp_path / "cert.pem"),
            key_path=str(tmp_path / "key.pem"),
        )

        assert result["access_key"] == "AKIAIOSFODNN7EXAMPLE"
        assert result["secret_key"] == "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        assert result["token"] == "FwoGZXIvYXdzEBY..."
        assert result["expiry_time"] == "2099-01-01T00:00:00Z"
        # Verify tls_ctx_opt from _build_tls_context_from_path is passed through
        mock.assert_called_once_with(
            endpoint="example.credentials.iot.ap-northeast-1.amazonaws.com",
            role_alias="test-role-alias",
            thing_name="test-thing",
            tls_ctx_opt=mock_build.return_value,
        )

    def test_tls_context_built_with_cert_and_key(self, mocker: MockerFixture):
        """Verify cert and key file paths are passed to _build_tls_context_from_path."""
        mock_build = mocker.patch(f"{MODULE}._build_tls_context_from_path")
        self._mock_awscrt(mocker)

        _fetch_iot_credentials(
            endpoint="example.credentials.iot.ap-northeast-1.amazonaws.com",
            role_alias="test-role-alias",
            thing_name="test-thing",
            cert_path="/path/to/cert.pem",
            key_path="/path/to/key.pem",
        )

        mock_build.assert_called_once_with("/path/to/cert.pem", "/path/to/key.pem")

    def test_error_response_does_not_leak_body(self, mocker: MockerFixture):
        """Verify non-200 response raises ValueError without leaking body."""
        mocker.patch(f"{MODULE}._build_tls_context_from_path")
        mocker.patch(
            f"{MODULE}._fetch_iot_credentials_via_awscrt",
            side_effect=ValueError(
                "Error getting credentials from IoT credential provider: status=403"
            ),
        )

        with pytest.raises(ValueError, match="status=403") as exc_info:
            _fetch_iot_credentials(
                endpoint="example.credentials.iot.ap-northeast-1.amazonaws.com",
                role_alias="test-role-alias",
                thing_name="test-thing",
                cert_path="/path/to/cert.pem",
                key_path="/path/to/key.pem",
            )

        assert "secret" not in str(exc_info.value)


class TestParseCredentialsResponse:
    """Tests for _parse_credentials_response."""

    def test_success(self):
        """Verify successful parsing of credential response."""
        body = (
            b'{"credentials": {'
            b'"accessKeyId": "AKID", '
            b'"secretAccessKey": "SECRET", '
            b'"sessionToken": "TOKEN", '
            b'"expiration": "2099-01-01T00:00:00Z"}}'
        )
        result = _parse_credentials_response(200, body, "https://example.com")
        assert result == {
            "access_key": "AKID",
            "secret_key": "SECRET",
            "token": "TOKEN",
            "expiry_time": "2099-01-01T00:00:00Z",
        }

    def test_error_does_not_leak_body(self):
        """Verify non-200 response raises ValueError without leaking body."""
        with pytest.raises(ValueError, match="status=403") as exc_info:
            _parse_credentials_response(
                403, b"secret error details", "https://example.com"
            )
        assert "secret" not in str(exc_info.value)


class TestCreateBoto3Session:
    """Tests for _create_boto3_session."""

    @pytest.mark.parametrize(
        "_region",
        ["ap-northeast-1", "us-west-2", "eu-central-1"],
    )
    def test_region_is_set(self, _region: str):
        """Verify region is correctly set on the session."""
        mock_refresh = MagicMock()
        session = _create_boto3_session(_region, mock_refresh)

        assert session.region_name == _region


# --- Integration tests using real awscrt objects --- #


def _generate_tls_certificates(cert_dir: Path) -> dict[str, Path]:
    """Generate CA, server, and client certificates using openssl CLI."""

    san_cnf = cert_dir / "san.cnf"
    san_cnf.write_text(
        "[req]\n"
        "distinguished_name = req_dn\n"
        "req_extensions = v3_req\n"
        "[req_dn]\n"
        "[v3_req]\n"
        "subjectAltName = DNS:localhost,IP:127.0.0.1\n"
        "[v3_ext]\n"
        "subjectAltName = DNS:localhost,IP:127.0.0.1\n"
    )

    def _run(*args: str) -> None:
        subprocess.run(args, check=True, capture_output=True)

    # CA key + self-signed cert
    _run(
        "openssl", "req", "-x509", "-newkey", "rsa:2048",
        "-keyout", str(cert_dir / "ca.key"),
        "-out", str(cert_dir / "ca.pem"),
        "-days", "1", "-nodes", "-subj", "/CN=TestCA",
    )  # fmt: skip

    # Server cert (CN=localhost, SAN=localhost+127.0.0.1)
    _run(
        "openssl", "req", "-newkey", "rsa:2048",
        "-keyout", str(cert_dir / "server.key"),
        "-out", str(cert_dir / "server.csr"),
        "-nodes", "-subj", "/CN=localhost",
        "-config", str(san_cnf),
    )  # fmt: skip
    _run(
        "openssl", "x509", "-req",
        "-in", str(cert_dir / "server.csr"),
        "-CA", str(cert_dir / "ca.pem"),
        "-CAkey", str(cert_dir / "ca.key"),
        "-CAcreateserial",
        "-out", str(cert_dir / "server.pem"),
        "-days", "1",
        "-extensions", "v3_ext",
        "-extfile", str(san_cnf),
    )  # fmt: skip

    # Client cert
    _run(
        "openssl", "req", "-newkey", "rsa:2048",
        "-keyout", str(cert_dir / "client.key"),
        "-out", str(cert_dir / "client.csr"),
        "-nodes", "-subj", "/CN=TestClient",
    )  # fmt: skip
    _run(
        "openssl", "x509", "-req",
        "-in", str(cert_dir / "client.csr"),
        "-CA", str(cert_dir / "ca.pem"),
        "-CAkey", str(cert_dir / "ca.key"),
        "-CAcreateserial",
        "-out", str(cert_dir / "client.pem"),
        "-days", "1",
    )  # fmt: skip

    return {
        "ca": cert_dir / "ca.pem",
        "server_cert": cert_dir / "server.pem",
        "server_key": cert_dir / "server.key",
        "client_cert": cert_dir / "client.pem",
        "client_key": cert_dir / "client.key",
    }


class _CredentialHandler(BaseHTTPRequestHandler):
    """HTTP handler that mimics AWS IoT credential provider responses."""

    def do_GET(self):
        if "error" in self.path:
            body = b"Forbidden"
            self.send_response(403)
        else:
            body = json.dumps(
                {
                    "credentials": {
                        "accessKeyId": "AKID_INTEGRATION",
                        "secretAccessKey": "SECRET_INTEGRATION",
                        "sessionToken": "TOKEN_INTEGRATION",
                        "expiration": "2099-01-01T00:00:00Z",
                    }
                }
            ).encode()
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A002
        pass  # suppress request logging during tests


@pytest.fixture(scope="module")
def tls_certificates(tmp_path_factory):
    """Generate self-signed CA, server, and client certs for mTLS testing."""
    cert_dir = tmp_path_factory.mktemp("certs")
    return _generate_tls_certificates(cert_dir)


@pytest.fixture(scope="module")
def mtls_server(tls_certificates):
    """Start a local HTTPS server requiring client certificate authentication."""
    certs = tls_certificates

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(certs["server_cert"]), str(certs["server_key"]))
    ctx.load_verify_locations(str(certs["ca"]))
    ctx.verify_mode = ssl.CERT_REQUIRED

    server = HTTPServer(("127.0.0.1", 0), _CredentialHandler)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    port = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield port, certs

    server.shutdown()


class TestAwsCrtIntegration:
    """Integration tests exercising real awscrt objects against a local mTLS server."""

    def test_build_tls_context_from_path(self, tls_certificates):
        """_build_tls_context_from_path creates a usable TlsContextOptions."""
        certs = tls_certificates
        result = _build_tls_context_from_path(
            cert_path=str(certs["client_cert"]),
            key_path=str(certs["client_key"]),
        )
        # Verify the full chain: TlsContextOptions -> ClientTlsContext -> connection options
        tls_ctx = ClientTlsContext(result)
        conn_opts = tls_ctx.new_connection_options()
        assert conn_opts is not None

    def test_fetch_credentials_success(self, mtls_server):
        """Full awscrt HTTP flow against a local mTLS HTTPS server."""
        port, certs = mtls_server

        tls_opts = TlsContextOptions.create_client_with_mtls_from_path(
            cert_filepath=str(certs["client_cert"]),
            pk_filepath=str(certs["client_key"]),
        )
        tls_opts.override_default_trust_store_from_path(
            ca_filepath=str(certs["ca"]),
        )

        result = _fetch_iot_credentials_via_awscrt(
            endpoint="localhost",
            role_alias="test-role",
            thing_name="test-thing",
            tls_ctx_opt=tls_opts,
            port=port,
        )

        assert result == {
            "access_key": "AKID_INTEGRATION",
            "secret_key": "SECRET_INTEGRATION",
            "token": "TOKEN_INTEGRATION",
            "expiry_time": "2099-01-01T00:00:00Z",
        }

    def test_fetch_credentials_error_response(self, mtls_server):
        """Non-200 response from the server raises ValueError."""
        port, certs = mtls_server

        tls_opts = TlsContextOptions.create_client_with_mtls_from_path(
            cert_filepath=str(certs["client_cert"]),
            pk_filepath=str(certs["client_key"]),
        )
        tls_opts.override_default_trust_store_from_path(
            ca_filepath=str(certs["ca"]),
        )

        with pytest.raises(ValueError, match="status=403"):
            _fetch_iot_credentials_via_awscrt(
                endpoint="localhost",
                role_alias="error",
                thing_name="test-thing",
                tls_ctx_opt=tls_opts,
                port=port,
            )

    def test_pkcs11lib_api_exists(self):
        """Verify Pkcs11Lib class and expected constructor parameter exist.

        Actual PKCS#11 operations require a real shared library and TPM
        hardware, so we only verify the API surface is intact.
        """
        import inspect

        sig = inspect.signature(Pkcs11Lib.__init__)
        assert "file" in sig.parameters

    def test_create_client_with_mtls_pkcs11_api_exists(self):
        """Verify create_client_with_mtls_pkcs11 has the expected parameters.

        _build_tls_context_pkcs11 calls this with 7 keyword arguments.
        Ensure the method signature is compatible.
        """
        import inspect

        sig = inspect.signature(TlsContextOptions.create_client_with_mtls_pkcs11)
        expected_params = {
            "pkcs11_lib",
            "user_pin",
            "slot_id",
            "token_label",
            "private_key_label",
            "cert_file_path",
            "cert_file_contents",
        }
        assert expected_params.issubset(sig.parameters.keys())

    def test_awscrt_error_attributes(self):
        """Verify AwsCrtError can be instantiated and has expected attributes."""
        err = AwsCrtError(
            code=1049,
            name="AWS_IO_TLS_ERROR_NEGOTIATION_FAILURE",
            message="TLS negotiation failed",
        )
        assert err.code == 1049
        assert err.name == "AWS_IO_TLS_ERROR_NEGOTIATION_FAILURE"
        assert err.message == "TLS negotiation failed"
        assert isinstance(err, Exception)
