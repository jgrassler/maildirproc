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

import imaplib
import subprocess
import sys

from email import errors as email_errors
from email import header as email_header
from email import parser as email_parser

from maildirproc.mail.base import MailBase

if sys.version_info[0] < 3:
    from maildirproc.util import ascii

class ImapMail(MailBase):
    def __init__(self, processor, **kwargs):
        self._uid = kwargs['uid']
        self.message_flags = []
        super(ImapMail, self).__init__(processor, **kwargs)

    @property
    def uid(self):
        return self._uid

    def copy(self, folder):
        self._processor.log("==> Copying {0} to {1}".format(self.uid, folder))
        try:
            self._processor.imap.copy(self.uid, folder)
        except self._processor.imap.error as e:
            self._processor.log_imap_error("Copying message UID %s to %s "
                                           " failed: %s" % (self.uid, folder, e))
            raise

    def delete(self):
        try:
            self._processor.log("==> Deleting %s" % self.uid)
            self._processor.imap.store(self.uid, '+FLAGS', '\\Deleted')
            self._processor.imap.expunge()
        except self._processor.imap.error as e:
            # Fail hard because repeated failures here can leave a mess of
            # messages with `Deleted` flags.
            self._processor.log_imap_error(
                "Error: Could not delete message {0} {1}: {2}".format(
                    source, target, e))
            raise

    def forward(self, addresses, env_sender, delete=True):
        if isinstance(addresses, basestring):
            addresses = [addresses]
        else:
            addresses = list(addresses)
        if delete:
            copy = ""
        else:
            copy = " copy"
        flags = self._processor.sendmail_flags
        if env_sender is not None:
            flags += " -f {0}".format(env_sender)

        self._processor.log(
            "==> Forwarding{0} to {1!r}".format(copy, addresses))
        try:
            ret, msg = self._processor.imap.fetch(self.uid, "RFC822")
        except self._processor.error as e:
						# Fail soft, since we haven't changed any mailbox state or forwarded
            # anything, yet. Hence we might as well retry later.
            self._processor.log_imap_error(
                "Error forwarding: Could not retrieve message UID {0}: {1}"
                "{1}".format(uid, e))
            return

        p = subprocess.Popen(
            "{0} {1} -- {2}".format(
                self._processor.sendmail,
                flags,
                " ".join(addresses)
                ),
            shell=True,
            stdin=subprocess.PIPE)

        p.stdin.write(msg)
        p.stdin.close()
        sendmail_status = p.wait()

        if sendmail_status != 0:
            self._processor.log_error("Forwarding message failed: %s "
                                      "exited %d" % (self._processor.sendmail,
                                                     sendmail_status))
            return

        if delete:
            self.delete()

    def forward_copy(self, addresses, env_sender=None):
        self.forward(addresses, env_sender, delete=False)

    def move(self, folder):
        self._processor.log("==> Moving UID {0} to {1}".format(self.uid, folder))
        self.copy(folder)
        self.delete()

    def parse_mail(self):
        self._processor.log("")
        self._processor.log("New mail detected with UID {0}:".format(self.uid))

        try:
            ret, data = self._processor.imap.fetch(self.uid,
                                                   "(BODY.PEEK[HEADER] FLAGS)")
        except self._processor.imap.error as e:
            # Anything imaplib raises an exception for is fatal.
            self._processor.fatal_error("Error retrieving message "
                                        "with UID %s: %s" % (self.uid, e))
        if ret != 'OK':
            self._processor.log_error(
                "Error: Could not retrieve message {0}: {1}".format(self.uid,
                                                                    ret))
            return False

        flags = imaplib.ParseFlags(data[0][0])

        for flag in flags:
            self.message_flags.append(flag.decode('ascii'))


        headers = email_parser.Parser().parsestr(data[0][1].decode('ascii'),
                                                 headersonly=True)

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

    def is_seen(self):
        return '\Seen' in self.message_flags

    def _log_processing(self):
        self._processor.log("UID:       {0}".format(self.uid))
        for name in "Message-ID Subject Date From To Cc".split():
            self._processor.log(
                "{0:<11} {1}".format(name + ":", ascii(self[name])))
