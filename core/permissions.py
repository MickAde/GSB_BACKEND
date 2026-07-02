from rest_framework.permissions import BasePermission


class IsStudent(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'STUDENT')


class IsTeacher(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'TEACHER')


class IsMainAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'MAIN_ADMIN')


class IsSubAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'SUB_ADMIN')


class IsAnyAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated
            and request.user.role in ('MAIN_ADMIN', 'SUB_ADMIN')
        )


class IsVisitor(BasePermission):
    message = 'Your free trial has expired. Please contact your school administrator.'

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated and request.user.role == 'VISITOR'):
            return False
        return request.user.is_visitor_trial_active


class IsSchoolMember(BasePermission):
    """Any user attached to a school (student, teacher, or admin)."""
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated
            and request.user.school_id is not None
        )


class IsSameSchool(BasePermission):
    """Object-level: the object's school_id must match the requesting user's school_id."""
    def has_object_permission(self, request, view, obj):
        return str(getattr(obj, 'school_id', None)) == str(request.user.school_id)


class IsPlatformOwner(BasePermission):
    """is_staff flag marks the platform owner / superuser — not a school-scoped role."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)
