#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Python 2.7

import sys
import os
import re
import json
import ssl
import httplib
import urllib
import socket
from xml.etree import ElementTree as ET

# Configuration from environment variables
USERNAME = os.environ['USERNAME']
PASSWORD = os.environ['PASSWORD']
DOMAIN_SLD = os.environ['DOMAIN_SLD']
DOMAIN_TLD = os.environ['DOMAIN_TLD']
TARGET_HOST = os.environ['TARGET_HOST']

def validate_ipv4(addr):
    """Validate IPv4 address format"""
    if not addr:
        return False
    try:
        socket.inet_pton(socket.AF_INET, addr)
        return True
    except socket.error:
        return False

def validate_ipv6(addr):
    """Validate IPv6 address format"""
    if not addr:
        return False
    try:
        socket.inet_pton(socket.AF_INET6, addr)
        return True
    except socket.error:
        return False

def resolve_dns(hostname, record_type):
    """Resolve DNS record using system resolver"""
    try:
        if record_type == 'A':
            return socket.getaddrinfo(hostname, None, socket.AF_INET)[0][4][0]
        elif record_type == 'AAAA':
            return socket.getaddrinfo(hostname, None, socket.AF_INET6)[0][4][0]
    except (socket.gaierror, IndexError):
        return None

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
            # Handle multiple set-cookie headers
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
    
    # Extract token from HTML form
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

def update_records(records, host, new_ipv4, new_ipv6):
    """Update or verify A and AAAA records for specified host"""
    found_a = False
    found_aaaa = False
    current_ipv4 = None
    current_ipv6 = None
    
    for record in records:
        if record['host'] == host and record['rrtype'] == 'a':
            found_a = True
            current_ipv4 = record['address']
            record['address'] = new_ipv4
        elif record['host'] == host and record['rrtype'] == 'aaaa':
            found_aaaa = True
            current_ipv6 = record['address']
            record['address'] = new_ipv6
    
    if not found_a:
        raise Exception("A record for '%s' not found in current DNS records" % host)
    if not found_aaaa:
        raise Exception("AAAA record for '%s' not found in current DNS records" % host)
    
    # Return records and whether there was any change
    changed = (current_ipv4 != new_ipv4) or (current_ipv6 != new_ipv6)
    return records, changed, current_ipv4, current_ipv6

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

def main():
    if len(sys.argv) != 3:
        print >> sys.stderr, "Usage: %s <new_ipv4> <new_ipv6>" % sys.argv[0]
        sys.exit(1)
    
    new_ipv4 = sys.argv[1]
    new_ipv6 = sys.argv[2]
    
    # Validate IP addresses
    if not validate_ipv4(new_ipv4):
        print >> sys.stderr, "Error: Invalid IPv4 address: %s" % new_ipv4
        sys.exit(1)
    
    if not validate_ipv6(new_ipv6):
        print >> sys.stderr, "Error: Invalid IPv6 address: %s" % new_ipv6
        sys.exit(1)
    
    fqdn = "%s.%s.%s" % (TARGET_HOST, DOMAIN_SLD, DOMAIN_TLD)
    
    # Check current DNS values
    print "Checking current DNS records for %s..." % fqdn
    current_ipv4 = resolve_dns(fqdn, 'A')
    current_ipv6 = resolve_dns(fqdn, 'AAAA')
    
    print "Current A record: %s" % (current_ipv4 or "(not resolved)")
    print "Current AAAA record: %s" % (current_ipv6 or "(not resolved)")
    
    if current_ipv4 == new_ipv4 and current_ipv6 == new_ipv6:
        print "DNS records already match requested values. No update needed."
        sys.exit(0)
    
    print "\nProceeding with update..."
    
    try:
        # Step 1: Login
        print "Logging in..."
        cookies = login(USERNAME, PASSWORD)
        
        # Step 2: Get token
        print "Getting SSO token..."
        token = get_token(cookies, DOMAIN_SLD, DOMAIN_TLD)
        
        # Step 3: Get current records
        print "Fetching current DNS records..."
        xml_data = get_records(DOMAIN_SLD, DOMAIN_TLD, token)
        records = parse_records(xml_data)
        
        # Step 4: Update records
        print "Updating records for %s..." % TARGET_HOST
        updated_records, api_changed, api_ipv4, api_ipv6 = update_records(records, TARGET_HOST, new_ipv4, new_ipv6)
        
        # Check if update is actually needed based on API data
        if not api_changed:
            print "API records already match requested values. No update needed."
            sys.exit(0)
        
        # Step 5: Post updated records
        print "Posting updated DNS records..."
        result = set_records(DOMAIN_SLD, DOMAIN_TLD, token, updated_records)
        
        print "\nDNS update successful!"
        if api_ipv4 != new_ipv4:
            print "A record changed: %s -> %s" % (api_ipv4, new_ipv4)
        if api_ipv6 != new_ipv6:
            print "AAAA record changed: %s -> %s" % (api_ipv6, new_ipv6)
        
    except Exception as e:
        print >> sys.stderr, "Error: %s" % str(e)
        sys.exit(1)

if __name__ == '__main__':
    main()
