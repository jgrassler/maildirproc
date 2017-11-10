# -*- coding: utf-8; mode: python -*-

# Copyright (C) 2006-2010 Joel Rosdahl <joel@rosdahl.net>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA
# 02110-1301, USA.

import sys
from email import errors as email_errors
from email import header as email_header
from email import parser as email_parser


if sys.version_info[0] < 3:
    from maildirproc.util import ascii

from maildirproc.util import iso_8601_now
from maildirproc.util import sha1sum

from maildirproc.mail.target import MailTarget
from maildirproc.mail.header import MailHeader

class MailBase(object):
    def __init__(self, processor, maildir, mail_path):
        self._processor = processor
        self._maildir = maildir
        self._path = mail_path
        self._target = MailTarget(self)
        self._headers = {}
        if self._parse_mail():
            self._log_processing()

    @property
    def maildir(self):
        return self._maildir

    @property
    def path(self):
        return self._path

    @property
    def processor(self):
        return self._processor

    @property
    def target(self):
        return self._target

    def __getitem__(self, header_name):
        return MailHeader(
            self, header_name, self._headers.get(header_name.lower(), ""))

    def from_mailing_list(self, list_name):
        list_name = list_name.lower()
        for headername in [
                "delivered-to", "mailing-list", "x-beenthere",
                "x-mailing-list"]:
            if self[headername].contains(list_name):
                self._processor.log_debug(
                    "... Mail is on mailing list {0}".format(list_name))
                return True
        self._processor.log_debug(
            "... Mail is not on mailing list {0}".format(list_name))
        return False

    # ----------------------------------------------------------------

    def _log_processing(self):
        try:
            fp = open(self.path, "rb")
        except IOError as e:
            # The file was probably (re)moved by some other process.
            self._processor.log_mail_opening_error(self.path, e)
            return
        self._processor.log("SHA1:       {0}".format(ascii(sha1sum(fp))))
        for name in "Message-ID Subject Date From To Cc".split():
            self._processor.log(
                "{0:<11} {1}".format(name + ":", ascii(self[name])))

    def _parse_mail(self):
        # We'll just use some encoding that handles all byte values
        # without bailing out. Non-ASCII characters should not exist
        # in the headers according to email standards, but if they do
        # anyway, we mustn't crash.
        encoding = "iso-8859-1"

        self._processor.log("")
        self._processor.log("New mail detected at {0}:".format(iso_8601_now()))
        self._processor.log("Path:       {0}".format(ascii(self.path)))
        try:
            fp = open(self.path, encoding=encoding)
        except IOError as e:
            # The file was probably (re)moved by some other process.
            self._processor.log_mail_opening_error(self.path, e)
            return False
        headers = email_parser.Parser().parse(fp, headersonly=True)
        fp.close()
        for name in headers.keys():
            value_parts = []
            for header in headers.get_all(name, []):
                try:
                    for (s, c) in email_header.decode_header(header):
                        # email.header.decode_header in Python 3.x may
                        # return either [(str, None)] or [(bytes,
                        # None), ..., (bytes, encoding)]. We must
                        # compensate for this.
                        if not isinstance(s, str):
                            s = s.decode(c if c else "ascii")
                        value_parts.append(s)
                except (email_errors.HeaderParseError, LookupError,
                        ValueError):
                    self._processor.log_error(
                        "Error: Could not decode header {0}".format(
                            ascii(header)))
                    value_parts.append(header)
            self._headers[name.lower()] = " ".join(value_parts)
        return True

