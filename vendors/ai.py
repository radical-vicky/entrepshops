"""xAI Grok client for AI-powered product suggestions.

Uses the official `openai` SDK, pointed at xAI's OpenAI-compatible endpoint.
One function: `suggest_product(text, image_file=None)`.

Enforces a 7-second total time budget so the request returns before
Vercel's 10-second serverless timeout kills it.
"""

import base64
import json
import logging
import random
import time

from django.conf import settings

log = logging.getLogger(__name__)


# Vercel Hobby plan gives functions 10 seconds. Leave headroom.
TOTAL_BUDGET_SECONDS = 7.0

# Per-model: only 2 attempts, short waits.
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
    'grok-4.6',
    'grok-4.7',
    'grok-3',
]


def _model_chain():
    primary = getattr(settings, 'XAI_MODEL', '') or 'grok-4.6'
    chain = [primary] + [m for m in DEFAULT_MODEL_CHAIN if m != primary]
    return chain[:MAX_MODELS]


def _build_prompt(text, departments, categories):
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

    return '\n'.join(parts)


def suggest_product(text, image_file=None):
    """Call Grok. Returns a dict, or None on any failure.

    Enforces a total time budget so the request never exceeds Vercel's
    function timeout.
    """
    start = time.monotonic()

    api_key = getattr(settings, 'XAI_API_KEY', '')
    if not api_key:
        log.warning('XAI_API_KEY not set — AI suggestions disabled.')
        return None

    if not text and not image_file:
        return None

    try:
        from openai import OpenAI
        from openai import APIStatusError, APIConnectionError
    except ImportError:
        log.exception('openai is not installed. Run: pip install openai')
        return None

    # Departments and categories to feed the prompt.
    try:
        from store.models import Category, Department
        departments = list(
            Department.objects.filter(is_active=True).values_list('name', flat=True)
        )
        categories = list(Category.objects.values_list('name', flat=True))
    except Exception:
        departments = []
        categories = []

    prompt = _build_prompt(text, departments, categories)

    # Build the OpenAI-format messages. Grok accepts the same shape.
    user_content = [{'type': 'text', 'text': prompt}]

    if image_file:
        try:
            image_file.seek(0)
            image_bytes = image_file.read()
            mime_type = getattr(image_file, 'content_type', 'image/jpeg') or 'image/jpeg'
            b64 = base64.b64encode(image_bytes).decode('ascii')
            user_content.append({
                'type': 'image_url',
                'image_url': {
                    'url': f'data:{mime_type};base64,{b64}',
                },
            })
            user_content[0]['text'] += (
                '\n\nAn image of the product is attached. '
                'Analyse it to refine the title, description, and pricing.'
            )
        except Exception:
            log.exception('Could not read uploaded image; continuing with text only.')

    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': user_content},
    ]

    try:
        client = OpenAI(
            api_key=api_key,
            base_url=getattr(settings, 'XAI_BASE_URL', 'https://api.x.ai/v1'),
            timeout=TOTAL_BUDGET_SECONDS,
        )
    except Exception:
        log.exception('Could not create xAI client')
        return None

    chain = _model_chain()
    log.info('Grok: chain=%s', chain)

    for model_name in chain:
        elapsed = time.monotonic() - start
        remaining = TOTAL_BUDGET_SECONDS - elapsed
        if remaining <= 1.5:
            log.warning(
                'Grok: skipping %s — only %.1fs left in budget.',
                model_name, remaining,
            )
            break

        response = _try_model(
            client=client,
            model_name=model_name,
            messages=messages,
            deadline=start + TOTAL_BUDGET_SECONDS,
        )

        if response is not None:
            parsed = _parse_response(response)
            if parsed is not None:
                log.info(
                    'Grok: success with %s (%.1fs)',
                    model_name, time.monotonic() - start,
                )
                return parsed
            log.warning('Grok: %s returned unparseable output.', model_name)

    log.warning('Grok: budget exhausted or all models failed.')
    return None


def _try_model(client, model_name, messages, deadline):
    """Call one model with limited retries, respecting an absolute deadline."""
    from openai import APIStatusError, APIConnectionError

    for attempt in range(ATTEMPTS_PER_MODEL):
        if time.monotonic() >= deadline - 1.5:
            log.warning(
                'Grok: no time left for %s attempt %d.',
                model_name, attempt + 1,
            )
            return None

        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.4,
                response_format={'type': 'json_object'},
            )
            return response

        except APIStatusError as exc:
            # 5xx or 429 — retry once if budget allows.
            if exc.status_code >= 500 or exc.status_code == 429:
                wait = BASE_WAIT_SECONDS + random.uniform(0, 1.0)
                log.warning(
                    'Grok %s status %d (attempt %d/%d): %s. Backoff %.1fs.',
                    model_name, exc.status_code, attempt + 1, ATTEMPTS_PER_MODEL,
                    str(exc)[:200], wait,
                )
                if attempt < ATTEMPTS_PER_MODEL - 1 and time.monotonic() + wait < deadline - 1.5:
                    time.sleep(wait)
                else:
                    return None
            else:
                log.warning(
                    'Grok %s client error %d: %s. Moving on.',
                    model_name, exc.status_code, str(exc)[:200],
                )
                return None

        except APIConnectionError as exc:
            log.warning('Grok %s connection error: %s', model_name, exc)
            return None

        except Exception:
            log.exception('Unexpected error calling %s', model_name)
            return None

    return None


def _parse_response(response):
    try:
        raw = response.choices[0].message.content or ''
    except (AttributeError, IndexError):
        log.warning('Grok returned an unexpected response shape')
        return None

    if not raw:
        log.warning('Grok returned empty response')
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
        log.exception('Grok returned invalid JSON: %s', cleaned[:500])
        return None

    required = ('title', 'description', 'department', 'category')
    if not all(data.get(k) for k in required):
        log.warning('Grok response missing required fields: %s', data)
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
