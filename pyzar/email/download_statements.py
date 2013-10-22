#!/usr/bin/env python

import getpass
import logging
import os
from pyzar import config as pyzar_config
import fnmatch
import urlparse
import mailbot
import email.utils
import datetime
import tempfile
import stat

TARGET_PATH = None

class StatementMailBot(mailbot.MailBot):
    pass

class StatementCallback(mailbot.Callback):
    def trigger(self):
        headers = dict(self.message.items())
        message_time = email.utils.mktime_tz(email.utils.parsedate_tz(headers.get('Date', '')))
        message_timestamp = datetime.datetime.utcfromtimestamp(message_time) if message_time else datetime.datetime.utcnow()
        date_str = message_timestamp.strftime("%Y-%m-%d-%H_%M_%S")
        for message_part in self.message.walk():
            content_type, filename = message_part.get_content_type(), message_part.get_filename()
            if not (filename and filename.endswith(".ofx")):
                continue
            ofx_contents = message_part.get_payload(decode=True)
            ofx_length = len(ofx_contents)
            tmp_fd, tmp_filename = tempfile.mkstemp(suffix=".ofx", dir=TARGET_PATH)
            try:
                with os.fdopen(tmp_fd, 'wb') as tmp_file:
                    tmp_file.write(ofx_contents)
                i, write_file = 0, True
                while True:
                    output_filename = os.path.join(TARGET_PATH, "%s%s.ofx" % (date_str, "-%d" % i if i else ""))
                    if os.path.exists(output_filename):
                        length = os.stat(output_filename).st_size
                        if length == ofx_length:
                            with open(output_filename, 'rb') as existing_file:
                                existing_contents = existing_file.read()
                            if existing_contents == ofx_contents:
                                write_file = False
                                logging.info("Found identical file at %s", output_filename)
                                break
                    else:
                        break
                    i += 1
                if not write_file:
                    continue
                os.rename(tmp_filename, output_filename)
                logging.info("Saved to %s", output_filename)
            finally:
                if os.path.exists(tmp_filename):
                    os.remove(tmp_filename)

def main():
    global TARGET_PATH
    logging.getLogger().setLevel(logging.INFO)
    TARGET_PATH = pyzar_config.get_config().get('email', 'statement_dir')
    MAIL_URL = urlparse.urlparse(pyzar_config.get_config().get('email', 'url'))
    if MAIL_URL.scheme == 'imap':
        ssl = False
    elif MAIL_URL.scheme == 'imaps':
        # Is this supported by the RFCs?
        ssl = True
    else:
        raise ValueError("URL scheme should be imap or imaps - got %s" % MAIL_URL.scheme)
    USERNAME = pyzar_config.get_config().get('email', 'username') if not MAIL_URL.username else MAIL_URL.username
    PASSWORD = getpass.getpass("enter email password for %s: " % MAIL_URL.hostname) if not MAIL_URL.password else MAIL_URL.password
    StatementMailBot.home_folder = MAIL_URL.path
    bot = StatementMailBot(MAIL_URL.hostname, USERNAME, PASSWORD, port=MAIL_URL.port, ssl=ssl)
    mailbot.register(StatementCallback)
    bot.process_messages()

if __name__ == '__main__':
    main()

