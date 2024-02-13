# ------ common build args ------ #
ARG PYTHON_VERSION=3.11.7
ARG PYTHON_BASE_VER=slim-bookworm
ARG PYTHON_VENV=/venv

#
# ------ prepare virtual env ------ #
#
FROM python:${PYTHON_VERSION}-${PYTHON_BASE_VER} as deps_installer
# install build base
RUN set -eux; \
	apt-get update && \
	apt-get install -y --no-install-recommends \
		python3-dev \
		gcc \
		git 

# install otaclient deps
ARG PYTHON_VENV
ARG OTACLIENT_REQUIREMENTS
COPY "${OTACLIENT_REQUIREMENTS}" /tmp/requirements.txt

RUN set -eux; \
	python3 -m venv ${PYTHON_VENV} && \
	. ${PYTHON_VENV}/bin/activate && \
	export PYTHONDONTWRITEBYTECODE=1 && \
	python3 -m pip install --no-cache-dir -U pip setuptools wheel && \
	python3 -m pip install --no-cache-dir -r /tmp/requirements.txt && \

# cleanup the virtualenv
# see python-slim Dockerfile for more details
	find ${PYTHON_VENV} -depth \
		\( \
			\( -type d -a \( -name test -o -name tests -o -name idle_test \) \) \
			-o \( -type f -a \( -name '*.pyc' -o -name '*.pyo' -o -name 'libpython*.a' \) \) \
		\) -exec rm -rf '{}' +