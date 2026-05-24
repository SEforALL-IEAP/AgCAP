"""
Translation loader module for AgCAP platform
Loads CSV translations and provides helper functions for UI text and column name translation
Supports English (en), French (fr), and Portuguese (pt)

CSV files are stored in agcap_platform/translations/ (same directory as this module).
"""

import csv
import os

# Storage for translations loaded from CSV
TRANSLATIONS = {'en': {}, 'fr': {}, 'pt': {}}
# COLUMN_TRANSLATIONS stores translations per country: {'MDG': {'en': {}, 'fr': {}, 'pt': {}}, 'MOZ': {...}}
COLUMN_TRANSLATIONS = {}


def load_translations():
    """Load UI text translations from CSV"""
    csv_path = os.path.join(os.path.dirname(__file__), 'translations', 'ui_text.csv')
    if os.path.exists(csv_path):
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = row['key']
                TRANSLATIONS['en'][key] = row['en']
                fr_value = (row.get('fr') or '').strip()
                TRANSLATIONS['fr'][key] = fr_value if fr_value else row['en']
                pt_value = (row.get('pt') or '').strip()
                TRANSLATIONS['pt'][key] = pt_value if pt_value else row['en']


def load_column_translations(country_code='MDG'):
    """
    Load database column translations for a specific country dataset.

    Args:
        country_code: 3-letter country code ('MDG', 'MOZ', etc.)

    Each country has its own column translation file: translations/columns_{country_code}.csv
    """
    global COLUMN_TRANSLATIONS

    if country_code not in COLUMN_TRANSLATIONS:
        COLUMN_TRANSLATIONS[country_code] = {'en': {}, 'fr': {}, 'pt': {}}

    csv_path = os.path.join(
        os.path.dirname(__file__),
        'translations',
        f'columns_{country_code}.csv'
    )

    if os.path.exists(csv_path):
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                en_col = row['en']
                fr_col = (row.get('fr') or '').strip()
                pt_col = (row.get('pt') or '').strip()

                COLUMN_TRANSLATIONS[country_code]['en'][en_col] = en_col
                COLUMN_TRANSLATIONS[country_code]['fr'][en_col] = fr_col if fr_col else en_col
                COLUMN_TRANSLATIONS[country_code]['pt'][en_col] = pt_col if pt_col else en_col


def t(key, lang='en', **kwargs):
    """
    Translation function with English fallback.

    Args:
        key: Translation key (e.g., 'sidebar.layers')
        lang: Language code ('en', 'fr', or 'pt')
        **kwargs: Format variables for string interpolation

    Returns:
        Translated string (falls back to English if translation missing)
    """
    if lang not in ['en', 'fr', 'pt']:
        lang = 'en'

    value = TRANSLATIONS.get(lang, {}).get(key)

    if value is None:
        value = TRANSLATIONS.get('en', {}).get(key, key)

    if kwargs:
        try:
            value = value.format(**kwargs)
        except (KeyError, ValueError):
            pass

    return value


def get_column_translation(col_name, lang='en', country_code='MDG'):
    """
    Get translated column name for a specific country dataset.

    Args:
        col_name: Original column name (English)
        lang: Language code ('en', 'fr', or 'pt')
        country_code: 3-letter country code ('MDG', 'MOZ', etc.)

    Returns:
        Translated column name or original if translation missing
    """
    if lang not in ['en', 'fr', 'pt']:
        lang = 'en'

    if lang == 'en':
        return col_name

    if country_code not in COLUMN_TRANSLATIONS:
        return col_name

    return COLUMN_TRANSLATIONS[country_code].get(lang, {}).get(col_name, col_name)


def get_spider_label_patterns(lang='en'):
    """
    Get patterns to strip from column names for spider chart labels.

    These patterns are used to clean column names for display on polar axis labels.
    For example: 'Ag Cooling Demand Export Market' → 'Export Market'
    """
    if lang == 'fr':
        return {
            'ag': 'Demande Refroid. Agri. ',
            'fish': 'Demande Refroid. Pêche ',
            'prod_prefix': 'Production de ',
            'prod_suffix': ''
        }
    elif lang == 'pt':
        return {
            'ag': 'Demanda Refrigeração Agri. ',
            'fish': 'Demanda Refrigeração Pesca ',
            'prod_prefix': 'Produção de ',
            'prod_suffix': ''
        }
    else:
        return {
            'ag': 'Ag Cooling Demand ',
            'fish': 'Fish Cooling Demand ',
            'prod_prefix': '',
            'prod_suffix': ' production'
        }


# Load UI translations on module import
load_translations()
# Note: Column translations are loaded per-country by each app using load_column_translations(country_code)
