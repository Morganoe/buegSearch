#! /usr/bin/env python3

from os.path import isfile
from urllib.request import unquote
from socket import *
from time import sleep
from copy import deepcopy
from time import clock
import sys
import re
import os
import tempfile
import subprocess
import threading

DEFAULT_PORT = 80
MAX_PAGE_SEARCH = 150
PAGE_INCREMENT = 40

def main():
    if len(sys.argv) == 2:
        port = int(sys.argv[1])
    else:
        port = DEFAULT_PORT
    
    host = ''  # Means localhost
    
    sock = socket(AF_INET, SOCK_STREAM)
    sock.bind((host, port))
    sock.listen(10) # Allows for no more than 10 pending connections

    while(True):
        buff = ""
        conn, addr = sock.accept()
        print("New connection at: ", addr)
        while(True):
            try:
                data = conn.recv(1024)
                if data == b"": break
                buff += bytes.decode(data)

                # Allows for program to continue without blocking
                conn.setblocking(0)
            except:
                break
        conn.setblocking(1)
        #handle_message(conn, buff)
        #conn.close()
        try:
            handle_message(conn, buff)
        except Exception as ex:
            print("Error: " + str(ex))
            send_500_error(conn)
        finally:
            conn.close()


def handle_message(sock, mesg):
    ''' Determines how to handle incoming http messages. '''
    print(mesg)

    # Retrieves the first word of the first line
    # Which should be the html command
    cmd = mesg.splitlines()[0].split(" ")[0]
    if cmd == "GET":
        handle_GET(sock, mesg)
    elif cmd == "POST":
        handle_POST(sock, mesg)


def handle_GET(sock, mesg):
    ''' Handles http GET requests. '''
    path = mesg.split(" ")[1][1:]
    
    # This line is to remove any '?'s from the GET path
    # They only show up on occasion at end of string
    path = path.split("?")[0]

    if path == "":
        path = "home.html"

    if ".html" not in path:
        path += ".html"

    if path is not "home.html" and path is not "form.html":
        path = "./page_cache/" + path

    msg = "HTTP/1.1 200 OK\r\n\r\n"
    try:
        f = open(path, "r")
        msg += f.read()
    except IOError:
        msg = "HTTP/1.1 404 NOT FOUND\r\n\r\n"
    finally:
        sock.sendall(str.encode(msg))

def handle_POST(sock, mesg):
    ''' Handles http POST requests. '''
    start = clock()
    inpt = clean_input(mesg)
    inpt_skim, in_strs = parse_internal_strings(inpt)
    
    # Create match index for further use
    index = build_index(inpt_skim, in_strs)
   
    # Incrementally build index from iterative webpage crawls
    visited = []
    queue = open("start_db.txt").read().split()
    page_count = 0
    state_fname = "crawl_log.txt"
    
    for i in range(MAX_PAGE_SEARCH):
        if(len(queue) == 0):
            break

        # Take a break, save current state of server, then rebuild
        # data structures
        if(page_count % PAGE_INCREMENT == PAGE_INCREMENT - 1):
            sleep(1)
            save_state(state_fname, page_count, index, queue, visited)
            page_count, index, queue, visited = load_state(state_fname)
        page_count += 1
        # Open first link in queue
        l = queue.pop(0)
        if l not in visited:
            visited.append(l)
            
            # Remove trailing '/' to avoid hostname conflicts
            if(l[-1] == '/'):
                l = l[:-1]
            host, path = get_host_from_link(l)
            if host == "www.eg.bucknell.edu":
               send_sock = socket(AF_INET, SOCK_STREAM)
               send_sock.connect((host, DEFAULT_PORT))
            
               # If pdf, convert to text using pdftotext and then read
               fn, fe = os.path.splitext(l)
               if fe == ".pdf":
                   resp = handle_pdf(send_sock, host, path)
               # Check if link if a cached file
               # If is, then read that
               elif is_file("./page_cache/", host + path):
                   resp = get_file_data("./page_cache/", host + path)
               # Else, go find online and cache into file
               else:
                   send_html_get(send_sock, host, path)
                   resp = get_html_response(send_sock)
                   resp = remove_html_comments(resp)
                   # Store data in cache for later
                   try:
                       write_to_file("./page_cache/", host + path, resp.split('\r\n\r\n')[1])
                   except IndexError:
                       continue
               if resp != None and resp != "":
                   links = extract_links(resp)
                   links = clean_links(links, host, path)
                   for i in links:
                       fn, fe = os.path.splitext(i)
                       if fe == '.txt' or fe == '.html' or fe == '.xml' or fe == "" or fe == ".pdf":
                           if i not in queue and i not in visited:
                               h2, p2 = get_host_from_link(i)
                               if h2 == "www.eg.bucknell.edu":
                                   queue += [i]
                   page_words = extract_words(resp)
                   matches = match_words(page_words, inpt_skim, in_strs, index, l)
                   send_sock.close()
            else:
                i -= 1
        else:
            i -= 1

    page = str(construct_resp_site(inpt, index, start))
    sock.sendall(str.encode(page))
    save_state(state_fname, page_count, index, queue, visited)


