#! /usr/bin/env python3
# -*- coding: utf-8 -*-

__version__ = '2.3'
__program__ = 'HawkScan'
__author__ = 'codejump'
__twitter__ = 'https://twitter.com/c0dejump'
__projects__ = 'https://github.com/c0dejump'


#modules in standard library
import requests
import sys, os, re
import time
from datetime import datetime
from time import strftime
import argparse
from bs4 import BeautifulSoup
import json
import traceback
from requests.exceptions import Timeout
from requests.auth import HTTPBasicAuth
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import signal
import random

# external modules
from config import PLUS, WARNING, INFO, LESS, LINE, FORBI, BACK, EXCL, SERV_ERR, BYP, WAF, EXT_B, MINI_B
try:
    from Queue import Queue
except:
    import queue as Queue
import threading
from threading import Thread

from fake_useragent import UserAgent
try:
    UserAgent = UserAgent()
except Exception:
    UserAgent = ["Mozilla/5.0 (Windows NT 6.3; WOW64; Trident/7.0; LCJB; rv:11.0) like Gecko", "c0dejump", "Mozilla/5.0 (X11; Linux x86_64; rv:102.0) Gecko/20100101 Firefox/102.0"]

from static.banner import banner

from report.creat_report import create_report

from modules.waf.detect_waf import verify_waf
from modules.waf.bypass_waf import bypass_waf

from modules.before_fuzzing.before_run import before_start
from modules.before_fuzzing.check_subdomain import subdomain

from modules.during_fuzzing.parsing_html import parsing_html
from modules.during_fuzzing.bypass_forbidden import bypass_forbidden
from modules.during_fuzzing.check_backup import scan_backup, vim_backup

from modules.manage_dir import manage_dir

from modules.terminal_size import terminal_size
from modules.output import multiple_outputs
from modules.resume import resume_options

from modules.after_fuzzing.scan_errors import scan_error
try:
    from modules.after_fuzzing.send_notify import notify_scan_completed
except:
    notify = False

from modules.proxy.check_proxy import check_proxy

from modules.auto_update import auto_update
from run_modules import check_modules


try:
    enclosure_queue = Queue()
except:
    enclosure_queue = Queue.Queue()

requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
#requests.packages.urllib3.util.ssl_.DEFAULT_CIPHERS += ':ADH-AES128-SHA256'
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module='bs4')

rec_list = []
#list to append url and then recursif scan

req_p = u""
#for exclude option

stat = 0

tw, th = terminal_size() # determine terminal size

header_parsed = {}

basic_user_agent = {"User-agent": "Mozilla/5.0 (Windows NT 6.3; WOW64; Trident/7.0; LCJB; rv:11.0) like Gecko"}


class ThreadManager:
    """
    Class ThreadManager:
        To manage threads (add_thread())
        To stop thread (stop_thread())
    """
    workers = []

    lock = threading.Lock()

    def __init__(self, queue):
        self.queue = queue
 
    def add_thread(self, i, threads, manager):
        """
        add thread from function definded_thread()
        """
        #print(self.workers[0])
        t_event = threading.Event()
        worker = threading.Thread(target=thread_wrapper, args=(i, self.queue, threads, manager, t_event))
        worker.daemon = True
        worker.start()
        self.workers.append((worker, t_event))

    def stop_thread(self):
        """ for stop thread => #TODO to remake"""
        t, e = self.workers[0]
        e = e.set() # put event to set True for stop thread
        del self.workers[0]


