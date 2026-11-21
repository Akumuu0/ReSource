"""Permission checks (design: AccessCheck interface and access matrix, Table 6-2).

Every service calls these checks on the server. Hiding a button in a page is
only for convenience; these functions are what really stop a user.
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def require_role(user, *roles):
    """Stop the action unless the user has one of the given roles."""
    if not user.is_authenticated or user.role not in roles:
        raise PermissionDenied("Your role is not allowed to do this.")


def require_department(user, department, message="This belongs to another department."):
    """Stop the action unless the user works in the given department."""
    if user.department_id != department.id:
        raise PermissionDenied(message)


def role_required(*roles):
    """View decorator: the user must be signed in and have one of the roles."""

    def decorator(view_function):
        @login_required
        @wraps(view_function)
        def wrapper(request, *args, **kwargs):
            require_role(request.user, *roles)
            return view_function(request, *args, **kwargs)

        return wrapper

    return decorator
