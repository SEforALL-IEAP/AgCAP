"""
Translation loader module for AgCAP platform
Loads CSV translations and provides helper functions for UI text and column name translation
Supports English (en), French (fr), and Portuguese (pt)
"""

import csv
import os

# Storage for translations loaded from CSV
TRANSLATIONS = {'en': {}, 'fr': {}, 'pt': {}}
# COLUMN_TRANSLATIONS now stores translations per country: {'MDG': {'en': {}, 'fr': {}, 'pt': {}}, 'MOZ': {...}}
COLUMN_TRANSLATIONS = {}

# --- Legacy column-name normalization ---
# Raw data files for any country may still use the pre-rename "Cooling Demand" naming
# (SEforALL renamed the index family to "Cooling Potential" since the indices were always
# relative proxies for cooling potential, never a quantified measure of demand). Rather than
# requiring every data file to be re-exported before deployment, normalize known legacy names
# to current ones right after load. Safe to call on already-current data: only renames a column
# if the legacy name is present AND the current name isn't already there.
LEGACY_COLUMN_RENAMES = {
    'Ag Cooling Demand Export Market': 'Ag Cooling Potential Export Market',
    'Ag Cooling Demand National Market': 'Ag Cooling Potential National Market',
    'Ag Cooling Demand Fresh Markets': 'Ag Cooling Potential Fresh Markets',
    'Ag Cooling Demand ALL Markets': 'Ag Cooling Potential ALL Markets',
    'Ag Cooling Demand ALL Markets - class': 'Ag Cooling Potential ALL Markets - class',
    'Fish Cooling Demand Export Market': 'Fish Cooling Potential Export Market',
    'Fish Cooling Demand National Market': 'Fish Cooling Potential National Market',
    'Fish Cooling Demand Fresh Markets': 'Fish Cooling Potential Fresh Markets',
    'Fish Cooling Demand ALL Markets': 'Fish Cooling Potential ALL Markets',
    'Fish Cooling Demand ALL Markets - class': 'Fish Cooling Potential ALL Markets - class',
    # Fixes a typo ("installeld") present in older pipeline exports.
    'Solar PV Output (kWh/year per installeld kW)': 'Solar PV Output (kWh/year per installed kW)',
}


def normalize_legacy_columns(gdf):
    """Rename legacy pre-rename column names to their current equivalents. Call this immediately
    after reading any country's settlement dataset, before anything else touches its columns.

    Deliberately scoped to the Cooling Demand -> Cooling Potential terminology rename only.
    Other structural changes to the pipeline schema (admin field names, fishing-activity
    structure, crop category names) are not naming variants of the same data - they're the
    pipeline producing genuinely different/restructured columns - so they are not normalized
    here. A file using the old structure for those should be re-exported from the current
    pipeline, not silently reinterpreted.
    """
    rename_map = {
        old: new for old, new in LEGACY_COLUMN_RENAMES.items()
        if old in gdf.columns and new not in gdf.columns
    }
    if rename_map:
        gdf = gdf.rename(columns=rename_map)
    return gdf


def load_translations():
    """Load UI text translations from CSV"""
    csv_path = os.path.join(os.path.dirname(__file__), 'translations', 'ui_text.csv')
    if os.path.exists(csv_path):
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = row['key']
                TRANSLATIONS['en'][key] = row['en']
                # Fallback to English if French translation is empty
                fr_value = (row.get('fr') or '').strip()
                TRANSLATIONS['fr'][key] = fr_value if fr_value else row['en']
                # Fallback to English if Portuguese translation is empty
                pt_value = (row.get('pt') or '').strip()
                TRANSLATIONS['pt'][key] = pt_value if pt_value else row['en']


