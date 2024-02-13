# ------ common build args ------ #
ARG PYTHON_VERSION=3.11.7
ARG PYTHON_BASE_VER=slim-bookworm
ARG PYTHON_VENV=/venv

#
# ------ prepare venv ------ #
#
FROM python:${PYTHON_VERSION}-${PYTHON_BASE_VER} as venv_builder

ARG PYTHON_VENV

COPY . /source_code

# ------ install build deps ------ #
RUN set -eux; \
	apt-get update ; \
	apt-get install -y --no-install-recommends \
		python3-dev \
		libcurl4-openssl-dev \
		libssl-dev \
		gcc \
		git

# ------ setup virtual env and build ------ #
RUN set -eux ; \
	python3 -m venv ${PYTHON_VENV} ; \
	. ${PYTHON_VENV}/bin/activate ; \
	export PYTHONDONTWRITEBYTECODE=1 ; \
	cd /source_code ;\
	python3 -m pip install -U pip ; \
	python3 -m pip install .

# ------ post installation, cleanup ------ #
# cleanup the python venv again
# see python-slim Dockerfile for more details
RUN set -eux ; \
	find ${PYTHON_VENV} -depth \
			\( \
				\( -type d -a \( -name test -o -name tests -o -name idle_test \) \) \
				-o \( -type f -a \( -name '*.pyc' -o -name '*.pyo' -o -name 'libpython*.a' \) \) \
			\) -exec rm -rf '{}' +

#
# ------ build final image ------ #
#
FROM python:${PYTHON_VERSION}-${PYTHON_BASE_VER}

ARG PYTHON_VENV
ARG CMD_NAME

COPY --from=venv_builder ${PYTHON_VENV} ${PYTHON_VENV}

# add missing libs
RUN set -eux ; \
	apt-get update ; \
	apt-get install -y --no-install-recommends \
		libcurl4 ; \
	rm -rf \
		/var/lib/apt/lists/* \
		/root/.cache \
		/tmp/*

# add mount points placeholder
RUN mkdir -p /opt /greengrass

ENV PATH="${PYTHON_VENV}/bin:${PATH}"

CMD ["iot_logging_server"]