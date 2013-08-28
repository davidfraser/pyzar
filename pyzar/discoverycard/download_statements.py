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
# useful for debugging
from xml.etree.ElementTree import tostring as ts

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
    start_page = session.post("%s/banking/Controller" % DOMAIN, params={"action": "dologin", "countryCode": "ZA", "country": "15", "skin": "2", "targetDiv": "workspace"})
    login_page = repost_form(start_page, "bodyform")
    signon_data = {"Username": USERNAME, "Password": PASSWORD}
    signon_response = repost_form(login_page, "login_banking_form", signon_data)
    controller_response = repost_form(signon_response, "result_login")
    home_response = repost_form(controller_response, "LoggedInForm")
    accounts_response = session.post("%s/banking/Controller" % DOMAIN, params={"nav": "accounts.summaryofaccountbalances.navigator.SummaryOfAccountBalances", "FARFN": "4", "actionchild": "1", "isTopMenu": "true", "targetDiv": "workspace"})

    accounts_tree = html5lib.parse(accounts_response.text, treebuilder="lxml")
    # This has not been tested with multiple accounts
    accounts_form = accounts_tree.findall('.//{%(html)s}div[@data-value="tableHeaderRow_0"]' % NS)
    date = datetime.date.today().strftime("%Y%m%d")
    if accounts_form:
        for account_row in accounts_form:
            account_name_parent = account_row.find('.//{%(html)s}div[@name="doubleItem_bottom_div_accountNumber"]' % NS)
            account_link = account_row.find('.//{%(html)s}div[@name="doubleItem_top_div_nickname0"]//{%(html)s}a' % NS)
            if account_link is None:
                continue
            link_js = account_link.attrib['onclick']
            account_view_url = link_js[link_js.find('/banking/Controller'):]
            account_view_url = account_view_url[:account_view_url.find("'")]
            account_name = account_name_parent.text.strip()
            if account_name and account_view_url:
                logging.info("Selecting account %s", account_name)
                account_view_page = session.get("%s%s" % (DOMAIN, account_view_url))
                account_view_tree = html5lib.parse(account_view_page.text, treebuilder="lxml")
                sub_tabs = account_view_tree.findall('.//{%(html)s}div[@class="subTabText"]' % NS)
                action_menu_button = account_view_tree.find('.//{%(html)s}div[@id="actionMenuButton0"]' % NS)
                real_account_name = account_name
                # We can only retrieve the real account name if we have appropriate rights
                if action_menu_button is not None:
                    real_account_name_js = action_menu_button.attrib["onclick"]
                    real_account_name = real_account_name_js[real_account_name_js.find("accountNumber=")+len("accountNumber="):]
                    real_account_name = real_account_name[:real_account_name.find("&")].strip()
                    if real_account_name != account_name and len(real_account_name) == len(account_name):
                        logging.info("Account name is actually %s", real_account_name)
                history_subtab = [sub_tab.getparent() for sub_tab in sub_tabs if sub_tab.text.strip() == "Transaction History"]
                if not history_subtab:
                    logging.warning("Could not locate transaction history subtab")
                    continue
                history_url = history_subtab[0].attrib["data-value"]
                history_page = session.get("%s%s" % (DOMAIN, history_url))
                history_tree = html5lib.parse(history_page.text, treebuilder="lxml")
                # fetching the extra page causes this to retrieve fuller history
                extended_history_params = {"targetDiv": "workspace", "nav": "accounts.transactionhistory.navigator.TransactionHistoryTCSFuller", "transactionHistoryTables_searchField": "", "transactionHistoryTables_limitSelectionDropdown": "140"}
                history_page_2 = session.get("%s/banking/Controller" % DOMAIN, params=extended_history_params)
                download_label = history_tree.find('.//{%(html)s}div[@class="tableActionButton downloadButton"]' % NS)
                download_js = download_label.attrib["onclick"]
                download_url = download_js[download_js.find("url:")+len("url:"):].lstrip()
                download_url = download_url[download_url.find("'")+1:]
                download_url = download_url[:download_url.find("'")]
                download_page = session.get("%s%s" % (DOMAIN, download_url))
                data = {"nav": "accounts.transactionhistory.navigator.TransactionHistoryDDADownload",
                        "doDownload": "true",
                        "downloadFormat": "ofx",
                       }
                download_response = session.get("%s/banking/Controller" % DOMAIN, params=data, stream=True)
                zf = zipfile.ZipFile(StringIO.StringIO(download_response.raw.data))
                file_pattern = "%s.ofx" % account_name.replace("_", "?").replace("*", "?")
                for actual_file_name in fnmatch.filter(zf.namelist(), file_pattern):
                    ofx_contents = zf.read(actual_file_name)
                    actual_account_name = actual_file_name.replace(".ofx", "")
                    if "_" in actual_account_name and fnmatch.fnmatch("%s.ofx" % real_account_name, file_pattern):
                        actual_account_name = real_account_name
                    ofx_filename = os.path.join(TARGET_PATH, "%s-%s.ofx" % (actual_account_name, date))
                    if os.path.exists(ofx_filename):
                        overwrite = "x"
                        while overwrite[:1] not in "yn":
                            overwrite = raw_input("%s exists; overwrite? [yes/no]:" % ofx_filename).lower()[:1]
                        if not overwrite == "y":
                            continue
                    logging.info("Saving to %s", ofx_filename)
                    open(ofx_filename, "w").write(ofx_contents)
    logoff_page = session.get("%s/banking/Controller" % DOMAIN, params={"nav": "navigator.UserLogoff", "isTopMenu": "true", "targetDiv": "workspace"})
    logoff_success = "You have been successfully logged out" in logoff_page.text
    if logoff_success:
        logging.info("Logout complete")

if __name__ == '__main__':
    main()