def send_html_get(sock, host, path):
    ''' Send out http get request for given page. '''
    send_str  = "GET " + path + " HTTP/1.1\r\nHost: " + host + "\r\n"
    send_str += "User-Agent: self-module\r\n"
    send_str += "Accept: text/html.application/xhtml+cml\r\n"
    send_str += "Accept-Charset: ISO-8859-1,utf-8;q=0.7\r\n"
    send_str += "Keep-Alive: timeout=60\r\n"
    send_str += "Connection: close\r\n"
    send_str += "\r\n"
    sock.sendall(str.encode(send_str))


def get_html_response(sock, is_pdf = False):
    ''' Retrieve http response from given request. '''
    resp = ""
    buf = b""
    while(True):
        try:
            data = sock.recv(1024)
            if not data: break
            buf += data
            sock.setblocking(0)
        except:
           pass
    if is_pdf:
        return buf
    
    resp = buf.decode("utf-8")
    sock.setblocking(1)
    return resp


def extract_links(html):
    ''' Find and return all html links in the given html code. '''
    href_pattern = r'<a\s.*\s*href\s*=\s*\n*\r*\s*"((https?://)?[.a-z0-9\?/=:~_-]+\s*)"'
    meta_pattern = r'<\s*meta\s*.*\s*URL=(.*)\s*"'
    
    matches = re.findall(href_pattern, html, flags = re.IGNORECASE|re.MULTILINE)
    matches1 = re.findall(meta_pattern, html, flags = re.IGNORECASE|re.MULTILINE)
    
    skimmed_matches = []
    for s in matches:
        skimmed_matches += [s[0]]
    for s in matches1:
        skimmed_matches += [s]

    return skimmed_matches


def extract_words(html):
    ''' Find and return a list of all words to be parsed for matches from html. '''
    stop_words = open("stop.txt", "r").read()

    words = re.findall(r'\w+', html, flags = re.IGNORECASE|re.MULTILINE)
    for i in words:
        if i in stop_words:
            while i in words:
                words.remove(i)
    return words


def match_words(words, inpt, in_str, index, fname):
    ''' Check if any words in query match words in the given html words. '''
    wordstr = " ".join(words)
    ret = False
    # Check if internal strings are in the given webpage
    if in_str is not None:
        for i in in_str:
            if i in wordstr:
                index[i] += [fname]
                ret = True

    # Check if rest occur in webpage
    for i in inpt:
        if i.lower() in list(map(str.lower, words)):
            index[i] += [fname]
            ret = True
    
    return ret


def construct_resp_site(query, matches, time):
    ''' Determine which response page to build and send to client. '''
    num_matches = 0
    for i in matches.keys():
        num_matches += len(matches[i])
    
    if(num_matches > 0):
        return match_site(query, matches, time)
    return no_match_site(query)


def match_site(query, index, start):
    ''' Build a site of all link matches and send to client. '''
    num_matches = 0
    count = 0
    used = []
    for i in list(index.values()):
        num_matches += len(i)
    
    end = clock()
    
    buff  = "HTTP/1.1 200 OK\r\n\r\n"
    buff += "<html>"
    buff += "<head>"
    if(num_matches == 1):
        buff += '<title>' + str(num_matches) + ' match!</title>'
    else:
        buff += '<title>' + str(num_matches) + ' matches!</title>'
    buff += "</head>"
    buff += "<body>"
    buff += "<p>Query: " + query + "</p>"
    if(num_matches == 1):
        buff += "<p>" + str(num_matches) + " Match found in " + "%.2f" %(end-start) + " seconds</p>"
    else:
        buff += "<p>" + str(num_matches) + " Matches found in " + "%.2f"%(end-start) + " seconds</p>"
    buff += "<p>"
    # Populate with links from index
    for i in index.values():
        for j in i:
            if j not in used:
                used += [j]
                count += 1
                buff += "<p>" + str(count) + '. <a href = "'
                buff += str(j) + '"' + '>'
                buff += str(j)
                buff += '</a>'
                buff += "<br>"
    buff += '</p>'
    buff += "<br>"
    buff += '<a href="/">'
    buff += "   <button>Try again!</button>"
    buff += "</a>"
    buff += "</body>"
    buff += "</html>"
    return buff
    