class filterManager:
    """
    Class filterManager:
        Filter page or response status code for remove false positif
        functions:
            - check_exclude_code
            - check_exclude_page
    """

    def exclude_type(self, req_p, s, req, res, directory, forbi, get_date, bp_current, parsing, len_req):
        if type(req_p) == list and len(req_p) > 1:
            #print(len_req)
            self.check_multiple(s, req, res, directory, forbi, get_date, bp_current, parsing, size_bytes=len_req)
        elif type(req_p) == int:
            self.check_exclude_code(s, res, req, directory, get_date, bp_current, parsing)
        else:
            #print(req)
            self.check_exclude_page(s, req, res, directory, forbi, get_date, bp_current, parsing, size_bytes=len_req)


    def  check_multiple(self, s, req, res, directory, forbi, HOUR, bp_current, parsing=False, size_bytes=False):
        """
        Check_multiple: check multiple exclude, ex:
        --exclude 500,1337b,https://www.exemple.com
        --exclude 500,403
        """
        req_bytes = len(req.content)
        exclude_bytes = "[{}b]".format(req_bytes)
        list_exclude = {}
        for l_exclude in req_p:
            list_exclude[l_exclude] = False
        #print(list_exclude) #Debug
        for m_exclude in req_p:
            try:
                if int(m_exclude):
                    #print(m_exclude)
                    check_code = self.check_exclude_code(s, res, req, directory, HOUR, bp_current, parsing, multiple=True)
                    if check_code:
                        list_exclude[m_exclude] = True
            except:
                check_page = self.check_exclude_page(s, req, res, directory, forbi, HOUR, parsing, size_bytes, multiple=m_exclude)
                if check_page:
                    list_exclude[m_exclude] = True
        #print(list_exclude)
        if False not in list_exclude.values():
            if req.status_code in [403, 401]:
                print("{} {} {:<13}{:<10} ".format(HOUR, FORBI, exclude_bytes, res))
                bp_current += 1
                bypass_forbidden(res, exclude[:-1] if "b" in exclude else False)
                bp_current -= 1
            elif req.status_code in [400, 500]:
                print("{} {} {:<13}{:<10}  [{}]".format(HOUR, SERV_ERR, exclude_bytes, res, req.status_code))
            elif req.status_code in [301, 302]:
                redirect_link = ""
                for rh in req.headers:
                    if "location" in rh or "Location" in rh:
                        loc = req.headers[rh]
                        redirect_link = loc if "http" in loc.split("/")[0] else "{}{}".format(url, loc)
                        req_loc = s.get(loc, verify=False, allow_redirects=False, headers=basic_user_agent)
                        if "/".join(res.split("/")[1:]) == "/".join(loc.split("/")[1:-1]) and len(req_loc.content) != index_len and not "." in loc:
                            print(" \033[33m[<>]\033[0m {} redirect to \033[33m{}\033[0m [\033[33mPotential Hidden Directory\033[0m]".format(res, loc))
                    else:
                        req_loc = s.get(res, verify=False, allow_redirects=True, headers=basic_user_agent)
                        redirect_link = req_loc.url
                print("{} {} {:<13}{:<10}\033[33m → {}\033[0m {}\r".format(HOUR, LESS, exclude_bytes, res, redirect_link, req.status_code))
            else:
                print("{} {} {:<13}{:<10}  [{}]".format(HOUR, PLUS, exclude_bytes, res, req.status_code))
            for l_exclude in req_p:
                list_exclude[l_exclude] = False



    def check_exclude_code(self, s, res, req, directory, HOUR, bp_current, parsing=False, multiple=False):
        """
        check_exclude_code: 
        You can activate this option to pass the  bp_current,response status code, ex:
        --exclude 500
        """
        req_bytes = len(req.content)
        exclude_bytes = "[{}b]".format(req_bytes)
        req_st = str(req.status_code) if multiple else req.status_code
        if multiple and req_st in req_p:
            return False
        elif req_st == req_p:
            pass
        elif req_st in [403, 401]:
            bp_current += 1
            bypass_forbidden(res)
            bp_current -= 1
        elif req_st in [500, 400, 422, 423, 424, 425]:
            print("{} {} {:<13}{:<10} \033[33m{} Server Error\033[0m".format(HOUR, SERV_ERR, exclude_bytes, res, req.status_code))
            if js and req_bytes > 0:
                parsing.get_javascript(res, req, directory)
        elif req_st in [301, 302]:
            redirect_link = ""
            for rh in req.headers:
                if "location" in rh or "Location" in rh:
                    loc = req.headers[rh]
                    redirect_link = loc if "http" in loc.split("/")[0] else "{}{}".format(url, loc)
                    req_loc = s.get(redirect_link, verify=False, allow_redirects=False, headers=basic_user_agent)
                    if "/".join(res.split("/")[1:]) == "/".join(loc.split("/")[1:-1]) and len(req_loc.content) != index_len and not "." in loc:
                        print(" \033[33m[<>]\033[0m {} redirect to \033[33m{}\033[0m [\033[33mPotential Hidden Directory\033[0m]".format(res, loc))
                else:
                    req_loc = s.get(res, verify=False, allow_redirects=True, headers=basic_user_agent)
                    redirect_link = req_loc.url
            print("{} {} {:<13}{:<10}\033[33m → {}\033[0m {}\r".format(HOUR, LESS, exclude_bytes, res, redirect_link, req.status_code))
            if js and req_bytes > 0:
                parsing.get_javascript(res, req, directory)
        else:
            if multiple:
                return True
            else:
                print("{} {} {:<13}{:<10}".format(HOUR, PLUS, exclude_bytes, res))
                if req_bytes > 0:
                    html_actions(directory, res, req, parsing)
                output_scan(directory, res, req_bytes, 200)


    def check_exclude_page(self, s, req, res, directory, forbi, HOUR, bp_current, parsing=False, size_bytes=False, multiple=False):
        """
        Check_exclude_page:  
        If scan blog, or social network etc.. you can activate this option to pass profil/false positive pages or response status code.
        Do a percentage btw pages.
        for use this option you do defined a profil/false positive page base, ex: 
            --exclude url.com/profil/codejump
        OR
            --exclude 240b for just number of bytes
        """
        scoring = 0
        multiple = multiple if multiple else "0b"
        req_bytes = len(req.content)

        if multiple and "." in multiple:
            print("\n\033[34mHi ! Sorry but multiple excludes with an url doesn't work for the moment, please put a number or bytes number\n(ex: --exclude 404,1337b)\033[0m")
            pid = os.getpid()
            os.killpg(pid, signal.SIGSTOP)

        if "b" in exclude[0][-1] and int(exclude[0][0]) or multiple[-1] == "b" and int(multiple[0]):
            #For exclude bytes number
            multiple = False if multiple == "0b" else multiple
            req_len = int(exclude[0][0:-1]) if not multiple else int(multiple.split('b')[0])
            exclude_bytes = "[{}b]".format(req_bytes)
            if multiple and req_bytes == req_len:
                return False
            elif multiple and req_bytes != req_len:
                return True
            if not multiple:
                if req_bytes == req_len:
                    pass
                elif req_bytes != req_len and req.status_code == 200:
                    print("{} {} {:<13}{:<10}".format(HOUR, PLUS, exclude_bytes, res))
                    if req_bytes > 0:
                        html_actions(directory, res, req, parsing)
                elif req_bytes != req_len and req.status_code in [401, 403]:
                    print("{} {} {:<13}{:<10}".format(HOUR, FORBI, exclude_bytes, res))
                elif req_bytes != req_len and req.status_code in [500, 502, 400, 422, 423, 424, 425]:
                    print("{} {} {:<13}{:<10} \033[33m{} Server Error\033[0m".format(HOUR, SERV_ERR, exclude_bytes, res, req.status_code))
                elif req_bytes != req_len and req.status_code in [301, 302]:
                    redirect_link = req.url
                    print("{} {} {:<13}{:<10}\033[33m → {}\033[0m {}\r".format(HOUR, LESS, exclude_bytes, res, redirect_link, req.status_code))
                    if js and req_bytes > 0:
                        parsing.get_javascript(res, req, directory)
        else:
            ### Exclude page ###
            ## TODO
            multiple = False if multiple == "0b" else multiple
            if stat == 301 or stat == 302:
                req = requests.get(req.url, verify=False, headers=basic_user_agent)
            words = req_p
            for w in words.split("\n"):
                if w in req.text:
                    scoring += 1
                else:
                    pass
            len_wd = [lines for lines in words.split("\n")] #to avoid to do line per line
            perc = round(float(scoring) / len(len_wd) * 100)#to do a percentage for check look like page
            #print(req.text)
            #print(perc) #DEBUG percentage
            #print(multiple)
            if perc >= 80:
                pass
            elif perc > 50 and perc < 80:
                print("{} {} {} [Potential exclude page with {}%]".format(HOUR, EXCL, res, perc))
            else:
                exclude_bytes = "[{}b]".format(len(req.content))
                if req.status_code in [403, 401]:
                    bp_current += 1
                    print("{} {} {:<13}{:<10} \033[31m{} Forbidden \033[0m".format(HOUR, FORBI, exclude_bytes, res, req.status_code))
                    bypass_forbidden(res, exclude[:-1] if "b" in exclude else False)
                    bp_current -= 1
                elif req.status_code in [500, 400, 422, 423, 424, 425]:
                    if multiple:
                        return True
                    else:
                        print("{} {} {:<13}{:<10} \033[33m{} Server Error\033[0m".format(HOUR, SERV_ERR, exclude_bytes, res, req.status_code))
                else:
                    if multiple:
                        return True
                    else:
                        if req_bytes > 0:
                            html_actions(directory, res, req, parsing)
                        print("{} {} {:<13}{:<10}".format(HOUR, PLUS, exclude_bytes, res))
                #check backup
                create_backup(res, directory, forbi)
                #output scan.txt
                output_scan(directory, res, len(req.content), stats=200)
                if res[-1] == "/" and recur:
                    if ".git" in res:
                        pass
                    else:
                        spl = res.split("/")[3:]
                        result = "/".join(spl)
                        rec_list.append(result)
                        output_scan(directory, res, len(req.content), stats=200)


