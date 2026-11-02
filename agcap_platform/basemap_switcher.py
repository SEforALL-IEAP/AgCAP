"""
Basemap switcher shared by all country apps.

A thumbnail button in the bottom-left corner of the map that opens a grid of
basemap preview cards above it. Styles live in assets/basemap_switcher.css.

Previews are static images in assets/basemaps/<COUNTRY_CODE>/<style>.jpg, rendered
from Plotly's own MapLibre styles (a new country without its own set falls back to
the MDG previews).

The selector keeps the id 'basemap-dropdown' (with a 'value' property), so the
map callback that reads Input('basemap-dropdown', 'value') needs no changes.
"""
import json
from pathlib import Path

from dash import html, dcc, Input, Output

from translation_loader import t

DEFAULT_BASEMAP = 'open-street-map'
_PREVIEW_DIR = Path(__file__).resolve().parent.parent / 'assets' / 'basemaps'

# (MapLibre style value, translation key)
BASEMAPS = [
    ('open-street-map', 'basemap.streets'),
    ('carto-positron', 'basemap.light'),
    ('carto-voyager', 'basemap.voyager'),
    ('carto-darkmatter', 'basemap.dark'),
    ('satellite', 'basemap.satellite'),
    ('satellite-streets', 'basemap.hybrid'),
]


def _previews(app, country_code):
    folder = country_code if (_PREVIEW_DIR / country_code).is_dir() else 'MDG'
    return {value: app.get_asset_url(f'basemaps/{folder}/{value}.jpg') for value, _ in BASEMAPS}


def _thumb(src, img_id=None):
    return html.Div(html.Img(src=src, alt='', **({'id': img_id} if img_id else {})), className='bm-thumb')


def basemap_switcher(lang, app, country_code, default=DEFAULT_BASEMAP):
    """Map overlay component: toggle button + collapsible panel of basemap cards."""
    previews = _previews(app, country_code)
    options = [
        {
            'label': html.Div([_thumb(previews[value]), html.Span(t(key, lang), className='bm-name')],
                              className='bm-card'),
            'value': value,
        }
        for value, key in BASEMAPS
    ]
    return html.Div(id='basemap-switcher', children=[
        html.Button(
            [
                _thumb(previews[default], img_id='basemap-toggle-img'),
                html.Span(t('basemap.title', lang), className='bm-toggle-label'),
            ],
            id='basemap-toggle', n_clicks=0, title=t('basemap.title', lang),
        ),
        html.Div(
            dcc.RadioItems(
                id='basemap-dropdown', options=options, value=default,
                className='bm-options', labelClassName='bm-option', inputClassName='bm-input',
            ),
            id='basemap-panel', className='bm-panel',
        ),
    ])


def register_basemap_callbacks(app, country_code):
    """Open/close the panel and keep the toggle preview in sync with the selection."""
    previews_json = json.dumps(_previews(app, country_code))
    app.clientside_callback(
        """
        function(n_clicks, value) {
            var P = """ + previews_json + """;
            var trig = ((window.dash_clientside.callback_context || {}).triggered || []).map(function(t) { return t.prop_id; });
            var panel = document.getElementById('basemap-panel');
            var open = !!(panel && panel.classList.contains('open'));
            if (trig.some(function(p) { return p.indexOf('basemap-toggle') === 0; })) {
                open = !open;
            } else if (trig.some(function(p) { return p.indexOf('basemap-dropdown') === 0; })) {
                open = false;
            }
            return ['bm-panel' + (open ? ' open' : ''), P[value] || P['""" + DEFAULT_BASEMAP + """']];
        }
        """,
        [Output('basemap-panel', 'className'), Output('basemap-toggle-img', 'src')],
        Input('basemap-toggle', 'n_clicks'),
        Input('basemap-dropdown', 'value'),
    )
