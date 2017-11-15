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

import codecs
import imaplib
import locale
import os
import random
import socket
import ssl
import re
import sys
import time

from maildirproc.util import iso_8601_now
from maildirproc.util import safe_write

from maildirproc.mail.dryrun import DryRunMail
from maildirproc.mail.imap import ImapMail
from maildirproc.processor.generic import MailProcessor

class ImapProcessor(MailProcessor):
    def __init__(self, *args, **kwargs):
        self._folders = []

        self.interval = kwargs['interval']
  
        if kwargs['port'] == None:
            kwargs['port'] = 143

        if kwargs['use_ssl']:
            if kwargs['port'] == None:
                kwargs['port'] = 993
            ssl_context = ssl.SSLContext()
            if 'certfile' in kwargs:
                ssl_context.load_cert_chain(kwargs['certfile'])
            else:
                ssl_context.create_default_context()

            try:
                self.imap = imaplib.IMAP4_SSL(host=kwargs['host'], 
                                              port=kwargs['port'],
                                              sl_context=ssl_context)
            except Exception as e:
                self.fatal_error("Couldn't connect to IMAP server "
                                 "imaps://%s:%d: %s" % ( kwargs['host'],
                                                         kwargs['port'], e))
        else:
            try:
                self.imap = imaplib.IMAP4(host=kwargs['host'], port=kwargs['port'])
            except Exception as e:
                self.fatal_error("Couldn't connect to IMAP server "
                                 "imap://%s:%d: %s" % ( kwargs['host'],
                                                        kwargs['port'], e))


        if 'dry_run' in kwargs and kwargs['dry_run'] is True:
            self._mail_class = DryRunMail
        else:
            self.imap.login(kwargs['user'], kwargs['password'])
            self._mail_class = ImapMail

        try:
            _, namespace_data = self.imap.namespace()
        except self.imap.error as e:
            self.fatal_error("Couldn't retrieve name space separator for "
                              "IMAP server: %s", e)

        p = re.compile('\(\(".*" "(.*)"')
        self.separator = p.match(namespace_data[0].decode('ascii')).group(1)

        super(ImapProcessor, self).__init__(*args, **kwargs)

    def get_folders(self):
        return self._folders

    def set_folders(self, folders):
        self._folders = folders

    folders = property(get_folders, set_folders)

    # ----------------------------------------------------------------
    # Interface used by MailBase and descendants:


    def log_imap_error(self, operation, errmsg):
        self.log_error(
            "IMAP Error: {0} failed: {1}".format(
                errmsg, errmsg))
    # ----------------------------------------------------------------

    def _select(self, folder):
        try:
            status, data = self.imap.select(mailbox=folder)
        except self.imap.error as e:
            self.fatal_error("Couldn't select folder %s: %s" % (folder, e))
        if status != 'OK':
            self.fatal_error("Couldn't select folder %s: %s / %s" % (folder,
                              status, data[0].decode('ascii')))
            return False
        self.selected = folder
        return True

    def _status(self, folder):
        try:
            status, data = self.imap.select(mailbox=folder)
        except self.imap.error as e:
            self.fatal_error("Couldn't query status for "
                             "folder %s: %s" % (folder, e))
        data = data[0].decode('ascii')
        # STATUS ends SELECT state, so return to previously selected folder.
        self._select(self.selected)
        return (status == 'OK', data)

    def list_messages(self, folder):
        self._select(folder)
        ret, data = self.imap.search(None, "ALL")
        if ret != 'OK':
            log_imap_error("Listing messages in folder %s failed: %s" % (folder, ret))
            return []
        return data[0].decode('ascii').split()

    def create_folder(self, folder):
        exists, detail = self._status(folder)

        if exists:
            self.log("==> Not creating folder %s: folder exists." % folder)
            return

        self.log("==> Creating folder %s" % folder)
        try:
            status, data = self.imap.create(folder)
        except self.imap.error as e:
            self.fatal_error("Couldn't create folder %s: %s", folder, e)
        if status != 'OK':
            self.fatal_error("Couldn't create folder "
                             "%s: %s / %s" % (folder,
                                              status, data[0].decode('ascii')))
        try:
            status, data = self.imap.subscribe(folder)
        except self.imap.error as e:
            self.fatal_error("Couldn't subscribe to folder %s: %s", folder, e)
        if status != 'OK':
            self.fatal_error("Couldn't subscribe to folder "
                             "%s: %s / %s" % (folder,
                                              status, data[0].decode('ascii')))

        self.log("==> Successfully created folder %s" % folder)

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
                for message in self.list_messages(folder):
                    yield self._mail_class(self, folder=folder, uid=message)

            if self._run_once:
                break
            time.sleep(self.interval)