class runFuzzing:
    """
    Class runFuzzing:
    Run fuzzing of webpage
    functions:
    - tryUrl
    """
    def light_mode(self, uri, directory, s, forced=False, u_agent=False):
        filterM = filterManager()
        parsing = parsing_html()

        percentage = lambda x, y: float(x) / float(y) * 100.00

        waf = False
        tested_bypass = False

        global bp_current
        bp_current = 0

        global n_error
        n_error = 0
        
        res = uri
        page = "/".join(res.split("/")[3:])
        #print("{} :: {}".format(res.split("/"), "/".join(res.split("/")[3:]))) #DEBUG  
        try:
            user_agent_r = random.choice(UserAgent) if type(UserAgent) == list else UserAgent.random
            user_agent = {'User-agent': u_agent} if u_agent else {'User-agent': user_agent_r} #for a random user-agent
            try:
                forbi = False

                req = requests.get(res, verify=False, timeout=10)

                if ts: #if --timesleep option defined
                    time.sleep(ts)
                if req == 404:
                    status_link = req
                elif req != 404 and req.history:
                    status_link = [histo.status_code for histo in req.history]
                else:
                    status_link = req.status_code

                len_req = len(req.content) if req != 404 else False   
                bytes_len = "[{}b]".format(len_req)    
                display_res = res if tw > 110 else page 
                #print(status_link) #DEBUG status response

                if status_link == 200:
                    if exclude:
                        filterM.exclude_type(req_p, s, req, res, directory, forbi, get_date(), bp_current, parsing, len_req)
                    else:            
                        if len(req.content) > 0:
                            html_actions(directory, res, req, parsing)
                        print("{} {} {:<13}{:<10}".format(get_date(), PLUS, bytes_len, display_res))
                        output_scan(directory, res, len_req, stats=200) #check backup
                        create_backup(res, directory, forbi) #add directory for recursif scan
                elif status_link in [401, 403]:
                    if exclude:
                        filterM.exclude_type(req_p, s, req, res, directory, forbi, get_date(), bp_current, parsing, len_req)
                    else:
                        two_verify = requests.get(url, verify=False, headers=basic_user_agent)
                        if "Generated by cloudfront" in req.text and "Request blocked" in req.text and two_verify.status_code in [403, 401]:
                            print("{} {} Cloudflare protection activated on {}, wait 60s please".format(get_date(), WARNING, req.url))
                            time_wait(time_i)
                        if not forced:
                            forbi = True
                            print("{} {} {:<13}{:<10} \033[31m{} Forbidden \033[0m".format(get_date(), FORBI, bytes_len, display_res, status_link))
                        elif not forced and recur:
                            pass
                        else:
                            """print("{} {} {:<13}{:<10} \033[31m{} Forbidden \033[0m".format(get_date(), FORBI, bytes_len, display_res, status_link))
                            output_scan(directory, res, len_req, stats=403)"""
                            pass
                elif status_link == 404:
                    pass
                elif status_link == 405:
                    if exclude:
                        filterM.exclude_type(req_p, s, req, res, directory, forbi, get_date(), bp_current, parsing, len_req)
                    else:
                        print("{} {} {:<13}{:<10} [405]".format(get_date(), INFO, bytes_len, display_res))
                        if len(req.content) > 0:
                            html_actions(directory, res, req, parsing)
                    #report.create_report_url(status_link, res, directory)
                elif status_link in [301, 302]:
                    if exclude:
                        filterM.exclude_type(req_p, s, req, res, directory, forbi, get_date(), bp_current, parsing, len_req)
                    else:
                        redirect_link = ""
                        for rh in req.headers:
                            if "location" in rh or "Location" in rh:
                                loc = req.headers[rh]
                                redirect_link = loc if "http" in loc.split("/")[0] else "{}{}".format(url, loc)
                                req_loc = requests.get(redirect_link, verify=False, allow_redirects=False, headers=basic_user_agent)
                                if "/".join(res.split("/")[1:]) == "/".join(loc.split("/")[1:-1]) and len(req_loc.content) != index_len and not "." in loc:
                                    print(" \033[33m[<>]\033[0m {} redirect to \033[33m{}\033[0m [\033[33mPotential Hidden Directory\033[0m]".format(res, loc))
                            else:
                                req_loc = requests.get(res, verify=False, allow_redirects=True, headers=basic_user_agent)
                                redirect_link = req_loc.url
                        print("{} {} {:<13}{:<10}\033[33m → {}\033[0m {}\r".format(get_date(), LESS, bytes_len, display_res, redirect_link, status_link))
                        if len(req.content) > 0:
                            html_actions(directory, res, req, parsing)
                        output_scan(directory, res, len_req, stats=301)
                        #report.create_report_url(status_link, res, directory) #TODO
                elif status_link == 304:
                    print("{}\033[33m[+] \033[0m {}\033[33m 304 Not modified \033[0m".format(get_date(), display_res))
                    if len(req.content) > 0:
                        html_actions(directory, res, req, parsing)
                    #report.create_report_url(status_link, res, directory) #TODO                
                elif status_link in [307, 308]:
                    pass
                elif status_link in [400, 500]:
                    #pass
                    if exclude:
                        filterM.exclude_type(req_p, s, req, res, directory, forbi, get_date(), bp_current, parsing, len_req)
                    else:
                        if len(req.content) > 0:
                            html_actions(directory, res, req, parsing)          
                        print("{} {} {:<13}{:<10} \033[33m{} Server Error\033[0m".format(get_date(), SERV_ERR, bytes_len, display_res, status_link))
                        output_scan(directory, res, len_req, stats=status_link)
                elif status_link in [422, 423, 424, 425]:
                    print("{} {} {} \033[33mError WebDAV\033[0m\r".format(get_date(), LESS, res if tw > 110 else page))
                    if len(req.content) > 0:
                        html_actions(directory, res, req, parsing)
                    #report.create_report_url(status_link, res, directory) #TODO
                elif status_link == 405:
                    print("{} {} {}".format(get_date(), PLUS, display_res))
                    #output_scan(directory, res, stats=405)
                elif status_link == 503:
                    req_test_index = requests.get(url, verify=False, headers=basic_user_agent) # take origin page url (index) to check if it's really unavailable
                    if req_test_index.status_code == 503 and not forced:
                        #manager.stop_thread() #TODO
                        print("{}{} Service potentialy Unavailable, The site web seem unavailable please wait...\n".format(get_date(), WARNING))
                        time_wait(time_i)
                    else:
                        pass
                elif status_link in [429, 522]:
                    if "Just a moment" in req.text:
                        print("{} {} Cloudflare protection activated, wait 60s please".format(get_date(), WARNING))
                        time_wait(time_i)
                    else:
                        pass
            except Timeout:
                n_error += 1
                #traceback.print_exc() #DEBUG
                with open(directory + "/errors.txt", "a+") as write_error:
                    write_error.write(res+"\n")
                #pass
            except Exception:
                n_error += 1
                if print_error:
                    traceback.print_exc() #DEBUG
                with open(directory + "/errors.txt", "a+") as write_error:
                    write_error.write(res+"\n")
        except Exception:
            n_error += 1
            if print_error:
                traceback.print_exc() #DEBUG


    def tryUrl(self, i, q, threads, manager=False, directory=False, forced=False, u_agent=False, nLine=False):
        """
        tryUrl:
        Test all URL contains in the dictionnary with multi-threading.
        This script run functions:
        - create_backup()
        - dl()
        - suffix_backup()
        - mail()
        """
        global n
        n = 0 if not nLine else nLine

        global n_error
        n_error = 0

        global bp_current
        bp_current = 0

        filterM = filterManager()
        parsing = parsing_html()

        s = requests.session()
        s.verify=False

        thread_score = 0
        score_next = 0
        #waf_score = 0
        percentage = lambda x, y: float(x) / float(y) * 100.00
        stop_add_thread = False
        time_i = 60
        waf = False
        tested_bypass = False

        for numbers in range(len_w):
            n += 1
            thread_count = threading.active_count() - 1
            res = q.get()
            page = "/".join(res.split("/")[3:])
            #print("{} :: {}".format(res.split("/"), "/".join(res.split("/")[3:]))) #DEBUG  

            if auto and not stop_add_thread:
                thrds, scores = defined_thread(threads, thread_score, score_next)
                if scores == 1:
                    thread_score += 1
                if thrds == 1:
                    threads += 1
                    score_next += 1
                    manager.add_thread(i, threads, manager)
                #print("{}: {}".format(threading.currentThread().getName() ,thread_score))#DEBUG
            try:
                user_agent_r = random.choice(UserAgent) if type(UserAgent) == list else UserAgent.random
                user_agent = {'User-agent': u_agent} if u_agent else {'User-agent': user_agent_r} #for a random user-agent
                try:
                    forbi = False
                    if ts: #if --timesleep option defined
                        time.sleep(ts)

                    req = defined_connect(s, res, user_agent, header_parsed)    

                    waf = verify_waf(s, req, res, user_agent) if not forced else False
                    #verfiy_waf function, to check if waf detected, True: detected # False: not detected    

                    if waf:
                        if not tested_bypass:
                            try_bypass_waf = bypass_waf(req, res)
                            #print(try_bypass_waf) #DEBUG
                            #print(user_agent) #DEBUG
                            if try_bypass_waf == False: # if not worked not repeat
                                print("{}\033[31m[-]\033[0m Our tests not bypass it, sorry".format(BYP))
                                tested_bypass = True
                            elif try_bypass_waf and type(try_bypass_waf) is not bool:
                                user_agent.update(try_bypass_waf)
                        time_wait(time_i)
                        #TODO: if waf_score == X: manager.stop_thread() & re-create with the bypass or potentialy use TOR (apt install tor, pip install torrequest) for next requests after that.
                    if req == 404:
                        status_link = req
                    elif req != 404 and req.history:
                        status_link = [histo.status_code for histo in req.history]
                    else:
                        status_link = req.status_code
                    len_req = len(req.content) if req != 404 else False   

                    bytes_len = "[{}b]".format(len_req)    

                    display_res = res if tw > 110 else page 

                    #print(status_link) #DEBUG status response
                    if status_link == 200:
                        if exclude:
                            filterM.exclude_type(req_p, s, req, res, directory, forbi, get_date(), bp_current, parsing, len_req)
                        else:            
                            if "robots.txt" in res.split("/")[3:]:
                                print("{} {} {}".format(get_date(), PLUS, res))
                                for r in req.text.split("\n"):
                                    print("\t\u251c {}".format(r))

                            if len(req.content) > 0:
                                html_actions(directory, res, req, parsing)

                            print("{} {} {:<13}{:<10}".format(get_date(), PLUS, bytes_len, display_res))
                            output_scan(directory, res, len_req, stats=200) #check backup
                            create_backup(res, directory, forbi) #add directory for recursif scan
                            if res[-1] == "/" and recur:
                                if ".git" in res:
                                    pass
                                else:
                                    spl = res.split("/")[3:]
                                    result = "/".join(spl)
                                    rec_list.append(result)
                            #report.create_report_url(status_link, res, directory) #TODO
                        if backup != None:
                            vim_backup(s, url, res, user_agent, exclude)
                            scan_backup(s, url, res, js, req_p, bp_current, exclude, backup, header_parsed, user_agent, directory, forbi, filterM, page, tw, parsing, authent, get_date=get_date())
                    elif status_link in [401, 403]:
                        two_verify = s.get(url, verify=False, headers=basic_user_agent)

                        if "Generated by cloudfront" in req.text and "Request blocked" in req.text and two_verify.status_code in [403, 401]:
                            print("{} {} Cloudflare protection activated on {}, wait 60s please".format(get_date(), WARNING, req.url))
                            time_wait(time_i)

                        if exclude:
                            filterM.exclude_type(req_p, s, req, res, directory, forbi, get_date(), bp_current, parsing, len_req)
                        else:         
                            if res[-1] == "/" and recur and bytes_len != htaccess_len:
                                bp_current += 1
                                print("{} {} {:<13}{:<10} \033[31m{} Forbidden \033[0m".format(get_date(), FORBI, bytes_len, display_res, status_link))
                                bypass_forbidden(res)
                                bp_current -= 1
                                if ".htaccess" in res or ".htpasswd" in res or ".git" in res or "wp" in res:
                                    output_scan(directory, res, len_req, stats=403)
                                else:
                                    spl = res.split("/")[3:]
                                    result = "/".join(spl)
                                    rec_list.append(result)
                                    output_scan(directory, res, len_req, stats=403)
                                #report.create_report_url(status_link, res, directory)
                            if not forced:
                                forbi = True
                                print("{} {} {:<13}{:<10} \033[31m{} Forbidden \033[0m".format(get_date(), FORBI, bytes_len, display_res, status_link))
                                bp_current += 1
                                bypass_forbidden(res)
                                bp_current -= 1
                                create_backup(res, directory, forbi)
                                output_scan(directory, res, len_req, stats=403)
                                #report.create_report_url(status_link, res, directory)
                            elif not forced and recur:
                                pass
                            else:
                                """print("{} {} {:<13}{:<10} \033[31m{} Forbidden \033[0m".format(get_date(), FORBI, bytes_len, display_res, status_link))
                                output_scan(directory, res, len_req, stats=403)"""
                                pass
                            if backup != None and backup == []:
                                vim_backup(s, url, res, user_agent, exclude)
                                scan_backup(s, url, res, js, req_p, bp_current, exclude, backup, header_parsed, user_agent, directory, forbi, filterM, page, tw, parsing, authent, get_date=get_date())
                    elif status_link == 404:
                        pass
                    elif status_link == 405:
                        if exclude:
                            filterM.exclude_type(req_p, s, req, res, directory, forbi, get_date(), bp_current, parsing, len_req)
                        else:
                            print("{} {} {:<13}{:<10} [405]".format(get_date(), INFO, bytes_len, display_res))
                            if len(req.content) > 0:
                                html_actions(directory, res, req, parsing)
                        #report.create_report_url(status_link, res, directory)
                    elif status_link in [301, 302]:
                        if exclude:
                            filterM.exclude_type(req_p, s, req, res, directory, forbi, get_date(), bp_current, parsing, len_req)
                        else:
                            redirect_link = ""
                            for rh in req.headers:
                                if "location" in rh or "Location" in rh:
                                    loc = req.headers[rh]
                                    redirect_link = loc if "http" in loc.split("/")[0] else "{}{}".format(url, loc)
                                    req_loc = s.get(redirect_link, verify=False, allow_redirects=False, headers=basic_user_agent)
                                    if "/".join(res.split("/")[1:]) == "/".join(loc.split("/")[1:-1]) and len(req_loc.content) != index_len and not "." in loc:
                                        print(" \033[33m[<>]\033[0m {} redirect to \033[33m{}\033[0m [\033[33mPotential Hidden Directory\033[0m]".format(res, loc))
                                else:
                                    req_loc = s.get(res, verify=False, allow_redirects=True, headers=basic_user_agent)
                                    redirect_link = req_loc.url
                            print("{} {} {:<13}{:<10}\033[33m → {}\033[0m {}\r".format(get_date(), LESS, bytes_len, display_res, redirect_link, status_link))
                            if len(req.content) > 0:
                                html_actions(directory, res, req, parsing)
                            output_scan(directory, res, len_req, stats=301)
                            #report.create_report_url(status_link, res, directory) #TODO
                    elif status_link == 304:
                        print("{}\033[33m[+] \033[0m {}\033[33m 304 Not modified \033[0m".format(get_date(), display_res))
                        if len(req.content) > 0:
                            html_actions(directory, res, req, parsing)
                        #report.create_report_url(status_link, res, directory) #TODO                
                    elif status_link in [307, 308]:
                        pass
                    elif status_link in [400, 500]:
                        #pass
                        if exclude:
                            filterM.exclude_type(req_p, s, req, res, directory, forbi, get_date(), bp_current, parsing, len_req)
                        else:
                            vim_backup(s, url, res, user_agent, exclude)
                            if len(req.content) > 0:
                                html_actions(directory, res, req, parsing)          
                            print("{} {} {:<13}{:<10} \033[33m{} Server Error\033[0m".format(get_date(), SERV_ERR, bytes_len, display_res, status_link))
                            output_scan(directory, res, len_req, stats=status_link)
                    elif status_link in [422, 423, 424, 425]:
                        print("{} {} {} \033[33mError WebDAV\033[0m\r".format(get_date(), LESS, res if tw > 110 else page))
                        if len(req.content) > 0:
                            html_actions(directory, res, req, parsing)
                        #report.create_report_url(status_link, res, directory) #TODO
                    elif status_link == 405:
                        print("{} {} {}".format(get_date(), PLUS, display_res))
                        #output_scan(directory, res, stats=405)
                    elif status_link == 503:
                        req_test_index = requests.get(url, verify=False, headers=basic_user_agent) # take origin page url (index) to check if it's really unavailable
                        if req_test_index.status_code == 503 and not forced:
                            #manager.stop_thread() #TODO
                            print("{}{} Service potentialy Unavailable, The site web seem unavailable please wait...\n".format(get_date(), WARNING))
                            time_wait(time_i)
                        else:
                            pass
                    elif status_link in [429, 522]:
                        if "Just a moment" in req.text:
                            print("{} {} Cloudflare protection activated, wait 60s please".format(get_date(), WARNING))
                            time_wait(time_i)
                        else:
                            req_test_many = s.get(url, verify=False, timeout=10, allow_redirects=False, headers=basic_user_agent)
                            if req_test_many in [429, 522]:
                                print("{} {} Too many requests, web service seem to be offline".format(get_date(), WARNING))
                                print("{} {} STOP so many requests, we should wait a little...".format(get_date(), WARNING))
                                time_wait(time_i)
                            else:
                                pass
                    if backup:
                        scan_backup(s, url, res, js, req_p, bp_current, exclude, backup, header_parsed, user_agent, directory, forbi, filterM, page, tw, parsing, authent, get_date=get_date())
                except Timeout:
                    n_error += 1
                    #traceback.print_exc() #DEBUG
                    with open(directory + "/errors.txt", "a+") as write_error:
                        write_error.write(res+"\n")
                    #pass
                except Exception:
                    n_error += 1
                    if print_error:
                        traceback.print_exc() #DEBUG
                    with open(directory + "/errors.txt", "a+") as write_error:
                        write_error.write(res+"\n")
                q.task_done()
            except Exception:
                n_error += 1
                if print_error:
                    traceback.print_exc() #DEBUG
                q.task_done()
            Progress(len_w, thread_count, nLine, page, percentage, tw, bp_current)


