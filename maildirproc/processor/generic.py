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
            self, rcfile, log_fp, log_level=1, dry_run=False, run_once=False,
            auto_reload_rcfile=False):
        self._rcfile = rcfile
        self._log_fp = log_fp
        self._log_level = log_level
        self._run_once = run_once or dry_run
        self._auto_reload_rcfile = auto_reload_rcfile
        self._maildir_base = None
        self._deliveries = 0
        self._maildirs = []
        self._sendmail = "/usr/sbin/sendmail"
        self._sendmail_flags = "-i"
        self.rcfile_modified = False
        self._previous_rcfile_mtime = self._get_previous_rcfile_mtime()
        if dry_run:
            self._mail_class = DryRunMail
        else:
            self._mail_class = MaildirMail

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

    def get_maildir_base(self):
        return self._maildir_base

    def set_maildir_base(self, path):
        self._maildir_base = os.path.expanduser(path)

    maildir_base = property(get_maildir_base, set_maildir_base)

    def get_maildirs(self):
        return self._maildirs

    def set_maildirs(self, maildirs):
        self._maildirs = maildirs

    maildirs = property(get_maildirs, set_maildirs)

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
        if not self._maildirs:
            self.fatal_error("Error: No maildirs to process")

        self.rcfile_modified = False
        mtime_map = {}
        while True:
            if self.auto_reload_rcfile:
                current_rcfile_mtime = self._get_previous_rcfile_mtime()
                if current_rcfile_mtime != self._previous_rcfile_mtime:
                    self._previous_rcfile_mtime = current_rcfile_mtime
                    self.rcfile_modified = True
                    self.log_info("Detected modified RC file; reloading")
                    break
            for maildir in self._maildirs:
                maildir_path = os.path.join(self._maildir_base, maildir)
                for subdir in ["cur", "new"]:
                    subdir_path = os.path.join(maildir_path, subdir)
                    cur_mtime = os.path.getmtime(subdir_path)
                    if cur_mtime != mtime_map.setdefault(subdir_path, 0):
                        if cur_mtime < int(time.time()):
                            # If cur_mtime == int(time.time()) we
                            # can't be sure that everything has been
                            # processed; a new mail may be delivered
                            # later the same second.
                            mtime_map[subdir_path] = cur_mtime
                        for mail_file in os.listdir(subdir_path):
                            mail_path = os.path.join(subdir_path, mail_file)
                            yield self._mail_class(self, maildir, mail_path)
            if self._run_once:
                break
            time.sleep(1)

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
    # Interface used by MailBase and descendants:

    def create_maildir_name(self):
        """Create and return a unique name for a Maildir message."""
        hostname = socket.gethostname()
        hostname = hostname.replace("/", "\\057")
        hostname = hostname.replace(":", "\\072")
        now = time.time()
        delivery_identifier = "M{0}P{1}Q{2}R{3:0>8x}".format(
            round((now - int(now)) * 1000000),
            os.getpid(),
            self._deliveries,
            random.randint(0, 0xffffffff))
        self._deliveries += 1
        return "{0}.{1}.{2}".format(now, delivery_identifier, hostname)

    def log_io_error(self, errmsg, os_errmsg):
        self.log_error(
            "Error: {0} (error message from OS: {1})".format(
                errmsg, os_errmsg))

    def log_mail_opening_error(self, path, errmsg):
        self.log_io_error(
            "Could not open {0}; some other process probably (re)moved"
            " it".format(path),
            errmsg)

    def rename(self, source, target):
        try:
            os.rename(source, target)
        except OSError as e:
            self.log_error(
                "Error: Could not rename {0} to {1}: {2}".format(
                    source, target, e))

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
