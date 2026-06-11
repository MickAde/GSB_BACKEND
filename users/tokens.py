from rest_framework_simplejwt.tokens import RefreshToken


def get_tokens_for_user(user):
    """
    Issues a JWT pair with the routing context embedded in the access token.
    school_id and role are read by TenantMiddleware on every subsequent request,
    avoiding a DB lookup per API call.
    """
    refresh = RefreshToken.for_user(user)

    refresh['role']     = user.role
    refresh['school_id'] = str(user.school_id) if user.school_id else None
    refresh['is_staff']  = user.is_staff

    return {
        'access': str(refresh.access_token),
        'refresh': str(refresh),
    }
