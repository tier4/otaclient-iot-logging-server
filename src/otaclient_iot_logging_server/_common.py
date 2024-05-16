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

from queue import Queue
from typing import Literal, TypedDict

from typing_extensions import NotRequired, TypeAlias

LogsQueue: TypeAlias = "Queue[tuple[str, LogMessage]]"


class LogMessage(TypedDict):
    timestamp: int  # in milliseconds
    message: str


class LogEvent(TypedDict):
    logGroupName: str
    logStreamName: str
    logEvents: list[LogMessage]
    sequenceToken: NotRequired[str]


PKCS11URI = TypedDict(
    "PKCS11URI",
    {
        "object": str,
        "pin-value": NotRequired[str],
        "token": NotRequired[str],
        "type": NotRequired[Literal["cert", "private"]],
    },
)
"""
NOTE: Not all possible segments are defined here.
        see https://www.rfc-editor.org/rfc/rfc7512.html for more details.
      In normal case, <object>(priv_key_label) is enough, as long as there is
        only one private key inside the slot.
"""