def time_wait(time_i):
    while time_i != 0:
        time_i -= 1
        time.sleep(1)
        sys.stdout.write(" Time Remaining for thread: {}\r".format(time_i))


def html_actions(directory, res, req, parsing):
    dl(res, req, directory) # dl files and calcul size
    parsing.html_recon(res, req, directory) #try to found S3 buckets
    parsing.get_links(req, directory) #scrape all link
    if js:
        parsing.get_javascript(res, req, directory) #try to found js keyword



def status(r, stat, directory, u_agent, thread, manageDir):
    """
    Status:
     - Get response status of the website (200, 302, 404...).
     - Check if a backup exist before to start the scan.
     If exist it restart scan from to the last line of backup.
    """
    check_b = manageDir.check_backup(directory)
    #check backup before start scan
    last_line = ''
    if check_b == True:
        with open(directory + "/backup.txt", "r") as word:
            for ligne in word.readlines():
                print("{}{}{}".format(BACK, url, ligne.strip()))
                lignes = ligne.split("\n") #take the last line in file
                last_line = lignes[-2]
        with open(wordlist, "r") as f:
            for nLine, line in enumerate(f):
                if line.strip() == last_line:
                    print(LINE)
                    forced = False
                    check_words(url, wordlist, directory, u_agent, thread, forced, nLine)
    elif not check_b:
        try:
            os.remove(directory + "/backup.txt")
            print("{} Restarting scan...".format(INFO))
        except:
            pass
        print(LINE)

    if auth:
        r = requests.get(url, allow_redirects=False, verify=False, auth=(auth.split(":")[0], auth.split(":")[1]))
        if r.status_code in [200, 302, 301]:
            print("{} Authentification successfull\n".format(PLUS))
            stat = r.status_code
        else:
            print("{} Authentification error".format(LESS))
            continue_error = input("The authentification seems bad, continue ? [y/N]")
            if continue_error not in ["y", "Y"]:
                sys.exit()

    if stat == 200:
        check_words(url, wordlist, directory, u_agent, thread)
    elif stat in [301, 302]:
        req_red = requests.get(url, verify=False, headers=basic_user_agent)
        message_type = "Permanently" if stat == 301 else "Temporarily"
        follow = input("{} {} Moved {} → {}\nDo you want follow redirection ? [y/N]".format(PLUS, stat, message_type, req_red.url))
        print("")
        stat = stat if follow == "y" or follow == "Y" else 0
        check_words(url, wordlist, directory, u_agent, thread)
    elif stat == 304:
        pass
    elif stat == 404:
        not_found = input("{} URL return 404 response / forced ? [y/N]: ".format(LESS))
        if not_found == "y" or not_found == "Y":
            forced = True
            check_words(url, wordlist, directory, u_agent, thread, forced)
        else:
            sys.exit()
    elif stat in [403, 401]:
        fht = input(FORBI + " URL return {} response / forced ? [y/N]: ".format(stat))
        if fht == "y" or fht == "Y":
            forced = True
            check_words(url, wordlist, directory, u_agent, thread, forced)
        else:
            sys.exit()
    else:
        not_found = input("{} URL return {} response / forced ? [y/N]: ".format(LESS, stat))
        if not_found == "y" or not_found == "Y":
            forced = True
            check_words(url, wordlist, directory, u_agent, thread, forced)
        else:
            sys.exit()


