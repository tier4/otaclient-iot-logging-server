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
"""otaclient AWS IoT logging server configs."""


from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import AnyHttpUrl, BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurableLoggingServerConfig(BaseSettings):
    model_config = SettingsConfigDict(frozen=True, validate_default=True)

    # the default location of greengrass configuration files.
    # NOTE(20240209): allow user to change this values with env vars,
    GREENGRASS_V1_CONFIG: str = "/greengrass/config/config.json"
    GREENGRASS_V2_CONFIG: str = "/greengrass/v2/init_config/config.yaml"

    AWS_PROFILE_INFO: str = "/opt/ota/client/aws_profile_info.yaml"
    """The path to aws_profile_info.yaml."""

    LISTEN_ADDRESS: str = "127.0.0.1"
    LISTEN_PORT: int = 8083
    SERVER_LOGGING_LEVEL: int = logging.INFO
    SERVER_LOGGING_LOG_FORMAT: str = (
        "[%(asctime)s][%(levelname)s]-%(name)s:%(funcName)s:%(lineno)d,%(message)s"
    )

    MAX_LOGS_BACKLOG: int = 4096
    MAX_LOGS_PER_MERGE: int = 512
    UPLOAD_INTERVAL: int = 60  # in seconds


class AWSProfileInfo(BaseModel):
    class Profile(BaseModel):
        model_config = SettingsConfigDict(frozen=True)
        profile_name: str
        account_id: str
        credential_endpoint: AnyHttpUrl

    profiles: list[Profile]

    def get_profile_info(self, profile_name: str) -> Profile:
        for profile in self.profiles:
            if profile.profile_name == profile_name:
                return profile
        raise KeyError(f"failed to get profile info for {profile_name=}")


def load_profile_info(_cfg_fpath: str) -> AWSProfileInfo:
    _cfg = yaml.safe_load(Path(_cfg_fpath).read_text())
    return AWSProfileInfo.model_validate(_cfg)


server_cfg = ConfigurableLoggingServerConfig()
profile_info = load_profile_info(server_cfg.AWS_PROFILE_INFO)
