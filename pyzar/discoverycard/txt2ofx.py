#!/usr/bin/env python

import collections
import datetime
import logging
import os
import re
import genshi.template

TXT_RE = re.compile(r"Discovery :-\) R(?P<amount>[0-9]+[.][0-9]+) (?P<category>[a-zA-Z ]+) @ (?P<details>.+) from card a/c(?P<account>[0-9.]+) using card(?P<card>[0-9.]+)[.] Avail (?P<avail>R[0-9-]+)[.] (?P<date>[0-9]+[A-Za-z]+ [0-9]+:[0-9]+)")

OFXTransaction = collections.namedtuple("OFXTransaction", "type date amount id name memo")

SCRIPT_DIR = os.path.dirname(os.path.realpath(os.path.abspath(__file__)))
OFX_TEMPLATE_FILENAME = os.path.join(SCRIPT_DIR, "csv-ofx.genshi.txt")

class OFXFile(object):
    def __init__(self):
        self.transactions = []
        self.balance_amount = None
        self.balance_date = None

    def generate(self):
        source = open(OFX_TEMPLATE_FILENAME, "r").read()
        template = genshi.template.NewTextTemplate(source, filename=OFX_TEMPLATE_FILENAME)
        context = genshi.template.Context(**self.generate_context())
        return template.generate(context)

    def set_account_info(self, bank_id, bank_account, currency):
        self.bank_id = bank_id
        self.bank_account = bank_account
        self.currency = currency

    @classmethod
    def create_sample(cls):
        ofx_file = cls()
        ofx_file.date_served = datetime.datetime.now()
        ofx_file.set_account_info(1, 40891249, "ZAR")
        ofx_file.date_start = datetime.date(2008,8,15)
        ofx_file.date_end = datetime.date(2009,2,4)
        ofx_file.transactions = []
        tx = OFXTransaction("DEBIT", datetime.date(2008,8,15), -500.0, "200808157", "GROCERY STORE 19H00   408912490", "AUTOBANK CASH WITHDRAWAL AT")
        ofx_file.transactions.append(tx)
        ofx_file.balance_amount = 3041.30
        ofx_file.balance_date = datetime.date(2009,2,4)
        return ofx_file

    def generate_context(self):
        return {"date_served": self.date_served,
                "date_start": self.date_start, "date_end": self.date_end, "transactions": self.transactions,
                "currency": self.currency, "bank_id": self.bank_id, "bank_account": self.bank_account,
                "balance_amount": self.balance_amount, "balance_date": self.balance_date,
               }

class TxtFile(object):
    def __init__(self):
        self.tx_list = []

    @classmethod
    def read(cls, f):
        """Constructs a TxtFile by reading from the given file"""
        if isinstance(f, basestring):
            f = open(f, "rb")
        txt_file = cls()
        txt_file.transactions = []
        for line in f.readlines():
            if not line.strip():
                continue
            m = TXT_RE.match(line)
            if m:
                txt_file.transactions.append(m.groupdict())
            else:
                logging.warning("Couldn't parse text entry: %s", line)
        return txt_file

TYPE_MAP = {"reserved for purchase": "DEBIT", "goods purchased": "DEBIT"}

def txt2ofx_tx(tx_dict, row_num):
    """Converts the CSV file transaction dictionary to an OFXTransaction"""
    tx_type = TYPE_MAP.get(tx_dict["category"], None)
    if tx_type is None:
        logging.info("Skipping unknown transaction %r", tx_type)
    tx_date = datetime.datetime.strptime(tx_dict["date"], "%d%b %H:%M")
    ref_date = datetime.datetime.now()
    tx_date = tx_date.replace(year=ref_date.year)
    if tx_date > ref_date:
        tx_date = tx_date.replace(year=ref_date.year-1)
    tx_amount = float(tx_dict["amount"])
    if tx_type == "DEBIT":
        tx_amount = -tx_amount
    tx_id = "%s%d" % (tx_date.strftime("%Y%m%d%H%M"), row_num)
    tx_memo = tx_name = tx_dict["details"].strip()
    return OFXTransaction(tx_type, tx_date, tx_amount, tx_id, tx_name, tx_memo)

def txt2ofx(txt_file):
    """Returns an OFXFile with the same info as the txt file"""
    ofx_file = OFXFile()
    for tx_dict in txt_file.transactions:
        try:
            ofx_tx = txt2ofx_tx(tx_dict, len(ofx_file.transactions)+7)
            if ofx_tx is None:
                print "Ignoring transaction %r" % (tx_dict)
                continue
            ofx_file.transactions.append(ofx_tx)
        except Exception, e:
            print "Error converting transaction %r: %s" % (tx_dict, e)
    ofx_file.date_start = min(tx.date for tx in ofx_file.transactions)
    ofx_file.date_end = max(tx.date for tx in ofx_file.transactions)
    ofx_file.date_served = ofx_file.date_end
    last_trans = txt_file.transactions[-1]
    account_number = last_trans["account"].lstrip(".")
    ofx_file.set_account_info(1, int(account_number), "ZAR")
    if last_trans.get('avail', None) is not None:
        ofx_file.balance_amount = float(last_trans["avail"].strip('R'))
        ofx_file.balance_date = datetime.datetime.strptime(last_trans["date"], "%d%b %H:%M")
    return ofx_file

def main():
    import sys
    txt_filename = sys.argv[1]
    if len(sys.argv) > 2:
        ofx_filename = sys.argv[2]
    else:
        ofx_filename = txt_filename.replace(".txt", ".ofx")
    txt_file = TxtFile.read(txt_filename)
    ofx_file = txt2ofx(txt_file)
    ofx_contents = ofx_file.generate().render()
    open(ofx_filename, "w").write(ofx_contents)

if __name__ == "__main__":
    main()

