#!/usr/bin/env python

import csv
import collections
import datetime
import os
import genshi.template

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

class CSVLabels:
    DATE_RECEIVED, DATE_POSTED, CARD_HOLDER, DESCRIPTION, CATEGORY, AMOUNT = ("Transaction Date", "Date posted", "Card holder", "Description", "Type", "Amount")

class CSVFile(object):
    def __init__(self):
        self.tx_list = []

    @classmethod
    def read(cls, f):
        """Constructs a CSVFile by reading from the given file"""
        if isinstance(f, basestring):
            f = open(f, "rb")
        csv_file = cls()
        csv_file.account_info = {}
        column_headings = [CSVLabels.DATE_RECEIVED, CSVLabels.DATE_POSTED, CSVLabels.CARD_HOLDER, CSVLabels.DESCRIPTION, CSVLabels.CATEGORY, CSVLabels.AMOUNT]
        csv_file.transactions = []
        reader = csv.reader(f)
        reader.next()
        for row in reader:
            if row:
                csv_file.transactions.append(dict((k, v.strip()) for k, v in zip(column_headings, row) if k or v))
        return csv_file

TYPE_MAP = {"DR": "DEBIT", "CR": "CREDIT"}

def csv2ofx_tx(tx_dict, reference_date, row_num):
    """Converts the CSV file transaction dictionary to an OFXTransaction"""
    if tx_dict[CSVLabels.CATEGORY] in ("Authorisation", "Authorisation Declined"):
        return None
    tx_type = "DEBIT" if tx_dict[CSVLabels.AMOUNT].startswith("(") else "CREDIT"
    tx_date = datetime.datetime.strptime(tx_dict[CSVLabels.DATE_POSTED], "%d-%m-%Y").date()
    tx_amount = float(tx_dict[CSVLabels.AMOUNT].strip("(R )").replace(",", ""))
    if tx_type == "DEBIT":
        tx_amount = -tx_amount
    tx_id = "%s%d" % (tx_date.strftime("%Y%m%d"), row_num)
    tx_memo = tx_name = tx_dict[CSVLabels.DESCRIPTION].strip()
    return OFXTransaction(tx_type, tx_date, tx_amount, tx_id, tx_name, tx_memo)

def csv2ofx(csv_file):
    """Returns an OFXFile with the same info as the csv file"""
    ofx_file = OFXFile()
    ofx_file.date_served = csv_file.account_info["Date"]
    account_number = csv_file.account_info.get("Acc", csv_file.account_info.get("Account", None))
    ofx_file.set_account_info(1, int(account_number), "ZAR")
    for tx_dict in csv_file.transactions:
        try:
            ofx_tx = csv2ofx_tx(tx_dict, ofx_file.date_served, len(ofx_file.transactions)+7)
            if ofx_tx is None:
                print "Ignoring transaction %r" % (tx_dict)
                continue
            ofx_file.transactions.append(ofx_tx)
        except Exception, e:
            print "Error converting transaction %r: %s" % (tx_dict, e)
    ofx_file.date_start = min(tx.date for tx in ofx_file.transactions)
    ofx_file.date_end = ofx_file.date_served.date()
    last_trans = csv_file.transactions[-1]
    if "Balance" in last_trans:
        ofx_file.balance_amount = float(last_trans["Balance"].strip())
        if last_trans["OD"] == "OD":
            ofx_file.balance_amount = -ofx_file.balance_amount
        ofx_file.balance_date = parse_csv_date(last_trans, ofx_file.date_served)
    return ofx_file

def main():
    import sys
    csv_filename = sys.argv[1]
    if len(sys.argv) > 2:
        ofx_filename = sys.argv[2]
    else:
        ofx_filename = csv_filename.replace(".csv", ".ofx")
    csv_file = CSVFile.read(sys.argv[1])
    csv_file.account_info["Date"] = datetime.datetime.fromtimestamp(os.stat(sys.argv[1]).st_ctime)
    csv_file.account_info["Account"] = os.path.splitext(sys.argv[1])[0].split("-")[0]
    ofx_file = csv2ofx(csv_file)
    ofx_contents = ofx_file.generate().render()
    open(ofx_filename, "w").write(ofx_contents)

if __name__ == "__main__":
    main()

