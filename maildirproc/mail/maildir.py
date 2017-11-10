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

import shutil
import subprocess

from maildirproc.mail.base import MailBase

class MaildirMail(MailBase):
    def copy(self, maildir):
        self._processor.log("==> Copying to {0}".format(maildir))
        self._copy(maildir)

    def delete(self):
        self._processor.log("==> Deleting")
        self._delete()

    def forward(self, addresses, env_sender=None):
        self._forward(True, addresses, env_sender)

    def forward_copy(self, addresses, env_sender=None):
        self._forward(False, addresses, env_sender)

    def move(self, maildir):
        self._processor.log("==> Moving to {0}".format(maildir))
        flagpart = self._get_flagpart()
        target = os.path.join(
            self._processor.maildir_base,
            maildir,
            self.path.split(os.sep)[-2],  # new/cur
            self._processor.create_maildir_name() + flagpart)
        self._processor.rename(self.path, target)

    # ----------------------------------------------------------------

    def _copy(self, maildir):
        try:
            source_fp = open(self.path, "rb")
        except IOError as e:
            # The file was probably (re)moved by some other process.
            self._processor.log_mail_opening_error(self.path, e)
            return

        tmp_target = os.path.join(
            self._processor.maildir_base,
            maildir,
            "tmp",
            self._processor.create_maildir_name())
        try:
            tmp_target_fp = os.fdopen(
                os.open(tmp_target, os.O_WRONLY | os.O_CREAT | os.O_EXCL),
                "wb")
        except IOError as e:
            self._processor.log_io_error(
                "Could not open {0} for writing".format(tmp_target),
                e)
            return
        try:
            shutil.copyfileobj(source_fp, tmp_target_fp)
            source_fp.close()
            tmp_target_fp.close()
        except IOError as e:
            self._processor.log_io_error(
                "Could not copy {0} to {1}".format(self.path, tmp_target),
                e)
            return

        flagpart = self._get_flagpart()
        target = os.path.join(
            self._processor.maildir_base,
            maildir,
            self.path.split(os.sep)[-2],  # new/cur
            self._processor.create_maildir_name() + flagpart)
        try:
            self._processor.rename(tmp_target, target)
        except IOError as e:
            self._processor.log_io_error(
                "Could not rename {0} to {1}".format(tmp_target, target),
                e)

    def _delete(self):
        try:
            os.unlink(self.path)
        except OSError as e:
            # The file was probably moved.
            self._processor.log_io_error(
                "Could not delete {0}; some other process probably (re)moved"
                " it".format(self.path),
                e)

    def _forward(self, delete, addresses, env_sender):
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
            source_fp = open(self.path, "rb")
        except IOError as e:
            # The file was probably moved.
            self._processor.log_mail_opening_error(self.path, e)
            return

        p = subprocess.Popen(
            "{0} {1} -- {2}".format(
                self._processor.sendmail,
                flags,
                " ".join(addresses)
                ),
            shell=True,
            stdin=subprocess.PIPE)
        shutil.copyfileobj(source_fp, p.stdin)
        p.stdin.close()
        p.wait()
        source_fp.close()

        if delete:
            self._delete()

    def _get_flagpart(self):
        parts = os.path.basename(self.path).split(":2,")
        if len(parts) == 2:
            return ":2," + parts[1]
        else:
            return ""