def load_column_translations(country_code='MDG'):
    """
    Load database column translations for a specific country dataset

    Args:
        country_code: 3-letter country code ('MDG', 'MOZ', etc.)

    Each country has its own column translation file: translations/columns_{country_code}.csv
    This allows different datasets to have different column names without conflicts.
    """
    global COLUMN_TRANSLATIONS

    # Initialize country-specific dictionary if not exists
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
                # Fallback to English if translation is empty
                fr_col = (row.get('fr') or '').strip()
                pt_col = (row.get('pt') or '').strip()

                COLUMN_TRANSLATIONS[country_code]['en'][en_col] = en_col
                COLUMN_TRANSLATIONS[country_code]['fr'][en_col] = fr_col if fr_col else en_col
                COLUMN_TRANSLATIONS[country_code]['pt'][en_col] = pt_col if pt_col else en_col


def t(key, lang='en', **kwargs):
    """
    Translation function with English fallback

    Args:
        key: Translation key (e.g., 'sidebar.layers')
        lang: Language code ('en', 'fr', or 'pt')
        **kwargs: Format variables for string interpolation (e.g., value=123)

    Returns:
        Translated string (falls back to English if translation missing)

    Examples:
        t('sidebar.layers', 'fr') → 'Couches'
        t('spider_charts.total_production', 'fr', value='1,234') → 'Production agricole périssable totale (t/an) 1,234'
    """
    # Validate language, default to English
    if lang not in ['en', 'fr', 'pt']:
        lang = 'en'

    # Get translation from the specified language
    value = TRANSLATIONS.get(lang, {}).get(key)

    # Fallback to English if translation missing
    if value is None:
        value = TRANSLATIONS.get('en', {}).get(key, key)

    # Handle string formatting with provided kwargs
    if kwargs:
        try:
            value = value.format(**kwargs)
        except (KeyError, ValueError):
            # Return unformatted if format fails
            pass

    return value


def get_column_translation(col_name, lang='en', country_code='MDG'):
    """
    Get translated column name for a specific country dataset

    Args:
        col_name: Original column name (English)
        lang: Language code ('en', 'fr', or 'pt')
        country_code: 3-letter country code ('MDG', 'MOZ', etc.)

    Returns:
        Translated column name or original if translation missing

    Examples:
        get_column_translation('Ag Cooling Demand Export Market', 'fr', 'MDG')
        → 'Demande Refroid. Agri. Marché Export'

        get_column_translation('Cashew Nut production', 'pt', 'MOZ')
        → 'Produção de Castanha de Caju'
    """
    # Validate language
    if lang not in ['en', 'fr', 'pt']:
        lang = 'en'

    if lang == 'en':
        return col_name

    # Return translated column name or fallback to original column name
    if country_code not in COLUMN_TRANSLATIONS:
        return col_name  # Country not loaded, fallback to original

    return COLUMN_TRANSLATIONS[country_code].get(lang, {}).get(col_name, col_name)


def get_spider_label_patterns(lang='en'):
    """
    Get patterns to strip from column names for spider chart labels

    These patterns are used to clean column names for display on polar axis labels.
    For example: 'Ag Cooling Potential Export Market' → 'Export Market'

    Args:
        lang: Language code ('en', 'fr', or 'pt')

    Returns:
        Dictionary of text patterns to remove from column names
    """
    if lang == 'fr':
        return {
            'ag': 'Potentiel Refroid. Agri. ',
            'fish': 'Potentiel Refroid. Pêche ',
            'prod_prefix': 'Production de ',
            'prod_suffix': ''
        }
    elif lang == 'pt':
        # Portuguese patterns
        return {
            'ag': 'Potencial Refrigeração Agri. ',
            'fish': 'Potencial Refrigeração Pesca ',
            'prod_prefix': 'Produção de ',
            'prod_suffix': ''
        }
    else:
        return {
            'ag': 'Ag Cooling Potential ',
            'fish': 'Fish Cooling Potential ',
            'prod_prefix': '',
            'prod_suffix': ' production'
        }


# Load UI translations on module import
load_translations()
# Note: Column translations are loaded per-country by each app using load_column_translations(country_code)