def create_backup(res, directory, forbi):
    """Create backup file"""
    with open(directory + "/backup.txt", "a+") as words:
        #delete url to keep just file or dir
        anti_sl = res.split("/")
        rep = str(anti_sl[3:])
        result = rep.replace("['","").replace("']","").replace("',", "/").replace(" '","")
        words.write(result + "\n")


def dl(res, req, directory):
    """ Download files """
    #extensions = ['.json', '.txt', '.html', '.jsp', '.xml', '.aspx', '.zip', '.old', '.bak', 
    #'.sql', '.js', '.asp', '.ini', '.rar', '.dat', '.log', '.backup', '.dll', '.save', '.BAK', '.inc', '.md', ".info"]
    d_files = directory + "/files/"
    if not os.path.exists(d_files):
        try:
            os.makedirs(d_files)
        except:
            pass
    anti_sl = res.split("/")
    rep = anti_sl[3:]
    result = rep[-1]
    p_file = d_files + result
    if "." in result:
        with open(p_file, 'w+') as fichier:
            try:
                fichier.write(str(req.text))
            except:
                pass


def output_scan(directory, res, size_res, stats):
    """
    output_scan:
    Output to scan
    """
    mo = multiple_outputs()
    directory = output if output else directory
    if output_type == "csv":
        mo.csv_output(directory, res, stats, size_res)
        mo.raw_output(directory, res, stats, size_res)
    elif output_type == "json":
        mo.json_output(directory, res, stats, size_res)
        mo.raw_output(directory, res, stats, size_res)
    else:
        mo.raw_output(directory, res, stats, size_res)


