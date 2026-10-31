from rest_framework.permissions import BasePermission, SAFE_METHODS

class IsAdminRole(BasePermission):
    """Allow only a Brightloop admin (or Django superuser)."""
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_superuser or getattr(user, "role", None) == "ADMIN"))

class IsStaffOrAdmin(BasePermission):
    """Allow internal staff and admins."""
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_superuser or getattr(user, "role", None) in {"ADMIN", "STAFF"}))

class ReadOnlyOrAdmin(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        user = request.user
        return bool(user and user.is_authenticated and (user.is_superuser or getattr(user, "role", None) == "ADMIN"))
