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

import os
import shutil
import subprocess

from email import errors as email_errors
from email import header as email_header
from email import parser as email_parser

from maildirproc.mail.base import MailBase
from maildirproc.util import iso_8601_now
from maildirproc.util import sha1sum

class ImapMail(MailBase):
    def __init__(self, processor, **kwargs):
        self._uid = kwargs['uid']
        super(ImapMail, self).__init__(processor, **kwargs)

    @property
    def uid(self):
        return self._uid

    def copy(self, folder):
        self._processor.log("==> Copying to {0}".format(folder))
        self._copy(maildir)

    def delete(self):
        self._processor.log("==> Deleting %s" % self.uid)
        self._delete()

    def forward(self, addresses, env_sender=None):
        self._forward(True, addresses, env_sender)

    def forward_copy(self, addresses, env_sender=None):
        self._forward(False, addresses, env_sender)

    def move(self, folder):
        self._processor.log("==> Moving UID {0} to {1}".format(self.uid,
                                                               folder))
        self._processor.rename(self.uid, target)

    def parse_mail(self):
        # We'll just use some encoding that handles all byte values
        # without bailing out. Non-ASCII characters should not exist
        # in the headers according to email standards, but if they do
        # anyway, we mustn't crash.
        encoding = "iso-8859-1"

        self._processor.log("")
        self._processor.log("New mail detected with UID {0}:".format(self.uuid))

        try:
            ret, data = self._processor.fetch(self.uid, "BODY.PEEK[HEADER]")
        except self._processor.imap.error as e:
            # Anything imaplib raises an exception for is fatal.
            self._processor.fatal_error("Error retrieving message "
                                        "with UID %s: %s" % self.uid, e)
       if ret != True:
           self._processor.log_error(
               "Error: Could not retrieve message {0}: {1}".format(self.uid,
                                                                   ret)
           return False

        headers = email_parser.Parser().parsestr(data, headersonly=True)

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
                        "Error: Could not decode header {0} in message "
                        "UID {1}".format(ascii(header), self.uid))
                    value_parts.append(header)
            self._headers[name.lower()] = " ".join(value_parts)
        return True

    # ----------------------------------------------------------------

    def _copy(self, folder):

    def _delete(self):

    def _forward(self, delete, addresses, env_sender):

    def is_seen(self):

    def _get_flagpart(self):

    def _log_processing(self):
        self._processor.log("UID:       {0}".format(self.uid)))
        for name in "Message-ID Subject Date From To Cc".split():
            self._processor.log(
                "{0:<11} {1}".format(name + ":", ascii(self[name])))
