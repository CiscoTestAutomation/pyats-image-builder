# Dockerfile
FROM python:3.7

# install netcat-openbsd for ssh proxy
RUN apt-get update
RUN apt-get install netcat-openbsd

ADD . /pyats-image-builder

RUN cd /pyats-image-builder; make install
