import json
from unittest.mock import Mock, patch

import httpx
from django.test import SimpleTestCase
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from orchestrator.agents.research.agent import build_research_agent, execute_research
from orchestrator.tools.research.search_tools import search_web
from orchestrator.tools.research.webpage_tools import PageText, public_destination, read_webpage


class ResearchTests(SimpleTestCase):
    @patch('orchestrator.agents.research.agent.build_research_agent')
    def test_failed_search_stops_before_next_model_turn(self, build):
        question = HumanMessage(content='Find sources')
        reply = AIMessage(content='', usage_metadata={
            'input_tokens': 7, 'output_tokens': 3, 'total_tokens': 10,
        })
        failure = ToolMessage(name='search_web', tool_call_id='1', content=json.dumps({
            'sources': [], 'error': 'no_results',
        }))

        def states(*args, **kwargs):
            yield {'messages': [question, reply, failure]}
            self.fail('A failed search should end the model loop.')

        build.return_value.stream.side_effect = states
        result = execute_research('Find sources')
        self.assertEqual(result.status, 'error')
        self.assertEqual(result.errors, ['no_results'])
        self.assertEqual(result.model_responses, 1)
        self.assertEqual(result.tokens, 10)
        self.assertEqual(result.summary.findings, [])

    @patch('orchestrator.agents.research.agent.create_agent')
    @patch('orchestrator.agents.research.agent.get_llm')
    def test_builder(self, factory, create):
        build_research_agent()
        factory.assert_called_once_with(None)
        kwargs = create.call_args.kwargs
        self.assertIn('Agentix Research Specialist', kwargs['system_prompt'])
        self.assertEqual([tool.name for tool in kwargs['tools']], ['search_web', 'read_webpage'])

    @patch.dict('os.environ', {'TAVILY_API_KEY': 'fixture-key'})
    @patch('orchestrator.tools.research.search_tools.httpx.post')
    def test_provider(self, post):
        post.return_value.json.return_value = {'usage': {'credits': 1}, 'results': [
            dict(title='Official', url='https://example.org/', content='Summary'),
            dict(title='Invalid', url='file:///secret', content='Invalid'),
        ]}
        result = search_web(query='test')
        self.assertEqual([source['title'] for source in result['sources']], ['Official'])
        self.assertEqual(result['credits'], 1)
        self.assertEqual(post.call_args.kwargs['json']['search_depth'], 'basic')

    @patch.dict('os.environ', {'TAVILY_API_KEY': 'fixture-key'})
    @patch('orchestrator.tools.research.search_tools.httpx.post')
    def test_empty_timeout_and_quota(self, post):
        post.return_value.json.return_value = {'results': []}
        self.assertEqual(search_web(query='test')['error'], 'no_results')
        post.return_value.status_code = 432
        self.assertEqual(search_web(query='test')['error'], 'search_quota')
        post.side_effect = httpx.ReadTimeout('timeout')
        self.assertEqual(search_web(query='test')['error'], 'search_timeout')

    @patch.dict('os.environ', {'TAVILY_API_KEY': ''})
    @patch('orchestrator.tools.research.search_tools.httpx.post')
    def test_missing_key_makes_no_request(self, post):
        self.assertEqual(search_web(query='test')['error'], 'missing_tavily_key')
        post.assert_not_called()

    @patch('orchestrator.tools.research.webpage_tools.socket.getaddrinfo')
    def test_nonpublic_resolution(self, dns):
        dns.return_value = [(0, 0, 0, '', ('169.254.169.254', 80))]
        with self.assertRaises(ValueError):
            public_destination('http://www.example.org/')
        with self.assertRaises(ValueError):
            public_destination('file:///secret')
        with self.assertRaises(ValueError):
            public_destination('http://user@www.example.org/')

    @patch('orchestrator.tools.research.webpage_tools.public_destination', side_effect=TimeoutError)
    def test_page_timeout(self, resolve):
        self.assertEqual(read_webpage('https://example.org/')['error'], 'page_timeout')

    def test_html_extraction(self):
        html = PageText()
        html.feed('<title>Official</title><nav>menu</nav><script>ignore</script><p>Content</p>')
        self.assertEqual(html.title, ['Official'])
        self.assertEqual(html.text, ['Content'])

    @patch('orchestrator.tools.research.webpage_tools.socket.create_connection')
    @patch('orchestrator.tools.research.webpage_tools.socket.getaddrinfo')
    @patch('orchestrator.tools.research.webpage_tools.http.client.HTTPConnection')
    def test_redirect_to_private_address_is_blocked(self, connection, dns, connect):
        dns.side_effect = [
            [(0, 0, 0, '', ('93.184.215.14', 80))],
            [(0, 0, 0, '', ('127.0.0.1', 80))],
        ]
        response = connection.return_value.getresponse.return_value
        response.status = 302
        response.getheader.return_value = 'http://127.0.0.1/'
        result = read_webpage('http://example.org/')
        self.assertEqual(result['error'], 'unsafe_or_unreachable_url')
        self.assertEqual(connect.call_count, 1)
        self.assertEqual(connect.call_args.args[0], ('93.184.215.14', 80))

    def test_grounding_and_invalid_output(self):
        agent = Mock()
        question = HumanMessage(content='Compare')
        evidence = ToolMessage(name='search_web', tool_call_id='1', content=json.dumps({
            'sources': [dict(title='Official', url='https://example.org/',
                             excerpt='Evidence', provider='tavily')]
        }))
        for url, expected in [('https://example.org/', 'ok'), ('https://example.com/', 'error')]:
            answer = dict(answer='Summary', findings=[dict(claim='Finding', urls=[url])])
            agent.invoke.return_value = {'messages': [question, evidence, AIMessage(content=json.dumps(answer))]}
            self.assertEqual(execute_research('Compare', agent=agent).status, expected)
        agent.invoke.return_value = {'messages': [question, AIMessage(content='invalid JSON')]}
        self.assertEqual(execute_research('Compare', agent=agent).status, 'error')
