"""Single-request OpenAI transport with no redirects or automatic retries."""

import json
import urllib.error
import urllib.request


class ProviderHTTPError(RuntimeError):
    def __init__(self, endpoint, error):
        self.endpoint = endpoint
        self.status = error.code
        self.request_id = (error.headers or {}).get('x-request-id')
        self.retry_after = (error.headers or {}).get('retry-after')
        super().__init__(f'API HTTP {self.status}; no automatic retry')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("API redirects are not allowed")


class Responses:
    def __init__(self, key):
        if not key:
            raise ValueError("OPENAI_API_KEY is not configured")
        self.key = key
        self.opener = urllib.request.build_opener(NoRedirect())
        self.last_request_id = None

    def post(self, endpoint, payload, timeout, *, request_id=None):
        self.last_request_id = None
        headers = {"Authorization": "Bearer " + self.key, "Content-Type": "application/json"}
        if request_id:
            headers["X-Client-Request-Id"] = request_id
        request = urllib.request.Request("https://api.openai.com/v1/" + endpoint,
                                         data=json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode(),
                                         headers=headers)
        try:
            with self.opener.open(request, timeout=timeout) as response:
                self.last_request_id = getattr(response, 'headers', {}).get('x-request-id')
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise ProviderHTTPError(endpoint, error) from None
