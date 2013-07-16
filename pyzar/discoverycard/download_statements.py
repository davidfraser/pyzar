#!/usr/bin/env python

import datetime
import getpass
import logging
import os
import urllib
import urllib2
import zipfile
import StringIO
import html5lib
from pyzar import config as pyzar_config
import fnmatch

XHTML = "http://www.w3.org/1999/xhtml"
NS = {"html": XHTML}
DOMAIN = "https://www.discoveryonlinebanking.co.za"

def parse_response(response):
    """parses the given http response or response contents and returns an lxml-constructed etree"""
    if hasattr(response, "read"):
        response = response.read()
    return html5lib.parse(response, treebuilder="lxml")

def get_form_value(response, form_name, key_name):
    controller_tree = parse_response(response)
    controller_form = controller_tree.xpath('.//html:form[@name="%s"]' % form_name, namespaces=NS)[0]
    for form_input in controller_form.xpath('.//html:input', namespaces=NS):
        if form_input.attrib['name'] == key_name:
           return form_input.attrib['value']

def repost_form(response, form_name, override_values=None):
    """Discovery Online Banking keeps on redirecting through a controller, reading parameters from a form, and then reposts them to get the desired page"""
    controller_tree = parse_response(response)
    target_dict = {}
    controller_forms = controller_tree.xpath('.//html:form[@name="%s"]' % form_name, namespaces=NS)
    if controller_forms:
        controller_form = controller_forms[0]
        target_url = controller_form.attrib['action']
        for form_input in controller_form.xpath('.//html:input', namespaces=NS):
            if form_input.attrib['type'] == 'hidden' and 'value' in form_input.attrib:
               target_dict[form_input.attrib['name']] = form_input.attrib['value']
        if override_values:
            target_dict.update(override_values)
    else:
        form_input = controller_tree.xpath('.//html:input[@name="%s"]' % form_name, namespaces=NS)[0]
        target_url = form_input.attrib['onclick'].replace("parent.result.location=", "").strip("'")
    target_page = opener.open("%s%s" % (DOMAIN, target_url), urllib.urlencode(target_dict))
    return target_page

def main():
    TARGET_PATH = pyzar_config.get_config().get('discoverycard', 'statement_dir')

    logging.getLogger().setLevel(logging.INFO)

    opener = urllib2.build_opener(urllib2.HTTPCookieProcessor())

    initial_page = opener.open(DOMAIN)

    USERNAME = raw_input("enter username: ")
    PASSWORD = getpass.getpass("enter password: ")

    # omitted: backButtonBlocker, BrowserType, BrowserVersion, OperatingSystem
    signon_dict = {"LoginButton": "Login", "action": "login", "Username": USERNAME, "Password": PASSWORD, "formname": "LOGIN_FORM", "url": 2}
    signon_data = urllib.urlencode(signon_dict)
    signon_response = opener.open("%s/login/Controller" % DOMAIN, signon_data)
    controller_response = repost_form(signon_response, "result_login")
    home_response = repost_form(controller_response, "homePageForm")
    accounts_response = opener.open("%s/Controller?%s" % (DOMAIN, urllib.urlencode({"action": "load_accounts"})))
    accounts_response = repost_form(accounts_response, "redirectForm").read()
    accounts_response = repost_form(accounts_response, "bodyform").read()
    accounts_tree = html5lib.parse(accounts_response, treebuilder="lxml")
    accounts_form = accounts_tree.xpath('.//html:form[@name="ACCOUNTS_TAB_FORM"]', namespaces=NS)
    date = datetime.date.today().strftime("%Y%m%d")
    if accounts_form:
        for account_row in accounts_form[0].xpath('.//html:table//html:tr', namespaces=NS)[1:]:
            history_url, account_name = None, None
            for link in account_row.xpath('.//html:a', namespaces=NS):
                link_target = link.attrib.get('href', '')
                if "acc_trans_hist" in link_target:
                    history_url = link_target
                    if link.text.strip().startswith("Discovery"):
                        account_description = link.text.strip()
                        break
            account_number_tds = account_row.xpath('.//html:td', namespaces=NS)
            for account_number_td in account_number_tds:
                for account_number_child in account_number_td.iterchildren():
                     if account_number_child.text and account_number_child.text.strip() == "account number":
                         account_name = account_number_child.tail.strip()
                         break
                if account_name:
                    break
            if account_name and history_url:
                logging.info("Selecting account %s", account_name)
                history_page = opener.open("%s%s" % (DOMAIN, history_url)).read()
                key = get_form_value(history_page, "bodyform", "key")
                history_page = repost_form(history_page, "bodyform").read()
                # TODO: this isn't getting the right download for some reason
                data = {"ANRFN": get_form_value(history_page, "FORMDDAHISTSELCRIT_108", "ANRFN"),
                        "action": "downloadTransactionHistory",
                        "downloadFormat": "ofx",
                        "formname": "FORMDDAHISTSELCRIT_108",
                        "function": "",
                        "key": key,
                       }
                download_response = opener.open("%s/Controller?%s" % (DOMAIN, urllib.urlencode(data))).read()
                zf = zipfile.ZipFile(StringIO.StringIO(download_response))
                for actual_file_name in fnmatch.filter(zf.namelist(), "%s.ofx" % account_name):
                    ofx_contents = zf.read(actual_file_name)
                    actual_account_name = actual_file_name.replace(".ofx", "")
                    ofx_filename = os.path.join(TARGET_PATH, "%s-%s.ofx" % (actual_account_name, date))
                    if os.path.exists(ofx_filename):
                        overwrite = "x"
                        while overwrite[:1] not in "yn":
                            overwrite = raw_input("%s exists; overwrite? [yes/no]:" % ofx_filename).lower()[:1]
                        if not overwrite == "y":
                            continue
                    logging.info("Saving to %s", ofx_filename)
                    open(ofx_filename, "w").write(ofx_contents)
    # TODO: logout

if __name__ == '__main__':
    main()

