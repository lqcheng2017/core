# @author:  Renzo Frigato

import datetime
import logging
import base
import json
import util
import copy
import os

from . import validators
from . import listauth
from . import files
from dao import mongostorage

log = logging.getLogger('scitran.api')


def initialize_list_configurations():
    container_default_configurations = {
        'tags': {
            'storage': mongostorage.StringListStorage,
            'permchecker': listauth.default_sublist,
            'use_oid': True,
        },
        'files': {
            'storage': mongostorage.ListStorage,
            'permchecker': listauth.default_sublist,
            'use_oid': True,
            'key_fields': ['filename']
        },
        'permissions': {
            'storage': mongostorage.ListStorage,
            'permchecker': listauth.permissions_sublist,
            'use_oid': True,
            'key_fields': ['_id', 'site'],
            'schema_file': 'permission.json'
        },
        'notes': {
            'storage': mongostorage.ListStorage,
            'permchecker': listauth.notes_sublist,
            'use_oid': True,
            'key_fields': ['_id'],
            'check_item_perms': True
        },
    }
    list_handler_configurations = {
        'groups': {
            'roles':{
                'storage': mongostorage.ListStorage,
                'permchecker': listauth.group_roles_sublist,
                'use_oid': False,
                'key_fields': ['_id']
            }
        },
        'projects': copy.deepcopy(container_default_configurations),
        'sessions': copy.deepcopy(container_default_configurations),
        'acquisitions': copy.deepcopy(container_default_configurations),
        'collections': copy.deepcopy(container_default_configurations)
    }
    # preload the Storage instances for all configurations
    for coll_name, coll_config in list_handler_configurations.iteritems():
        for list_name, list_config in coll_config.iteritems():
            storage_class = list_config['storage']
            storage = storage_class(
                coll_name,
                list_name,
                use_oid=list_config.get('use_oid', False),
                key_fields=list_config.get('key_fields')
            )
            list_config['storage'] = storage
    return list_handler_configurations


list_handler_configurations = initialize_list_configurations()


class ListHandler(base.RequestHandler):
    """
    This class handle operations on a generic sublist of a container like tags, group roles, user permissions, etc.

    The pattern used is:
    1) initialize request
    2) exec request
    3) check and return result

    Specific behaviors (permissions checking logic for authenticated and not superuser users, storage interaction)
    are specified in the routes defined in api.py
    """

    def __init__(self, request=None, response=None):
        super(ListHandler, self).__init__(request, response)
        self._initialized = None

    def get(self, coll_name, list_name, **kwargs):
        _id = kwargs.pop('cid')
        container, permchecker, storage, _, keycheck = self._initialize_request(coll_name, list_name, _id, query_params=kwargs)

        result = keycheck(permchecker(storage.exec_op))('GET', _id, query_params=kwargs)

        if result is None:
            self.abort(404, 'Element not found in list {} of collection {} {}'.format(storage.list_name, storage.coll_name, _id))
        return result

    def post(self, coll_name, list_name, **kwargs):
        _id = kwargs.pop('cid')
        container, permchecker, storage, validator, keycheck = self._initialize_request(coll_name, list_name, _id)

        payload = self.request.POST.mixed()
        payload.update(kwargs)
        result = keycheck(validator(permchecker(storage.exec_op)))('POST', _id, payload=payload)

        if result.modified_count == 1:
            return {'modified':result.modified_count}
        else:
            self.abort(404, 'Element not added in list {} of collection {} {}'.format(storage.list_name, storage.coll_name, _id))

    def put(self, coll_name, list_name, **kwargs):
        _id = kwargs.pop('cid')
        container, permchecker, storage, validator, keycheck = self._initialize_request(coll_name, list_name, _id, query_params=kwargs)

        result = keycheck(validator(permchecker(storage.exec_op)))('PUT', _id, query_params=kwargs, payload=self.request.POST.mixed())

        if result.modified_count == 1:
            return {'modified':result.modified_count}
        else:
            self.abort(404, 'Element not updated in list {} of collection {} {}'.format(storage.list_name, storage.coll_name, _id))

    def delete(self, coll_name, list_name, **kwargs):
        _id = kwargs.pop('cid')
        container, permchecker, storage, _, keycheck = self._initialize_request(coll_name, list_name, _id, query_params=kwargs)
        result = keycheck(permchecker(storage.exec_op))('DELETE', _id, query_params=kwargs)

        if result.modified_count == 1:
            return {'modified': result.modified_count}
        else:
            self.abort(404, 'Element not removed from list {} in collection {} {}'.format(storage.list_name, storage.coll_name, _id))

    def _initialize_request(self, coll_name, list_name, _id, query_params=None):
        """
        This method loads:
        1) the container that will be modified
        2) the storage class that will handle the database actions
        3) the permission checker decorator that will be used
        """
        config = list_handler_configurations[coll_name][list_name]
        storage = config['storage']
        permchecker = config['permchecker']
        storage.dbc = self.app.db[storage.coll_name]
        if not config.get('check_item_perms'):
            query_params = None
        container = storage.get_container(_id, query_params)
        if container is not None:
            if self.superuser_request:
                permchecker = listauth.always_ok
            elif self.public_request:
                permchecker = listauth.public_request(self, container)
            else:
                permchecker = permchecker(self, container)
        else:
            self.abort(404, 'Element {} not found in collection {}'.format(_id, storage.coll_name))
        validator = validators.from_schema_file(self, config.get('schema_file'))
        keycheck = validators.key_check(self, config.get('schema_file'))
        return container, permchecker, storage, validator, keycheck

