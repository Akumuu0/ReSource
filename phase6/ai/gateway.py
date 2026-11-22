"""AIGateway: the ONLY class that talks to the AI provider (design Section 4.1, Fig. 9-4).

For every call it:
  1. removes personal data from the text (SEC-11),
  2. calls Gemini with a 20-second time limit (PER-5),
  3. checks the answer,
  4. uses the rule-based fallback if anything went wrong (AI-6),
  5. saves an AIOutput row (feature, input, output, confidence, source).
The human decision is added to that row later with AIOutput.record_decision().
"""
import json
import re
import time

from django.conf import settings
from google import genai
from google.genai import errors, types

from accounts.models import User

from .models import AIOutput

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
RECORD_CODE = re.compile(r"\b[AR]-\d{4}-\d{4}\b")  # asset and request codes
LONG_NUMBER = re.compile(r"\b\d{6,}\b")             # university IDs, phone numbers


class AIResult:
    """What a service gets back: the data (from the AI or from the fallback) and the saved record."""

    def __init__(self, data, output):
        self.data = data
        self.output = output

    @property
    def used_ai(self):
        return self.output.used_ai


class AIGateway:

    def run(self, feature, system, prompt, schema, fallback, user, validate=None, confidence=None):
        """Ask the AI for JSON that follows `schema`. If that fails in any way, use `fallback()`.

        validate(data) returns "" when the answer is fine, or a short problem description.
        confidence, if given, is stored instead of the one in the answer.
        """
        clean_prompt = self.strip_personal_data(prompt)

        started = time.monotonic()
        data, note = self.call_model(system, clean_prompt, schema)
        latency_ms = int((time.monotonic() - started) * 1000)

        if data is not None and validate:
            problem = validate(data)
            if problem:
                data, note = None, f"AI answer rejected: {problem}"

        source = AIOutput.AI_SOURCE
        if data is None:
            data, source = fallback(), AIOutput.FALLBACK_SOURCE

        output = AIOutput.objects.create(
            feature=feature,
            input_text=clean_prompt,
            output_text=json.dumps(data),
            confidence=confidence if confidence is not None else data.get("confidence"),
            source=source,
            note=note,
            model_name=settings.AI_MODEL if source == AIOutput.AI_SOURCE else "",
            latency_ms=latency_ms,
            requested_by=user,
        )
        return AIResult(data, output)

    def call_model(self, system, prompt, schema):
        """Send the prompt to Gemini. Returns (data, note); data is None if anything failed."""
        if not settings.GEMINI_API_KEY:
            return None, "No API key set"

        client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=types.HttpOptions(
                timeout=settings.AI_TIMEOUT_SECONDS * 1000,             # in milliseconds: stop after 20 seconds
                retry_options=types.HttpRetryOptions(attempts=1),       # one try only, so 20 s is the real limit
            ),
        )
        try:
            response = client.models.generate_content(
                model=settings.AI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    max_output_tokens=2048,
                    # Short tasks need little thinking; the JSON schema makes the answer valid JSON.
                    thinking_config=types.ThinkingConfig(thinking_level="LOW"),
                    response_mime_type="application/json",
                    response_json_schema=schema,
                ),
            )
        except errors.APIError as error:  # the service answered with an error: bad key, quota, overload...
            return None, f"AI service error {error.code}"
        except Exception as error:  # no answer at all: time limit reached or no connection
            return None, f"No answer from the AI service ({type(error).__name__})"

        if not response.text:
            return None, "AI answer was empty"
        try:
            return json.loads(response.text), "OK"
        except ValueError:
            return None, "AI answer was not valid JSON"

    @staticmethod
    def strip_personal_data(text):
        """Remove e-mails, record codes, long numbers and names of registered users."""
        text = EMAIL.sub("[email]", text)
        text = RECORD_CODE.sub("[code]", text)
        text = LONG_NUMBER.sub("[number]", text)
        names = set()
        for user in User.objects.all():
            names.update([user.username, user.first_name, user.last_name, user.get_full_name()])
        for name in sorted(names, key=len, reverse=True):  # full names first
            if len(name) >= 3:
                text = re.sub(rf"\b{re.escape(name)}\b", "[name]", text, flags=re.IGNORECASE)
        return text
