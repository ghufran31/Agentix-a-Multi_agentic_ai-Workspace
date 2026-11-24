import re

from orchestrator.agents.research.schemas import Source


class UngroundedCitation(ValueError):
    pass


def ground_summary(summary, evidence):
    citations = {}
    findings = []
    for finding in summary.findings:
        urls = []
        for url in finding.urls:
            # HTTP origin URLs with and without the root slash address the same page.
            # Do not normalize paths, queries, fragments, or scheme changes.
            if url not in evidence and re.fullmatch(r'https?://[^/?#]+', url):
                url += '/'
            if url not in evidence:
                raise UngroundedCitation('Citation did not match observed evidence.')
            citations[url] = evidence[url]
            urls.append(url)
        findings.append(finding.model_copy(update={'urls': urls}))
    return (summary.model_copy(update={'findings': findings}),
            [Source.model_validate(source) for source in citations.values()])
