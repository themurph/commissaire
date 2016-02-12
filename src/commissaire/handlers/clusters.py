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
Cluster(s) handlers.
"""

import datetime
import falcon
import etcd
import json

from commissaire.resource import Resource
from commissaire.jobs import POOLS, clusterexec
from commissaire.handlers.models import (
    Cluster, Clusters, ClusterRestart, ClusterUpgrade, Host)


class ClustersResource(Resource):
    """
    Resource for working with Clusters.
    """

    def on_get(self, req, resp):
        """
        Handles GET requests for Clusters.

        :param req: Request instance that will be passed through.
        :type req: falcon.Request
        :param resp: Response instance that will be passed through.
        :type resp: falcon.Response
        """
        try:
            clusters_dir = self.store.get('/commissaire/clusters/')
        except etcd.EtcdKeyNotFound:
            self.logger.warn(
                'Etcd does not have any clusters. Returning [] and 404.')
            resp.status = falcon.HTTP_404
            req.context['model'] = None
            return
        results = []
        # Don't let an empty clusters directory through
        if len(clusters_dir._children):
            for cluster in clusters_dir.leaves:
                results.append(cluster.key.split('/')[-1])
            resp.status = falcon.HTTP_200
            req.context['model'] = Clusters(clusters=results)
        else:
            self.logger.debug(
                'Etcd has a clusters directory but no content.')
            resp.status = falcon.HTTP_200
            req.context['model'] = None


class ClusterResource(Resource):
    """
    Resource for working with a single Cluster.
    """

    def _calculate_hosts(self, cluster):
        """
        Calculates the hosts metadata for the cluster.

        :param cluster: The name of the cluster.
        :type cluster: str
        """
        try:
            # XXX: Not sure which wil be more efficient: fetch all
            #      the host data in one etcd call and sort through
            #      them, or fetch the ones we need individually.
            #      For the MVP phase, fetch all is better.
            etcd_resp = self.store.get('/commissaire/hosts')
        except etcd.EtcdKeyNotFound:
            self.logger.warn(
                'Etcd does not have any hosts. '
                'Cannot determine cluster stats.')
            return

        available = unavailable = total = 0
        for child in etcd_resp._children:
            host = Host(**json.loads(child['value']))
            if host.address in cluster.hostset:
                total += 1
                if host.status == 'active':
                    available += 1
                else:
                    unavailable += 1

        cluster.hosts['total'] = total
        cluster.hosts['available'] = available
        cluster.hosts['unavailable'] = unavailable

    def on_get(self, req, resp, name):
        """
        Handles retrieval of an existing Cluster.

        :param req: Request instance that will be passed through.
        :type req: falcon.Request
        :param resp: Response instance that will be passed through.
        :type resp: falcon.Response
        :param name: The name of the Cluster being requested.
        :type name: str
        """
        key = '/commissaire/clusters/{0}'.format(name)
        try:
            etcd_resp = self.store.get(key)
            self.logger.info(
                'Request for cluster {0}.'.format(name))
            self.logger.debug('{0}'.format(etcd_resp))
        except etcd.EtcdKeyNotFound:
            self.logger.info(
                'Request for non-existent cluster {0}.'.format(name))
            resp.status = falcon.HTTP_404
            return

        cluster = Cluster(**json.loads(etcd_resp.value))
        self._calculate_hosts(cluster)
        # Have to set resp.body explicitly to include Hosts.
        resp.body = cluster.to_json_with_hosts()
        resp.status = falcon.HTTP_200

    def on_put(self, req, resp, name):
        """
        Handles the creation of a new Cluster.

        :param req: Request instance that will be passed through.
        :type req: falcon.Request
        :param resp: Response instance that will be passed through.
        :type resp: falcon.Response
        :param name: The name of the Cluster being created.
        :type name: str
        """
        # PUT is idempotent, and since there's no body to this request,
        # there's nothing to conflict with.  The request should always
        # succeed, even if we didn't actually do anything.
        key = '/commissaire/clusters/{0}'.format(name)
        try:
            etcd_resp = self.store.get(key)
            self.logger.info(
                'Creation of already exisiting cluster {0} requested.'.format(
                    name))
        except etcd.EtcdKeyNotFound:
            cluster = Cluster(status='ok', hostset=[])
            etcd_resp = self.store.set(key, cluster.to_json(secure=True))
            self.logger.info(
                'Created cluster {0} per request.'.format(name))
        cluster = Cluster(**json.loads(etcd_resp.value))
        resp.status = falcon.HTTP_201

    def on_delete(self, req, resp, name):
        """
        Handles the deletion of a Cluster.

        :param req: Request instance that will be passed through.
        :type req: falcon.Request
        :param resp: Response instance that will be passed through.
        :type resp: falcon.Response
        :param name: The name of the Cluster being deleted.
        :type name: str
        """
        key = '/commissaire/clusters/{0}'.format(name)
        resp.body = '{}'
        try:
            self.store.delete(key)
            resp.status = falcon.HTTP_410
            self.logger.info(
                'Deleted cluster {0} per request.'.format(name))
        except etcd.EtcdKeyNotFound:
            self.logger.info(
                'Deleting for non-existent cluster {0} requested.'.format(
                    name))
            resp.status = falcon.HTTP_404


class ClusterHostsResource(Resource):
    """
    Resource for managing host membership in a Cluster.
    """

    def get_cluster_model(self, name):
        """
        Returns a Cluster instance from the etcd record for the given
        cluster name, if it exists, or else None.

        :param name: Name of a cluster
        :type name: str
        """
        key = '/commissaire/clusters/{0}'.format(name)
        try:
            etcd_resp = self.store.get(key)
            self.logger.info(
                'Request for cluster {0}.'.format(name))
            self.logger.debug('{0}'.format(etcd_resp))
        except etcd.EtcdKeyNotFound:
            self.logger.info(
                'Request for non-existent cluster {0}.'.format(name))
            return None
        return Cluster(**json.loads(etcd_resp.value))

    def on_get(self, req, resp, name):
        """
        Handles GET requests for Cluster hosts.

        :param req: Request instance that will be passed through.
        :type req: falcon.Request
        :param resp: Response instance that will be passed through.
        :type resp: falcon.Response
        :param name: The name of the Cluster being requested.
        :type name: str
        """
        cluster = self.get_cluster_model(name)
        if not cluster:
            resp.status = falcon.HTTP_404
            return

        resp.body = json.dumps(cluster.hostset)
        resp.status = falcon.HTTP_200

    def on_put(self, req, resp, name):
        """
        Handles PUT requests for Cluster hosts.
        This replaces the entire host list for a Cluster.

        :param req: Request instance that will be passed through.
        :type req: falcon.Request
        :param resp: Response instance that will be passed through.
        :type resp: falcon.Response
        :param name: The name of the Cluster being requested.
        :type name: str
        """
        try:
            req_body = json.loads(req.stream.read().decode())
            old_hosts = set(req_body['old'])  # Ensures no duplicates
            new_hosts = set(req_body['new'])  # Ensures no duplicates
        except (KeyError, TypeError):
            self.logger.info(
                'Bad client PUT request for cluster {0}: {1}'.
                format(name, req_body))
            resp.status = falcon.HTTP_400
            return

        cluster = self.get_cluster_model(name)
        if not cluster:
            resp.status = falcon.HTTP_404
            return

        # old_hosts must match current hosts to accept new_hosts.
        # Note: Order doesn't matter, so etcd's atomic comparison
        #       of the raw values would be too strict.
        if old_hosts != set(cluster.hostset):
            self.logger.info(
                'Conflict setting hosts for cluster {0}'.format(name))
            resp.status = falcon.HTTP_409
            return

        # FIXME: Need input validation.  For each new host,
        #        - Does the host exist at /commissaire/hosts/{IP}?
        #        - Does the host already belong to another cluster?

        # FIXME: Should guard against races here, since we're fetching
        #        the cluster record and writing it back with some parts
        #        unmodified.  Use either locking or a conditional write
        #        with the etcd 'modifiedIndex'.  Deferring for now.

        key = '/commissaire/clusters/{0}'.format(name)
        cluster.hostset = list(new_hosts)
        self.store.set(key, cluster.to_json(secure=True))
        resp.status = falcon.HTTP_200


class ClusterSingleHostResource(ClusterHostsResource):
    """
    Resource for managing a single host's membership in a Cluster.
    """

    def on_get(self, req, resp, name, address):
        """
        Handles GET requests for individual hosts in a Cluster.
        This is a membership test, returning 200 OK if the host
        address is part of the cluster, or else 404 Not Found.

        :param req: Request instance that will be passed through.
        :type req: falcon.Request
        :param resp: Response instance that will be passed through.
        :type resp: falcon.Response
        :param name: The name of the Cluster being requested.
        :type name: str
        :param address: The address of the Host being requested.
        :type address: str
        """
        cluster = self.get_cluster_model(name)
        if not cluster:
            resp.status = falcon.HTTP_404
            return

        if address in cluster.hostset:
            resp.status = falcon.HTTP_200
        else:
            resp.status = falcon.HTTP_404

    def on_put(self, req, resp, name, address):
        """
        Handles PUT requests for individual hosts in a Cluster.
        This adds a single host to the cluster, idempotently.

        :param req: Request instance that will be passed through.
        :type req: falcon.Request
        :param resp: Response instance that will be passed through.
        :type resp: falcon.Response
        :param name: The name of the Cluster being requested.
        :type name: str
        :param address: The address of the Host being requested.
        :type address: str
        """
        cluster = self.get_cluster_model(name)
        if not cluster:
            resp.status = falcon.HTTP_404
            return

        # FIXME: Need input validation.
        #        - Does the host exist at /commissaire/hosts/{IP}?
        #        - Does the host already belong to another cluster?

        # FIXME: Should guard against races here, since we're fetching
        #        the cluster record and writing it back with some parts
        #        unmodified.  Use either locking or a conditional write
        #        with the etcd 'modifiedIndex'.  Deferring for now.

        key = '/commissaire/clusters/{0}'.format(name)
        hostset = set(cluster.hostset)
        hostset.add(address)  # Ensures no duplicates
        cluster.hostset = list(hostset)
        self.store.set(key, cluster.to_json(secure=True))
        resp.status = falcon.HTTP_200

    def on_delete(self, req, resp, name, address):
        """
        Handles DELETE requests for individual hosts in a Cluster.
        This removes a single host from the cluster, idempotently.

        :param req: Request instance that will be passed through.
        :type req: falcon.Request
        :param resp: Response instance that will be passed through.
        :type resp: falcon.Response
        :param name: The name of the Cluster being requested.
        :type name: str
        :param address: The address of the Host being requested.
        :type address: str
        """
        cluster = self.get_cluster_model(name)
        if not cluster:
            resp.status = falcon.HTTP_404
            return

        # FIXME: Should guard against races here, since we're fetching
        #        the cluster record and writing it back with some parts
        #        unmodified.  Use either locking or a conditional write
        #        with the etcd 'modifiedIndex'.  Deferring for now.

        key = '/commissaire/clusters/{0}'.format(name)
        if address in cluster.hostset:
            cluster.hostset.remove(address)
            self.store.set(key, cluster.to_json(secure=True))
        resp.status = falcon.HTTP_200


class ClusterRestartResource(Resource):
    """
    Resource for initiating or querying a Cluster restart.
    """

    def on_get(self, req, resp, name):
        """
        Handles GET (or "status") requests for a Cluster restart.

        :param req: Request instance that will be passed through.
        :type req: falcon.Request
        :param resp: Response instance that will be passed through.
        :type resp: falcon.Response
        :param name: The name of the Cluster being restarted.
        :type name: str
        """
        cluster_key = '/commissaire/clusters/{0}'.format(name)
        key = '/commissaire/cluster/{0}/restart'.format(name)
        try:
            try:
                self.store.get(cluster_key)
            except etcd.EtcdKeyNotFound:
                resp.status = falcon.HTTP_404
                return
            status = self.store.get(key)
        except etcd.EtcdKeyNotFound:
            # Return "204 No Content" if we have no status,
            # meaning no restart is in progress.  The client
            # can't be expected to know that, so it's not a
            # client error (4xx).
            resp.status = falcon.HTTP_204
            return
        resp.status = falcon.HTTP_200
        req.context['model'] = ClusterRestart(**json.loads(status.value))

    def on_put(self, req, resp, name):
        """
        Handles PUT (or "initiate") requests for a Cluster restart.

        :param req: Request instance that will be passed through.
        :type req: falcon.Request
        :param resp: Response instance that will be passed through.
        :type resp: falcon.Response
        :param name: The name of the Cluster being restarted.
        :type name: str
        """
        POOLS['clusterexecpool'].spawn(
            clusterexec.clusterexec, name, 'restart', self.store)
        key = '/commissaire/cluster/{0}/restart'.format(name)
        cluster_restart_default = {
            'status': 'in_process',
            'restarted': [],
            'in_process': [],
            'started_at': datetime.datetime.utcnow().isoformat(),
            'finished_at': None
        }
        cluster_restart = ClusterRestart(**cluster_restart_default)
        self.store.set(key, cluster_restart.to_json())
        resp.status = falcon.HTTP_201
        req.context['model'] = cluster_restart


class ClusterUpgradeResource(Resource):
    """
    Resource for initiating or querying a Cluster upgrade.
    """

    def on_get(self, req, resp, name):
        """
        Handles GET (or "status") requests for a Cluster upgrade.

        :param req: Request instance that will be passed through.
        :type req: falcon.Request
        :param resp: Response instance that will be passed through.
        :type resp: falcon.Response
        :param name: The name of the Cluster being upgraded.
        :type name: str
        """
        cluster_key = '/commissaire/clusters/{0}'.format(name)
        key = '/commissaire/cluster/{0}/upgrade'.format(name)
        try:
            try:
                self.store.get(cluster_key)
            except etcd.EtcdKeyNotFound:
                resp.status = falcon.HTTP_404
                return
            status = self.store.get(key)
        except etcd.EtcdKeyNotFound:
            # Return "204 No Content" if we have no status,
            # meaning no upgrade is in progress.  The client
            # can't be expected to know that, so it's not a
            # client error (4xx).
            resp.status = falcon.HTTP_204
            return

        resp.status = falcon.HTTP_200
        req.context['model'] = ClusterUpgrade(**json.loads(status.value))

    def on_put(self, req, resp, name):
        """
        Handles PUT (or "initiate") requests for a Cluster upgrade.

        :param req: Request instance that will be passed through.
        :type req: falcon.Request
        :param resp: Response instance that will be passed through.
        :type resp: falcon.Response
        :param name: The name of the Cluster being upgraded.
        :type name: str
        """
        data = req.stream.read().decode()
        try:
            args = json.loads(data)
            upgrade_to = args['upgrade_to']
        except (KeyError, ValueError):
            resp.status = falcon.HTTP_400
            return
        # FIXME: How do I pass 'upgrade_to'?
        POOLS['clusterexecpool'].spawn(
            clusterexec.clusterexec, name, 'upgrade', self.store)
        key = '/commissaire/cluster/{0}/upgrade'.format(name)
        cluster_upgrade_default = {
            'status': 'in_process',
            'upgrade_to': upgrade_to,
            'upgraded': [],
            'in_process': [],
            'started_at': datetime.datetime.utcnow().isoformat(),
            'finished_at': None
        }
        cluster_upgrade = ClusterUpgrade(**cluster_upgrade_default)
        self.store.set(key, cluster_upgrade.to_json())
        resp.status = falcon.HTTP_201
        req.context['model'] = cluster_upgrade
