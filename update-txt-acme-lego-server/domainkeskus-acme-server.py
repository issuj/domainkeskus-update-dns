#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Python 2.7

import sys
import os
import re
import json
import ssl
import base64
import httplib
import urllib
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from xml.etree import ElementTree as ET

# Configuration from environment variables
USERNAME = os.environ['USERNAME']
PASSWORD = os.environ['PASSWORD']
DOMAIN_SLD = os.environ['DOMAIN_SLD']
DOMAIN_TLD = os.environ['DOMAIN_TLD']
BIND_IP = os.environ['BIND_IP']
BIND_PORT = int(os.environ['BIND_PORT'])
HTTP_AUTH_USERNAME = os.environ['HTTP_AUTH_USERNAME']
HTTP_AUTH_PASSWORD = os.environ['HTTP_AUTH_PASSWORD']


def constant_time_compare(a, b):
    """Constant-time string comparison (hmac.compare_digest may be missing on old 2.7)"""
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    return result == 0


def https_request(host, method, path, body=None, headers=None, cookies=None):
    """Make HTTPS request with certificate validation"""
    ctx = ssl.create_default_context()
    conn = httplib.HTTPSConnection(host, context=ctx)

    if headers is None:
        headers = {}

    if cookies:
        headers['Cookie'] = '; '.join(['%s=%s' % (k, v) for k, v in cookies.items()])

    if body:
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
        headers['Content-Length'] = str(len(body))

    conn.request(method, path, body, headers)
    resp = conn.getresponse()
    resp_body = resp.read()
    resp_headers = dict(resp.getheaders())
    conn.close()

    return resp.status, resp_headers, resp_body


def extract_cookies(headers):
    """Extract cookies from Set-Cookie headers"""
    cookies = {}
    for key, value in headers.items():
        if key.lower() == 'set-cookie':
            parts = value.split(';')[0].split('=', 1)
            if len(parts) == 2:
                cookies[parts[0]] = parts[1]
    return cookies


def login(username, password):
    """Step 1: Login and get session cookies"""
    body = urllib.urlencode({'userid': username, 'passwd': password})
    status, headers, resp = https_request(
        'old.domainkeskus.com',
        'POST',
        '/func/asiakaslogin.php',
        body
    )

    if status != 200:
        raise Exception("Login failed with status: %d" % status)

    cookies = extract_cookies(headers)
    if not cookies:
        raise Exception("No session cookies received from login")

    return cookies


def get_token(cookies, sld, tld):
    """Step 2: Get SSO token from euronicdns interface"""
    status, headers, resp = https_request(
        'old.domainkeskus.com',
        'GET',
        '/func/euronicdns.php?domain=%s.%s' % (sld, tld),
        cookies=cookies
    )

    if status != 200:
        raise Exception("Token request failed with status: %d" % status)

    match = re.search(r'<input[^>]+name="token"[^>]+value="([^"]+)"', resp)
    if not match:
        raise Exception("Could not extract token from response")

    return match.group(1)


def get_records(sld, tld, token):
    """Step 3: Fetch current DNS records"""
    params = json.dumps({"scope": "host"})
    body = urllib.urlencode({
        'sld': sld,
        'tld': tld,
        'token': token,
        'parameters': params
    })

    status, headers, resp = https_request(
        'dnsaccess.euronic.fi',
        'POST',
        '/api/getRecords',
        body
    )

    if status != 200:
        raise Exception("getRecords failed with status: %d" % status)

    return resp


def parse_records(xml_data):
    """Parse XML response into list of record dictionaries"""
    root = ET.fromstring(xml_data)
    zone = root.find('.//zone')
    if zone is None:
        raise Exception("No zone found in response")

    records = []
    for elem in zone:
        record = {
            'host': elem.get('host', '@'),
            'rrtype': elem.tag,
            'address': elem.text or '',
            'attr': {}
        }
        records.append(record)

    return records


def set_records(sld, tld, token, records):
    """Step 4: Post updated DNS records"""
    zone_data = []
    for record in records:
        zone_data.append({
            'host': record['host'],
            'rrtype': record['rrtype'],
            'address': record['address'],
            'attr': record['attr']
        })

    params = json.dumps({"scope": "host", "zone": zone_data})
    body = urllib.urlencode({
        'sld': sld,
        'tld': tld,
        'token': token,
        'parameters': params
    })

    status, headers, resp = https_request(
        'dnsaccess.euronic.fi',
        'POST',
        '/api/setRecords',
        body
    )

    if status != 200:
        raise Exception("setRecords failed with status: %d" % status)

    return resp


