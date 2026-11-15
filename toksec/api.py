"""Single-request OpenAI transport with no redirects or automatic retries."""

import json
import urllib.error
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("API redirects are not allowed")


class Responses:
    def __init__(self, key):
        if not key:
            raise ValueError("OPENAI_API_KEY is not configured")
        self.key = key
        self.opener = urllib.request.build_opener(NoRedirect())

    def post(self, endpoint, payload, timeout):
        request = urllib.request.Request("https://api.openai.com/v1/" + endpoint,
                                         data=json.dumps(payload).encode(),
                                         headers={"Authorization": "Bearer " + self.key,
                                                  "Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"API HTTP {error.code}; no automatic retry") from None
