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

import pycurl
from boto3 import Session
from botocore.credentials import DeferredRefreshableCredentials
from botocore.session import get_session as get_botocore_session

from otaclient_iot_logging_server._common import Credentials
from otaclient_iot_logging_server.greengrass_config import IoTSessionConfig

logger = logging.getLogger(__name__)


class Boto3Session:
    """A refreshable boto3 session with pkcs11.

    Reference:
    https://github.com/awslabs/aws-iot-core-credential-provider-session-helper/blob/main/src/awsiot_credentialhelper/boto3_session.py
    """

    def __init__(self, config: IoTSessionConfig) -> None:
        self._config = config

    def get_session(self, **kwargs) -> Session:
        session = get_botocore_session()
        # NOTE: session does have an attribute named _credentials
        session._credentials = DeferredRefreshableCredentials(  # type: ignore
            method="sts-assume-role",
            refresh_using=self._get_credentials,
        )
        session.set_config_variable("region", self._config.region)

        # set other configs if any
        for k, v in kwargs.items():
            session.set_config_variable(k, v)
        return Session(botocore_session=session)

    def _get_credentials(self) -> Credentials:
        """Get credentials using mtls from credential_endpoint."""
        gg_config = self._config
        connection = pycurl.Curl()
        connection.setopt(pycurl.URL, gg_config.aws_credential_refresh_url)

        # ------ client auth option ------ #
        # TPM2.0 support, if private_key is provided as pkcs11 URI,
        #   enable to use pkcs11 interface from openssl.
        _enable_pkcs11_engine = False
        if gg_config.private_key_path.startswith("pkcs11:"):
            _enable_pkcs11_engine = True
            connection.setopt(pycurl.SSLKEYTYPE, "eng")
        connection.setopt(pycurl.SSLKEY, gg_config.private_key_path)

        if gg_config.certificate_path.startswith("pkcs11:"):
            _enable_pkcs11_engine = True
            connection.setopt(pycurl.SSLCERTTYPE, "eng")
        connection.setopt(pycurl.SSLCERT, gg_config.certificate_path)

        if _enable_pkcs11_engine:
            connection.setopt(pycurl.SSLENGINE, "pkcs11")

        # ------ server auth option ------ #
        connection.setopt(pycurl.SSL_VERIFYPEER, 1)
        connection.setopt(pycurl.CAINFO, gg_config.ca_path)
        connection.setopt(pycurl.CAPATH, None)
        connection.setopt(pycurl.SSL_VERIFYHOST, 2)

        # ------ set required header ------ #
        headers = [f"x-amzn-iot-thingname:{gg_config.thing_name}"]
        connection.setopt(pycurl.HTTPHEADER, headers)

        # ------ execute the request and parse creds ------ #
        response = connection.perform_rs()
        status = connection.getinfo(pycurl.HTTP_CODE)
        connection.close()

        if status // 100 != 2:
            _err_msg = f"failed to get cred: {status=}"
            logger.debug(_err_msg)
            raise ValueError(_err_msg)

        try:
            response_json = json.loads(response)
            assert isinstance(response_json, dict), "response is not a json object"
        except Exception as e:
            _err_msg = f"cred response is invalid: {e!r}\nresponse={response}"
            logger.debug(_err_msg)
            raise ValueError(_err_msg)

        try:
            _creds = response_json["credentials"]
            creds = Credentials(
                access_key=_creds["accessKeyId"],
                secret_key=_creds["secretAccessKey"],
                token=_creds["sessionToken"],
                expiry_time=_creds["expiration"],
            )
            logger.debug(f"loaded credential={creds}")
            return creds
        except Exception as e:
            _err_msg = f"failed to create Credentials object from response: {e!r}\nresponse_json={response_json}"
            logger.debug(_err_msg)
            raise ValueError(_err_msg)
