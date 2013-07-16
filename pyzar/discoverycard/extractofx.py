#!/usr/bin/env python

import logging
import os
import re
import zipfile
from pyzar import config as pyzar_config

def main():
    latest_date = {}

    for input_fn in os.listdir(os.getcwd()):
        if input_fn.endswith(".ofx"):
            account = input_fn[:-len(".ofx")].split("-")[0]
            contents = open(input_fn, "r").read()
            date_start = re.findall(r"^[<]DTSTART[>](.*)$", contents, re.M)[0]
            date_end = re.findall(r"^[<]DTEND[>](.*)$", contents, re.M)[0]
            if date_end > latest_date.get(account, None):
                latest_date[account] = date_end

    ACCOUNT_TYPE = pyzar_config.get_config().get('discoverycard', 'account_type', 'silver')
    FILENAME = "transaction_history_Discovery_%s_Account.zip" % (ACCOUNT_TYPE.title())
    zf = zipfile.ZipFile(FILENAME)
    errors = 0
    successes = 0
    for f_info in zf.filelist:
        filename = f_info.filename
        if filename.endswith(".ofx"):
            account = filename[:-len(".ofx")]
            contents = zf.read(filename)
            date_start = re.findall(r"^[<]DTSTART[>](.*)$", contents, re.M)[0]
            date_end = re.findall(r"^[<]DTEND[>](.*)$", contents, re.M)[0]
            if account in latest_date and date_start > latest_date[account]:
                logging.warning("%s covers from %s to %s, but latest existing data finishes at %s", filename, date_start, date_end, latest_date[account])
                errors += 1
            output_fn = "%s-%s.ofx" % (account, date_end)
            if os.path.exists(output_fn):
                logging.warning("File %s exists: not saving", output_fn)
            else:
                open(output_fn, "wb").write(contents)
                successes += 1
        else:
            logging.warning("Unexpected file %s found", filename)
            errors += 1
    zf.close()
    if successes and not errors:
        logging.warning("Unzipped successfully; removing zipfile")
        os.remove(FILENAME)

if __name__ == '__main__':
    main()