def defined_thread(thread, i, score_next):
    """
    Defined_thread: to defined the threads number
    """
    #print("score: {}".format(score_next))
    thread_count = threading.active_count()
    res_time = 0
    try:
        start = time.time()
        req = requests.get(url, verify=False)
        end = time.time()
        res_time = end - start
    except Exception:
        pass
    if res_time != 0 and res_time < 1 and thread_count < 30:
        #automaticly 30 threads MAX
        score = 1
        if i == 40 and score_next == 0:
            return 1, i;
        elif i == 160 and score_next == 1:
            return 1, i;
        elif i == 340 and score_next == 2:
            return 1, i;
        else:
            return 0, score;
    else:
        return 0, 0;


def defined_connect(s, res, user_agent=False, header_parsed=False):
    allow_redirection = True if stat == 301 or stat == 302 else False
    global authent
    authent = (auth.split(":")[0], auth.split(":")[1]) if auth else False
    if header_parsed:
        for h in header_parsed:
            for u in user_agent:
                header = {"{}".format(h):"{}".format(header_parsed[h]), "{}".format(u):"{}".format(user_agent[u])}
    else:
        if user_agent:
            for u in user_agent:
                header = {"Connection":"close", "Cache-Control": "no-cache", "{}".format(u):"{}".format(user_agent[u])}
        else:
            header = {"Connection":"close", "Cache-Control": "no-cache", "Pragma": "no-cache"}

    JS_error = ["You need to enable JavaScript to run this app", "JavaScript Required", "without JavaScript enabled",
    "This website requires JavaScript", "Please enable JavaScript", "Loading"]

    if proxy:
        retry_strategy = Retry(
            total=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
            )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        ip = random.choice(proxy_list)
        if not ip.startswith("http://"):
            proxies = {"https": ip}
            s.proxies.update(proxies)
        else:
            proxies = {"https": ip, "http": ip}
            s.proxies.update(proxies)
    req = s.get(res, headers=header, allow_redirects=allow_redirection, verify=False, timeout=15, auth=authent)
    if any(js_e in req.text for js_e in JS_error):
        #print("{} This URL need to active JS: {}".format(INFO, res)) #TODO
        return 404
    else:
        return req


def thread_wrapper(i, q, threads, manager, t_event, directory=False, forced=False, u_agent=False):
    while not q.empty() and not t_event.isSet():
        #print("DEBUG: {}".format(t_event.isSet())) #DEBUG
        tryUrl(i, q, threads, manager, directory, forced, u_agent)


def get_date():
    now = time.localtime(time.time())
    hour_t = time.strftime("%H:%M:%S", now)
    HOUR = "\033[36m[{}] \033[0m".format(hour_t)
    return HOUR


def Progress(len_w, thread_count, nLine, page, percentage, tw, bp_current):
    """
    Progress: just a function to print the scan progress
    """
    progress_print = "\033[36m {0}/{1} | T:{2} | Err: {3} | Cb: {4} | {5}\033[0m\r".format(n+nLine, len_w, thread_count, n_error, bp_current, page if len(page) < 55 else page.split("/")[-3:-1])
    little_progress_print = "\033[36m {0}/{1} | Err: {2} | Cb: {3} | {4}\033[0m\r".format(n, len_w, n_error, bp_current, page if len(page) < 70 else page.split("/")[-3:-1])
    if tw < 110:
        sys.stdout.write(little_progress_print)
        if len(little_progress_print) > 36: sys.stdout.write("\033[K") #clear line
    else:
        per = percentage(n+nLine, len_w)
        sys.stdout.write("\033[36m {0:.2f}% - {1}/{2} | T:{3} | Err: {4} | Cb: {5} | {6}\033[0m\r".format(per, n+nLine, len_w, thread_count, n_error, bp_current, page if len(page) < 55 else page.split("/")[-3:-1]))
        if len(progress_print) > 55: sys.stdout.write("\033[K") #clear line 


