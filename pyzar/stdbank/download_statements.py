#!/usr/bin/env python

import datetime
import getpass
import logging
import os
import urllib
import urllib2
import html5lib
from pyzar import config as pyzar_config

XHTML = "http://www.w3.org/1999/xhtml"
NS = {"html": XHTML}

def account_data(account_number, kwargs):
    """get the account number and other data in the form appropriate for redirector.do"""
    kwargs = kwargs.copy()
    kwargs["selected_account_no"] = account_number
    return urllib.urlencode(kwargs)

def main():
    TARGET_PATH = pyzar_config.get_config().get('stdbank', 'statement_dir')

    logging.getLogger().setLevel(logging.INFO)

    opener = urllib2.build_opener(urllib2.HTTPCookieProcessor())

    initial_page = opener.open("https://www.encrypt.standardbank.co.za")
    # redirect to www[0-9]*.encrypt.standardbank.co.za
    initial_url = initial_page.geturl()
    DOMAIN = initial_url.rstrip("/")
    internet_banking_page = opener.open("%s/ibsa/InternetBanking" % DOMAIN)

    CARD_NUMBER = raw_input("enter card number: ")
    CARD_PIN = getpass.getpass("enter pin:         ")
    CARD_PASSWORD = getpass.getpass("enter password:    ")

    signon_data = urllib.urlencode({"ccn": CARD_NUMBER, "csp": CARD_PIN, "pwd": CARD_PASSWORD, "login": "Login"})
    signon_result = opener.open("%s/ibsa/customer/signon.do" % DOMAIN, signon_data)
    account_types = ["provisional", "history"]
    account_balances = opener.open("%s/ibsa/accounts/getbalances.do" % DOMAIN)
    accounts_html = account_balances.read()
    accounts_tree = html5lib.parse(accounts_html, treebuilder="lxml")
    accounts_table = accounts_tree.xpath('.//html:div[@class="ContentTable"]/html:table[3]', namespaces=NS)[0]
    account_links = [("".join(account_link.itertext()), account_link.attrib['href']) for account_link in accounts_table.xpath('.//html:tr//html:td//html:a', namespaces=NS)]
    date = datetime.date.today().strftime("%Y%m%d")
    for account_name, account_link in account_links:
        account_number = account_link[account_link.rfind("=")+1:]
        for account_type in account_types:
            if account_type == "provisional":
                logging.info("Loading account %s provisional statement", account_name)
                account_set_page = opener.open("%s%s" % (DOMAIN, account_link))
                suffix = ""
            elif account_type == "history":
                logging.info("Loading account %s history statement", account_name)
                account_history_query_page = opener.open("%s/ibsa/accounts/statements/redirector.do" % DOMAIN, account_data(account_number, {"step.3": "History"}))
                account_history_page = opener.open("%s/ibsa/accounts/statements/redirector.do" % DOMAIN, account_data(account_number, {"date_range_option": "90", "act.1": "Continue"}))
                suffix = "-history"
            account_download_format = opener.open("%s/ibsa/accounts/statements_download_format.jsp" % DOMAIN)
            ofx_filename = os.path.join(TARGET_PATH, "statement-%s-%s%s.ofx" % (account_number, date, suffix))
            if os.path.exists(ofx_filename):
                overwrite = "x"
                while overwrite[:1] not in "yn":
                    overwrite = raw_input("%s exists; overwrite? [yes/no]:" % ofx_filename).lower()[:1]
                if not overwrite == "y":
                    continue
            ofx_file = opener.open("%s/ibsa/accounts/statements/download.do?format=OFX" % DOMAIN)
            ofx_contents = ofx_file.read()
            logging.info("Saving to %s", ofx_filename)
            with open(ofx_filename, "w") as ofx_file:
                ofx_file.write(ofx_contents)

if __name__ == "__main__":
    main()

