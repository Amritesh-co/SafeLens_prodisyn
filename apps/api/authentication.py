from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import UserSession


class SessionTokenAuthentication(TokenAuthentication):
    """
    Authenticates requests using SafeLensAI per-session tokens.

    Each browser/device gets its own UserSession token.
    When that session is logged out or replaced by another login,
    the old token becomes invalid immediately.
    """

    def authenticate_credentials(self, key):
        session = (
            UserSession.objects
            .select_related("user")
            .filter(
                token=key,
                logout_time__isnull=True,
                user__is_active=True,
            )
            .first()
        )

        if not session:
            raise AuthenticationFailed(
                "Invalid or expired session."
            )

        return (session.user, session)