# Copyright (C) 2016  Red Hat, Inc
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
Test cases for the commissaire.oscmd.rhel module.
"""

from . test_oscmd import _Test_OSCmd
from commissaire.oscmd import rhel


class Test_RHEL_OSCmd(_Test_OSCmd):
    """
    Tests for the OSCmd class for RHEL.
    """

    oscmdcls = rhel.OSCmd

    def test_rhel_oscmd_commands(self):
        """
        Verify RHEL's OSCmd returns proper data on restart.
        """
        for meth in self.expected_methods:
            cmd = getattr(self.instance, meth)()
            self.assertEquals(list, type(cmd))
