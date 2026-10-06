"""Google Gemini client for AI-powered product suggestions.

Uses the new `google-genai` SDK. One function: `suggest_product(text, image_file=None)`.

Enforces a hard time budget so the request returns before Vercel's
10-second serverless timeout kills it.
"""

import json
import logging
import random
import time

from django.conf import settings

log = logging.getLogger(__name__)


# Vercel Hobby plan gives functions 10 seconds. Leave headroom for
# framework overhead, DB queries, and the return trip.
TOTAL_BUDGET_SECONDS = 7.0

# Per-model: only 2 attempts now, shorter waits.
ATTEMPTS_PER_MODEL = 2
BASE_WAIT_SECONDS = 2.0

# Try at most this many models before giving up.
MAX_MODELS = 2


SYSTEM_PROMPT = """You are a product classification assistant for an online shop in Kenya called Entrep Shop.

A seller has given you a short description and/or an image of a product they want to list.

Your job: return a JSON object with everything needed to create a good product listing on the shop.

You MUST return pure JSON matching this schema exactly:

{
  "title": "<a clear, specific product name, e.g. 'HP Pavilion 15 Intel Core i5 8GB RAM 256GB SSD Laptop'>",
  "description": "<a 2-4 sentence sales description in English. Neutral tone. No emoji. Mention what the product is, who it's for, and 2-3 key features. Do NOT invent specs you don't see.>",
  "department": "<ONE of the exact department names listed below>",
  "category": "<A short category name, 1-3 words, e.g. 'Computers', 'Smart Screens', 'Fridges', 'Audio'>",
  "price_low_kes": <integer, lowest fair retail price in Kenyan Shillings>,
  "price_high_kes": <integer, highest fair retail price in Kenyan Shillings>,
  "price_notes": "<one short sentence explaining the price range, e.g. 'Entry-level laptops in Kenya range from KES 35,000 to 60,000 depending on RAM and storage.'>"
}

Rules:
- Prices must be in KES and reflect the Kenyan retail market as of 2025. Be conservative.
- Choose the department from the list provided. If nothing fits well, pick the closest.
- Category should be short and reusable. Prefer existing categories listed below.
- Do not add fields. Do not wrap the JSON in markdown. Return only the JSON object.
"""


DEFAULT_MODEL_CHAIN = [
    'gemini-flash-latest',
    'gemini-2.5-flash',
    'gemini-2.0-flash',
]


def _model_chain():
    primary = getattr(settings, 'GEMINI_MODEL', '') or 'gemini-flash-latest'
    chain = [primary] + [m for m in DEFAULT_MODEL_CHAIN if m != primary]
    return chain[:MAX_MODELS]


def _build_prompt(text, image_file, departments, categories):
    parts = [SYSTEM_PROMPT]

    if departments:
        parts.append(
            '\nAvailable departments (you MUST choose one of these exact names):\n'
            + '\n'.join(f'- {d}' for d in departments)
        )

    if categories:
        parts.append(
            '\nExisting categories already in the shop (prefer these if the item fits):\n'
            + '\n'.join(f'- {c}' for c in categories)
        )

    if text:
        parts.append(f'\nSeller typed: "{text.strip()[:400]}"')

    if image_file:
        parts.append(
            '\nAn image of the product is attached. Analyse it to refine '
            'the title, description, and pricing.'
        )

    parts.append('\nReturn the JSON object now.')

    return '\n'.join(parts)


