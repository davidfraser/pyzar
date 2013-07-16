#!/usr/bin/env python

import csv
import collections
import datetime
import os
import re
import genshi.template

OFXTransaction = collections.namedtuple("OFXTransaction", "type date amount id name memo")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OFX_TEMPLATE_FILENAME = os.path.join(SCRIPT_DIR, "csv-ofx.genshi.txt")

class OFXFile(object):
    def __init__(self):
        self.transactions = []

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

class CSVFile(object):
    def __init__(self):
        self.tx_list = []

    @classmethod
    def read(cls, f):
        """Constructs a CSVFile by reading from the given file"""
        if isinstance(f, basestring):
            f = open(f, "rb")
        csv_file = cls()
        csv_file.bank_info = []
        csv_file.account_info = {}
        column_headings = []
        csv_file.transactions = []
        reader = csv.reader(f)
        reader.next()
        section = "BANK_INFO"
        for row in reader:
            if section == "BANK_INFO":
                if row:
                    csv_file.bank_info.append(row[0])
                else:
                    section = "HEADER"
            elif section == "HEADER":
                if not row:
                    section = "ACCOUNT_INFO"
            elif section == "ACCOUNT_INFO":
                if row:
                    csv_file.account_info[row[0].rstrip(":")] = row[1]
                else:
                    section = "START_TRANSACTIONS"
            elif section == "START_TRANSACTIONS":
                if row and row[0] == "Statement Follows:":
                    section = "TRANSACTIONS_HEADER"
            elif section == "TRANSACTIONS_HEADER":
                column_headings = row
                section = "TRANSACTIONS"
            elif section == "TRANSACTIONS":
                if row:
                    # old files have descriptions carrying onto the next line, so we need to paste them back
                    if csv_file.transactions and (True not in [bool(col.strip()) for col in row[1:]]):
                        transaction = csv_file.transactions[-1]
                        description = transaction[column_headings[0]]
                        transaction[column_headings[0]] = description.rstrip() + " " + row[0].strip()
                    else:
                        csv_file.transactions.append(dict((k, v) for k, v in zip(column_headings, row) if k or v))
        return csv_file

TYPE_MAP = {"DR": "DEBIT", "CR": "CREDIT"}

def parse_csv_date(tx_dict, reference_date):
    """gets the date out of the given transaction dictionary, relative to the reference date (it must be before this) (so we can get the year)"""
    if not tx_dict["Date"].strip():
        # a final balance transaction doesn't have the date, but should be regarded as the same as the reference date
        return reference_date
    tx_date = datetime.datetime.strptime("%s %d" % (tx_dict["Date"], reference_date.year), "%d %B %Y")
    while tx_date > reference_date:
        tx_date = tx_date.replace(year=tx_date.year-1)
    tx_date = tx_date.date()
    return tx_date

def csv2ofx_tx(tx_dict, reference_date, row_num):
    """Converts the CSV file transaction dictionary to an OFXTransaction"""
    tx_type = TYPE_MAP[tx_dict["DR /CR"]]
    tx_date = parse_csv_date(tx_dict, reference_date)
    tx_amount = float(tx_dict["Amount"].strip())
    if tx_type == "DEBIT":
        tx_amount = -tx_amount
    tx_id = "%s%d" % (tx_date.strftime("%Y%m%d"), row_num)
    if tx_dict.get("Reference", "").strip():
        tx_name = tx_dict["Reference"].strip()
        tx_memo = tx_dict["Description"].strip() + " " + tx_name
    else:
        tx_memo = tx_name = tx_dict["Description"].strip()
    return OFXTransaction(tx_type, tx_date, tx_amount, tx_id, tx_name, tx_memo)

def csvfile2ofxfile(csv_file):
    """Returns an OFXFile with the same info as the csv file"""
    ofx_file = OFXFile()
    ofx_file.date_served = datetime.datetime.strptime(csv_file.account_info["Date"], "%Y-%m-%d")
    account_number = csv_file.account_info.get("Acc", csv_file.account_info.get("Account", None))
    ofx_file.set_account_info(1, int(account_number), "ZAR")
    for tx_dict in csv_file.transactions:
        if not tx_dict["DR /CR"]:
            continue
        try:
            ofx_tx = csv2ofx_tx(tx_dict, ofx_file.date_served, len(ofx_file.transactions)+7)
            ofx_file.transactions.append(ofx_tx)
        except Exception, e:
            print "Error converting transaction %r: %s" % (tx_dict, e)
    ofx_file.date_start = min(tx.date for tx in ofx_file.transactions) if ofx_file.transactions else ofx_file.date_served.date()
    ofx_file.date_end = ofx_file.date_served.date()
    # if not csv_file.transactions:
    #      import pdb ; pdb.set_trace()
    last_trans = csv_file.transactions[-1]
    ofx_file.balance_amount = float(last_trans["Balance"].strip())
    if last_trans["OD"] == "OD":
        ofx_file.balance_amount = -ofx_file.balance_amount
    ofx_file.balance_date = parse_csv_date(last_trans, ofx_file.date_served)
    return ofx_file

def csv2ofx(csv_filename, ofx_filename):
    """converts a standard bank csv statement to an ofx file"""
    csv_file = CSVFile.read(csv_filename)
    ofx_file = csvfile2ofxfile(csv_file)
    ofx_contents = ofx_file.generate().render()
    with open(ofx_filename, "w") as ofx_filewriter:
        ofx_filewriter.write(ofx_contents)

def cleanup_csv(csv_contents):
    """Does various cleanups due to errors in stdbank csv generation historically; returns adjusted contents"""
    # A Random extra quote mark on this line, sometimes
    csv_contents = csv_contents.replace('"VAT Reg No. 4100105461","","","","","","', '"VAT Reg No. 4100105461","","","","","",')
    # Extra single quote mark at end of file
    if csv_contents.endswith('\r\n"\r\n'):
        csv_contents = csv_contents[:-3]
    # Quote strings containing comma in percentage sign
    if '"' not in csv_contents:
        csv_contents = re.sub("(INTEREST[^,]*@[0-9]+,[0-9]+%)", r'"\1"', csv_contents)
        csv_contents = re.sub("(MAESTRO[^,]*CASH: R *[0-9]+,[0-9]+)", r'"\1"', csv_contents)
    return csv_contents

def main():
    import sys
    csv_filename = sys.argv[1]
    if len(sys.argv) > 2:
        ofx_filename = sys.argv[2]
    else:
        ofx_filename = csv_filename.replace(".csv", ".ofx")
    csv2ofx(csv_filename, ofx_filename)

if __name__ == "__main__":
    main()

