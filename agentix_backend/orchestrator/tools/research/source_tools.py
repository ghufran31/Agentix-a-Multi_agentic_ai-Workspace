from orchestrator.agents.research.schemas import Source


def grounded_sources(summary, evidence):
    citations = dict.fromkeys(url for finding in summary.findings for url in finding.urls)
    if any(url not in evidence for url in citations):
        raise ValueError('A citation did not come from a tool result in this turn.')
    return [Source.model_validate(evidence[url]) for url in citations]