def check_words(url, wordlist, directory, u_agent, thread, forced=False, nLine=False):
    """
    check_words:
    Functions wich manage multi-threading
    """
    #report = create_report_test()
    #report.create_report_base(directory, header_)
    runFuzz = runFuzzing()
    threads = 3 if auto else thread
    link_url = []
    hiddend = []

    index_req = requests.get(url, verify=False, allow_redirects=False, headers=basic_user_agent)
    htaccess_req = requests.get("{}.htaccess".format(url), verify=False, allow_redirects=False, headers=basic_user_agent)

    global index_len
    index_len = len(index_req.content)

    global htaccess_len
    htaccess_len = len(htaccess_req.content)
            
    with open(wordlist, "r") as payload:
        links = payload.read().splitlines()
    state = links[nLine:] if nLine else links # For restart from the last line found in the dico
    try:
        for link in state:
            link_url = "{}{}{}".format(url, prefix, link) if prefix else "{}{}".format(url, link) #url/prefix-words or url/words
            enclosure_queue.put(link_url)
        manager = ThreadManager(enclosure_queue)
        for i in range(threads):
            worker = Thread(target=runFuzz.tryUrl, args=(i, enclosure_queue, threads, manager, directory, forced, u_agent, nLine))
            worker.daemon = True
            worker.start()
        enclosure_queue.join()
    except KeyboardInterrupt:
        if not file_url:
            print(" {}Canceled by keyboard interrupt (Ctrl-C) ".format(INFO))
            sys.exit()
        else:
            print(" {}Canceled by keyboard interrupt (Ctrl-C), next site ".format(INFO))
    """
        Recursif: For recursif scan
    """
    if rec_list != []:
        print(LINE)
        size_rec_list = len(rec_list)
        i_r = 0
        forced = True
        while i_r < size_rec_list:
            url_rec = "{}{}".format(url, rec_list[i_r])
            print("{} Entering in directory: {}".format(INFO, rec_list[i_r]))
            print(LINE)
            with open(wordlist, "r") as payload:
                links = payload.read().splitlines()
                for i in range(threads):
                    worker = Thread(target=runFuzz.tryUrl, args=(i, enclosure_queue, threads, manager, directory, forced, u_agent, nLine))
                    worker.daemon = True
                    worker.start()
                for link in links:
                    link_url = "{}{}{}".format(url, prefix, link) if prefix else "{}{}".format(url, link)
                    enclosure_queue.put(link_url)
                enclosure_queue.join()
                i_r = i_r + 1
            print(LINE)
    else:
        print("\n{}not other directory to scan".format(INFO))
    try:
        os.remove(directory + "/backup.txt")
    except:
        print("{}backup.txt not found".format(INFO))
    if notify:
        notify_scan_completed()
        

def start_scan(subdomains, r, stat, directory, u_agent, thread, manageDir, header_, forbi):
    if subdomains:
        subdomain(subdomains)
    if light_mode:
        runFuzz = runFuzzing()

        s = requests.session()
        s.verify=False

        c = 0
        with open(wordlist, "r") as payload:
            links = payload.read().splitlines()
        for l in links:
            uri = "{}{}".format(url, l)
            runFuzz.light_mode(uri, directory, s)
            c+=1
            sys.stdout.write(" {}/{} - {} \r".format(c, len(links), l))
            sys.stdout.write("\033[K")
    else:
        status(r, stat, directory, u_agent, thread, manageDir)
    scan_error(directory, forbi, filterManager)
    print(LINE)
    try:
        create_report(directory, header_)
        print("\n{} The report has been created".format(PLUS))
    except:
        print("\n{} An error occurred, the report cannot be created".format(WARNING))
    print(LINE)



def create_structure_scan(r, url, stat, u_agent, thread, subdomains, beforeStart):
    """
    create_structure_scan:
    Create directory with the website name to keep a scan backup.
    """
    ram = check_modules()
    manageDir = manage_dir()

    now = datetime.now()
    today = now.strftime("_%Y-%m-%d")

    backup_exist = False
    found_dire = False
    creat_other = True
    dire_exists = []

    today_hour = now.strftime("_%Y-%m-%d_%H-%M")

    dire = ''
    forbi = False
    url = url if len(url.split('/')) == 4 else '/'.join(url.split('/')[:-2]) + '/'
    if 'www' in url:
        direct = url.split('.')
        director = direct[1]
        dire = "{}.{}".format(direct[1], direct[2].replace("/",""))
        directory = "sites/{}{}".format(dire, today)
    else:
        direct = url.split('/')
        director = direct[2]
        dire = director
        directory = "sites/" + dire

    listdir = os.listdir("sites/")
    for ld in listdir:
        if dire in ld:
            found_dire = True
            dire_exists.append(ld)

    if not found_dire or force_first_step and not not_first_step:
        creat_other = False
        dire_date = "{}{}".format(dire, today_hour)
        directory = directory if not force_first_step else "sites/{}".format(dire_date)
        os.makedirs(directory) if not force_first_step else os.makedirs(directory) # creat the dir
        os.makedirs(directory+"/output/") if not force_first_step else os.makedirs("sites/{}/output/".format(directory))

        if not file_url and not not_first_step:
            mods = ram.run_all_modules(beforeStart, url, directory, dire, thread) # Run all modules
            if mods:
                thread = mods

        start_scan(subdomains, r, stat, directory, u_agent, thread, manageDir, header_, forbi)
    else:
        for de in dire_exists:
            if os.path.exists("sites/{}/backup.txt".format(de)):
                backup_exist = True
                de = "sites/{}".format(de)
                start_scan(subdomains, r, stat, de, u_agent, thread, manageDir, header_, forbi) 

    #print("creat_other: {} // bck_exst: {}".format(creat_other, backup_exist)) #DEBUG
    if not backup_exist and creat_other:
        new_directory = "sites/{}{}".format(dire, today_hour)
        os.makedirs(new_directory)
        os.makedirs("{}/output/".format(new_directory))
        start_scan(subdomains, r, stat, new_directory, u_agent, thread, manageDir, header_, forbi)


def main(url):
    beforeStart = before_start()
    beforeStart.test_timeout(url, first=True)
    user_agent_r = random.choice(UserAgent) if type(UserAgent) == list else UserAgent.random
    r = requests.get(url, allow_redirects=False, verify=False, timeout=15, headers={'User-agent': user_agent_r})
    stat = r.status_code
    if backup is not None:
        if len(backup) > 0 and backup[0] == "min":
            bckp = MINI_B  
        else:
            bckp = EXT_B if backup == [] else [bck.replace(",","") for bck in backup]
    resume_options(url, thread if not light_mode else 0, wordlist, recur, js, exclude, proxy, header=False if header_ == None else header_, backup=False if backup == None else bckp)
    print(LINE)
    create_structure_scan(r, url, stat, u_agent, thread, subdomains, beforeStart)



