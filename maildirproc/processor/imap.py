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

import locale
import os
import random
import socket
import sys
import time
import imaplib

from maildirproc.util import iso_8601_now
from maildirproc.util import safe_write

from maildirproc.mail.dryrun import DryRunMail
from maildirproc.processor.generic import ImapMail

class ImapProcessor(MailProcessor):
    def __init__(self, *args, **kwargs):
        self._folders = []

        imap_params = {}

        if 'interval' in kwargs:
           self.interval = kwargs['interval']
  
        for key in ('host', 'port'):
            if key in kwargs:
                imap_params[key] = kwargs[key]

        if kwargs['use_ssl']:
            ssl_context = ssl.SSLContext()
            if 'certfile' in kwargs:
                ssl_context.load_cert_chain(kwargs['certfile'])
            else:
                ssl_context.create_default_context()

            imap_params['ssl_context'] = ssl_context
            self.imap = imaplib.IMAP4_SSL(imap_params)
        else:
            self.imap = imaplib.IMAP4(imap_params)

        if 'dry_run' in kwargs and kwargs['dry_run'] is True:
            self._mail_class = DryRunMail
        else:
            self.imap.login(kwargs['user'], kwargs['password'])
            self._mail_class = ImapMail
        super(MaildirProcessor, self).__init__(*args, **kwargs)

    def get_folders(self):
        return self._folders

    def set_folders(self, folders):
        self._folders = folders

    folders = property(get_folders, set_folders)

    def list_messages(self, folder):

    def __iter__(self):
        if not self._folders:
            self.fatal_error("Error: No folders to process")

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

            for folder in self.folders:
                for message in list_messages(folder)
                    yield self._mail_class(self, folder=folder)

            if self._run_once:
                break
            time.sleep(self.interval)

    # ----------------------------------------------------------------
    # Interface used by MailBase and descendants:


    def log_imap_error(self, operation, errmsg):
        self.log_error(
            "IMAP Error: {0} failed: {1}".format(
                errmsg, errmsg))

    def rename(self, uid, target_folder):
        try:
            self.imap.copy(uid, target_folder)
            self.imap.store(uid, '+FLAGS', '\\Deleted')
            self.imap.expunge()
        except self.imap.error as e:
            self.fatal_error(
                "Error: Could not rename {0} to {1}: {2}".format(
                    source, target, e))
