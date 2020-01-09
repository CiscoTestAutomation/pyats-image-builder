FROM python:{python_version}
LABEL support "pyats-support@cisco.com"

ENV TINI_VERSION=0.18.0
{env}

COPY image .

RUN apt-get update \
 && apt-get install -y --no-install-recommends iputils-ping telnet openssh-client curl build-essential \
 && curl -fsSL https://github.com/krallin/tini/releases/download/v${{TINI_VERSION}}/tini-static-amd64 -o /bin/tini \
 && chmod +x /bin/tini \
 && pip3 install --upgrade --no-cache-dir setuptools pip virtualenv \
 && virtualenv ${{VENV_LOC}} \
 && ${{VENV_LOC}}/bin/pip install --no-cache-dir -r ${{INSTALL_LOC}}/requirements.txt \
 && apt-get remove -y curl build-essential\
 && apt-get autoremove -y\
 && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

ENTRYPOINT ["/bin/tini", "--", "/install/entrypoint.sh"]
WORKDIR ${{WORKSPACE}}
