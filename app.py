import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
import plotly.express as px
import requests
import json

# ══════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════
st.set_page_config(
    page_title='Cibloscope Mobilité',
    page_icon='🎯',
    layout='wide',
    initial_sidebar_state='expanded'
)

st.markdown("""
<style>
[data-testid="stMetricValue"] { font-size: 1.6rem; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# CHARGEMENT DONNÉES
# ══════════════════════════════════════════════════════════════
@st.cache_data
def load_data():
    df_score = pd.read_parquet('df_score_final.parquet')
    df_score['COMMUNE'] = df_score['COMMUNE'].astype(str).str.zfill(5)
    df_score['DEP']     = df_score['COMMUNE'].str[:2]

    df_vitaux = pd.read_parquet('df_vitaux_n2.parquet')

    dep_vitaux = pd.read_csv(
        'cibloscope_dep_population_vitale.csv', dtype={'DEP': str}
    )
    dep_vitaux['DEP'] = dep_vitaux['DEP'].str.zfill(2)

    df_mercato = pd.read_parquet('mercato_checkpoint.parquet')

    return df_score, df_vitaux, dep_vitaux, df_mercato


@st.cache_data
def load_geo():
    """Charge le GeoJSON communes sans geopandas."""
    GEO_URL = (
        'https://raw.githubusercontent.com/gregoiredavid/'
        'france-geojson/master/communes-version-simplifiee.geojson'
    )
    r = requests.get(GEO_URL, timeout=60)
    geojson = r.json()
    rows = [
        {
            'code': f['properties']['code'].zfill(5),
            'nom' : f['properties']['nom'],
        }
        for f in geojson['features']
    ]
    return pd.DataFrame(rows), geojson


# ── Chargement avec messages d'état ───────────────────────────
with st.spinner('Chargement des données...'):
    try:
        df_score, df_vitaux, dep_vitaux, df_mercato = load_data()
    except FileNotFoundError as e:
        st.error(f"""
**Fichier manquant : `{e.filename}`**

Uploadez dans le repo GitHub les fichiers suivants :
- `df_score_final.parquet`
- `df_vitaux_n2.parquet`
- `cibloscope_dep_population_vitale.csv`
- `mercato_checkpoint.parquet`
""")
        st.stop()

with st.spinner('Chargement de la carte...'):
    df_codes, geojson_raw = load_geo()

RATIO_CALIBRATION = 28_000_000 / max(len(df_score), 1)

# ══════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════
st.sidebar.title('🎯 Cibloscope Mobilité')
st.sidebar.caption('Ciblage des dépendances vitales à la voiture')

onglet = st.sidebar.radio(
    'Navigation',
    ['📊 Tableau de bord', '🗺️ Carte Cibloscope',
     '🔄 Mercato', '📋 Export'],
    label_visibility='collapsed'
)

st.sidebar.divider()
st.sidebar.subheader('Filtres')

seuil_pct = st.sidebar.slider(
    'Seuil prioritaire (percentile)',
    min_value=60, max_value=95, value=80, step=5
)

secteurs_dispo = ['Tous'] + sorted(
    df_vitaux['secteur_vital'].dropna().unique().tolist()
)
secteur_filtre = st.sidebar.selectbox('Secteur vital', secteurs_dispo)

deps_dispo = ['Tous'] + sorted(df_score['DEP'].unique().tolist())
dep_filtre = st.sidebar.selectbox('Département', deps_dispo)

st.sidebar.divider()
st.sidebar.caption(
    'Sources : INSEE MOBPRO 2022 · GTFS PAN · '
    'Ameli 2023 · Nemotron-Personas-France · Filosofi 2021'
)

# ══════════════════════════════════════════════════════════════
# SEGMENTATION DYNAMIQUE
# ══════════════════════════════════════════════════════════════
p_seuil = df_score['score'].quantile(seuil_pct / 100)
p50     = df_score['score'].quantile(0.50)

df_score['segment'] = np.where(
    df_score['score'] >= p_seuil, 'Prioritaire',
    np.where(df_score['score'] >= p50, 'Secondaire', 'Hors cible')
)

# Filtres
df_filtre = df_score.copy()
if dep_filtre != 'Tous':
    df_filtre = df_filtre[df_filtre['DEP'] == dep_filtre]

df_vitaux_filtre = df_vitaux.copy()
if secteur_filtre != 'Tous':
    df_vitaux_filtre = df_vitaux_filtre[
        df_vitaux_filtre['secteur_vital'] == secteur_filtre
    ]
if dep_filtre != 'Tous':
    df_vitaux_filtre = df_vitaux_filtre[
        df_vitaux_filtre['COMMUNE'].fillna('').str[:2] == dep_filtre
    ]

# ══════════════════════════════════════════════════════════════
# ONGLET 1 — TABLEAU DE BORD
# ══════════════════════════════════════════════════════════════
if onglet == '📊 Tableau de bord':

    st.title('📊 Tableau de bord Cibloscope')
    st.caption(
        'Contexte : crise Ormuz 2026 — pétrole 150$/baril — '
        'identification des travailleurs vitaux captifs'
    )

    n_prior   = (df_filtre['segment'] == 'Prioritaire').sum()
    act_prior = df_filtre[df_filtre['segment'] == 'Prioritaire']['w_total'].sum()
    act_total = df_filtre['w_total'].sum()
    n_vitaux_est = len(df_vitaux_filtre) * RATIO_CALIBRATION
    n_mercato_est = (
        df_mercato['deux_receptifs'].astype(bool).sum() * RATIO_CALIBRATION
        if 'deux_receptifs' in df_mercato.columns else 0
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric('🔴 Communes prioritaires',
              f'{n_prior:,}', f'Top {100 - seuil_pct}%')
    c2.metric('👷 Actifs prioritaires',
              f'{act_prior/1e6:.2f}M', f'/ {act_total/1e6:.1f}M total')
    c3.metric('🏥 Travailleurs vitaux captifs',
              f'{n_vitaux_est/1e6:.2f}M', 'estimation calibrée')
    c4.metric('🔄 Opportunités mercato',
              f'{n_mercato_est/1e3:.0f}k paires', 'intra + inter-DEP')

    st.divider()

    col_g1, col_g2 = st.columns(2)

    with col_g1:
        st.subheader('Distribution ICA')
        fig_hist = px.histogram(
            df_filtre, x='ica', nbins=50,
            color_discrete_sequence=['#e74c3c'],
            labels={'ica': 'Indice de Captivité Automobile'},
            title=f'{len(df_filtre):,} communes'
        )
        fig_hist.add_vline(
            x=df_filtre['ica'].quantile(seuil_pct / 100),
            line_dash='dash', line_color='orange',
            annotation_text=f'P{seuil_pct}'
        )
        fig_hist.update_layout(showlegend=False, height=350)
        st.plotly_chart(fig_hist, use_container_width=True)

    with col_g2:
        st.subheader('Secteurs vitaux')
        sc = (
            df_vitaux_filtre['secteur_vital']
            .value_counts().reset_index()
        )
        sc.columns = ['secteur', 'nb']
        sc['nb_k'] = (sc['nb'] * RATIO_CALIBRATION / 1000).round(0)
        fig_bar = px.bar(
            sc.head(10), x='nb_k', y='secteur', orientation='h',
            color='nb_k', color_continuous_scale='Reds',
            labels={'nb_k': 'Effectif estimé (k)', 'secteur': ''},
            title='Par secteur (milliers)'
        )
        fig_bar.update_layout(
            showlegend=False, height=350, coloraxis_showscale=False
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    st.subheader('Top 15 départements')
    dep_agg = (
        df_filtre.groupby('DEP')
        .agg(
            score_moy      = ('score',   'mean'),
            ica_moy        = ('ica',     'mean'),
            n_prioritaires = ('segment', lambda x: (x == 'Prioritaire').sum()),
            actifs         = ('w_total', 'sum'),
        )
        .reset_index()
        .nlargest(15, 'score_moy')
        .round(3)
    )
    st.dataframe(dep_agg, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════
# ONGLET 2 — CARTE
# ══════════════════════════════════════════════════════════════
elif onglet == '🗺️ Carte Cibloscope':

    st.title('🗺️ Carte Cibloscope')

    col_o1, col_o2 = st.columns(2)
    with col_o1:
        variable_carte = st.selectbox(
            'Variable',
            ['score', 'ica', 'svs'],
            format_func=lambda x: {
                'score': 'Score composite',
                'ica'  : 'ICA — Captivité automobile',
                'svs'  : 'SVS — Vitalité sectorielle',
            }[x]
        )
    with col_o2:
        n_max = st.slider('Nb communes (performance)', 500, 5000, 2000, 500)

    # Préparer les données carte
    df_carte = (
        df_filtre
        .nlargest(n_max, variable_carte)
        [['COMMUNE', variable_carte, 'segment', 'pct_voiture', 'w_total']]
        .copy()
    )

    # Filtrer le GeoJSON pour ne garder que les communes dans df_carte
    codes_carte = set(df_carte['COMMUNE'].tolist())
    score_map   = df_carte.set_index('COMMUNE')[variable_carte].to_dict()
    seg_map     = df_carte.set_index('COMMUNE')['segment'].to_dict()

    geojson_filtre = {
        'type': 'FeatureCollection',
        'features': [
            f for f in geojson_raw['features']
            if f['properties']['code'].zfill(5) in codes_carte
        ]
    }

    m = folium.Map(
        location=[46.6, 2.4],
        zoom_start=6 if dep_filtre == 'Tous' else 9,
        tiles='CartoDB positron'
    )

    folium.Choropleth(
        geo_data=geojson_filtre,
        data=df_carte,
        columns=['COMMUNE', variable_carte],
        key_on='feature.properties.code',
        fill_color='RdYlGn_r',
        fill_opacity=0.75,
        line_opacity=0.05,
        legend_name=variable_carte.upper(),
        nan_fill_color='#f0f0f0',
        bins=7
    ).add_to(m)

    folium.GeoJson(
        geojson_filtre,
        style_function=lambda x: {'fillOpacity': 0, 'weight': 0},
        highlight_function=lambda x: {'weight': 2, 'color': '#333'},
        tooltip=folium.GeoJsonTooltip(
            fields=['code', 'nom'],
            aliases=['Code', 'Commune'],
            sticky=True
        )
    ).add_to(m)

    st_folium(m, width='100%', height=550)

    st.subheader(f'Top 20 — {variable_carte.upper()}')
    cols_disp = [c for c in
                 ['COMMUNE', 'DEP', 'score', 'ica', 'svs',
                  'pct_voiture', 'w_total', 'segment']
                 if c in df_filtre.columns]
    st.dataframe(
        df_filtre.nlargest(20, variable_carte)[cols_disp].round(3),
        use_container_width=True, hide_index=True
    )


# ══════════════════════════════════════════════════════════════
# ONGLET 3 — MERCATO
# ══════════════════════════════════════════════════════════════
elif onglet == '🔄 Mercato':

    st.title('🔄 Algorithme Mercato')
    st.caption(
        'Échanges de postes entre travailleurs vitaux '
        'qui réduisent la distance domicile-travail des deux parties'
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        gain_min = st.slider('Gain minimum (km)', 5, 50, 10)
    with c2:
        filtre_receptifs = st.checkbox('Les deux réceptifs', value=False)
    with c3:
        cols_niveau = [c for c in ['niveau'] if c in df_mercato.columns]
        if cols_niveau:
            niveaux = ['Tous'] + sorted(df_mercato['niveau'].dropna().unique())
            niveau_filtre = st.selectbox('Niveau', niveaux)
        else:
            niveau_filtre = 'Tous'

    # Filtres
    df_m = df_mercato[df_mercato['gain_km'] >= gain_min].copy()
    if filtre_receptifs and 'deux_receptifs' in df_m.columns:
        df_m = df_m[df_m['deux_receptifs'] == True]
    if niveau_filtre != 'Tous' and 'niveau' in df_m.columns:
        df_m = df_m[df_m['niveau'] == niveau_filtre]
    if dep_filtre != 'Tous' and 'dep_a' in df_m.columns:
        df_m = df_m[df_m['dep_a'] == dep_filtre]
    if secteur_filtre != 'Tous' and 'secteur' in df_m.columns:
        df_m = df_m[df_m['secteur'] == secteur_filtre]

    km_eco = df_m['gain_km'].sum() * RATIO_CALIBRATION if len(df_m) else 0
    r1, r2, r3, r4 = st.columns(4)
    r1.metric('Paires viables', f'{len(df_m):,}')
    r2.metric('Gain moyen',
              f'{df_m["gain_km"].mean():.1f} km' if len(df_m) else '—')
    r3.metric('Les deux réceptifs',
              f'{df_m["deux_receptifs"].sum():,}'
              if len(df_m) and 'deux_receptifs' in df_m.columns else '—')
    r4.metric('Km éco/jour (extrapolé)',
              f'{km_eco/1e6:.1f}M' if km_eco else '—')

    st.divider()

    if len(df_m) > 0:
        col_g1, col_g2 = st.columns(2)

        with col_g1:
            if 'secteur' in df_m.columns:
                fig_s = px.box(
                    df_m, x='secteur', y='gain_km',
                    title='Gain par secteur',
                    labels={'gain_km': 'Gain (km)', 'secteur': ''}
                )
                fig_s.update_layout(showlegend=False, height=350)
                st.plotly_chart(fig_s, use_container_width=True)

        with col_g2:
            if 'niveau' in df_m.columns:
                fig_n = px.histogram(
                    df_m, x='gain_km', color='niveau', nbins=30,
                    title='Distribution gains N1 vs N2',
                    labels={'gain_km': 'Gain (km)'},
                    barmode='overlay', opacity=0.7
                )
                fig_n.update_layout(height=350)
                st.plotly_chart(fig_n, use_container_width=True)

        st.subheader(f'Top 50 paires ({len(df_m):,} résultats)')
        cols_aff = [c for c in [
            'secteur', 'niveau', 'dep_a', 'nom_commune_a', 'nom_commune_b',
            'gain_km', 'deux_receptifs', 'score_indiv_a', 'score_indiv_b'
        ] if c in df_m.columns]
        st.dataframe(
            df_m.nlargest(50, 'gain_km')[cols_aff].round(3),
            use_container_width=True, hide_index=True
        )
    else:
        st.info('Aucune paire ne correspond aux filtres.')


# ══════════════════════════════════════════════════════════════
# ONGLET 4 — EXPORT
# ══════════════════════════════════════════════════════════════
elif onglet == '📋 Export':

    st.title('📋 Export — Notes ministérielles')

    col_e1, col_e2 = st.columns(2)

    with col_e1:
        st.subheader('Score communes')
        cols_exp = [c for c in
                    ['COMMUNE', 'DEP', 'score', 'segment',
                     'ica', 'svs', 'pct_voiture', 'w_total']
                    if c in df_filtre.columns]
        df_exp_com = df_filtre[cols_exp].sort_values(
            'score', ascending=False
        ).round(3)
        st.dataframe(df_exp_com.head(20),
                     use_container_width=True, hide_index=True)
        st.download_button(
            '⬇️ CSV communes',
            data=df_exp_com.to_csv(index=False).encode('utf-8'),
            file_name='cibloscope_communes.csv',
            mime='text/csv'
        )

    with col_e2:
        st.subheader('Population vitale / département')
        dep_sort = dep_vitaux.sort_values(
            'n_vitaux_estimes', ascending=False
        )
        st.dataframe(dep_sort.head(20),
                     use_container_width=True, hide_index=True)
        st.download_button(
            '⬇️ CSV départements',
            data=dep_sort.to_csv(index=False).encode('utf-8'),
            file_name='cibloscope_departements.csv',
            mime='text/csv'
        )

    st.divider()
    st.subheader('Mercato complet')
    st.dataframe(
        df_mercato.sort_values('gain_km', ascending=False).head(30),
        use_container_width=True, hide_index=True
    )
    st.download_button(
        '⬇️ CSV mercato',
        data=df_mercato.to_csv(index=False).encode('utf-8'),
        file_name='mercato_complet.csv',
        mime='text/csv'
    )

    st.divider()
    st.subheader('Synthèse ministérielle')

    n_prior   = (df_score['segment'] == 'Prioritaire').sum()
    n_vit     = len(df_vitaux) * RATIO_CALIBRATION
    n_merc    = (
        df_mercato['deux_receptifs'].astype(bool).sum() * RATIO_CALIBRATION
        if 'deux_receptifs' in df_mercato.columns else 0
    )
    gain_tot  = df_mercato['gain_km'].sum() * RATIO_CALIBRATION

    synthese = f"""## Cibloscope Mobilité — Synthèse
*Contexte : crise Ormuz 2026, pétrole 150$/baril*

| Indicateur | Valeur |
|---|---|
| Communes prioritaires (top {100-seuil_pct}%) | {n_prior:,} |
| Travailleurs vitaux captifs estimés | {n_vit/1e6:.2f}M |
| Paires mercato viables (extrapolé) | {n_merc/1e3:.0f}k |
| Km économisés/jour si mercato activé | {gain_tot/1e6:.1f}M km |
| Litres carburant/jour économisés | {gain_tot*0.07/1e6:.1f}M L |

### Sources
INSEE MOBPRO 2022 · GTFS PAN · Ameli 2023 ·
Nemotron-Personas-France · Filosofi 2021
"""
    st.markdown(synthese)
    st.download_button(
        '⬇️ Synthèse Markdown',
        data=synthese.encode('utf-8'),
        file_name='cibloscope_synthese.md',
        mime='text/markdown'
    )