def no_match_site(query):
    ''' Build a page telling client no matches were found. '''
    buff  = "HTTP/1.1 200 OK\r\n\r\n"
    buff += "<html>"
    buff += "<head>"
    buff += "<title>No matches!</title>"
    buff += "</head>"
    buff += "<body>"
    buff += "<p>Query: " + query + "</p>"
    buff += "<p>No matches!</p>"
    buff += '<form method="GET" action="/">'
    buff += '<input type="submit" value="Try again!">'
    buff += "</body>"
    buff += "</html>"
    return buff
 

def parse_internal_strings(words):
    ''' Find and return all quoted portions of query for phrase matching. '''
    ret = []
    ret_in_str = []
    temp = deepcopy(words)
    matches = re.findall(r'\"(.+?)\"', temp)
    
    # Make internal string list
    for i in matches:
        ret_in_str += [i.strip()]
        temp = re.sub(r'\"(.+?)\"', '', temp)
    
    # Make rest of strings in list
    temp = temp.split(" ")
    for i in temp:
        if i is not "" and i is not " ":
            ret += [i]
    
    return ret, ret_in_str


def build_index(strs, in_strs):
    ''' Build reverse index for use in parsing and matching. '''
    ret = {}
    for i in strs:
        ret[i] = []

    for j in in_strs:
        ret[j] = []

    return ret


def get_host_from_link(link):
    ''' Parse out the host from a given link. '''
    temp = deepcopy(link)
    add = ""

    if "https://" in temp:
        temp = re.sub("https://", '', temp)
        add = "https://"
    else:
        temp = re.sub("http://", '', temp)
        add = "http://"

    temp = temp.split('/', 1)
    if len(temp) <= 1:
        temp += ['/']
    if temp[1] == "":
        temp[1] = "/"
    fn, fe = os.path.splitext(temp[1])
    if temp[1][-1] is not '/' and fe == "":
        temp[1] = temp[1] + '/'

    return temp[0], '/' + temp[1]


def convertRelPath(inPath, currentUrl):
    ''' Convert relative links to absolute paths given the host and relative path. '''
    temp = currentUrl.rfind('/')
    fn, fe = os.path.splitext(currentUrl[temp:])
    if fe != "":
        currentUrl = currentUrl[0:temp+1]
    loc = currentUrl.find('://') + 3
    loc = currentUrl[loc:].find('/')
    path = deepcopy(currentUrl[loc:])
    if inPath == None:
        return path
    elif inPath[0] == '/':
        path = deepcopy(inPath)
    else:
        path += inPath
    if path == None:
        return currentUrl
    i = findStrLoc(path, '/./', 0)
    while i >= 0:
        temp = deepcopy(path[:i])
        temp += path[i+2:]
        path = deepcopy(temp)
        i = findStrLoc(path, "/./", 0)

    i = findStrLoc(path, "/../", 0)
    while i >= 0:
        i2 = findloc_r(path, '/', i-2)
        if i2 < 0:
            i2 = i
        temp = deepcopy(path[:i2])
        temp += path[i+3:]
        path = deepcopy(temp)
        i = findStrLoc(path, "/../", 0)
    return path[1:]


def findloc_r(s, c, i):
    ''' Used to find position of given character from offset in reverse. '''
    while i >= 0 and s[i] != 0 and s[i] != c:
        i -= 1
    if i >= 0 and s[i] == c:
        return i
    else:
        return -1


def findStrLoc(s, pattern, i):
    ''' Used to find position of given character from offset. '''
    found = -1
    while i < len(s) and found == -1:
        if s[i] == pattern[0] and s[i:i+len(pattern)] == pattern:
            found = i 
        i += 1

    return found


def clean_links(links, host, path):
    ''' Clean up links found on a webpage by converting to absolute paths and
    completing partial links. '''
    for i in range(len(links)):
        if "http://" not in links[i] and "https://" not in links[i]:
            # If link is host root link
            if links[i][0] == "/":
                links[i] = convertRelPath(links[i], host)[1:]
            # If link is not host root link
            elif links[i][0:2] != './' or links[i][0:3] != '../':
                links[i] = "./" + links[i]
                links[i] = convertRelPath(links[i], host + path)[1:]
            links[i] = "http://" + host + links[i]
    return links


def remove_html_comments(html):
    ''' Remove comments in html to avoid unnecessary parsing. '''
    pattern = r'<!--.*?-->'
    r = re.compile(pattern, re.IGNORECASE|re.DOTALL|re.MULTILINE)
    html = r.sub("", html)
    return html


def is_file(dname, fname):
    ''' Checks if given file exists. '''
    return os.path.isfile(conv_to_cache_name(dname, fname))


