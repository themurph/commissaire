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
Test cases for the commissaire.handlers.clusters module.
"""

import json

import etcd
import falcon

from . import TestCase
from mock import MagicMock
from commissaire.handlers import clusters
from commissaire.middleware import JSONify


class Test_Clusters(TestCase):
    """
    Tests for the Clusters model.
    """
    # XXX: Based on Test_Hosts

    def test_clusters_creation(self):
        """
        Verify Clusters model.
        """
        # Make sure clusters is required
        self.assertRaises(
            TypeError,
            clusters.Clusters
        )

        # Make sure an empty Clusters is still valid
        clusters_model = clusters.Clusters(clusters=[])
        self.assertEquals(
            '[]',
            clusters_model.to_json())

        # Make sure a Cluster is accepted as expected
        clusters_model = clusters.Clusters(
            clusters=[clusters.Cluster(status='ok', hostset=[])])
        self.assertEquals(1, len(clusters_model.clusters))
        self.assertEquals(type(str()), type(clusters_model.to_json()))

        # Make sure other instances are not accepted
        clusters_model = clusters.Clusters(clusters=[object()])


class Test_ClustersResource(TestCase):
    """
    Tests for the Clusters resource.
    """
    # XXX: Based on Test_HostsResource

    cluster_name = u'development'
    #acluster = ('{"status": "ok",'
    #            ' "hosts": {"total": 1, "available": 1, "unavailable": 0}}')

    def before(self):
        self.api = falcon.API(middleware=[JSONify()])
        self.datasource = etcd.Client()
        self.return_value = MagicMock(etcd.EtcdResult)
        self.datasource.get = MagicMock(name='get')
        self.datasource.get.return_value = self.return_value
        self.resource = clusters.ClustersResource(self.datasource)
        self.api.add_route('/api/v0/clusters', self.resource)

    def test_clusters_listing(self):
        """
        Verify listing Clusters.
        """
        child = MagicMock(key=self.cluster_name)
        self.return_value._children = [child]
        self.return_value.leaves = self.return_value._children

        body = self.simulate_request('/api/v0/clusters')
        # datasource's get should have been called once
        self.assertEquals(1, self.datasource.get.call_count)
        self.assertEqual(falcon.HTTP_200, self.srmock.status)

        self.assertEqual(
            [self.cluster_name],
            json.loads(body[0]))

    def test_clusters_listing_with_no_clusters(self):
        """
        Verify listing Clusters when no clusters exist.
        """
        self.return_value._children = []
        self.return_value.leaves = self.return_value._children

        body = self.simulate_request('/api/v0/clusters')
        # datasource's get should have been called once
        self.assertEquals(1, self.datasource.get.call_count)
        self.assertEqual(self.srmock.status, falcon.HTTP_200)
        self.assertEqual({}, json.loads(body[0]))

    def test_clusters_listing_with_no_etcd_result(self):
        """
        Verify listing Clusters handles no etcd result properly.
        """
        self.datasource.get.side_effect = etcd.EtcdKeyNotFound

        body = self.simulate_request('/api/v0/clusters')
        # datasource's get should have been called once
        self.assertEquals(1, self.datasource.get.call_count)
        self.assertEqual(self.srmock.status, falcon.HTTP_404)
        self.assertEqual('{}', body[0])


class Test_Cluster(TestCase):
    """
    Tests for the Cluster model.
    """
    # XXX: Based on Test_Host

    def test_cluster_creation(self):
        """
        Verify cluster model.
        """
        # Make sure it requires data
        self.assertRaises(
            TypeError,
            clusters.Cluster)

        # Make sure a Cluster creates expected results
        cluster_model = clusters.Cluster(status='OK', hostset=[])
        self.assertEquals(type(str()), type(cluster_model.to_json()))
        self.assertIn('total', cluster_model.hosts)
        self.assertIn('available', cluster_model.hosts)
        self.assertIn('unavailable', cluster_model.hosts)


class Test_ClusterResource(TestCase):
    """
    Tests for the Cluster resource.
    """
    # Based on Test_HostResource

    acluster = ('{"status": "ok",'
                ' "hosts": {"total": 1,'
                '           "available": 1,'
                '           "unavailable": 0}}')

    etcd_cluster = '{"status": "ok", "hostset": ["10.2.0.2"]}'
    etcd_host = ('{"address": "10.2.0.2", "ssh_priv_key": "dGVzdAo=",'
                 ' "status": "active", "os": "atomic",'
                 ' "cpus": 2, "memory": 11989228, "space": 487652,'
                 ' "last_check": "2015-12-17T15:48:18.710454",'
                 ' "cluster":"development"}')

    def before(self):
        self.api = falcon.API(middleware=[JSONify()])
        self.datasource = MagicMock(etcd.Client)
        self.return_value = MagicMock(etcd.EtcdResult)
        self.datasource.get = MagicMock(name='get')
        self.datasource.get.return_value = self.return_value
        self.datasource.set = MagicMock(name='set')
        self.datasource.set.return_value = self.return_value
        self.datasource.delete = MagicMock(name='delete')
        self.datasource.delete.return_value = self.return_value
        self.resource = clusters.ClusterResource(self.datasource)
        self.api.add_route('/api/v0/cluster/{name}', self.resource)

    def test_cluster_retrieve(self):
        """
        Verify retrieving a cluster.
        """
        # Verify if the cluster exists the data is returned
        child = {'value': self.etcd_host}
        hosts_return_value = MagicMock(
            etcd.EtcdResult, leaves=[child],
            value=child, _children=[child])
        # First call return is etcd_cluster, second is the host_return_value
        self.datasource.get.side_effect = (
            MagicMock(value=self.etcd_cluster), hosts_return_value)

        body = self.simulate_request('/api/v0/cluster/development')
        # datasource's get should have been called once
        self.assertEquals(2, self.datasource.get.call_count)
        self.assertEqual(self.srmock.status, falcon.HTTP_200)
        self.assertEqual(
            json.loads(self.acluster),
            json.loads(body[0]))

        # Verify no cluster returns the proper result
        self.datasource.get.reset_mock()
        self.datasource.get.side_effect = etcd.EtcdKeyNotFound

        body = self.simulate_request('/api/v0/cluster/bogus')
        self.assertEquals(1, self.datasource.get.call_count)
        self.assertEqual(falcon.HTTP_404, self.srmock.status)
        self.assertEqual({}, json.loads(body[0]))

    def test_cluster_create(self):
        """
        Verify creating a cluster.
        """
        # Verify with creation
        self.datasource.get.side_effect = etcd.EtcdKeyNotFound
        self.datasource.set.return_value = MagicMock(
            value=self.etcd_cluster)
        body = self.simulate_request(
            '/api/v0/cluster/development', method='PUT')
        self.assertEquals(falcon.HTTP_201, self.srmock.status)
        self.assertEquals('{}', body[0])

        # Verify with existing cluster
        self.datasource.get.return_value = MagicMock(
            value=self.etcd_cluster)
        body = self.simulate_request(
            '/api/v0/cluster/development', method='PUT')
        self.assertEquals(falcon.HTTP_201, self.srmock.status)
        self.assertEquals('{}', body[0])

    def test_cluster_delete(self):
        """
        Verify deleting a cluster.
        """
        # Verify with proper deletion
        body = self.simulate_request(
            '/api/v0/cluster/development', method='DELETE')
        self.assertEquals(falcon.HTTP_410, self.srmock.status)
        self.assertEquals('{}', body[0])

        # Verify when key doesn't exist
        self.datasource.delete.side_effect = etcd.EtcdKeyNotFound
        body = self.simulate_request(
            '/api/v0/cluster/development', method='DELETE')
        self.assertEquals(falcon.HTTP_404, self.srmock.status)
        self.assertEquals('{}', body[0])


class Test_ClusterRestart(TestCase):
    """
    Tests for the ClusterRestart model.
    """

    def test_cluster_restart_creation(self):
        """
        Verify cluster restart model.
        """
        # Make sure it requires data
        self.assertRaises(
            TypeError,
            clusters.ClusterRestart)

        # Make sure a Cluster creates expected results
        cluster_restart_model = clusters.ClusterRestart(
            status='inprocess', restarted=[], in_process=[],
            started_at=None, finished_at=None)

        self.assertEquals(type(str()), type(cluster_restart_model.to_json()))


class Test_ClusterRestartResource(TestCase):
    """
    Tests for the ClusterRestart resource.
    """

    arestart = ('{"status": "", "restarted": "", "in_process": "",'
                ' "started_at": "", "finished_at": ""}')

    def before(self):
        self.api = falcon.API(middleware=[JSONify()])
        self.datasource = MagicMock(etcd.Client)
        self.datasource.get = MagicMock(name='get')
        self.datasource.set = MagicMock(name='set')
        self.resource = clusters.ClusterRestartResource(self.datasource)
        self.api.add_route('/api/v0/cluster/{name}/restart', self.resource)

    def test_cluster_restart_retrieve(self):
        """
        Verify retrieving a cluster restart.
        """
        # Verify if the cluster restart exists the data is returned
        self.datasource.get.return_value = MagicMock(value=self.arestart)
        body = self.simulate_request('/api/v0/cluster/development/restart')
        self.assertEqual(falcon.HTTP_200, self.srmock.status)
        self.assertEquals(2, self.datasource.get.call_count)
        self.assertEqual(json.loads(self.arestart), json.loads(body[0]))

        # Verify no cluster restart returns the proper result
        self.datasource.get.reset_mock()
        self.datasource.get.side_effect = [None, etcd.EtcdKeyNotFound]
        body = self.simulate_request('/api/v0/cluster/development/restart')
        self.assertEquals(2, self.datasource.get.call_count)
        self.assertEqual(falcon.HTTP_204, self.srmock.status)
        self.assertEqual([], body)  # Empty data'''

    def test_cluster_restart_create(self):
        """
        Verify creating a cluster restart.
        """
        # Verify with creation
        body = self.simulate_request(
            '/api/v0/cluster/development/restart',
            method='PUT')
        self.assertEquals(falcon.HTTP_201, self.srmock.status)
        result = json.loads(body[0])
        self.assertEquals('in_process', result['status'])
        self.assertEquals([], result['restarted'])
        self.assertEquals([], result['in_process'])


class Test_ClusterHostsResource(TestCase):
    """
    Tests for the ClusterHosts resource.
    """

    ahostset = '["10.2.0.2"]'

    etcd_cluster = '{"status": "ok", "hostset": ["10.2.0.2"]}'

    def before(self):
        self.api = falcon.API(middleware=[JSONify()])
        self.datasource = MagicMock(etcd.Client)
        self.return_value = MagicMock(etcd.EtcdResult)
        self.datasource.get = MagicMock(name='get')
        self.datasource.get.return_value = self.return_value
        self.datasource.set = MagicMock(name='set')
        self.datasource.set.return_value = self.return_value
        self.resource = clusters.ClusterHostsResource(self.datasource)
        self.api.add_route('/api/v0/cluster/{name}/hosts', self.resource)

    def test_cluster_hosts_retrieve(self):
        """
        Verify retrieving a cluster host list.
        """

        # Verify if the cluster exists the host list is returned
        self.datasource.get.return_value = MagicMock(value=self.etcd_cluster)
        body = self.simulate_request('/api/v0/cluster/development/hosts')
        self.assertEquals(1, self.datasource.get.call_count)
        self.assertEqual(falcon.HTTP_200, self.srmock.status)
        self.assertEqual(
            json.loads(self.ahostset),
            json.loads(body[0]))

        # Verify bad cluster name returns the proper result
        self.datasource.get.reset_mock()
        self.datasource.get.side_effect = etcd.EtcdKeyNotFound
        body = self.simulate_request('/api/v0/cluster/bogus/hosts')
        self.assertEquals(1, self.datasource.get.call_count)
        self.assertEqual(falcon.HTTP_404, self.srmock.status)
        self.assertEqual({}, json.loads(body[0]))

    def test_cluster_hosts_overwrite(self):
        """
        Verify overwriting a cluster host list.
        """

        # Verify setting host list works with a proper request
        self.datasource.get.return_value = MagicMock(value=self.etcd_cluster)
        body = self.simulate_request(
            '/api/v0/cluster/development/hosts', method='PUT',
            body='{"old": ["10.2.0.2"], "new": ["10.2.0.2", "10.2.0.3"]}')
        self.assertEquals(1, self.datasource.get.call_count)
        self.assertEquals(1, self.datasource.set.call_count)
        self.assertEqual(falcon.HTTP_200, self.srmock.status)
        self.assertEqual({}, json.loads(body[0]))

        # Verify bad request (KeyError) returns the proper result
        self.datasource.get.reset_mock()
        self.datasource.set.reset_mock()
        self.datasource.get.return_value = MagicMock(value=self.etcd_cluster)
        body = self.simulate_request(
            '/api/v0/cluster/development/hosts', method='PUT',
            body='{"new": ["10.2.0.2", "10.2.0.3"]}')
        self.assertEquals(0, self.datasource.get.call_count)
        self.assertEquals(0, self.datasource.set.call_count)
        self.assertEqual(falcon.HTTP_400, self.srmock.status)
        self.assertEqual({}, json.loads(body[0]))

        # Verify bad request (TypeError) returns the proper result
        self.datasource.get.reset_mock()
        self.datasource.set.reset_mock()
        self.datasource.get.return_value = MagicMock(value=self.etcd_cluster)
        body = self.simulate_request(
            '/api/v0/cluster/development/hosts', method='PUT',
            body='["10.2.0.2", "10.2.0.3"]')
        self.assertEquals(0, self.datasource.get.call_count)
        self.assertEquals(0, self.datasource.set.call_count)
        self.assertEqual(falcon.HTTP_400, self.srmock.status)
        self.assertEqual({}, json.loads(body[0]))

        # Verify bad cluster name returns the proper result
        self.datasource.get.reset_mock()
        self.datasource.set.reset_mock()
        self.datasource.get.side_effect = etcd.EtcdKeyNotFound
        body = self.simulate_request(
            '/api/v0/cluster/bogus/hosts', method='PUT',
            body='{"old": ["10.2.0.2"], "new": ["10.2.0.2", "10.2.0.3"]}')
        self.assertEquals(1, self.datasource.get.call_count)
        self.assertEquals(0, self.datasource.set.call_count)
        self.assertEqual(falcon.HTTP_404, self.srmock.status)
        self.assertEqual({}, json.loads(body[0]))

        # Verify host list conflict returns the proper result
        self.datasource.get.reset_mock()
        self.datasource.set.reset_mock()
        self.datasource.get.side_effect = None
        self.datasource.get.return_value = MagicMock(value=self.etcd_cluster)
        body = self.simulate_request(
            '/api/v0/cluster/development/hosts', method='PUT',
            body='{"old": [], "new": ["10.2.0.2", "10.2.0.3"]}')
        self.assertEquals(1, self.datasource.get.call_count)
        self.assertEquals(0, self.datasource.set.call_count)
        self.assertEqual(falcon.HTTP_409, self.srmock.status)
        self.assertEqual({}, json.loads(body[0]))


class Test_ClusterSingleHostResource(TestCase):
    """
    Tests for the ClusterSingleHost resource.
    """

    ahostset = '["10.2.0.2"]'

    etcd_cluster = '{"status": "ok", "hostset": ["10.2.0.2"]}'

    def before(self):
        self.api = falcon.API(middleware=[JSONify()])
        self.datasource = MagicMock(etcd.Client)
        self.return_value = MagicMock(etcd.EtcdResult)
        self.datasource.get = MagicMock(name='get')
        self.datasource.get.return_value = self.return_value
        self.datasource.set = MagicMock(name='set')
        self.datasource.set.return_value = self.return_value
        self.resource = clusters.ClusterSingleHostResource(self.datasource)
        self.api.add_route(
            '/api/v0/cluster/{name}/hosts/{address}', self.resource)

    def test_cluster_host_membership(self):
        """
        Verify host membership in a cluster.
        """

        # Verify member host returns the proper result
        self.datasource.get.return_value = MagicMock(value=self.etcd_cluster)
        body = self.simulate_request(
            '/api/v0/cluster/development/hosts/10.2.0.2')
        self.assertEquals(1, self.datasource.get.call_count)
        self.assertEqual(falcon.HTTP_200, self.srmock.status)
        self.assertEqual({}, json.loads(body[0]))

        # Verify non-member host returns the proper result
        self.datasource.get.reset_mock()
        self.datasource.get.return_value = MagicMock(value=self.etcd_cluster)
        body = self.simulate_request(
            '/api/v0/cluster/development/hosts/10.9.9.9')
        self.assertEquals(1, self.datasource.get.call_count)
        self.assertEqual(falcon.HTTP_404, self.srmock.status)
        self.assertEqual({}, json.loads(body[0]))

        # Verify bad cluster name returns the proper result
        self.datasource.get.reset_mock()
        self.datasource.get.side_effect = etcd.EtcdKeyNotFound
        body = self.simulate_request(
            '/api/v0/cluster/bogus/hosts/10.2.0.2')
        self.assertEquals(1, self.datasource.get.call_count)
        self.assertEqual(falcon.HTTP_404, self.srmock.status)
        self.assertEqual({}, json.loads(body[0]))

    def test_cluster_host_insert(self):
        """
        Verify insertion of host in a cluster.
        """

        # Verify inserting host returns the proper result
        self.datasource.get.return_value = MagicMock(value=self.etcd_cluster)
        body = self.simulate_request(
            '/api/v0/cluster/developent/hosts/10.2.0.3', method='PUT')
        self.assertEquals(1, self.datasource.get.call_count)
        self.assertEquals(1, self.datasource.set.call_count)
        self.assertEqual(falcon.HTTP_200, self.srmock.status)
        self.assertEqual({}, json.loads(body[0]))

        # Verify bad cluster name returns the proper result
        self.datasource.get.reset_mock()
        self.datasource.set.reset_mock()
        self.datasource.get.side_effect = etcd.EtcdKeyNotFound
        body = self.simulate_request(
            '/api/v0/cluster/bogus/hosts/10.2.0.3', method='PUT')
        self.assertEquals(1, self.datasource.get.call_count)
        self.assertEquals(0, self.datasource.set.call_count)
        self.assertEqual(falcon.HTTP_404, self.srmock.status)
        self.assertEqual({}, json.loads(body[0]))

    def test_cluster_host_delete(self):
        """
        Verify deletion of host in a cluster.
        """

        # Verify deleting host returns the proper result
        self.datasource.get.return_value = MagicMock(value=self.etcd_cluster)
        body = self.simulate_request(
            '/api/v0/cluster/development/hosts/10.2.0.2', method='DELETE')
        self.assertEquals(1, self.datasource.get.call_count)
        self.assertEquals(1, self.datasource.set.call_count)
        self.assertEqual(falcon.HTTP_200, self.srmock.status)
        self.assertEqual({}, json.loads(body[0]))

        # Verify bad cluster name returns the proper result
        self.datasource.get.reset_mock()
        self.datasource.set.reset_mock()
        self.datasource.get.side_effect = etcd.EtcdKeyNotFound
        body = self.simulate_request(
            '/api/v0/cluster/bogus/hosts/10.2.0.2', method='DELETE')
        self.assertEquals(1, self.datasource.get.call_count)
        self.assertEquals(0, self.datasource.set.call_count)
        self.assertEqual(falcon.HTTP_404, self.srmock.status)
        self.assertEqual({}, json.loads(body[0]))


class Test_ClusterUpgrade(TestCase):
    """
    Tests for the ClusterUpgrade model.
    """

    def test_cluster_upgrade_creation(self):
        """
        Verify cluster upgrade model.
        """
        # Make sure it requires data
        self.assertRaises(
            TypeError,
            clusters.ClusterUpgrade)

        # Make sure a Cluster Upgrade creates expected results
        cluster_upgrade_model = clusters.ClusterUpgrade(
            status='inprocess', upgrade_to='', upgraded=[], in_process=[],
            started_at=None, finished_at=None)

        self.assertEquals(type(str()), type(cluster_upgrade_model.to_json()))


class Test_ClusterUpgradeResource(TestCase):
    """
    Tests for the ClusterUpgrade resource.
    """

    aupgrade = ('{"status": "ok", "upgrade_to": "7.0.2", "upgraded": [],'
                ' "in_process": [], "started_at": "",'
                ' "finished_at": "0001-01-01T00:00:00"}')

    def before(self):
        self.api = falcon.API(middleware=[JSONify()])
        self.datasource = MagicMock(etcd.Client)
        self.datasource.get = MagicMock(name='get')
        self.datasource.set = MagicMock(name='set')
        self.resource = clusters.ClusterUpgradeResource(self.datasource)
        self.api.add_route('/api/v0/cluster/{name}/upgrade', self.resource)

    def test_cluster_upgrade_retrieve(self):
        """
        Verify retrieving a cluster upgrade.
        """
        # Verify if the cluster upgrade exists the data is returned
        self.datasource.get.return_value = MagicMock(value=self.aupgrade)
        body = self.simulate_request('/api/v0/cluster/development/upgrade')
        self.assertEquals(2, self.datasource.get.call_count)
        self.assertEqual(falcon.HTTP_200, self.srmock.status)
        self.assertEqual(json.loads(self.aupgrade), json.loads(body[0]))

        # Verify no cluster upgrade returns the proper result
        self.datasource.get.reset_mock()
        self.datasource.get.side_effect = (None, etcd.EtcdKeyNotFound)

        body = self.simulate_request('/api/v0/cluster/development/upgrade')
        self.assertEquals(2, self.datasource.get.call_count)
        self.assertEqual(falcon.HTTP_204, self.srmock.status)
        self.assertEqual([], body)  # Empty data

    def test_cluster_create(self):
        """
        Verify creating a cluster.
        """
        # Verify sending no/bad data returns a 400
        for put_data in (None, '{"nothing": "here"}"'):
            body = self.simulate_request(
                '/api/v0/cluster/development/upgrade',
                method='PUT',
                body=put_data)
            self.assertEquals(falcon.HTTP_400, self.srmock.status)
            self.assertEquals('{}', body[0])

        # Verify with creation
        body = self.simulate_request(
            '/api/v0/cluster/development/upgrade',
            method='PUT',
            body='{"upgrade_to": "7.0.2"}')
        self.assertEquals(falcon.HTTP_201, self.srmock.status)
        result = json.loads(body[0])
        self.assertEquals('in_process', result['status'])
        self.assertEquals('7.0.2', result['upgrade_to'])
        self.assertEquals([], result['upgraded'])
        self.assertEquals([], result['in_process'])
