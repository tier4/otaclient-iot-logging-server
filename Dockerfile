# ------ common build args ------ #
ARG UBUNTU_VER="jammy"

#
# ------ build package ------ #
#
FROM ubuntu:${UBUNTU_VER} AS builder

COPY . /src/

RUN set -eux; \
	# install build deps
	apt-get update ; \
	apt-get install -y --no-install-recommends \
		git \
		python3-pip \
		python3-venv; \
	apt-get clean; \
	# prepare build env
	mkdir -p /dist; \
	python3 -m venv /venv; \
	. /venv/bin/activate; \
	pip install hatch; \
	# start to build package
	cd /src; \
	hatch build -t wheel /dist

#
# ------ build image ------ #
#
FROM ubuntu:${UBUNTU_VER}

ENV VENV="/iot_logging_server_venv"

# add missing libs
RUN --mount=type=bind,from=builder,source=/dist,target=/dist \
	set -eux; \
	apt-get update; \
	apt-get install -y --no-install-recommends \
		python3-pip \
		python3-venv; \
	# install package
	python3 -m venv ${VENV}; \
	. ${VENV}/bin/activate; \
	pip install /dist/*.whl; \
	# cleanup
	apt-get purge -y python3-pip; \
	apt-get autoremove -y; \
	apt-get clean; \
	rm -rf \
		/var/lib/apt/lists/* \
		/root/.cache \
		/tmp/* ;\
	# cleanup the python env
	find ${VENV} -depth \
			\( \
				\( -type d -a \( -name test -o -name tests -o -name idle_test \) \) \
				-o \( -type f -a \( -name '*.pyc' -o -name '*.pyo' -o -name 'libpython*.a' \) \) \
			\) -exec rm -rf '{}' + ; \
	# add mount points placeholder
	mkdir -p /opt /greengrass

ENV PATH="${VENV}/bin:${PATH}"

CMD ["iot_logging_server"]
