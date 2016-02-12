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
Host(s) handlers.

"""
import falcon
import etcd
import json

from commissaire.queues import INVESTIGATE_QUEUE
from commissaire.resource import Resource
from commissaire.handlers.models import Cluster, Host, Hosts


class HostsResource(Resource):
    """
    Resource for working with Hosts.
    """

    def on_get(self, req, resp):
        """
        Handles GET requests for Hosts.

        :param req: Request instance that will be passed through.
        :type req: falcon.Request
        :param resp: Response instance that will be passed through.
        :type resp: falcon.Response
        """
        try:
            hosts_dir = self.store.get('/commissaire/hosts/')
        except etcd.EtcdKeyNotFound:
            self.logger.warn(
                'Etcd does not have any hosts. Returning [] and 404.')
            resp.status = falcon.HTTP_404
            req.context['model'] = None
            return
        results = []
        # Don't let an empty host directory through
        if len(hosts_dir._children):
            for host in hosts_dir.leaves:
                results.append(Host(**json.loads(host.value)))
            resp.status = falcon.HTTP_200
            req.context['model'] = Hosts(hosts=results)
        else:
            self.logger.debug(
                'Etcd has a hosts directory but no content.')
            resp.status = falcon.HTTP_200
            req.context['model'] = None


class HostResource(Resource):
    """
    Resource for working with a single Host.
    """

    def on_get(self, req, resp, address):
        """
        Handles retrieval of an existing Host.

        :param req: Request instance that will be passed through.
        :type req: falcon.Request
        :param resp: Response instance that will be passed through.
        :type resp: falcon.Response
        :param address: The address of the Host being requested.
        :type address: str
        """
        # TODO: Verify input
        try:
            host = self.store.get('/commissaire/hosts/{0}'.format(address))
        except etcd.EtcdKeyNotFound:
            resp.status = falcon.HTTP_404
            return

        resp.status = falcon.HTTP_200
        host.address = address
        req.context['model'] = Host(**json.loads(host.value))

    def on_put(self, req, resp, address):
        """
        Handles the creation of a new Host.

        :param req: Request instance that will be passed through.
        :type req: falcon.Request
        :param resp: Response instance that will be passed through.
        :type resp: falcon.Response
        :param address: The address of the Host being requested.
        :type address: str
        """
        # TODO: Verify input
        try:
            host = self.store.get('/commissaire/hosts/{0}'.format(address))
            resp.status = falcon.HTTP_409
            return
        except etcd.EtcdKeyNotFound:
            pass

        data = req.stream.read().decode()
        host_creation = json.loads(data)
        ssh_priv_key = host_creation['ssh_priv_key']
        host_creation['address'] = address
        host_creation['os'] = ''
        host_creation['status'] = 'investigating'
        host_creation['cpus'] = -1
        host_creation['memory'] = -1
        host_creation['space'] = -1
        host_creation['last_check'] = None

        # Don't store the cluster name in etcd.
        cluster_name = host_creation.pop('cluster', None)

        # Verify the cluster exists, if given.  Do it now
        # so we can fail before writing anything to etcd.
        if cluster_name:
            # XXX: Based on ClusterSingleHostResource.on_put().
            #      Add a util module to share common operations.
            cluster_key = '/commissaire/clusters/{0}'.format(cluster_name)
            try:
                etcd_resp = self.store.get(cluster_key)
                self.logger.info(
                    'Request for cluster {0}'.format(cluster_name))
                self.logger.debug('{0}'.format(etcd_resp))
            except etcd.EtcdKeyNotFound:
                self.logger.info(
                    'Request for non-existent cluster {0}.'.format(
                        cluster_name))
                resp.status = falcon.HTTP_409
                return
            cluster = Cluster(**json.loads(etcd_resp.value))
            hostset = set(cluster.hostset)
            hostset.add(address)  # Ensures no duplicates
            cluster.hostset = list(hostset)

        host = Host(**host_creation)
        new_host = self.store.set(
            '/commissaire/hosts/{0}'.format(
                address), host.to_json(secure=True))
        INVESTIGATE_QUEUE.put((host_creation, ssh_priv_key))

        # Add host to the requested cluster.
        if cluster_name:
            # FIXME: Should guard against races here, since we're fetching
            #        the cluster record and writing it back with some parts
            #        unmodified.  Use either locking or a conditional write
            #        with the etcd 'modifiedIndex'.  Deferring for now.
            self.store.set(cluster_key, cluster.to_json(secure=True))

        resp.status = falcon.HTTP_201
        req.context['model'] = Host(**json.loads(new_host.value))

    def on_delete(self, req, resp, address):
        """
        Handles the Deletion of a Host.

        :param req: Request instance that will be passed through.
        :type req: falcon.Request
        :param resp: Response instance that will be passed through.
        :type resp: falcon.Response
        :param address: The address of the Host being requested.
        :type address: str
        """
        resp.body = '{}'
        try:
            host = self.store.delete(
                '/commissaire/hosts/{0}'.format(address))
            resp.status = falcon.HTTP_410
        except etcd.EtcdKeyNotFound:
            resp.status = falcon.HTTP_404

        # Also remove the host from all clusters.
        # Note: We've done all we need to for the host deletion,
        #       so if an error occurs from here just log it and
        #       return.
        try:
            clusters_dir = self.store.get('/commissaire/clusters')
        except etcd.EtcdKeyNotFound:
            self.logger.warn('Etcd does not have any clusters')
            return
        if len(clusters_dir._children):
            for etcd_resp in clusters_dir.leaves:
                cluster = Cluster(**json.loads(etcd_resp.value))
                if address in cluster.hostset:
                    cluster.hostset.remove(address)
                    self.store.set(etcd_resp.key, cluster.to_json(secure=True))
