from ..dao import APIPermissionException
from ..types import Origin

PERMISSIONS = [
    {
        'rid': 'ro',
        'name': 'Read-Only',
    },
    {
        'rid': 'rw',
        'name': 'Read-Write',
    },
    {
        'rid': 'admin',
        'name': 'Admin',
    },
]

INTEGER_PERMISSIONS = {r['rid']: i for i, r in enumerate(PERMISSIONS)}

def _get_access(uid, container):
    permissions_list = container.get('permissions', [])
    for perm in permissions_list:
        if perm['_id'] == uid:
            return INTEGER_PERMISSIONS[perm['access']]
    return -1

def has_access(uid, container, perm):
    return _get_access(uid, container) >= INTEGER_PERMISSIONS[perm]

class APIAuthProviderException(Exception):
    pass

class APIUnknownUserException(Exception):
    pass

class APIRefreshTokenException(Exception):
    # Specifically alert a client when the user's refresh token expires
    # Requires client to ask for `offline=true` permission to receive a new one
    def __init__(self, msg):

        super(APIRefreshTokenException, self).__init__(msg)
        self.errors = {'core_status_code': 'invalid_refresh_token'}


def always_ok(exec_op):
    """
    This decorator leaves the original method unchanged.
    It is used as permissions checker when the request is a superuser_request
    """
    return exec_op

def require_login(handler_method):
    """
    A decorator to ensure the request is not a public request.

    Accepts superuser and non-superuser requests.
    Accepts drone and user requests.
    """
    def check_login(self, *args, **kwargs):
        if self.public_request:
            raise APIPermissionException('Login required.')
        return handler_method(self, *args, **kwargs)
    return check_login

def require_admin(handler_method):
    """
    A decorator to ensure the request is made as superuser.

    Accepts drone and user requests.
    """
    def check_admin(self, *args, **kwargs):
        if not self.user_is_admin:
            raise APIPermissionException('Admin user required.')
        return handler_method(self, *args, **kwargs)
    return check_admin

def require_superuser(handler_method):
    """
    A decorator to ensure the request is made as superuser.

    Accepts drone and user requests.
    """
    def check_superuser(self, *args, **kwargs):
        if not self.superuser_request:
            raise APIPermissionException('Superuser required.')
        return handler_method(self, *args, **kwargs)
    return check_superuser

def require_drone(handler_method):
    """
    A decorator to ensure the request is made as a drone.

    Will also ensure superuser, which is implied with a drone request.
    """
    def check_drone(self, *args, **kwargs):
        if self.origin.get('type', '') != Origin.device:
            raise APIPermissionException('Drone request required.')
        if not self.superuser_request:
            raise APIPermissionException('Superuser required.')
        return handler_method(self, *args, **kwargs)
    return check_drone
