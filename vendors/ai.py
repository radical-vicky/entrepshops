"""Google Gemini client for AI-powered product suggestions.

Uses the new `google-genai` SDK (the older `google-generativeai` package
is deprecated). One function: `suggest_product(text, image_file=None)`.

Returns a dict with keys:
    title, description, department, category, price_low, price_high, notes

On any failure (missing key, network error, bad response), returns None.
The calling view decides how to tell the user.
"""

import json
import logging

from django.conf import settings

log = logging.getLogger(__name__)


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


EXISTING_CATEGORIES_HINT = """
Existing categories already in the shop (prefer these if the item fits):
{categories}
"""


def _build_prompt(text, image_file, departments, categories):
    parts = []

    parts.append(SYSTEM_PROMPT)

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
        parts.append('\nAn image of the product is attached. Analyse it to refine the title, description, and pricing.')

    parts.append('\nReturn the JSON object now.')

    return '\n'.join(parts)


def suggest_product(text, image_file=None):
    """Call Gemini. Returns a dict, or None on any failure."""
    api_key = getattr(settings, 'GEMINI_API_KEY', '')
    if not api_key:
        log.warning('GEMINI_API_KEY not set — AI suggestions disabled.')
        return None

    if not text and not image_file:
        return None

    # Import lazily so a missing package doesn't crash Django startup.
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        log.exception('google-genai is not installed. Run: pip install google-genai')
        return None

    # Pull the current departments and categories to feed the prompt.
    try:
        from store.models import Category, Department
        departments = list(Department.objects.filter(is_active=True).values_list('name', flat=True))
        categories = list(Category.objects.values_list('name', flat=True))
    except Exception:
        departments = []
        categories = []

    prompt = _build_prompt(text, image_file, departments, categories)

    # Build the contents list. Gemini expects a list of Parts.
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
            log.exception('Could not read uploaded image')
            # Continue with text only rather than failing outright.

    try:
        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model=getattr(settings, 'GEMINI_MODEL', 'gemini-2.5-flash'),
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type='application/json',
                temperature=0.4,
            ),
        )
    except Exception:
        log.exception('Gemini API call failed')
        return None

    raw = getattr(response, 'text', '') or ''
    if not raw:
        log.warning('Gemini returned empty response')
        return None

    # Strip markdown fences if the model added them anyway.
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

    # Validate the fields we care about.
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