def conv_to_cache_name(dname, fname):
    ''' Converts path to save cache scheme ie. "/" -> "___". '''
    return dname + fname.replace("/", "___", len(fname))


def conv_from_cache_name(dname, fname):
    ''' Converts save cache name to web link name. '''
    return dname + fname.replace("___", "/". len(fname))


def get_file_data(dname, fname):
    ''' Read file data and return. '''
    # If pdf convert to text and return
    fn, fe = os.path.splitext(fname)
    if fe == ".pdf":
        data = open(conv_to_cache_name(dname, fname), "rb").read()
        tf = tempfile.NamedTemporaryFile()
        tf.write(data)
        tf.seek(0)

        otf = tempfile.NamedTemporaryFile()
        if len(data) > 0:
            out = subprocess.Popen(['pdftotext', '-layout', '-q', tf.name, otf.name], stdout = subprocess.PIPE).communicate()[0]
            return otf.read().decode("utf-8")
        else:
            return None
    
    return open(conv_to_cache_name(dname, fname), "r").read()


def write_to_file(dname, path, data):
    ''' Write html data to file for cache searching. '''
    fname = conv_to_cache_name(dname, path)
    if type(data) is str:
        f = open(fname, "w+")
    elif type(data) is bytes:
        f = open(fname, "wb+")
    f.write(data)
    f.close()


def clean_input(mesg):
    ''' Parse out and clean up query input from form page. '''
    # Take the argument line...
    inpt = mesg.splitlines()[-1]
    # Divide by each input except the last (the form info)
    inpt = inpt.split("&")[:-1]
    # Split the user text and the field name
    inpt = str(inpt[0].split("=")[-1])
    # Replace html +/spaces with whitespace
    inpt = inpt.replace("+", " ")
    # Decode string from html encoding to pystring
    inpt = unquote(inpt)
    return inpt


def save_state(fname, count, index, queue, visited):
    ''' Save state of crawler to file for continued use. '''
    f = open(fname, "w+")
    f.write(str(count))
    f.write("\n")
    f.write("\n")
    for i in queue:
        f.write(str(i))
        f.write("\n")
    f.write("\n")
    for i in visited:
        f.write(str(i))
        f.write("\n")
    f.write("\n")
    for i in index.keys():
        f.write(str(i))
        f.write("\n")
        for j in index[i]:
            f.write(str(j))
            f.write("\n")
        f.write("\n")
    f.write("\n")
    f.close()


def load_state(fname):
    ''' Loads the previous state of the parser from file. '''
    data = open(fname, "r").readlines()
    ret_count = 0
    ret_queue = []
    ret_visited = []
    ret_index = {}

    state = 0
    in_value_state = False
    curr_key = ""

    for i in range(len(data)):
        if data[i] == "\n" and state != 3:
            state += 1
            continue

        # data[i][:-1] removes trailing newline left by readlines()
        if state == 0:
            # Should only occur for first line
            # Page count
            ret_count = int(data[i][:-1])

        elif state == 1:
            # The queue
            ret_queue += [data[i][:-1]]

        elif state == 2:
            # The visited list
            ret_visited += [data[i][:-1]]

        elif state == 3:
            # The index
            if data[i] == "\n":
                in_value_state = False
                continue

            if not in_value_state:
                ret_index[data[i][:-1]] = []
                curr_key = data[i][:-1]
                in_value_state = True
                continue

            if in_value_state:
                ret_index[curr_key] += [data[i][:-1]]
                continue
        else:
            break

    return ret_count, ret_index, ret_queue, ret_visited


def send_500_error(sock):
    ''' Send default 500 error message incase server error occurs. '''
    s  = "HTTP/1.1 200 OK\r\n\r\n"
    s += "<html>"
    s += "<head>"
    s += "<title>Server error!</title>"
    s += '<meta http-equiv="refresh" content="5;URL=/">'
    s += "</head>"
    s += "<body>"
    s += "<p>500 Internal Server Error</p>"
    s += "<p>Redirecting in 5 seconds</p>"
    s += "</body>"
    s += "</html>"
    sock.sendall(str.encode(s))


def handle_pdf(sock, host, path):
    ''' Handles fetching and parsing pdf data.  '''
    if not is_file("./page_cache/", host + path):
        send_html_get(sock, host, path)
        resp = get_html_response(sock, True)
        resp = resp.decode("latin-1")
        # Remove html header 
        resp = resp.split("\r\n\r\n")[1]
        resp = resp.encode("latin-1")

        # Store data in cache for later
        if resp is not None:
            write_to_file("./page_cache/", host + path, resp)
    try:
        resp = get_file_data("./page_cache/", host + path)
    except:
        return None
    return resp


main()
