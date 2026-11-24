import asyncio
import json
import logging
from functools import wraps
from time import sleep
from uuid import UUID

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.exceptions import PermissionDenied, RequestDataTooBig
from django.core.handlers.asgi import ASGIRequest
from django.http import Http404, HttpResponseNotAllowed, JsonResponse, StreamingHttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from psycopg import Error as PostgresError

from companies.models import CompanyUser
from orchestrator.graph.checkpoints import ThreadBusy
from orchestrator.graph.console_contract import execution_state, history
from orchestrator.graph.console_runtime import console_services
from orchestrator.graph.console_isolation import ConsoleIsolationError
from orchestrator.graph.conversations import ConversationConflict


logger = logging.getLogger(__name__)


def error(code, status):
    return JsonResponse({'error': {'code': code}}, status=status)


def developer(*methods, page=False):
    def decorate(view):
        @wraps(view)
        @never_cache
        @csrf_protect
        def wrapped(request, *args, **kwargs):
            if not settings.AGENTIX_SUPERVISOR_CONSOLE_ENABLED:
                raise Http404
            if request.method not in methods:
                return HttpResponseNotAllowed(methods)
            if not request.user.is_authenticated:
                if page:
                    return redirect('admin:login')
                return error('authentication_required', 401)
            if not request.user.is_active or not request.user.is_staff:
                return error('developer_access_required', 403)

            membership = CompanyUser.objects.filter(
                user=request.user, user__is_active=True, user__is_staff=True,
            )
            selected = request.session.get('agentix_supervisor_company_id')
            if selected is not None:
                membership = membership.filter(company_id=selected)
            company_id = membership.order_by('company_id').values_list('company_id', flat=True).first()
            if company_id is None:
                return error('company_membership_required', 403)
            try:
                return view(request, company_id, *args, **kwargs)
            except PermissionDenied:
                return error('scope_denied', 403)
            except (ConversationConflict, ThreadBusy):
                return error('execution_conflict', 409)
            except (ValueError, RequestDataTooBig):
                return error('invalid_request', 400)
            except ConsoleIsolationError:
                return error('test_database_required', 503)
            except PostgresError:
                return error('storage_unavailable', 503)
            except Exception as exc:
                logger.error('Supervisor console request failed (%s)', type(exc).__name__)
                return error('console_failed', 500)
        return wrapped
    return decorate


def body(request, *, required=(), optional=()):
    if request.content_type != 'application/json' or len(request.body) > 20000:
        raise ValueError
    values = json.loads(request.body)
    if (not isinstance(values, dict) or not set(required) <= values.keys()
            or values.keys() - set(required) - set(optional)):
        raise ValueError
    return values


def mode():
    return settings.AGENTIX_SUPERVISOR_CONSOLE_MODE


def require_owner(journal, thread, request, company_id):
    if len(thread) > 300 or not journal.owns(thread, request.user.pk, company_id, mode()):
        raise PermissionDenied


@developer('GET', page=True)
@ensure_csrf_cookie
def console(request, company_id):
    return render(request, 'orchestrator/supervisor_console.html', {
        'mode': mode(),
        'test_writes': mode() == 'real' and settings.AGENTIX_SUPERVISOR_CONSOLE_TEST_WRITES,
    })


@developer('GET', 'POST')
def conversations(request, company_id):
    with console_services() as (service, journal):
        if request.method == 'GET':
            return JsonResponse({'conversations': journal.list(request.user.pk, company_id, mode()),
                                 'mode': mode()})
        body(request)
        thread = service.create_thread(request.user, company_id)
        journal.create(thread, request.user.pk, company_id, mode())
        return JsonResponse({'thread': thread, 'mode': mode()}, status=201)


@developer('GET', 'POST')
def messages(request, company_id, thread):
    with console_services() as (service, journal):
        require_owner(journal, thread, request, company_id)
        if request.method == 'GET':
            state, _ = service.read_state(thread, request.user, company_id)
            return JsonResponse({'messages': history(state)})
        payload = body(request, required=('message', 'request_id'), optional=('project_id',))
        if not isinstance(payload['request_id'], str):
            raise ValueError
        execution_id = UUID(payload['request_id']).hex
        project_id = payload.get('project_id')
        if project_id is not None and (type(project_id) is not int or not 0 < project_id < 2**63):
            raise ValueError

        def claim(identifier, *, check_only):
            if check_only:
                return journal.acknowledged(thread, identifier)
            journal.append(thread, {'type': 'submission_accepted', 'execution_id': identifier})

        service.turn(
            thread, request.user, company_id, payload['message'], project_id=project_id,
            execution_id=execution_id, claim=claim, events=lambda event: journal.append(thread, event),
        )
        return JsonResponse({'execution_id': execution_id})


@developer('GET')
def execution(request, company_id, thread):
    with console_services() as (service, journal):
        require_owner(journal, thread, request, company_id)
        state, active = service.read_state(thread, request.user, company_id)
        return JsonResponse(execution_state(state, active, mode()))


@developer('POST')
def approval(request, company_id, thread):
    payload = body(request, required=('approval_id', 'execution_id', 'approved'))
    with console_services() as (service, journal):
        require_owner(journal, thread, request, company_id)
        service.resume(thread, request.user, company_id, **payload,
                       events=lambda event: journal.append(thread, event))
    return JsonResponse({'execution_id': payload['execution_id']})


@developer('GET')
def events(request, company_id, thread):
    cursor = int(request.headers.get('Last-Event-ID') or request.GET.get('after', '0'))
    if not 0 <= cursor < 2**63:
        raise ValueError
    with console_services(journal_only=True) as (_, journal):
        require_owner(journal, thread, request, company_id)

    def poll(last_id):
        active = CompanyUser.objects.filter(
            user_id=request.user.pk, user__is_staff=True, user__is_active=True, company_id=company_id,
        ).exists()
        if not active:
            return None
        with console_services(journal_only=True) as (_, journal):
            if not journal.owns(thread, request.user.pk, company_id, mode()):
                return None
            return journal.after(thread, last_id)

    def frames(rows):
        for row in rows:
            yield f"id: {row['id']}\ndata: {json.dumps(row['event'], ensure_ascii=True)}\n\n"

    def stream_sync():
        last_id = cursor
        yield ': connected\n\n'
        for _ in range(25):
            rows = poll(last_id)
            if rows is None:
                return
            yield from frames(rows)
            if rows:
                last_id = rows[-1]['id']
            if len(rows) < 100:
                sleep(1)
            yield ': keepalive\n\n'

    async def stream_async():
        last_id = cursor
        yield ': connected\n\n'
        for _ in range(25):
            rows = await sync_to_async(poll)(last_id)
            if rows is None:
                return
            for frame in frames(rows):
                yield frame
            if rows:
                last_id = rows[-1]['id']
            if len(rows) < 100:
                await asyncio.sleep(1)
            yield ': keepalive\n\n'

    stream = stream_async() if isinstance(request, ASGIRequest) else stream_sync()
    response = StreamingHttpResponse(stream, content_type='text/event-stream')
    response['X-Accel-Buffering'] = 'no'
    return response
