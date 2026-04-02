import streamlit as st
import pandas as pd
import numpy as np
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

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
.metric-card {
    background: #f8f9fa;
    border-radius: 8px;
    padding: 1rem;
    border: 1px solid #e9ecef;
}
.metric-value { font-size: 2rem; font-weight: 600; color: #1a1a2e; }
.metric-label { font-size: 0.85rem; color: #6c757d; }
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

    dep_vitaux = pd.read_csv('cibloscope_dep_population_vitale.csv', dtype={'DEP': str})
    dep_vitaux['DEP'] = dep_vitaux['DEP'].str.zfill(2)

    df_mercato = pd.read_parquet('mercato_checkpoint.parquet')

    return df_score, df_vitaux, dep_vitaux, df_mercato

@st.cache_data
def load_geo():
    GEO_URL = ('https://raw.githubusercontent.com/gregoiredavid/'
               'france-geojson/master/communes-version-simplifiee.geojson')
    gdf = gpd.read_file(GEO_URL)
    gdf['code'] = gdf['code'].astype(str).str.zfill(5)
    return gdf

with st.spinner('Chargement des données...'):
    df_score, df_vitaux, dep_vitaux, df_mercato = load_data()
    gdf_communes = load_geo()

# ══════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════
st.sidebar.image(
    'https://upload.wikimedia.org/wikipedia/commons/thumb/c/c3/'
    'Flag_of_France.svg/320px-Flag_of_France.svg.png',
    width=60
)
st.sidebar.title('🎯 Cibloscope Mobilité')
st.sidebar.caption('Outil de ciblage des dépendances vitales à la voiture')

onglet = st.sidebar.radio(
    'Navigation',
    ['📊 Tableau de bord', '🗺️ Carte Cibloscope',
     '🔄 Mercato', '📋 Export'],
    label_visibility='collapsed'
)

st.sidebar.divider()
st.sidebar.subheader('Filtres')

# Filtre seuil prioritaire
seuil_pct = st.sidebar.slider(
    'Seuil prioritaire (percentile)',
    min_value=60, max_value=95, value=80, step=5,
    help='Top X% des communes les plus captives'
)

# Filtre secteur
secteurs_dispo = ['Tous'] + sorted(df_vitaux['secteur_vital'].unique().tolist())
secteur_filtre = st.sidebar.selectbox('Secteur vital', secteurs_dispo)

# Filtre département
deps_dispo = ['Tous'] + sorted(df_score['DEP'].unique().tolist())
dep_filtre = st.sidebar.selectbox('Département', deps_dispo)

st.sidebar.divider()
st.sidebar.caption(
    'Sources : INSEE MOBPRO 2021 · GTFS PAN · Ameli 2023 · '
    'Nvidia Nemotron-Personas-France · Filosofi 2021'
)

# ══════════════════════════════════════════════════════════════
# CALCUL SEGMENTATION DYNAMIQUE
# ══════════════════════════════════════════════════════════════
p_seuil = df_score['score'].quantile(seuil_pct / 100)
p50     = df_score['score'].quantile(0.50)

df_score['segment'] = np.where(
    df_score['score'] >= p_seuil, 'Prioritaire',
    np.where(df_score['score'] >= p50, 'Secondaire', 'Hors cible')
)

# Application filtres
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
        df_vitaux_filtre['COMMUNE'].str[:2] == dep_filtre
    ]

# ══════════════════════════════════════════════════════════════
# ONGLET 1 — TABLEAU DE BORD
# ══════════════════════════════════════════════════════════════
if onglet == '📊 Tableau de bord':

    st.title('📊 Tableau de bord Cibloscope')
    st.caption(f'Contexte : crise Ormuz 2026 — pétrole 150$/baril — '
               f'identification des travailleurs vitaux captifs')

    # ─── KPIs ──────────────────────────────────────────────────
    n_prior     = (df_filtre['segment'] == 'Prioritaire').sum()
    n_sec       = (df_filtre['segment'] == 'Secondaire').sum()
    act_prior   = df_filtre[df_filtre['segment']=='Prioritaire']['w_total'].sum()
    act_total   = df_filtre['w_total'].sum()
    RATIO       = 28_000_000 / len(df_score)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric('🔴 Communes prioritaires',
                  f'{n_prior:,}',
                  f'Top {100 - seuil_pct}%')
    with col2:
        st.metric('👷 Actifs prioritaires (estimés)',
                  f'{act_prior/1e6:.2f}M',
                  f'sur {act_total/1e6:.1f}M total')
    with col3:
        n_vitaux_est = len(df_vitaux_filtre) * RATIO
        st.metric('🏥 Travailleurs vitaux captifs',
                  f'{n_vitaux_est/1e6:.2f}M',
                  'estimation calibrée')
    with col4:
        n_mercato = (df_mercato['deux_receptifs'] == True).sum() * RATIO
        st.metric('🔄 Opportunités mercato',
                  f'{n_mercato/1e3:.0f}k paires',
                  'intra + inter-DEP')

    st.divider()

    # ─── Graphiques ────────────────────────────────────────────
    col_g1, col_g2 = st.columns(2)

    with col_g1:
        st.subheader('Distribution des scores ICA')
        fig_hist = px.histogram(
            df_filtre, x='ica', nbins=50,
            color_discrete_sequence=['#e74c3c'],
            labels={'ica': 'Indice de Captivité Automobile', 'count': 'Nb communes'},
            title=f'Distribution ICA — {len(df_filtre):,} communes'
        )
        fig_hist.add_vline(
            x=df_filtre['ica'].quantile(seuil_pct/100),
            line_dash='dash', line_color='orange',
            annotation_text=f'P{seuil_pct}'
        )
        fig_hist.update_layout(showlegend=False, height=350)
        st.plotly_chart(fig_hist, use_container_width=True)

    with col_g2:
        st.subheader('Secteurs vitaux détectés')
        secteur_counts = (
            df_vitaux_filtre['secteur_vital']
            .value_counts()
            .reset_index()
        )
        secteur_counts.columns = ['secteur', 'nb_personas']
        secteur_counts['nb_estimes'] = (
            secteur_counts['nb_personas'] * RATIO / 1000
        ).round(0)

        fig_bar = px.bar(
            secteur_counts.head(10),
            x='nb_estimes', y='secteur',
            orientation='h',
            color='nb_estimes',
            color_continuous_scale='Reds',
            labels={'nb_estimes': 'Effectif estimé (k)', 'secteur': ''},
            title='Travailleurs vitaux par secteur (milliers)'
        )
        fig_bar.update_layout(
            showlegend=False, height=350,
            coloraxis_showscale=False
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    # ─── Top départements ──────────────────────────────────────
    st.subheader('Top 15 départements — score Cibloscope moyen')
    dep_agg = (
        df_filtre.groupby('DEP')
        .agg(
            score_moy     = ('score',   'mean'),
            ica_moy       = ('ica',     'mean'),
            n_prioritaires= ('segment', lambda x: (x=='Prioritaire').sum()),
            actifs        = ('w_total', 'sum'),
        )
        .reset_index()
        .nlargest(15, 'score_moy')
        .round(3)
    )
    st.dataframe(
        dep_agg.rename(columns={
            'DEP': 'Département', 'score_moy': 'Score moy',
            'ica_moy': 'ICA moy', 'n_prioritaires': 'Communes prioritaires',
            'actifs': 'Actifs'
        }),
        use_container_width=True, hide_index=True
    )

# ══════════════════════════════════════════════════════════════
# ONGLET 2 — CARTE
# ══════════════════════════════════════════════════════════════
elif onglet == '🗺️ Carte Cibloscope':

    st.title('🗺️ Carte Cibloscope — Captivité automobile par commune')

    col_opt1, col_opt2 = st.columns(2)
    with col_opt1:
        variable_carte = st.selectbox(
            'Variable à afficher',
            ['score', 'ica', 'svs', 'cf'],
            format_func=lambda x: {
                'score': 'Score Cibloscope composite',
                'ica'  : 'ICA — Indice de Captivité Automobile',
                'svs'  : 'SVS — Score Vitalité Sectorielle',
                'cf'   : 'CF — Capacité de Financement (inversée)',
            }[x]
        )
    with col_opt2:
        n_communes_affichees = st.slider(
            'Nb communes affichées (performance)',
            min_value=1000, max_value=10000,
            value=3000, step=500
        )

    # Merge avec géométries
    df_carte = df_filtre.nlargest(n_communes_affichees, variable_carte)
    gdf_carte = gdf_communes.merge(
        df_carte[['COMMUNE', variable_carte, 'segment', 'pct_voiture', 'w_total']],
        left_on='code', right_on='COMMUNE', how='inner'
    )

    # Construction carte Folium
    lat_centre = 46.6 if dep_filtre == 'Tous' else \
        df_filtre.merge(
            gdf_communes[['code']].assign(
                lat=gdf_communes.geometry.centroid.y,
                lon=gdf_communes.geometry.centroid.x
            ), left_on='COMMUNE', right_on='code', how='left'
        )['lat'].mean()

    m = folium.Map(
        location=[46.6, 2.4],
        zoom_start=6 if dep_filtre == 'Tous' else 9,
        tiles='CartoDB positron'
    )

    folium.Choropleth(
        geo_data=gdf_carte[['geometry','code']].to_json(),
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
        gdf_carte[['geometry','nom','code',variable_carte,
                   'segment','pct_voiture','w_total']].to_json(),
        style_function=lambda x: {'fillOpacity':0,'weight':0},
        highlight_function=lambda x: {'weight':2,'color':'#333'},
        tooltip=folium.GeoJsonTooltip(
            fields=['nom','segment',variable_carte,'pct_voiture','w_total'],
            aliases=['Commune','Segment','Score','% voiture','Actifs'],
            localize=False, sticky=True
        )
    ).add_to(m)

    st_folium(m, width='100%', height=550)

    # Tableau sous la carte
    st.subheader(f'Top 20 communes — {variable_carte.upper()} le plus élevé')
    top20 = (
        df_filtre.nlargest(20, variable_carte)
        [['COMMUNE','DEP','score','ica','svs','pct_voiture','w_total','segment']]
        .round(3)
    )
    st.dataframe(top20, use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════
# ONGLET 3 — MERCATO
# ══════════════════════════════════════════════════════════════
elif onglet == '🔄 Mercato':

    st.title('🔄 Algorithme Mercato')
    st.caption(
        'Identification des échanges de postes entre travailleurs vitaux '
        'qui réduisent la distance domicile-travail des deux parties'
    )

    # ─── Filtres mercato ───────────────────────────────────────
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        gain_min = st.slider('Gain minimum (km)', 5, 50, 10)
    with col_f2:
        filtre_receptifs = st.checkbox('Les deux réceptifs uniquement', value=False)
    with col_f3:
        niveau_filtre = st.selectbox(
            'Niveau',
            ['Tous', 'intra_employeur', 'inter_departemental']
        )

    # Application filtres
    df_m = df_mercato[df_mercato['gain_km'] >= gain_min].copy()
    if filtre_receptifs:
        df_m = df_m[df_m['deux_receptifs'] == True]
    if niveau_filtre != 'Tous':
        df_m = df_m[df_m['niveau'] == niveau_filtre]
    if dep_filtre != 'Tous':
        df_m = df_m[df_m['dep_a'] == dep_filtre]
    if secteur_filtre != 'Tous':
        df_m = df_m[df_m['secteur'] == secteur_filtre]

    # ─── KPIs mercato ──────────────────────────────────────────
    RATIO = 28_000_000 / len(df_score)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric('Paires viables', f'{len(df_m):,}')
    with c2:
        st.metric('Gain moyen', f'{df_m["gain_km"].mean():.1f} km' if len(df_m) else '—')
    with c3:
        st.metric('Les deux réceptifs',
                  f'{df_m["deux_receptifs"].sum():,}' if len(df_m) else '—')
    with c4:
        km_eco = df_m['gain_km'].sum() * RATIO
        st.metric('Km éco/jour (extrapolé)',
                  f'{km_eco/1e6:.1f}M' if len(df_m) else '—')

    st.divider()

    col_g1, col_g2 = st.columns(2)

    with col_g1:
        st.subheader('Gain par secteur')
        if len(df_m) > 0:
            fig_sect = px.box(
                df_m, x='secteur', y='gain_km',
                color='secteur',
                labels={'gain_km': 'Gain (km)', 'secteur': ''},
                title='Distribution des gains par secteur'
            )
            fig_sect.update_layout(showlegend=False, height=350)
            st.plotly_chart(fig_sect, use_container_width=True)

    with col_g2:
        st.subheader('Gain par niveau')
        if len(df_m) > 0:
            fig_niv = px.histogram(
                df_m, x='gain_km', color='niveau',
                nbins=30,
                labels={'gain_km': 'Gain (km)', 'count': 'Nb paires'},
                title='Distribution des gains — N1 vs N2',
                barmode='overlay', opacity=0.7
            )
            fig_niv.update_layout(height=350)
            st.plotly_chart(fig_niv, use_container_width=True)

    # ─── Table des meilleures paires ──────────────────────────
    st.subheader(f'Top 50 meilleures paires ({len(df_m):,} résultats filtrés)')

    if len(df_m) > 0:
        cols_affich = [c for c in [
            'secteur','niveau','dep_a','nom_commune_a','nom_commune_b',
            'gain_km','deux_receptifs','score_indiv_a','score_indiv_b'
        ] if c in df_m.columns]

        st.dataframe(
            df_m.nlargest(50, 'gain_km')[cols_affich]
            .round(3),
            use_container_width=True, hide_index=True
        )
    else:
        st.info('Aucune paire ne correspond aux filtres sélectionnés.')

# ══════════════════════════════════════════════════════════════
# ONGLET 4 — EXPORT
# ══════════════════════════════════════════════════════════════
elif onglet == '📋 Export':

    st.title('📋 Export — Notes ministérielles')
    st.caption('Générez les fichiers pour les contributions ministérielles (délai : 8 avril)')

    col_e1, col_e2 = st.columns(2)

    with col_e1:
        st.subheader('📊 Score Cibloscope communes')
        df_export_communes = df_filtre[[
            'COMMUNE','DEP','score','segment',
            'ica','svs','cf','pct_voiture','w_total'
        ]].sort_values('score', ascending=False).round(3)

        st.dataframe(df_export_communes.head(20),
                     use_container_width=True, hide_index=True)

        csv_communes = df_export_communes.to_csv(index=False).encode('utf-8')
        st.download_button(
            '⬇️  Télécharger CSV communes',
            data=csv_communes,
            file_name='cibloscope_communes_export.csv',
            mime='text/csv'
        )

    with col_e2:
        st.subheader('🏥 Population vitale par département')
        df_export_dep = dep_vitaux.sort_values(
            'n_vitaux_estimes', ascending=False
        )
        st.dataframe(df_export_dep.head(20),
                     use_container_width=True, hide_index=True)

        csv_dep = df_export_dep.to_csv(index=False).encode('utf-8')
        st.download_button(
            '⬇️  Télécharger CSV départements',
            data=csv_dep,
            file_name='cibloscope_departements_export.csv',
            mime='text/csv'
        )

    st.divider()
    st.subheader('🔄 Opportunités mercato')

    df_mercato_export = df_mercato.sort_values('gain_km', ascending=False)
    st.dataframe(df_mercato_export.head(30),
                 use_container_width=True, hide_index=True)

    csv_mercato = df_mercato_export.to_csv(index=False).encode('utf-8')
    st.download_button(
        '⬇️  Télécharger CSV mercato complet',
        data=csv_mercato,
        file_name='mercato_complet_export.csv',
        mime='text/csv'
    )

    st.divider()
    st.subheader('📝 Synthèse chiffrée — Note ministérielle')

    RATIO = 28_000_000 / len(df_score)
    n_prior = (df_score['segment'] == 'Prioritaire').sum()
    n_vitaux_total = len(df_vitaux) * RATIO
    n_mercato_total = (df_mercato['deux_receptifs']==True).sum() * RATIO
    gain_total = df_mercato['gain_km'].sum() * RATIO

    synthese = f"""
## Cibloscope Mobilité — Synthèse pour note ministérielle
*Contexte : crise Ormuz 2026, pétrole 150$/baril*

### Résultats principaux

| Indicateur | Valeur |
|---|---|
| Communes prioritaires (top {100-seuil_pct}%) | {n_prior:,} |
| Travailleurs vitaux captifs estimés | {n_vitaux_total/1e6:.2f}M |
| Paires mercato viables (extrapolé) | {n_mercato_total/1e3:.0f}k |
| Km économisés/jour si mercato activé | {gain_total/1e6:.1f}M km |
| Litres carburant économisés/jour | {gain_total*0.07/1e6:.1f}M L |

### Sources
- INSEE MOBPRO 2021 — flux domicile-travail
- GTFS PAN transport.data.gouv.fr — couverture TC réelle
- Ameli 2023 — auxiliaires médicaux libéraux
- Nvidia Nemotron-Personas-France — population synthétique
- Filosofi 2021 — revenus médians communes
"""
    st.markdown(synthese)
    st.download_button(
        '⬇️  Télécharger synthèse Markdown',
        data=synthese.encode('utf-8'),
        file_name='cibloscope_synthese_ministerielle.md',
        mime='text/markdown'
    )