def suggest_product(text, image_file=None):
    """Call Gemini. Returns a dict, or None on any failure.

    Enforces a total time budget so the request never exceeds Vercel's
    function timeout.
    """
    start = time.monotonic()

    api_key = getattr(settings, 'GEMINI_API_KEY', '')
    if not api_key:
        log.warning('GEMINI_API_KEY not set — AI suggestions disabled.')
        return None

    if not text and not image_file:
        return None

    try:
        from google import genai
        from google.genai import types
        from google.genai import errors as genai_errors
    except ImportError:
        log.exception('google-genai is not installed. Run: pip install google-genai')
        return None

    try:
        from store.models import Category, Department
        departments = list(
            Department.objects.filter(is_active=True).values_list('name', flat=True)
        )
        categories = list(Category.objects.values_list('name', flat=True))
    except Exception:
        departments = []
        categories = []

    prompt = _build_prompt(text, image_file, departments, categories)
    contents = [prompt]

    if image_file:
        try:
            image_file.seek(0)
            image_bytes = image_file.read()
            mime_type = getattr(image_file, 'content_type', 'image/jpeg') or 'image/jpeg'
            contents.append(
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            )
        except Exception:
            log.exception('Could not read uploaded image; continuing with text only.')

    try:
        client = genai.Client(api_key=api_key)
    except Exception:
        log.exception('Could not create Gemini client')
        return None

    chain = _model_chain()
    log.info('Gemini: chain=%s', chain)

    for model_name in chain:
        elapsed = time.monotonic() - start
        remaining = TOTAL_BUDGET_SECONDS - elapsed
        if remaining <= 1.5:
            log.warning(
                'Gemini: skipping %s — only %.1fs left in budget.',
                model_name, remaining,
            )
            break

        response = _try_model(
            client=client,
            types=types,
            errors_module=genai_errors,
            model_name=model_name,
            contents=contents,
            deadline=start + TOTAL_BUDGET_SECONDS,
        )

        if response is not None:
            parsed = _parse_response(response)
            if parsed is not None:
                log.info(
                    'Gemini: success with %s (%.1fs)',
                    model_name, time.monotonic() - start,
                )
                return parsed
            log.warning('Gemini: %s returned unparseable output.', model_name)

    log.warning('Gemini: budget exhausted or all models failed.')
    return None


def _try_model(client, types, errors_module, model_name, contents, deadline):
    """Call one model with limited retries, respecting an absolute deadline."""

    for attempt in range(ATTEMPTS_PER_MODEL):
        # Do not start a request we can't finish in time.
        if time.monotonic() >= deadline - 1.5:
            log.warning(
                'Gemini: no time left for %s attempt %d.',
                model_name, attempt + 1,
            )
            return None

        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type='application/json',
                    temperature=0.4,
                ),
            )
            return response

        except errors_module.ServerError as exc:
            # 500/503 — brief backoff, then retry once if budget allows.
            wait = BASE_WAIT_SECONDS + random.uniform(0, 1.0)
            log.warning(
                'Gemini %s ServerError (attempt %d/%d): %s. '
                'Backoff %.1fs.',
                model_name, attempt + 1, ATTEMPTS_PER_MODEL,
                str(exc)[:200], wait,
            )
            if attempt < ATTEMPTS_PER_MODEL - 1 and time.monotonic() + wait < deadline - 1.5:
                time.sleep(wait)
            else:
                return None

        except errors_module.ClientError as exc:
            log.warning(
                'Gemini %s ClientError: %s. Moving on.',
                model_name, str(exc)[:200],
            )
            return None

        except Exception:
            log.exception('Unexpected error calling %s', model_name)
            return None

    return None


def _parse_response(response):
    raw = getattr(response, 'text', '') or ''
    if not raw:
        log.warning('Gemini returned empty response')
        return None

    cleaned = raw.strip()
    if cleaned.startswith('```'):
        cleaned = cleaned.strip('`')
        if cleaned.lower().startswith('json'):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        log.exception('Gemini returned invalid JSON: %s', cleaned[:500])
        return None

    required = ('title', 'description', 'department', 'category')
    if not all(data.get(k) for k in required):
        log.warning('Gemini response missing required fields: %s', data)
        return None

    return {
        'title': str(data.get('title', ''))[:200],
        'description': str(data.get('description', ''))[:5000],
        'department': str(data.get('department', '')).strip(),
        'category': str(data.get('category', '')).strip(),
        'price_low': _safe_int(data.get('price_low_kes')),
        'price_high': _safe_int(data.get('price_high_kes')),
        'price_notes': str(data.get('price_notes', ''))[:300],
    }


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