class NotesListHandler(ListHandler):
    def post(self, coll_name, list_name, **kwargs):
        _id = kwargs.pop('cid')
        container, permchecker, storage, validator, keycheck = self._initialize_request(coll_name, list_name, _id)

        payload = self.request.POST.mixed()
        payload['_id'] = payload.get('_id') or str(bson.objectid.ObjectId())
        payload['timestamp'] =  payload.get('timestamp') or datetime.datetime.utcnow()
        result = keycheck(validator(permchecker(storage.exec_op)))('POST', _id, payload=payload)

        if result.modified_count == 1:
            return {'modified':result.modified_count}
        else:
            self.abort(404, 'Element not added in list {} of collection {} {}'.format(storage.list_name, storage.coll_name, _id))


class FileListHandler(ListHandler):
    """
    This class implements a more specific logic for list of files as the api needs to interact with the filesystem.
    """

    def __init__(self, request=None, response=None):
        super(FileListHandler, self).__init__(request, response)

    def _check_ticket(self, ticket_id, _id, filename):
        ticket = self.app.db.downloads.find_one({'_id': ticket_id})
        if not ticket:
            self.abort(404, 'no such ticket')
        if ticket['target'] != _id or ticket['filename'] != filename or ticket['ip'] != self.request.client_addr:
            self.abort(400, 'ticket not for this resource or source IP')
        return ticket

    def get(self, coll_name, list_name, **kwargs):
        _id = kwargs.pop('cid')
        container, permchecker, storage = self._initialize_request(coll_name, list_name, _id)
        list_name = storage.list_name
        filename = kwargs.get('filename')
        ticket_id = self.request.GET.get('ticket')
        if ticket_id:
            ticket = self._check_ticket(ticket_id, _id, filename)
            fileinfo = storage.exec_op('GET', _id, query_params=kwargs)
        else:
            fileinfo = permchecker(storage.exec_op)('GET', _id, query_params=kwargs)
        if not fileinfo:
            self.abort(404, 'no such file')
        hash_ = self.request.GET.get('hash')
        if hash_ and hash_ != fileinfo['hash']:
            self.abort(409, 'file exists, hash mismatch')
        filepath = os.path.join(self.app.config['data_path'], str(_id)[-3:] + '/' + str(_id), filename)
        if self.request.GET.get('ticket') == '':    # request for download ticket
            ticket = util.download_ticket(self.request.client_addr, 'file', _id, filename, fileinfo['filesize'])
            return {'ticket': self.app.db.downloads.insert_one(ticket).inserted_id}
        else:                                       # authenticated or ticketed (unauthenticated) download
            zip_member = self.request.GET.get('member')
            if self.request.GET.get('info', '').lower() in ('1', 'true'):
                try:
                    with zipfile.ZipFile(filepath) as zf:
                        return [(zi.filename, zi.file_size, datetime.datetime(*zi.date_time)) for zi in zf.infolist()]
                except zipfile.BadZipfile:
                    self.abort(400, 'not a zip file')
            elif self.request.GET.get('comment', '').lower() in ('1', 'true'):
                try:
                    with zipfile.ZipFile(filepath) as zf:
                        self.response.write(zf.comment)
                except zipfile.BadZipfile:
                    self.abort(400, 'not a zip file')
            elif zip_member:
                try:
                    with zipfile.ZipFile(filepath) as zf:
                        self.response.headers['Content-Type'] = util.guess_mimetype(zip_member)
                        self.response.write(zf.open(zip_member).read())
                except zipfile.BadZipfile:
                    self.abort(400, 'not a zip file')
                except KeyError:
                    self.abort(400, 'zip file contains no such member')
            else:
                self.response.app_iter = open(filepath, 'rb')
                self.response.headers['Content-Length'] = str(fileinfo['filesize']) # must be set after setting app_iter
                if self.request.GET.get('view', '').lower() in ('1', 'true'):
                    self.response.headers['Content-Type'] = str(fileinfo.get('mimetype', 'application/octet-stream'))
                else:
                    self.response.headers['Content-Type'] = 'application/octet-stream'
                    self.response.headers['Content-Disposition'] = 'attachment; filename="' + filename + '"'

    def delete(self, coll_name, list_name, **kwargs):
        filename = kwargs.get('filename')
        _id = kwargs.get('cid')
        result = super(FileListHandler, self).delete(coll_name, list_name, **kwargs)
        filepath = os.path.join(self.app.config['data_path'], str(_id)[-3:] + '/' + str(_id), filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            log.info('removed file ' + filepath)
            result['removed'] = 1
        else:
            log.warning(filepath + ' does not exist')
            result['removed'] = 0
        return result

    def put(self, coll_name, list_name, **kwargs):
        fileinfo = super(FileListHandler, self).get(coll_name, list_name, **kwargs)
        # TODO: implement file metadata updates
        self.abort(400, 'PUT is not yet implemented')

    def post(self, coll_name, list_name, **kwargs):
        force = self.request.GET.get('force', '').lower() in ('1', 'true')
        _id = kwargs.pop('cid')
        container, permchecker, storage = self._initialize_request(coll_name, list_name, _id)
        payload = self.request.POST.mixed()
        payload.update(kwargs)
        filename = payload.get('filename')
        file_request = files.FileRequest.from_handler(self, filename)
        file_request.save_temp_file(self.app.config['upload_path'])
        file_datetime = datetime.datetime.utcnow()
        payload.update({
            'filesize': file_request.filesize,
            'filehash': file_request.sha1,
            'filetype': file_request.filetype,
            'flavor': file_request.flavor,
            'mimetype': file_request.mimetype,
            'tags': file_request.tags,
            'metadata': file_request.metadata,
            'created': file_datetime,
            'modified': file_datetime,
            'dirty': True
        })
        dest_path = os.path.join(self.app.config['data_path'], str(_id)[-3:] + '/' + str(_id))
        if not force:
            result = permchecker(storage.exec_op)('POST', _id, payload=payload)
        else:
            filepath = os.path.join(tempdir_path, filename)
            for f in container['files']:
                if f['filename'] == filename:
                    if file_request.identical(os.path.join(data_path, filename), f['filehash']):
                        log.debug('Dropping    %s (identical)' % filename)
                        os.remove(filepath)
                        self.abort(409, 'file exists; use force to overwrite')
                    else:
                        log.debug('Replacing   %s' % filename)
                        result = permchecker(storage.exec_op)('PUT', _id, payload=payload)
                    break
            else:
                result = permchecker(storage.exec_op)('POST', _id, payload=payload)
        if result.modified_count != 1:
            storage.exec_op('DELETE', _id, payload=payload)
            self.abort(404, 'Element not added in list {} of collection {} {}'.format(storage.list_name, storage.coll_name, _id))
        try:
            file_request.move_temp_file(dest_path)
        except IOError as e:
            result = storage.exec_op('DELETE', _id, payload=payload)
            raise e
        return {'modified': result.modified_count}
