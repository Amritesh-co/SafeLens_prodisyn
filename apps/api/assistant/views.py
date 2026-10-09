"""
POST /api/assistant/ask/

Request:
    {"question": "How many falls last week?",
     "history": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}

Response:
    {"answer": "...", "status": "ok", "sources": [...], "model": "gemma4:31b"}
"""

import logging
import os
from datetime import timedelta

from django.utils import timezone
from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.models import AssistantQueryLog

from . import agent, guardrails, llm
from .tools import Scope

logger = logging.getLogger(__name__)


def _enabled():
    return os.environ.get('ASSISTANT_ENABLED', 'True').strip().lower() in ('1', 'true', 'yes')


def _rate_limit():
    return int(os.environ.get('ASSISTANT_RATE_LIMIT_PER_HOUR', '30'))


class AssistantAskView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not _enabled():
            return Response({'detail': 'The assistant is disabled.'}, status=http_status.HTTP_503_SERVICE_UNAVAILABLE)

        user = request.user
        scope = Scope(user)
        if not scope.is_valid:
            return Response(
                {'detail': 'Your account is not linked to a tenant/role, so the assistant has no data to use.'},
                status=http_status.HTTP_403_FORBIDDEN,
            )

        raw_question = request.data.get('question')
        log = AssistantQueryLog(
            user=user,
            tenant=scope.tenant,
            question=str(raw_question or '')[:guardrails.MAX_QUESTION_CHARS * 2],
            model_name=llm.model_name(),
        )

        # Rate limit (counted from the audit log; no cache dependency).
        window_start = timezone.now() - timedelta(hours=1)
        recent = AssistantQueryLog.objects.filter(user=user, created_at__gte=window_start).exclude(status='rate_limited').count()
        if recent >= _rate_limit():
            log.status = 'rate_limited'
            log.save()
            return Response(
                {'detail': 'Too many assistant questions. Please try again later.'},
                status=http_status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Input guardrails
        try:
            question = guardrails.check_question(raw_question)
            history = guardrails.clean_history(request.data.get('history'))
        except guardrails.GuardrailViolation as exc:
            log.status = 'blocked'
            log.block_reason = exc.reason[:255]
            log.answer = exc.user_message
            log.save()
            return Response({'answer': exc.user_message, 'status': 'blocked', 'sources': []}, status=http_status.HTTP_200_OK)

        # Agent
        try:
            result = agent.run(scope, question, history)
        except llm.LLMError as exc:
            logger.warning("Assistant LLM error: %s", exc)
            log.status = 'error'
            log.block_reason = str(exc)[:255]
            log.save()
            return Response(
                {'detail': 'The assistant is temporarily unavailable. Please try again.'},
                status=http_status.HTTP_502_BAD_GATEWAY,
            )

        log.status = result['status']
        log.answer = result['answer']
        log.tool_calls = result['sources']
        log.latency_ms = result['latency_ms']
        log.save()

        return Response({
            'answer': result['answer'],
            'status': result['status'],
            'sources': [
                {'tool': s['tool'], 'arguments': s['arguments'], 'ok': s.get('ok', False)}
                for s in result['sources']
            ],
            'snapshots': result.get('snapshots', []),
            'model': log.model_name,
        })


# ---------------------------------------------------------------------------
# Dev playground: /assistant/  (only served when DEBUG=True)
# ---------------------------------------------------------------------------

from django.conf import settings
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.http import Http404
from django.views.generic import TemplateView

from .tools import _with_status

PLAYGROUND_LOGIN_URL = '/assistant/login/'


class DebugOnlyMixin:
    def dispatch(self, request, *args, **kwargs):
        if not settings.DEBUG:
            raise Http404()
        return super().dispatch(request, *args, **kwargs)


class AssistantLoginView(DebugOnlyMixin, auth_views.LoginView):
    template_name = 'api/assistant_login.html'
    redirect_authenticated_user = True
    next_page = '/assistant/'

    def get_default_redirect_url(self):
        return '/assistant/'


class AssistantLogoutView(DebugOnlyMixin, auth_views.LogoutView):
    next_page = PLAYGROUND_LOGIN_URL


class AssistantPlaygroundView(DebugOnlyMixin, LoginRequiredMixin, TemplateView):
    template_name = 'api/assistant_playground.html'
    login_url = PLAYGROUND_LOGIN_URL

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        scope = Scope(self.request.user)
        ctx['scope_valid'] = scope.is_valid
        ctx['role'] = scope.role
        ctx['tenant'] = scope.tenant
        ctx['model'] = llm.model_name()
        if not scope.is_valid:
            return ctx

        events = _with_status(scope.events()).select_related('camera__location')
        ctx['total_incidents'] = events.count()
        ctx['by_type'] = events.values('event_type').annotate(n=Count('event_id')).order_by('-n')
        ctx['by_status'] = events.values('review_status').annotate(n=Count('event_id')).order_by('-n')
        ctx['by_location'] = (
            events.values('camera__location__name').annotate(n=Count('event_id')).order_by('-n')
        )
        ctx['cameras'] = scope.cameras().select_related('location').order_by('location__name', 'name')
        ctx['incidents'] = events.order_by('-timestamp')[:100]
        first = events.order_by('timestamp').first()
        last = events.order_by('-timestamp').first()
        ctx['date_from'] = first.timestamp if first else None
        ctx['date_to'] = last.timestamp if last else None
        return ctx
