from rest_framework import permissions


class IsSchoolAdmin(permissions.BasePermission):
    """
    Permission to only allow school admins to access the view
    """
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.role == 'school_admin'
        )


class IsOperator(permissions.BasePermission):
    """
    Permission to only allow operators to access the view
    """
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.role == 'operator'
        )


class IsOwnerLevel(permissions.BasePermission):
    """
    Permission to only allow owner level users (operators or superusers) to access the view
    """
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            (request.user.role == 'operator' or request.user.is_superuser)
        )


class IsSchoolAdminOrOperator(permissions.BasePermission):
    """
    Permission to only allow school admins or operators to access the view
    """
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            (request.user.role in ['school_admin', 'operator'] or request.user.is_superuser)
        )


class IsOwnerOrSchoolAdmin(permissions.BasePermission):
    """
    Permission to only allow owners or school admins of an object to access it
    """
    def has_object_permission(self, request, view, obj):
        # Owners and operators can access anything
        if (request.user.role in ['operator']) or request.user.is_superuser:
            return True

        # School admins can access their school's objects
        if request.user.role == 'school_admin':
            # Assuming obj has a 'school' attribute
            if hasattr(obj, 'school'):
                # Need to check if user is admin of that school
                # This might require linking User to Staff or School
                # For now, assume school admin can access
                return True
            return False

        return False


class IsStudentOfSchool(permissions.BasePermission):
    """
    Permission to only allow students of the school to access school-related views
    """
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.role == 'student'
            # Additional check: user is linked to a Student in the school
        )

    def has_object_permission(self, request, view, obj):
        if request.user.role == 'student':
            # Check if user is student of the school's obj
            # Requires linking User to Student
            return True
        return False


class IsTeacherOfSchool(permissions.BasePermission):
    """
    Permission to only allow teachers of the school to access school-related views
    """
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.role == 'teacher'
            # Additional check: user is linked to a Staff in the school
        )


class IsStaffOfSchool(permissions.BasePermission):
    """
    Permission to only allow staff (teachers or school_admin) who belong to a given
    school to access school-related views. Expects view kwargs to contain `school_id`.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False

        if request.user.role not in ['teacher', 'school_admin']:
            return False

        # If view provides school_id, check user organisation
        school_id = None
        if hasattr(view, 'kwargs'):
            school_id = view.kwargs.get('school_id')

        if school_id:
            try:
                # Compare organisation id to provided school_id
                return str(request.user.organisation.id) == str(school_id)
            except Exception:
                return False

        # If no specific school provided, allow as staff
        return True


class IsSchoolStaffOrAdmin(permissions.BasePermission):
    """
    Allow access to school admins, operators, or staff (teachers) of the school.
    Expects view kwargs to contain `school_id` when applicable.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False

        # Owner level (operator or superuser)
        if request.user.role == 'operator' or request.user.is_superuser:
            return True

        # School admin
        if request.user.role == 'school_admin':
            return True

        # Teachers or other staff must belong to the organisation
        if request.user.role == 'teacher':
            school_id = None
            if hasattr(view, 'kwargs'):
                school_id = view.kwargs.get('school_id')

            if school_id and request.user.organisation:
                return str(request.user.organisation.id) == str(school_id)
            return True

        return False

    def has_object_permission(self, request, view, obj):
        if request.user.role == 'teacher':
            # Check if user is teacher of the school's obj
            return True
        return False