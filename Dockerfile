# ------ common build args ------ #
ARG PYTHON_VERSION=3.13
ARG PYTHON_BASE_VER=slim
ARG PYTHON_VENV=/venv

#
# ------ prepare venv ------ #
#
FROM python:${PYTHON_VERSION}-${PYTHON_BASE_VER} AS venv_builder

ARG PYTHON_VENV

COPY ./src ./pyproject.toml /source_code/

# ------ install build deps ------ #
RUN set -eux; \
	apt-get update ; \
	apt-get install -y --no-install-recommends \
		gcc \
		git \
		libcurl4-openssl-dev \
		libssl-dev \
		python3-dev; \
	apt-get clean; \
	# ------ setup virtual env and build ------ #
	python3 -m venv ${PYTHON_VENV} ; \
	. ${PYTHON_VENV}/bin/activate ; \
	export PYTHONDONTWRITEBYTECODE=1 ; \
	cd /source_code ;\
	python3 -m pip install -U pip ; \
	python3 -m pip install . ;\
	# ------ post installation, cleanup ------ #
	# cleanup the python venv again
	# see python-slim Dockerfile for more details
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
		/tmp/* ;\
	# add mount points placeholder
	mkdir -p /opt /greengrass

ENV PATH="${PYTHON_VENV}/bin:${PATH}"

CMD ["iot_logging_server"]
