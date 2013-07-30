#!/usr/bin/env python

import datetime
import getpass
import logging
import os
import zipfile
import StringIO
import html5lib
import requests
from pyzar import config as pyzar_config
import fnmatch

XHTML = "http://www.w3.org/1999/xhtml"
NS = {"html": XHTML}
DOMAIN = "https://www.discoveryonlinebanking.co.za"
BROWSER_DATA = {"BrowserType": "Chrome", "BrowserVersion": "28.0.1500.52 Safari/537.36", "OperatingSystem": "Linux i686"}

session = requests.Session()

def parse_response(response):
    """parses the given http response or response contents and returns an lxml-constructed etree"""
    return html5lib.parse(response.text, treebuilder="lxml")

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
    target_dict.update(BROWSER_DATA)
    controller_forms = controller_tree.xpath('.//html:form[@name="%s"]' % form_name, namespaces=NS)
    if controller_forms:
        controller_form = controller_forms[0]
        target_url = controller_form.attrib['action']
        for form_input in controller_form.xpath('.//html:input', namespaces=NS):
            if form_input.attrib.get('type', None) == 'hidden' and 'value' in form_input.attrib:
               target_dict[form_input.attrib['name']] = form_input.attrib['value']
        if override_values:
            target_dict.update(override_values)
    else:
        form_input = controller_tree.xpath('.//html:input[@name="%s"]' % form_name, namespaces=NS)[0]
        target_url = form_input.attrib['onclick'].replace("parent.result.location=", "").strip("'")
    if "://" not in target_url:
        target_url = "%s%s" % (DOMAIN, target_url)
    target_page = session.post(target_url, data=target_dict)
    return target_page

def main():
    TARGET_PATH = pyzar_config.get_config().get('discoverycard', 'statement_dir')

    logging.getLogger().setLevel(logging.INFO)

    initial_page = session.get(DOMAIN)

    USERNAME = raw_input("enter username: ")
    PASSWORD = getpass.getpass("enter password: ")

    # omitted: backButtonBlocker, BrowserType, BrowserVersion, OperatingSystem
    import pdb ; pdb.set_trace()
    start_page = session.post("%s/banking/Controller" % DOMAIN, params={"action": "dologin", "countryCode": "ZA", "country": "15", "skin": "2", "targetDiv": "workspace"})
    login_page = repost_form(start_page, "bodyform")
    signon_data = {"Username": USERNAME, "Password": PASSWORD}
    signon_response = repost_form(login_page, "login_banking_form", signon_data)
    controller_response = repost_form(signon_response, "result_login")
    home_response = repost_form(controller_response, "LoggedInForm")
    accounts_response = session.post("%s/banking/Controller" % DOMAIN, params={"nav": "accounts.summaryofaccountbalances.navigator.SummaryOfAccountBalances", "FARFN": "4", "actionchild": "1", "isTopMenu": "true", "targetDiv": "workspace"})
    accounts_tree = html5lib.parse(accounts_response.text, treebuilder="lxml")
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
                history_page = session.get("%s%s" % (DOMAIN, history_url))
                key = get_form_value(history_page, "bodyform", "key")
                history_page = repost_form(history_page, "bodyform")
                # TODO: this isn't getting the right download for some reason
                data = {"ANRFN": get_form_value(history_page, "FORMDDAHISTSELCRIT_108", "ANRFN"),
                        "action": "downloadTransactionHistory",
                        "downloadFormat": "ofx",
                        "formname": "FORMDDAHISTSELCRIT_108",
                        "function": "",
                        "key": key,
                       }
                download_response = session.get("%s/Controller" % DOMAIN, params=data, stream=True)
                zf = zipfile.ZipFile(download_response.raw)
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

