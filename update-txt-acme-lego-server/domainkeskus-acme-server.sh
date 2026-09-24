#!/bin/sh

# Domainkeskus credentials (same as update-a-aaaa)
USERNAME=user
PASSWORD=pass
DOMAIN_SLD=mydomain
DOMAIN_TLD=com

# HTTP server bind address (internal network side of the router)
BIND_IP=192.168.1.1
BIND_PORT=9090

# HTTP Basic auth credentials for the lego client (separate from above)
HTTP_AUTH_USERNAME=lego
HTTP_AUTH_PASSWORD=legopass

export USERNAME PASSWORD DOMAIN_SLD DOMAIN_TLD BIND_IP BIND_PORT HTTP_AUTH_USERNAME HTTP_AUTH_PASSWORD

SCRIPT_PATH=`dirname $0`

python "$SCRIPT_PATH/domainkeskus-acme-server.py"
