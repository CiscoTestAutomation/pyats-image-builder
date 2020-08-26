FROM python:{python_version}
LABEL support "pyats-support-ext@cisco.com"

ENV TINI_VERSION=0.18.0
ENV WORKSPACE="{workspace}"

RUN apt-get update \
 && apt-get install -y --no-install-recommends iputils-ping telnet openssh-client curl build-essential \
 && curl -fsSL https://github.com/krallin/tini/releases/download/v${{TINI_VERSION}}/tini-static-amd64 -o /bin/tini \
 && chmod +x /bin/tini \
 && pip3 install --upgrade --no-cache-dir setuptools pip virtualenv \
 && virtualenv ${{WORKSPACE}} \
 && ${{WORKSPACE}}/bin/pip install --no-cache-dir psutil \
 && apt-get remove -y curl build-essential \
 && apt-get autoremove -y \
 && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

WORKDIR ${{WORKSPACE}}

{env}

COPY . ${{WORKSPACE}}

{pre_cmd}

RUN ${{WORKSPACE}}/bin/pip install --disable-pip-version-check \
                                   --no-cache-dir \
                                   --requirement {workspace}/requirements.txt

{post_cmd}

ENTRYPOINT ["/bin/tini", "--", "{workspace}/entrypoint.sh"]