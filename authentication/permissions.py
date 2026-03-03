from rest_framework import permissions


class IsStudent(permissions.BasePermission):
    """
    Permission to only allow students to access the view
    """
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.role == 'student'
        )


class IsTeacher(permissions.BasePermission):
    """
    Permission to only allow teachers to access the view
    """
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.role == 'teacher'
        )


class IsAdmin(permissions.BasePermission):
    """
    Permission to only allow admins (operators or superusers) to access the view
    Note: School admins are handled in schools app permissions
    """
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            (request.user.role == 'operator' or request.user.is_superuser)
        )


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Permission to only allow owners of an object or admins to access it
    Note: School-specific ownership handled in schools app
    """
    def has_object_permission(self, request, view, obj):
        # Admins can access anything
        if request.user.role == 'operator' or request.user.is_superuser:
            return True
        
        # Check if object has a 'user' attribute
        if hasattr(obj, 'user'):
            return obj.user == request.user
        
        # If object is a User instance
        if obj.__class__.__name__ == 'User':
            return obj == request.user
        
        return False


class IsVerified(permissions.BasePermission):
    """
    Permission to only allow verified users
    """
    message = "Your email must be verified to perform this action."
    
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.is_verified
        )


class IsEnterpriseUser(permissions.BasePermission):
    """
    Permission to only allow enterprise users
    """
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.user_type == 'enterprise'
        )


class IsOrganisationMember(permissions.BasePermission):
    """
    Permission to only allow users who belong to an organisation
    """
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.organisation is not None
        )


class IsTrialActive(permissions.BasePermission):
    """
    Permission to only allow users with active trial
    """
    message = "Your trial has expired."
    
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.is_trial_active()
        )




class ReadOnly(permissions.BasePermission):
    """
    Permission to only allow read-only access (GET, HEAD, OPTIONS)
    """
    def has_permission(self, request, view):
        return request.method in permissions.SAFE_METHODS


# ============================================================================
# SSO-SPECIFIC PERMISSIONS
# ============================================================================

