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

from maildirproc.mail.dryrun import DryRunImap
from maildirproc.mail.imap import ImapMail
from maildirproc.processor.generic import MailProcessor

class ImapProcessor(MailProcessor):
    """
    This class is used for processing emails in IMAP mailboxes. It is chiefly
    concerned with folder and account level operations, such as establishing
    the IMAP session, creating and listing folders.
    """
    def __init__(self, *args, **kwargs):
        super(ImapProcessor, self).__init__(*args, **kwargs)

        self.header_cache={}
        self._folders={}

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
            self._mail_class = DryRunImap
        else:
            self._mail_class = ImapMail

        try:
            self.imap.login(kwargs['user'], kwargs['password'])
        except self.imap.error as e:
            self.fatal_imap_error("Login to IMAP server", e)

        try:
            _, namespace_data = self.imap.namespace()
        except self.imap.error as e:
            self.fatal_error("Couldn't retrieve name space separator for "
                              "IMAP server: %s", e)

        p = re.compile('\(\("(.*)" "(.*)"')
        self.prefix = p.match(namespace_data[0].decode('ascii')).group(1)
        self.separator = p.match(namespace_data[0].decode('ascii')).group(2)

        if kwargs['folders'] != None:
            self.set_folders(kwargs['folders'])


    def get_folders(self):
        return self._folders

    def set_folders(self, folders):
        """
        Setter method for the folders to operate on. Can be used to update the
        list of folders at runtime.
        """
        self._folders = folders

        self.log("==> Processing the following IMAP folders:")
        for folder in self.folders:
            self.log("    " + folder)
            self.log("")

        for folder in self.folders:
            self.header_cache[folder] = []
        self._cache_headers()

    folders = property(get_folders, set_folders)

    # ----------------------------------------------------------------
    # Logging methods

    def log_imap_error(self, operation, errmsg):
        self.log_error(
            "IMAP Error: {0} failed: {1}".format(
                operation, errmsg))

    def fatal_imap_error(self, operation, errmsg):
        self.fatal_error(
            "Fatal IMAP Error: {0} failed: {1}".format(
                operation, errmsg))

    # ----------------------------------------------------------------


    def create_folder(self, folder, parents=True):
        """
        Creates a new IMAP folder.

        It can safely be invoked with an existing folder name since it checks
        for existence of the folder first and will do nothing if the folder
        exists. This method creates a folder's parent directories recursively
        by default. If you do not wish this behaviour, please specify
        parents=False.
        """

        folder_list = self.path_list(folder, sep=self.separator)

        if len(folder_list) == 0:
            return

        if parents:
            self.create_folder(folder_list[:-1], parents=parents)

        target = self.list_path(folder, sep=self.separator)

        exists, detail = self._status(target)

        if exists:
            self.log("==> Not creating folder %s: folder exists." % folder)
            return

        self.log("==> Creating folder %s" % target)
        try:
            status, data = self.imap.create(target)
        except self.imap.error as e:
            self.fatal_error("Couldn't create folder %s: %s", target, e)
        if status != 'OK':
            self.fatal_error("Couldn't create folder "
                             "%s: %s / %s" % (target,
                                              status, data[0].decode('ascii')))
        try:
            status, data = self.imap.subscribe(target)
        except self.imap.error as e:
            self.fatal_error("Couldn't subscribe to folder %s: %s", target, e)
        if status != 'OK':
            self.fatal_error("Couldn't subscribe to folder "
                             "%s: %s / %s" % (target,
                                              status, data[0].decode('ascii')))

        self.log("==> Successfully created folder %s" % target)

    def list_messages(self, folder):
        """
        Lists all messages in an IMAP folder.
        """
        self._select(folder)
        try:
            ret, data = self.imap.uid('search', None, "ALL")
        except self.imap.error as e:
            self.fatal_error("Listing messages in folder %s "
                             "failed: %s" % (folder, e))
        if ret != 'OK':
            self.log_imap_error("Listing messages in folder %s failed: %s" % (folder,
                                                                              ret))
            return []
        return data[0].decode('ascii').split()


    def __iter__(self):
        """
        Iterator method used to invoke the processor from the filter
        configuration file.
        """
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
                for message in self.header_cache[folder]:
                    yield message

            if self._run_once:
                break
            time.sleep(self.interval)


    # ----------------------------------------------------------------

    def _cache_headers(self):
        """
        This method updates the processor's header cache for all folders this
        processor is configured to process.
        """
        self.log("Updating header cache...")
        for folder in self.folders:
            for message in self.list_messages(folder):
                self.header_cache[folder].append(
                    self._mail_class(self, folder=folder,
                                     uid=message))
        self.log("Header cache up to date.")

    def _select(self, folder):
        """
        Performs an IMAP SELECT on folder in preparation for retrieving the
        list of message UIDs in that folder.
        """
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
        """
        Performs an IMAP STATUS on folder. Primarily useful for checking folder
        existence.
        """
        try:
            status, data = self.imap.select(mailbox=folder)
        except self.imap.error as e:
            self.fatal_error("Couldn't query status for "
                             "folder %s: %s" % (folder, e))
        data = data[0].decode('ascii')
        # STATUS ends SELECT state, so return to previously selected folder.
        self._select(self.selected)
        return (status == 'OK', data)
