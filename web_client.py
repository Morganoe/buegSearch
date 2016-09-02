#! /usr/bin/env python3

import sys
import re
from socket import *


def main():
    DEFAULT_PORT = 80

    if len(sys.argv) < 3 or len(sys.argv) > 4:
        print("USAGE: <host> <path> [port]")
        exit()

    if len(sys.argv) == 4:
        port = int(sys.argv[3])
    else:
        port = DEFAULT_PORT
    
    host = sys.argv[1]
    path = sys.argv[2]

    print("Connecting to " + host + path + " at port " +str(port))

    sock = socket(AF_INET, SOCK_STREAM)
    sock.connect((host, port))

    send_html_get(sock, host, path)
    
    resp = get_html_response(sock)
#    resp = remove_html_comments(resp)
    print("From server:")
    print(resp)
    links = extract_links(resp)
    print(links)
    for s in links:
        print(s)
    sock.close()


def send_html_get(sock, host, path):
    send_str  = "GET " + path + " HTTP/1.1\r\nHost: " + host + "\r\n"
    send_str += "User-Agent: self-module\r\n"
    send_str += "Accept: text/html.application/xhtml+cml\r\n"
    send_str += "Accept-Charset: ISO-8859-1,utf-8;q=0.7\r\n"
    send_str += "Keep-Alive: timeout=60\r\n"
    send_str += "Connection: close\r\n"
    send_str += "\r\n"

    sock.sendall(str.encode(send_str))
    return


def get_html_response(sock):
    resp = ""
    while(True):
        data = sock.recv(1024)
        if not data: break
        resp += bytes.decode(data)
    return resp


def extract_links(html):
    pattern = r'<a\s.*\s*href\s*=\s*\n*\r*\s*"((https?://)?[.a-z0-9\?/=:~_-]+ *)"'
    pattern1 = r'<\s*meta\s*.*\s*URL=(.*)\s*"'
    matches = re.findall(pattern, html, flags = re.IGNORECASE|re.MULTILINE)
    m1 = re.findall(pattern1, html, flags = re.IGNORECASE|re.MULTILINE)
    # Removes the html boiler plate around the link   
    skimmed_matches = []
    for s in matches:
        skimmed_matches += [s[0]]
    for s in m1:
        skimmed_matches += [s]
    return skimmed_matches


def remove_html_comments(html):
    pattern = r'<!--.*-->'
    r = re.compile(pattern, re.IGNORECASE|re.DOTALL)
    html = r.sub("", html, count = len(html))
    return html


main()