def parse_fqdn(fqdn):
    """Validate fqdn and extract the host part.

    Accepts e.g. '_acme-challenge.example.com.' or
    '_acme-challenge.sub.example.com.' where example.com is the
    configured DOMAIN_SLD.DOMAIN_TLD. Returns the host string
    (e.g. '_acme-challenge' or '_acme-challenge.sub') or None if
    the fqdn does not match the configured domain.
    """
    if not fqdn:
        return None
    fqdn = fqdn.strip().rstrip('.')
    suffix = '.' + DOMAIN_SLD + '.' + DOMAIN_TLD
    if not fqdn.endswith(suffix):
        return None
    host = fqdn[:len(fqdn) - len(suffix)]
    if not host:
        return None
    return host


def present_txt(host, value):
    """Add or replace a TXT record for the given host"""
    cookies = login(USERNAME, PASSWORD)
    token = get_token(cookies, DOMAIN_SLD, DOMAIN_TLD)
    xml_data = get_records(DOMAIN_SLD, DOMAIN_TLD, token)
    records = parse_records(xml_data)

    for record in records:
        if record['host'] == host and record['rrtype'] == 'txt':
            record['address'] = value
            break
    else:
        records.append({
            'host': host,
            'rrtype': 'txt',
            'address': value,
            'attr': {}
        })

    set_records(DOMAIN_SLD, DOMAIN_TLD, token, records)


def cleanup_txt(host):
    """Remove the TXT record for the given host (no-op if absent)"""
    cookies = login(USERNAME, PASSWORD)
    token = get_token(cookies, DOMAIN_SLD, DOMAIN_TLD)
    xml_data = get_records(DOMAIN_SLD, DOMAIN_TLD, token)
    records = parse_records(xml_data)

    new_records = [
        r for r in records
        if not (r['host'] == host and r['rrtype'] == 'txt')
    ]

    if len(new_records) == len(records):
        return  # nothing to do

    set_records(DOMAIN_SLD, DOMAIN_TLD, token, new_records)


class AcmeHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def send_json(self, status, payload=None):
        body = json.dumps(payload) if payload is not None else ''
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def check_auth(self):
        header = self.headers.get('Authorization', '')
        if not header.startswith('Basic '):
            return False
        try:
            decoded = base64.b64decode(header[6:].strip())
        except Exception:
            return False
        if ':' not in decoded:
            return False
        user, _, password = decoded.partition(':')
        return (
            constant_time_compare(user, HTTP_AUTH_USERNAME) and
            constant_time_compare(password, HTTP_AUTH_PASSWORD)
        )

    def do_POST(self):
        if self.path not in ('/present', '/cleanup'):
            self.send_json(404, {'error': 'not found'})
            return

        if not self.check_auth():
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm="acme"')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return

        try:
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError
        except (ValueError, TypeError):
            self.send_json(400, {'error': 'invalid JSON body'})
            return

        host = parse_fqdn(data.get('fqdn'))
        if host is None:
            self.send_json(400, {
                'error': 'fqdn must be _acme-challenge[.sub].%s.%s' % (DOMAIN_SLD, DOMAIN_TLD)
            })
            return

        try:
            if self.path == '/present':
                value = data.get('value')
                if not value:
                    self.send_json(400, {'error': 'missing value'})
                    return
                present_txt(host, value)
            else:
                cleanup_txt(host)
        except Exception as e:
            self.log_message('error: %s', str(e))
            self.send_json(500, {'error': str(e)})
            return

        self.send_json(200)


def main():
    if not HTTP_AUTH_USERNAME or not HTTP_AUTH_PASSWORD:
        print >> sys.stderr, "Error: HTTP_AUTH_USERNAME and HTTP_AUTH_PASSWORD must be set"
        sys.exit(1)

    server = HTTPServer((BIND_IP, BIND_PORT), AcmeHandler)
    print "ACME httpreq server listening on %s:%d (domain: %s.%s)" % (
        BIND_IP, BIND_PORT, DOMAIN_SLD, DOMAIN_TLD)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
