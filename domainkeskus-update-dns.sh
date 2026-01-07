#!/bin/sh

USERNAME=user
PASSWORD=pass
TARGET_HOST=my-dynamic-ip-host
DOMAIN_SLD=mydomain
DOMAIN_TLD=com

IPV4=`ip addr show dev eth0 scope global | grep 'inet ' | cut -d ' ' -f 6 | cut -d '/' -f 1`
IPV6=`ip addr show dev eth0 scope global | grep 'inet6' | cut -d ' ' -f 6 | cut -d '/' -f 1`

export USERNAME PASSWORD DOMAIN_SLD DOMAIN_TLD TARGET_HOST

python domainkeskus-update-dns.py $IPV4 $IPV6

