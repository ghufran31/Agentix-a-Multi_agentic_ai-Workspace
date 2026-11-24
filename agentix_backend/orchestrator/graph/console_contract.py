"""Versioned browser projection. Keep raw checkpoint and tool payloads server-side."""


from orchestrator.agents.project.validation import RECEIVED_TYPES, describe_location


PROJECT_STAGES = {'tool_planning', 'structured_synthesis', 'output_validation'}
PROJECT_FINISH_REASONS = {'stop', 'length', 'content_filter', 'tool_calls'}
PROJECT_VALIDATION_CODES = {
    'invalid_json', 'missing_structured_output', 'OutputParserException',
    'ModelRefusalError', 'missing', 'model_type', 'model_attributes_type',
    'dict_type', 'list_type', 'string_type', 'int_type', 'float_type', 'bool_type',
    'literal_error', 'extra_forbidden', 'value_error', 'json_invalid', 'json_type',
    'too_short', 'too_long', 'string_too_short', 'string_too_long',
    'string_pattern_mismatch', 'greater_than', 'greater_than_equal',
    'less_than', 'less_than_equal',
}


def safe_task_error(result):
    if result is None or result.error is None:
        return None
    error = {'code': result.error.code}
    if result.capability == 'project.plan':
        metadata = result.metadata
        for source, target, allowed in (
            ('failure_stage', 'stage', PROJECT_STAGES),
            ('finish_reason', 'finish_reason', PROJECT_FINISH_REASONS),
        ):
            value = metadata.get(source)
            if isinstance(value, str) and value in allowed:
                error[target] = value
        provider_status = metadata.get('provider_status')
        if type(provider_status) is int and 400 <= provider_status <= 599:
            error['provider_status'] = provider_status
        if metadata.get('provider_code') == 'rate_limit_exceeded':
            error['provider_code'] = 'rate_limit_exceeded'
        codes = metadata.get('validation_codes')
        if isinstance(codes, list):
            safe = [code for code in codes[:12]
                    if isinstance(code, str) and code in PROJECT_VALIDATION_CODES]
            if safe:
                error['validation_codes'] = safe
        issues = metadata.get('validation_issues')
        if isinstance(issues, list):
            safe = []
            for item in issues[:12]:
                if not isinstance(item, dict):
                    continue
                loc, category, received = (item.get(key) for key in ('loc', 'type', 'received_type'))
                if (isinstance(loc, list) and isinstance(category, str) and category in PROJECT_VALIDATION_CODES
                        and isinstance(received, str) and received in RECEIVED_TYPES):
                    path, expected = describe_location(loc)
                    safe.append({'loc': path, 'type': category, 'expected_type': expected,
                                 'received_type': received})
            if safe:
                error['validation_issues'] = safe
    return error


def _output(result):
    data = result.output or {}
    if result.capability in {'demo.preview', 'demo.approval'}:
        return {key: data[key] for key in ('topic', 'simulated') if key in data}
    if result.capability == 'database.get_project':
        project = data['execution_results'][0]['data']['project']
        return {key: project.get(key) for key in ('id', 'name', 'status', 'priority')}
    if result.capability == 'database.create_project':
        return {key: data[key] for key in (
            'project_id', 'name', 'description', 'deadline', 'requirements_created',
            'matched_skills', 'unresolved_skills', 'warnings', 'duplicate_recovered',
        ) if key in data}
    if result.capability == 'matching.rank':
        ranking = data['structured_output']
        return {'candidates': ranking['candidates'], 'ranked_count': ranking['metadata']['ranked_count']}
    if result.capability == 'project.plan':
        return {'specification': data['structured_output']['specification']}
    if result.capability == 'research.search':
        return {'summary': data['summary'],
                'sources': [{'title': item['title'], 'url': item['url']} for item in data['sources']]}
    return None


def history(state):
    messages = []
    for message in state.get('messages', []):
        if message.type not in {'human', 'ai'} or not isinstance(message.content, str):
            continue
        content = message.content
        if message.type == 'ai' and content.startswith(('Mock run ', 'Specialist run ')):
            content = content.splitlines()[0]
        messages.append({'role': 'user' if message.type == 'human' else 'assistant',
                         'content': content})
    return messages


def execution_state(state, active, mode):
    plan = state.get('plan')
    decision = state.get('decision')
    results = state.get('results', {})
    summary = state.get('execution_summary')
    approvals = state.get('pending_approvals', [])
    status = ('awaiting_approval' if approvals else 'running' if active else
              summary.status if summary else decision.outcome if decision else 'idle')
    tasks = []
    for task in plan.tasks if plan else []:
        result = results.get(task.task_id)
        tasks.append({
            'task_id': task.task_id, 'capability': task.capability,
            'agent': result.agent if result else task.capability.split('.')[0],
            'depends_on': task.depends_on,
            'status': result.status if result else state.get('task_statuses', {}).get(task.task_id, 'pending'),
            'output': _output(result) if result and result.status == 'done' else None,
            'error': safe_task_error(result),
        })
    return {
        'mode': mode, 'execution_id': state.get('execution_id'), 'status': status,
        'decision': decision.outcome if decision else None,
        'plan': {'goal': plan.goal, 'tasks': tasks} if plan else None,
        'errors': [{'code': item.code} for item in state.get('errors', [])],
        'pending_approvals': [_approval(record) for record in approvals],
        'approval_records': [_approval(record) for record in state.get('approval_records', {}).values()],
    }


def _approval(record):
    safe = {key: record[key] for key in (
        'approval_id', 'execution_id', 'task_id', 'capability', 'expires_at', 'status',
    )}
    if record['capability'] == 'demo.approval':
        safe['summary'] = 'Simulated preview review'
        safe['inputs'] = {'topic': record['inputs']['topic']}
    if record['capability'] == 'database.create_project':
        review = record.get('review', {})
        safe['summary'] = 'Review project creation'
        safe['review'] = {key: review[key] for key in (
            'project_name', 'description', 'project_type', 'roles', 'skills',
            'deadline', 'fields_saved', 'requirements_not_persisted',
            'additional_fields_not_persisted', 'persistence_performed',
        ) if key in review}
    return safe