if __name__ == '__main__':
    #arguments
    parser = argparse.ArgumentParser(add_help = True)
    parser = argparse.ArgumentParser(description='\033[32m Version 2.3 | contact: https://twitter.com/c0dejump\033[0m')

    group = parser.add_argument_group('\033[34m> General\033[0m')
    group.add_argument("-u", help="URL to scan \033[31m[required]\033[0m", dest='url')
    group.add_argument("-f", help="file with multiple URLs to scan", dest='file_url', required=False)
    group.add_argument("-t", help="Number of threads to use for URL Fuzzing. \033[32mDefault: 30\033[0m", dest='thread', type=int, default=30, required=False)
    group.add_argument("--exclude", help="Exclude page, response code, response size. \033[33mEx: --exclude 500,337b\033[0m", required=False, dest="exclude", nargs="+")
    group.add_argument("--auto", help="Automatic threads depending response to website. Max: 30 \033[33m(In progress...)\033[0m", required=False, dest="auto", action='store_true')
    group.add_argument("--update", help="For automatic update", required=False, dest="update", action='store_true')
    group.add_argument("--lightmode", help="For a just simple fuzzing 1 request per second & a new session for each request", required=False, dest="light_mode", action='store_true')

    group = parser.add_argument_group('\033[34m> Wordlist Settings\033[0m')
    group.add_argument("-w", help="Wordlist used for Fuzzing the desired webite. \033[32mDefault: dichawk.txt\033[0m", dest='wordlist', default="dichawk.txt", required=False)
    group.add_argument("-b", help="Adding prefix/suffix backup extensions during the scan. \033[33mEx: -b .bak, .old | OR 'min' for default minimum backup\033[0m. \033[32mDefault: all extension in config.py\033[0m", required=False, dest="backup", nargs="*", action="store")
    group.add_argument("-p", help="Add prefix in wordlist to scan", required=False, dest="prefix")

    group = parser.add_argument_group('\033[34m> Request Settings\033[0m')
    group.add_argument("-H", help="Modify header. \033[33mEx: -H \"cookie:test\"\033[0m", required=False, dest="header_", type=str)
    group.add_argument("-a", help="Choice user-agent. \033[32mDefault: Random\033[0m", dest='_user_agent', required=False)
    group.add_argument("--auth", help="HTTP authentification. \033[33mEx: --auth admin:admin)\033[0m", required=False, dest="auth")
    group.add_argument("--timesleep", help="To define a timesleep/rate-limit if app is unstable during scan.", required=False, dest="ts", type=float, default=0)
    group.add_argument("--proxy", help="Defined a proxies during scan \033[33mEx: --proxy proxy.lst\033[0m #In progress", required=False, dest="proxy")
    group.add_argument("--error", help="print errors", required=False, dest="print_error", action='store_true')

    group = parser.add_argument_group('\033[34m> Tips\033[0m')
    group.add_argument("-r", help="Recursive dir/files", required=False, dest="recursif", action='store_true')
    group.add_argument("-s", help="Subdomain tester", dest='subdomains', required=False)
    group.add_argument("--js", help="For try to found keys or token in the javascript page", required=False, dest="javascript", action='store_true')
    group.add_argument("--nfs", help="Not the first step of scan during the first running (waf, vhosts, wayback etc...)", required=False, dest="not_first_step", action='store_true')
    group.add_argument("--ffs", help="Force the first step of scan during the first running (waf, vhosts, wayback etc...)", required=False, dest="force_first_step", action='store_true')
    group.add_argument("--notify", help="For receveid notify when the scan finished (work only on linux)", required=False, dest="notify", action='store_true')

    group = parser.add_argument_group('\033[34m> Export Settings\033[0m')
    group.add_argument("-o", help="Output different path (default in website directory). \033[33mEx: -o /tmp/toto.com will create a directory in /tmp/toto.com/output/raw.txt\033[0m", required=False, dest="output")
    group.add_argument("-of", help="Output file format. Available formats: json, csv, txt ", required=False, dest="output_type")

    results = parser.parse_args()
                                     
    url = results.url
    file_url = results.file_url
    light_mode = results.light_mode
    wordlist = results.wordlist
    subdomains = results.subdomains
    thread = results.thread
    u_agent = results._user_agent
    recur = results.recursif
    prefix = results.prefix
    output = results.output
    output_type = results.output_type
    backup = results.backup
    header_ = results.header_
    exclude = results.exclude 
    ts = results.ts
    auto = results.auto
    update = results.update
    js = results.javascript
    auth = results.auth
    not_first_step = results.not_first_step
    force_first_step = results.force_first_step
    notify = results.notify
    proxy = results.proxy
    print_error = results.print_error

    if len(sys.argv) < 2:
        print("{}URL target is missing, try using -u <url> \n".format(INFO))
        parser.print_help()
        sys.exit()

    banner()

    if update:
        auto_update

    len_w = 0 #calcul wordlist size

    with open(wordlist, 'r') as words:
        for l in words:
            len_w += 1

    if proxy:
        print("{}In progress...".format(INFO))
        """
        n = 0
        if not os.path.exists(proxy):
            print("{} File {} not exist".format(WARNING, proxy))
            sys.exti()
        global proxy_list

        proxy_list = check_proxy(proxy)
        while len(proxy_list) <= 0:
            proxy_list = check_proxy(proxy)"""


    if header_:
        s = header_.split(";")
        for c in s:
            if ":" in c:
                c = c.split(":", 1)
            elif "=" in c:
                c = c.split("=", 1)
            header_parsed.update([(c[0],c[1])])

    if exclude:
        exclude = exclude[0].split(",")
        if len(exclude) > 1:
            req_p = exclude
        elif "b" in exclude[0][-1] and int(exclude[0][0]):
            req_p = exclude
        elif len(exclude[0]) < 5: #Defined if it's int for response http code or strings for url
            if exclude[0] == "0b":
                req_p = 0
            else:
                req_p = int(exclude[0])
        else:
            page_url = "{}{}".format(url + "/" if url.split("/")[-1] != "" else url, exclude[0])
            req_exclude = requests.get(page_url, verify=False)
            req_p = req_exclude.text

    if file_url:
        #For scan multiple website to one time
        with open(file_url, "r") as f_url:
            for f in f_url.read().splitlines():
                url = f + "/" if f.split("/")[-1] != "" else f
                print("{} Type ctrl+c to pass next website".format(INFO))
                main(url)
            n_error = 0
            n = 0
    else:
        url = url + "/" if url.split("/")[-1] != "" else url
        main(url)
