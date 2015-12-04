import os
import cgi
import json
import shutil
import hashlib
import zipfile
import datetime

from . import util
from . import config

log = config.log


class FileStoreException(Exception):
    pass

class HashingFile(file):
    def __init__(self, file_path, hash_alg):
        super(HashingFile, self).__init__(file_path, "wb")
        self.hash_alg = hashlib.new(hash_alg)

    def write(self, data):
        self.hash_alg.update(data)
        return file.write(self, data)

    def get_hash(self):
        return self.hash_alg.hexdigest()




def getHashingFieldStorage(upload_dir, hash_alg):
    class HashingFieldStorage(cgi.FieldStorage):
        bufsize = 2**20
        def make_file(self, binary=None):
            self.open_file = HashingFile(os.path.join(upload_dir, self.filename), hash_alg)
            return self.open_file

        def get_hash(self):
            return self.open_file.get_hash()

    return HashingFieldStorage


class FileStore(object):
    """This class provides and interface for file uploads.
    To perform an upload the client of the class should follow these steps:

    1) initialize the request
    2) save a temporary file
    3) check identical
    4) move the temporary file to its destination

    The operations could be safely interleaved with other actions like permission checks or database updates.
    """

    def __init__(self, request, dest_path, filename=None, hash_alg='sha384'):
        self.client_addr = request.client_addr
        self.body = request.body_file
        self.environ = request.environ.copy()
        self.environ.setdefault('CONTENT_LENGTH', '0')
        self.environ['QUERY_STRING'] = ''
        self.hash_alg = hash_alg
        self.path = dest_path
        start_time = datetime.datetime.utcnow()
        if request.content_type == 'multipart/form-data':
            self._save_multipart_file(dest_path, hash_alg)
            self.payload = request.POST.mixed()
        else:
            self.payload = request.POST.mixed()
            self.filename = filename or self.payload.get('filename')
            self._save_body_file(dest_path, filename, hash_alg)
        self.duration = datetime.datetime.utcnow() - start_time
        self.mimetype = util.guess_mimetype(self.filename)
        self.filetype = util.guess_filetype(self.filename, self.mimetype)
        self.hash = self.received_file.get_hash()
        self.size = os.path.getsize(os.path.join(self.path, self.filename))

    def _save_multipart_file(self, dest_path, hash_alg):
        form = getHashingFieldStorage(dest_path, hash_alg)(fp=self.body, environ=self.environ, keep_blank_values=True)
        self.received_file = form['file'].file
        self.filename = form['file'].filename
        self.tags = json.loads(form['tags'].file.getvalue()) if 'tags' in form else None
        self.metadata = json.loads(form['metadata'].file.getvalue()) if 'metadata' in form else None

    def _save_body_file(self, dest_path, filename, hash_alg):
        if not filename:
            raise FileStoreException('filename is required for body uploads')
        self.filename = filename
        self.received_file = HashingFile(os.path.join(dest_path, filename), hash_alg)
        for chunk in iter(lambda: self.body.read(2**20), ''):
            self.received_file.write(chunk)
        self.tags = None
        self.metadata = None

    def move_file(self, target_path):
        target_filepath = target_path + '/' + self.filename
        filepath = self.path + '/' + self.filename
        if not os.path.exists(target_path):
            os.makedirs(target_path)
        shutil.move(filepath, target_filepath)
        self.path = target_path

    def identical(self, filepath, hash_):
        filepath1 = os.path.join(self.path, self.filename)
        if zipfile.is_zipfile(filepath) and zipfile.is_zipfile(filepath1):
            with zipfile.ZipFile(filepath) as zf1, zipfile.ZipFile(filepath1) as zf2:
                zf1_infolist = sorted(zf1.infolist(), key=lambda zi: zi.filename)
                zf2_infolist = sorted(zf2.infolist(), key=lambda zi: zi.filename)
                if zf1.comment != zf2.comment:
                    return False
                if len(zf1_infolist) != len(zf2_infolist):
                    return False
                for zii, zij in zip(zf1_infolist, zf2_infolist):
                    if zii.CRC != zij.CRC:
                        return False
                else:
                    return True
        else:
            return hash_ == self.hash
