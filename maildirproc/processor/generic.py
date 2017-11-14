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

import hashlib
import locale
import os
import random
import socket
import sys
import time

from maildirproc.util import iso_8601_now
from maildirproc.util import safe_write
from maildirproc.mail.dryrun import DryRunMail
from maildirproc.mail.maildir import MaildirMail

class MailProcessor(object):
    def __init__(
            self, rcfile, log_fp, **kwargs):

        defaults = {
          'log_level': 1,
          'dry_run': False,
          'run_once': False,
          'auto_reload_rcfile': False
          }

        for key in defaults:
            if key not in kwargs:
                kwargs[key] = defaults[key]

        self._rcfile = rcfile
        self._log_fp = log_fp
        self._log_level = kwargs['log_level']
        self._run_once = kwargs['run_once'] or kwargs['dry_run']
        self._auto_reload_rcfile = kwargs['auto_reload_rcfile']
        self._deliveries = 0
        self._sendmail = "/usr/sbin/sendmail"
        self._sendmail_flags = "-i"
        self.rcfile_modified = False
        self._previous_rcfile_mtime = self._get_previous_rcfile_mtime()

    def get_auto_reload_rcfile(self):
        return self._auto_reload_rcfile

    def set_auto_reload_rcfile(self, value):
        self._auto_reload_rcfile = value

    auto_reload_rcfile = property(
        get_auto_reload_rcfile, set_auto_reload_rcfile)

    def set_logfile(self, path_or_fp):
        if isinstance(path_or_fp, basestring):
            self._log_fp = open(
                os.path.expanduser(path_or_fp),
                "a",
                errors="backslashreplace")
        else:
            self._log_fp = path_or_fp
    logfile = property(fset=set_logfile)

    @property
    def rcfile(self):
        return self._rcfile

    def get_sendmail(self):
        return self._sendmail

    def set_sendmail(self, sendmail):
        self._sendmail = sendmail

    sendmail = property(get_sendmail, set_sendmail)

    def get_sendmail_flags(self):
        return self._sendmail_flags

    def set_sendmail_flags(self, sendmail_flags):
        self._sendmail_flags = sendmail_flags

    sendmail_flags = property(get_sendmail_flags, set_sendmail_flags)

    def __iter__(self):
        message = ("You need to implement an __iter__ operation in your actual "
                   "processor class")
        raise NotImplementedError(message)

    def log(self, text, level=1):
        if level <= self._log_level:
            safe_write(self._log_fp, text)
            self._log_fp.flush()

    def log_debug(self, text):
        self.log(text, 2)

    def log_error(self, text):
        self.log(text, 0)

    def log_info(self, text):
        self.log(text, 1)

    def fatal_error(self, text):
        self.log_error(text)
        safe_write(sys.stderr, text)
        sys.exit(1)

    # ----------------------------------------------------------------
    # Private methods:

    def _get_previous_rcfile_mtime(self):
        if self.rcfile == "-":
            return None
        else:
            try:
                return os.path.getmtime(self.rcfile)
            except OSError:
                # File does not exist.
                return None
