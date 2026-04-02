import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
import plotly.express as px
import requests

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
.explication {
    background: #f0f4ff;
    border-left: 4px solid #4a6cf7;
    padding: 0.8rem 1rem;
    border-radius: 0 6px 6px 0;
    margin: 0.5rem 0 1rem 0;
    font-size: 0.92rem;
    line-height: 1.6;
}
.lexique {
    background: #fff8e1;
    border-left: 4px solid #f59e0b;
    padding: 0.8rem 1rem;
    border-radius: 0 6px 6px 0;
    margin: 0.5rem 0 1rem 0;
    font-size: 0.92rem;
}
.alerte {
    background: #fff0f0;
    border-left: 4px solid #e74c3c;
    padding: 0.8rem 1rem;
    border-radius: 0 6px 6px 0;
    margin: 0.5rem 0;
    font-size: 0.92rem;
}
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
    df_vitaux   = pd.read_parquet('df_vitaux_n2.parquet')
    dep_vitaux  = pd.read_csv('cibloscope_dep_population_vitale.csv', dtype={'DEP': str})
    dep_vitaux['DEP'] = dep_vitaux['DEP'].str.zfill(2)
    df_mercato  = pd.read_parquet('mercato_checkpoint.parquet')
    return df_score, df_vitaux, dep_vitaux, df_mercato


@st.cache_data
def load_geo():
    GEO_URL = ('https://raw.githubusercontent.com/gregoiredavid/'
               'france-geojson/master/communes-version-simplifiee.geojson')
    r = requests.get(GEO_URL, timeout=60)
    geojson = r.json()
    rows = [{'code': f['properties']['code'].zfill(5),
              'nom': f['properties']['nom']}
            for f in geojson['features']]
    return pd.DataFrame(rows), geojson


with st.spinner('Chargement des données...'):
    try:
        df_score, df_vitaux, dep_vitaux, df_mercato = load_data()
    except FileNotFoundError as e:
        st.error(f"**Fichier manquant : `{e.filename}`** — vérifiez que tous les fichiers .parquet et .csv sont dans le repo GitHub.")
        st.stop()

with st.spinner('Chargement de la carte...'):
    df_codes, geojson_raw = load_geo()

RATIO_CALIBRATION = 28_000_000 / max(len(df_score), 1)


# ══════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════
st.sidebar.title('🎯 Cibloscope Mobilité')
st.sidebar.caption('Outil de ciblage des dépendances vitales à la voiture')

st.sidebar.markdown("""
**Navigation**
""")
onglet = st.sidebar.radio(
    'Navigation',
    ['📖 Guide de lecture', '📊 Tableau de bord',
     '🗺️ Carte Cibloscope', '🔄 Mercato', '📋 Export'],
    label_visibility='collapsed'
)

st.sidebar.divider()
st.sidebar.subheader('⚙️ Paramètres')

seuil_pct = st.sidebar.slider(
    'Seuil "Prioritaire" (percentile)',
    min_value=60, max_value=95, value=80, step=5,
    help='P80 = top 20% des communes les plus captives. Ajustez selon le budget disponible.'
)
st.sidebar.caption(
    f"Les communes au-dessus du P{seuil_pct} sont classées **Prioritaires** "
    f"({100 - seuil_pct}% les plus exposées)."
)

st.sidebar.divider()
st.sidebar.subheader('🔍 Filtres')

secteurs_dispo = ['Tous'] + sorted(df_vitaux['secteur_vital'].dropna().unique().tolist())
secteur_filtre = st.sidebar.selectbox('Secteur vital', secteurs_dispo,
    help='Filtrer l\'analyse sur un secteur d\'emploi vital spécifique.')

deps_dispo = ['Tous'] + sorted(df_score['DEP'].unique().tolist())
dep_filtre = st.sidebar.selectbox('Département', deps_dispo,
    help='Zoomer sur un département. "Tous" = France entière.')

st.sidebar.divider()
st.sidebar.markdown("""
**📚 Sources de données**
- INSEE MOBPRO 2022 — flux domicile-travail
- GTFS PAN — arrêts transport en commun
- Ameli 2023 — soignants libéraux
- Nemotron-Personas-France (Nvidia)
- Filosofi 2021 — revenus par commune
""")


# ══════════════════════════════════════════════════════════════
# SEGMENTATION DYNAMIQUE
# ══════════════════════════════════════════════════════════════
p_seuil = df_score['score'].quantile(seuil_pct / 100)
p50     = df_score['score'].quantile(0.50)

df_score['segment'] = np.where(
    df_score['score'] >= p_seuil, 'Prioritaire',
    np.where(df_score['score'] >= p50, 'Secondaire', 'Hors cible')
)

df_filtre = df_score.copy()
if dep_filtre != 'Tous':
    df_filtre = df_filtre[df_filtre['DEP'] == dep_filtre]

df_vitaux_filtre = df_vitaux.copy()
if secteur_filtre != 'Tous':
    df_vitaux_filtre = df_vitaux_filtre[df_vitaux_filtre['secteur_vital'] == secteur_filtre]
if dep_filtre != 'Tous':
    df_vitaux_filtre = df_vitaux_filtre[df_vitaux_filtre['COMMUNE'].fillna('').str[:2] == dep_filtre]


# ══════════════════════════════════════════════════════════════
# ONGLET 0 — GUIDE DE LECTURE
# ══════════════════════════════════════════════════════════════
if onglet == '📖 Guide de lecture':

    st.title('📖 Guide de lecture — Cibloscope Mobilité')

    st.markdown("""
    > **Cibloscope Mobilité** est un outil d'analyse territoriale qui identifie
    > les travailleurs français dont la mobilité professionnelle est **structurellement
    > dépendante de la voiture**, et pour qui un choc sur le prix du carburant
    > représente une menace directe sur leur capacité à exercer un emploi vital pour la société.
    """)

    st.divider()

    # ── Pourquoi cet outil ────────────────────────────────────
    st.header('🎯 Pourquoi cet outil ?')

    st.markdown("""
    Lors de la crise énergétique liée à la guerre en Ukraine en 2022, la France a versé
    **8 milliards d'euros de chèques carburant** à l'ensemble de la population sans
    aucun ciblage. Une grande partie de cette aide a bénéficié à des ménages qui n'en
    avaient pas besoin — ménages urbains avec accès aux transports en commun, hauts revenus,
    télétravailleurs.

    Face à un nouveau choc pétrolier (pétrole à 150$/baril dans le contexte de la crise
    Ormuz 2026), l'État ne peut plus se permettre ce saupoudrage. Il faut répondre à
    une question précise :
    """)

    st.markdown("""
    <div class="alerte">
    <strong>Question centrale</strong> : Qui, précisément, ne peut pas se passer de sa voiture
    pour exercer un emploi dont la société ne peut pas se passer ?
    <br><br>
    Exemple concret : une infirmière libérale en zone rurale qui fait 15 visites à domicile
    par jour dans un rayon de 30 km, sans aucun transport en commun disponible,
    avec un revenu de 2 200 €/mois. Si le gazole passe à 3€/litre, elle ne peut
    ni arrêter de travailler, ni changer de mode de transport, ni déménager.
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # ── Le score Cibloscope ───────────────────────────────────
    st.header('🧮 Le score Cibloscope — comment il est calculé')

    st.markdown("""
    Chaque commune reçoit un score composite entre 0 et 1, calculé à partir de
    trois dimensions indépendantes :
    """)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("""
        <div class="lexique">
        <strong>🚗 ICA — Indice de Captivité Automobile</strong>
        <br>Poids : 45%
        <br><br>
        Mesure la dépendance structurelle à la voiture dans une commune.
        Il combine :
        <ul>
        <li>le <strong>% de travailleurs utilisant la voiture</strong>
        (calculé à partir des flux domicile-travail INSEE 2022)</li>
        <li>la <strong>présence ou absence d'arrêts TC dans un rayon de 800m</strong>
        (données GTFS nationales)</li>
        </ul>
        <br>
        <strong>Exemple :</strong> Une commune rurale de Corrèze où 92% des actifs
        vont au travail en voiture et qui n'a aucun arrêt de bus dans un rayon
        de 5 km → ICA ≈ 0.88 (zone rouge).<br><br>
        Une commune de banlieue parisienne avec RER → ICA ≈ 0.30 (zone verte).
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown("""
        <div class="lexique">
        <strong>🏥 SVS — Score de Vitalité Sectorielle</strong>
        <br>Poids : 35%
        <br><br>
        Mesure l'importance des secteurs d'emploi <em>vitaux</em> dans la commune.
        Un secteur est vital s'il ne peut pas s'arrêter sans mettre en danger
        la population.
        <br><br>
        <strong>Secteurs vitaux identifiés :</strong>
        <ul>
        <li>Santé à domicile (IDEL, aides-soignants)</li>
        <li>Agriculture et élevage</li>
        <li>Transport de fret alimentaire</li>
        <li>Énergie et réseaux (eau, électricité)</li>
        <li>Sécurité (pompiers, gendarmes)</li>
        </ul>
        <strong>Source :</strong> Ameli 2023 (auxiliaires médicaux)
        + NLP sur population synthétique Nemotron.
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown("""
        <div class="lexique">
        <strong>💶 CF — Capacité de Financement (inversée)</strong>
        <br>Poids : 20%
        <br><br>
        Mesure le <em>besoin d'aide</em> financière d'une commune.
        C'est l'inverse du revenu médian : plus le revenu est faible,
        plus le CF est élevé, plus le besoin de soutien est fort.
        <br><br>
        <strong>Source :</strong> Filosofi 2021 (revenus disponibles médians
        par commune, DGFiP).
        <br><br>
        <strong>Exemple :</strong> Une commune ouvrière en Zone de Revitalisation
        Rurale avec un revenu médian de 16 000 €/an → CF ≈ 0.75.<br>
        Une commune résidentielle aisée avec 35 000 €/an → CF ≈ 0.15.
        </div>
        """, unsafe_allow_html=True)

    st.markdown("""
    <div class="explication">
    <strong>Formule finale :</strong>
    <code>Score = ICA × 0.45 + SVS × 0.35 + CF × 0.20</code>
    <br><br>
    Les pondérations reflètent la priorité donnée à la <em>dépendance structurelle</em>
    (ICA) avant la <em>nature de l'emploi</em> (SVS) et la <em>situation financière</em> (CF).
    Elles peuvent être ajustées selon les priorités politiques.
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # ── Segmentation ──────────────────────────────────────────
    st.header('🏷️ Les trois segments')

    seg1, seg2, seg3 = st.columns(3)
    with seg1:
        st.markdown("""
        <div class="alerte">
        <strong>🔴 Prioritaire</strong> — Top 20% (réglable)<br><br>
        Communes combinant forte captivité automobile, secteurs vitaux présents
        et revenus faibles. Ce sont les communes où un choc carburant crée
        une urgence sociale immédiate.<br><br>
        <em>Action recommandée :</em> ciblage des aides directes, déploiement
        prioritaire de VE en location, stations bioGNV.
        </div>
        """, unsafe_allow_html=True)
    with seg2:
        st.markdown("""
        <div class="lexique">
        <strong>🟡 Secondaire</strong> — P50 à P80<br><br>
        Communes avec dépendance réelle mais moins critique. Peuvent bénéficier
        d'actions indirectes (covoiturage organisé, bonus sur le coût des
        transports en commun périphériques).<br><br>
        <em>Action recommandée :</em> mercato professionnel, incitations
        au covoiturage, amélioration desserte TC.
        </div>
        """, unsafe_allow_html=True)
    with seg3:
        st.markdown("""
        <div class="explication">
        <strong>🟢 Hors cible</strong> — En dessous de P50<br><br>
        Communes avec alternatives modales disponibles ou emplois non vitaux.
        Ne pas cibler ces communes permet d'économiser des ressources
        publiques rares.<br><br>
        <em>Exemples typiques :</em> Paris, Lyon, grandes métropoles
        avec TC dense, communes résidentielles aisées proches des centres.
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # ── Le Mercato ────────────────────────────────────────────
    st.header('🔄 L\'algorithme Mercato — qu\'est-ce que c\'est ?')

    st.markdown("""
    Le **Mercato** est inspiré de la startup 1km à pied. L'idée est simple :
    dans une grande organisation avec plusieurs sites, deux employés peuvent
    **échanger leurs postes** si chacun habite plus près du site de l'autre.
    Les deux réduisent leur trajet, sans que l'organisation change d'effectifs.
    """)

    st.markdown("""
    <div class="explication">
    <strong>Exemple concret :</strong><br>
    — Marie est infirmière libérale, habite à Clermont-Ferrand,
    couvre le secteur de Riom (25 km nord).<br>
    — Sophie est infirmière libérale, habite à Riom,
    couvre le secteur de Clermont-Ferrand (25 km sud).<br><br>
    Si Marie et Sophie échangent leurs zones de patientèle, chacune travaille
    désormais à 5 km de chez elle au lieu de 25 km.
    <strong>Gain total : 40 km/jour × 220 jours = 8 800 km/an économisés.</strong><br>
    Cela représente environ 880 litres de carburant et 700 kg de CO₂ par an,
    pour une dépense publique de zéro euro.
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    **Deux niveaux sont analysés :**
    - **Niveau 1 (intra-employeur)** : deux personnes dans le même secteur et le même
    département → échange de site ou de zone.
    - **Niveau 2 (inter-départemental)** : deux personnes dans des départements voisins
    (< 80 km entre centroïdes) → l'une travaille "de l'autre côté de la frontière".

    Le signal de **réceptivité** est détecté automatiquement par analyse NLP :
    les travailleurs qui expriment un souhait de rapprochement domicile/travail
    dans leurs objectifs de carrière sont marqués comme "réceptifs".
    Ces paires sont prioritaires pour la mise en relation.
    """)

    st.divider()

    # ── Sources ───────────────────────────────────────────────
    st.header('📚 Sources de données utilisées')

    sources = {
        'INSEE MOBPRO 2022': (
            'Fichier des flux de mobilité domicile-travail entre communes. '
            'Contient le nombre d\'actifs se déplaçant de la commune A vers la commune B. '
            'Utilisé pour calculer les distances typiques de navette par commune. '
            '**Limite :** ce fichier est agrégé — il ne contient pas le mode de transport '
            'individuel (voiture/TC). On utilise un modèle statistique basé sur la distance '
            '(Enquête Nationale Transports 2019) pour estimer la probabilité d\'usage de la voiture.'
        ),
        'GTFS national (transport.data.gouv.fr)': (
            'Liste de tous les arrêts de transports en commun recensés en France '
            '(bus, tram, métro, cars interurbains). '
            'On calcule un buffer de 800m autour de chaque arrêt — distance maximale '
            'de marche généralement acceptée pour rejoindre un TC. '
            'Une commune dont le centroïde est dans ce buffer est considérée "couverte". '
            '**Résultat :** 40% des communes françaises ont un arrêt TC à moins de 800m.'
        ),
        'Ameli 2023 (Assurance Maladie)': (
            'Effectifs des auxiliaires médicaux libéraux par département '
            '(infirmiers, kinésithérapeutes, orthophonistes, etc.). '
            'Données désagrégées à la commune par pondération sur la population active. '
            '**Limite :** données au département, pas à la commune directement. '
            'La V2 intégrera le RPPS (Répertoire Partagé des Professionnels de Santé) '
            'qui donne la localisation exacte de chaque professionnel.'
        ),
        'Filosofi 2021 (DGFiP / INSEE)': (
            'Revenu disponible médian par unité de consommation, par commune. '
            'Dernière édition disponible — la série a été interrompue par INSEE '
            'en raison de la suppression de la taxe d\'habitation. '
            'Utilisé pour calculer la composante CF (Capacité de Financement).'
        ),
        'Nemotron-Personas-France (Nvidia / HuggingFace)': (
            '1 million de personas synthétiques représentatifs de la population active française, '
            'distribués géographiquement selon les données INSEE réelles. '
            'Chaque persona a un profil professionnel détaillé, une commune de résidence, '
            'des compétences et des objectifs de carrière. '
            'Utilisé pour simuler la population vitale et détecter les signaux mercato. '
            '**Note :** les personas sont synthétiques — aucune donnée personnelle réelle. '
            'Licence CC-BY 4.0.'
        ),
    }

    for source, description in sources.items():
        with st.expander(f'📂 {source}'):
            st.markdown(description)

    st.divider()

    st.header('⚠️ Limites de l\'outil')
    st.markdown("""
    Cibloscope est un **POC (Proof of Concept)** — il démontre la faisabilité
    de l'approche avec des données open data. Plusieurs améliorations sont
    nécessaires avant un déploiement opérationnel :

    | Limite actuelle | Solution V2 |
    |---|---|
    | ICA calculé par proxy distance (modèle ENTD) | Utiliser la variable TRANS du fichier détail MOBPRO individuel |
    | SVS basé sur Ameli département + NLP | Intégrer SIRENE (employeurs réels) + MSA (agricoles) |
    | Nemotron en échantillon 200k (limite RAM) | Colab Pro (25GB RAM) pour traiter 1M complets |
    | Granularité commune (35k mailles) | Passer à l'échelle IRIS (50k mailles) |
    | CF avec Filosofi 2021 (dernier millésime) | Attendre la reprise de la série INSEE |
    """)


# ══════════════════════════════════════════════════════════════
# ONGLET 1 — TABLEAU DE BORD
# ══════════════════════════════════════════════════════════════
elif onglet == '📊 Tableau de bord':

    st.title('📊 Tableau de bord Cibloscope')

    st.markdown("""
    <div class="explication">
    Ce tableau de bord présente la synthèse nationale de l'analyse.
    Utilisez les filtres dans la barre latérale pour zoomer sur un département
    ou un secteur vital spécifique. Le seuil "Prioritaire" est ajustable :
    P80 = top 20% des communes les plus exposées, P90 = top 10% (ciblage plus strict).
    </div>
    """, unsafe_allow_html=True)

    n_prior      = (df_filtre['segment'] == 'Prioritaire').sum()
    act_prior    = df_filtre[df_filtre['segment'] == 'Prioritaire']['w_total'].sum()
    act_total    = df_filtre['w_total'].sum()
    n_vitaux_est = len(df_vitaux_filtre) * RATIO_CALIBRATION
    n_mercato_est = (
        df_mercato['deux_receptifs'].astype(bool).sum() * RATIO_CALIBRATION
        if 'deux_receptifs' in df_mercato.columns else 0
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        '🔴 Communes prioritaires', f'{n_prior:,}',
        f'Top {100 - seuil_pct}% les plus captives',
        help='Communes dont le score Cibloscope dépasse le seuil défini dans la barre latérale.'
    )
    c2.metric(
        '👷 Actifs dans les zones prioritaires', f'{act_prior/1e6:.2f}M',
        f'sur {act_total/1e6:.1f}M actifs couverts',
        help='Nombre d\'actifs travaillant dans les communes prioritaires (source : flux MOBPRO).'
    )
    c3.metric(
        '🏥 Travailleurs vitaux captifs', f'{n_vitaux_est/1e6:.2f}M',
        'estimation calibrée (×28M actifs)',
        help='Extrapolation des personas Nemotron à la population active réelle.'
    )
    c4.metric(
        '🔄 Opportunités mercato', f'{n_mercato_est/1e3:.0f}k paires',
        'échanges viables détectés',
        help='Paires de travailleurs dont l\'échange de poste réduirait les trajets des deux.'
    )

    st.divider()

    col_g1, col_g2 = st.columns(2)

    with col_g1:
        st.subheader('📈 Distribution de l\'ICA par commune')
        st.markdown("""
        <div class="explication">
        <strong>Comment lire ce graphique :</strong> Chaque barre représente
        un groupe de communes avec le même niveau d'ICA (Indice de Captivité Automobile).
        La ligne orange verticale marque le seuil "Prioritaire" — toutes les communes
        à droite de cette ligne sont classées prioritaires.<br><br>
        <strong>Exemple de lecture :</strong> Si la courbe est très décalée à droite
        (ICA moyen > 0.65), cela signifie que la majorité des communes ont une forte
        dépendance à la voiture — typique d'une zone rurale. En Île-de-France,
        la courbe serait décalée à gauche (ICA moyen < 0.45).
        </div>
        """, unsafe_allow_html=True)

        ica_moy = df_filtre['ica'].mean()
        fig_hist = px.histogram(
            df_filtre, x='ica', nbins=50,
            color_discrete_sequence=['#e74c3c'],
            labels={'ica': 'ICA — Indice de Captivité Automobile', 'count': 'Nb communes'},
            title=f'{len(df_filtre):,} communes analysées — ICA moyen : {ica_moy:.3f}'
        )
        fig_hist.add_vline(
            x=df_filtre['ica'].quantile(seuil_pct / 100),
            line_dash='dash', line_color='orange',
            annotation_text=f'Seuil P{seuil_pct}'
        )
        fig_hist.update_layout(showlegend=False, height=380)
        st.plotly_chart(fig_hist, use_container_width=True)

        st.caption(
            f"ICA min : {df_filtre['ica'].min():.3f} | "
            f"médiane : {df_filtre['ica'].median():.3f} | "
            f"max : {df_filtre['ica'].max():.3f}"
        )

    with col_g2:
        st.subheader('📊 Travailleurs vitaux par secteur')
        st.markdown("""
        <div class="explication">
        <strong>Comment lire ce graphique :</strong> Chaque barre représente
        le nombre estimé (en milliers) de travailleurs dans ce secteur vital
        qui sont également captifs de la voiture (ICA élevé).<br><br>
        <strong>Méthode :</strong> Les effectifs sont estimés en multipliant
        les personas Nemotron identifiés dans chaque secteur par le ratio
        de calibration (28M actifs / taille de l'échantillon).
        Ce sont des <em>ordres de grandeur</em>, pas des chiffres exacts.<br><br>
        <strong>Exemple :</strong> "santé_domicile" à 150k signifie qu'environ
        150 000 infirmières libérales et aides-soignants exercent dans des communes
        où ils n'ont pas d'alternative à la voiture.
        </div>
        """, unsafe_allow_html=True)

        sc = df_vitaux_filtre['secteur_vital'].value_counts().reset_index()
        sc.columns = ['secteur', 'nb']
        sc['nb_k'] = (sc['nb'] * RATIO_CALIBRATION / 1000).round(0)

        LABELS_SECTEURS = {
            'santé_domicile'  : '🏥 Santé à domicile (IDEL, aides-soignants)',
            'santé_libérale'  : '👨‍⚕️ Santé libérale (médecins, kiné)',
            'agriculture'     : '🌾 Agriculture et élevage',
            'fret_alim'       : '🚛 Transport fret alimentaire',
            'énergie'         : '⚡ Réseaux énergie (électricité, gaz)',
            'eau'             : '💧 Réseaux eau potable',
            'sécurité'        : '🚒 Sécurité (pompiers, gendarmes)',
            'soins_domicile'  : '🏠 Soins à domicile (ambulanciers)',
            'pharmacie'       : '💊 Pharmacie',
            'distribution_alim': '🛒 Distribution alimentaire',
            'agri_support'    : '🌱 Support agricole (coopératives)',
            'école_primaire'  : '📚 Enseignement primaire',
        }
        sc['label'] = sc['secteur'].map(LABELS_SECTEURS).fillna(sc['secteur'])

        fig_bar = px.bar(
            sc.head(10), x='nb_k', y='label', orientation='h',
            color='nb_k', color_continuous_scale='Reds',
            labels={'nb_k': 'Effectif estimé (milliers)', 'label': ''},
            title='Effectifs estimés dans les zones captives'
        )
        fig_bar.update_layout(showlegend=False, height=380, coloraxis_showscale=False)
        st.plotly_chart(fig_bar, use_container_width=True)

    st.divider()

    st.subheader('🗂️ Top 15 départements les plus exposés')
    st.markdown("""
    <div class="explication">
    <strong>Comment lire ce tableau :</strong> Les départements sont classés par score
    Cibloscope moyen (plus le score est proche de 1, plus la dépendance est forte).
    La colonne "Communes prioritaires" indique combien de communes dans ce département
    dépassent le seuil défini.<br><br>
    <strong>Exemple de lecture :</strong> Un département avec score_moy = 0.72 et
    n_prioritaires = 180 a la majorité de son territoire en zone rouge.
    Un département avec score_moy = 0.45 mais n_prioritaires = 20 a quelques
    poches rurales isolées dans un tissu majoritairement urbain.
    </div>
    """, unsafe_allow_html=True)

    dep_agg = (
        df_filtre.groupby('DEP')
        .agg(
            score_moy      = ('score',   'mean'),
            ica_moy        = ('ica',     'mean'),
            svs_moy        = ('svs',     'mean'),
            n_prioritaires = ('segment', lambda x: (x == 'Prioritaire').sum()),
            n_communes     = ('score',   'count'),
            actifs         = ('w_total', 'sum'),
        )
        .reset_index()
        .nlargest(15, 'score_moy')
        .round(3)
    )
    dep_agg['% prioritaires'] = (
        dep_agg['n_prioritaires'] / dep_agg['n_communes'] * 100
    ).round(1)

    st.dataframe(
        dep_agg.rename(columns={
            'DEP': 'Dépt', 'score_moy': 'Score moy', 'ica_moy': 'ICA moy',
            'svs_moy': 'SVS moy', 'n_prioritaires': 'Communes prioritaires',
            'n_communes': 'Total communes', 'actifs': 'Actifs (flux)'
        }),
        use_container_width=True, hide_index=True
    )

    st.caption(
        "Score moy = score Cibloscope moyen des communes du département. "
        "ICA moy = captivité automobile moyenne. SVS moy = densité de secteurs vitaux. "
        "Actifs = total d'actifs en flux domicile-travail."
    )


# ══════════════════════════════════════════════════════════════
# ONGLET 2 — CARTE
# ══════════════════════════════════════════════════════════════
elif onglet == '🗺️ Carte Cibloscope':

    st.title('🗺️ Carte Cibloscope — Dépendance automobile par commune')

    st.markdown("""
    <div class="explication">
    <strong>Comment lire cette carte :</strong>
    Chaque commune est colorée selon l'indicateur sélectionné.
    <strong>Rouge = dépendance élevée / zone prioritaire.</strong>
    Vert = faible dépendance / alternatives disponibles. Gris = données insuffisantes.<br><br>
    Survolez une commune pour voir ses indicateurs détaillés.
    Zoomez pour voir les communes individuelles — les grandes villes apparaissent
    en vert (TC disponibles) entourées de couronnes périurbaines en orange/rouge.
    </div>
    """, unsafe_allow_html=True)

    col_o1, col_o2 = st.columns(2)
    with col_o1:
        variable_carte = st.selectbox(
            'Indicateur affiché',
            ['score', 'ica', 'svs'],
            format_func=lambda x: {
                'score': '🎯 Score Cibloscope composite (ICA×45% + SVS×35% + CF×20%)',
                'ica'  : '🚗 ICA — Indice de Captivité Automobile',
                'svs'  : '🏥 SVS — Score de Vitalité Sectorielle',
            }[x],
            help='Score = indicateur composite. ICA = dépendance voiture seule. SVS = présence secteurs vitaux.'
        )
    with col_o2:
        mode_affichage = st.selectbox(
            'Communes affichées',
            ['Toutes les communes', 'Prioritaires uniquement', 'Top 20% les plus exposées'],
            help='Réduire le nombre de communes améliore les performances de chargement.'
        )

    DESCRIPTIONS_CARTE = {
        'score': ('Score Cibloscope composite',
                  'Plus rouge = score plus élevé = commune plus prioritaire. '
                  'Le score combine captivité (ICA), secteurs vitaux (SVS) et revenus (CF).'),
        'ica'  : ('ICA — Indice de Captivité Automobile',
                  'Plus rouge = plus de travailleurs dépendants de la voiture ET absence de TC. '
                  'Les zones rurales et périurbaines sans réseau TC apparaissent en rouge.'),
        'svs'  : ('SVS — Score de Vitalité Sectorielle',
                  'Plus rouge = plus forte concentration d\'emplois vitaux (soignants, agricoles, énergie). '
                  'Les zones agricoles et les déserts médicaux apparaissent en rouge.'),
    }
    label_var, desc_var = DESCRIPTIONS_CARTE[variable_carte]
    st.caption(f"**{label_var}** — {desc_var}")

    # Sélection communes
    if mode_affichage == 'Toutes les communes':
        df_carte = df_filtre.copy()
    elif mode_affichage == 'Prioritaires uniquement':
        df_carte = df_filtre[df_filtre['segment'] == 'Prioritaire'].copy()
    else:
        seuil_p80 = df_filtre[variable_carte].quantile(0.80)
        df_carte = df_filtre[df_filtre[variable_carte] >= seuil_p80].copy()

    st.caption(f'{len(df_carte):,} communes affichées sur {len(df_filtre):,}')

    codes_carte = set(df_carte['COMMUNE'].astype(str).tolist())
    geojson_filtre = {
        'type': 'FeatureCollection',
        'features': [
            f for f in geojson_raw['features']
            if str(f['properties']['code']).zfill(5) in codes_carte
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
        fill_opacity=0.80,
        line_opacity=0.05,
        line_weight=0,
        legend_name=label_var,
        nan_fill_color='#e8e8e8',
        nan_fill_opacity=0.3,
        bins=7
    ).add_to(m)

    # Tooltips enrichis
    score_map = df_carte.set_index('COMMUNE').to_dict(orient='index')
    geojson_tt = {'type': 'FeatureCollection', 'features': []}
    for f in geojson_filtre['features']:
        code = str(f['properties']['code']).zfill(5)
        if code in score_map:
            r = score_map[code]
            geojson_tt['features'].append({
                'type': 'Feature',
                'geometry': f['geometry'],
                'properties': {
                    'Commune' : f['properties'].get('nom', ''),
                    'Segment' : str(r.get('segment', '')),
                    'Score'   : round(float(r.get('score', 0)), 3),
                    'ICA'     : round(float(r.get('ica', 0)), 3),
                    '% voiture': f"{round(float(r.get('pct_voiture', 0))*100, 1)}%",
                    'Actifs'  : int(r.get('w_total', 0)),
                }
            })

    folium.GeoJson(
        geojson_tt,
        style_function=lambda x: {'fillOpacity': 0, 'weight': 0},
        highlight_function=lambda x: {'weight': 2, 'color': '#333', 'fillOpacity': 0.1},
        tooltip=folium.GeoJsonTooltip(
            fields=['Commune', 'Segment', 'Score', 'ICA', '% voiture', 'Actifs'],
            aliases=['📍 Commune', '🏷️ Segment', '⭐ Score', '🚗 ICA',
                     '🚙 % voiture', '👷 Actifs flux'],
            sticky=True
        )
    ).add_to(m)

    st_folium(m, width='100%', height=580)

    st.subheader(f'Top 20 communes — {label_var}')
    st.markdown("""
    <div class="explication">
    Les 20 communes avec le score le plus élevé sur l'indicateur sélectionné.
    <strong>pct_voiture</strong> = % d'actifs utilisant la voiture pour aller travailler.
    <strong>w_total</strong> = nombre d'actifs en flux domicile-travail (poids statistique INSEE).
    </div>
    """, unsafe_allow_html=True)

    cols_disp = [c for c in ['COMMUNE', 'DEP', 'score', 'ica', 'svs',
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

    st.title('🔄 Algorithme Mercato — Échanges de postes')

    st.markdown("""
    <div class="explication">
    <strong>Principe :</strong> Le mercato identifie des paires de travailleurs
    dans le même secteur vital dont l'échange de lieu de travail réduirait
    la distance domicile-travail des <em>deux</em> personnes simultanément.
    C'est une action à <strong>coût public nul</strong> — elle ne nécessite
    aucune dépense, uniquement une mise en relation facilitée par l'employeur
    ou une AOM (Autorité Organisatrice de la Mobilité).<br><br>
    <strong>Deux niveaux sont analysés :</strong><br>
    — <strong>Intra-employeur (N1)</strong> : même secteur, même département.
    La personne A et la personne B travaillent dans la même organisation
    (ou le même type d'organisation) mais sur des sites différents.<br>
    — <strong>Inter-départemental (N2)</strong> : même secteur, départements voisins.
    Chacun travaille de "l'autre côté" de la frontière départementale.
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        gain_min = st.slider(
            'Gain minimum (km)',
            5, 50, 10,
            help='Gain total sur la somme des trajets des deux personnes. '
                 '10 km = chaque personne économise en moyenne 5 km/jour.'
        )
    with c2:
        filtre_receptifs = st.checkbox(
            'Les deux réceptifs uniquement', value=False,
            help='Ne montrer que les paires où les deux personnes ont exprimé '
                 'un souhait de rapprochement domicile/travail (signal NLP Nemotron).'
        )
    with c3:
        if 'niveau' in df_mercato.columns:
            niveaux = ['Tous'] + sorted(df_mercato['niveau'].dropna().unique())
            niveau_filtre = st.selectbox('Niveau', niveaux,
                help='N1 = intra-employeur | N2 = inter-départemental')
        else:
            niveau_filtre = 'Tous'

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
    litres_eco = km_eco * 0.07

    r1, r2, r3, r4 = st.columns(4)
    r1.metric('Paires viables (échantillon)', f'{len(df_m):,}',
              help='Paires dans l\'échantillon Nemotron avec un gain ≥ au seuil fixé.')
    r2.metric('Gain moyen par échange', f'{df_m["gain_km"].mean():.1f} km' if len(df_m) else '—',
              help='Réduction totale de la somme des trajets des deux personnes.')
    r3.metric('Paires doublement réceptives',
              f'{df_m["deux_receptifs"].sum():,}' if len(df_m) and 'deux_receptifs' in df_m.columns else '—',
              help='Paires où les deux personnes ont exprimé un souhait de rapprochement.')
    r4.metric('Litres carburant éco/jour (extrapolé)',
              f'{litres_eco/1e6:.2f}M L' if litres_eco else '—',
              help='Extrapolation à 28M d\'actifs. Base : 7L/100km.')

    if len(df_m) > 0:
        st.divider()

        col_g1, col_g2 = st.columns(2)

        with col_g1:
            st.subheader('Gain par secteur')
            st.markdown("""
            <div class="explication">
            La boîte à moustaches montre la <strong>distribution des gains</strong>
            pour chaque secteur. La ligne centrale = médiane. Plus la boîte est
            haute sur l'axe Y, plus les échanges dans ce secteur sont bénéfiques.
            Un secteur avec une grande boîte = très variable selon les communes.
            </div>
            """, unsafe_allow_html=True)
            if 'secteur' in df_m.columns:
                fig_s = px.box(
                    df_m, x='secteur', y='gain_km',
                    title='Distribution des gains (km) par secteur',
                    labels={'gain_km': 'Gain total (km)', 'secteur': ''},
                    color='secteur'
                )
                fig_s.update_layout(showlegend=False, height=380)
                st.plotly_chart(fig_s, use_container_width=True)

        with col_g2:
            st.subheader('Répartition N1 vs N2')
            st.markdown("""
            <div class="explication">
            Comparaison des gains selon le niveau d'échange.
            Les échanges <strong>inter-départementaux (N2)</strong> ont tendance
            à générer des gains plus importants car les distances sont plus grandes,
            mais ils sont aussi plus difficiles à mettre en œuvre.
            Les échanges <strong>intra-employeur (N1)</strong> sont plus facilement
            activables mais les gains sont souvent plus modestes.
            </div>
            """, unsafe_allow_html=True)
            if 'niveau' in df_m.columns:
                fig_n = px.histogram(
                    df_m, x='gain_km', color='niveau', nbins=30,
                    title='Distribution des gains — N1 (intra) vs N2 (inter-DEP)',
                    labels={'gain_km': 'Gain (km)', 'count': 'Nb paires'},
                    barmode='overlay', opacity=0.7
                )
                fig_n.update_layout(height=380)
                st.plotly_chart(fig_n, use_container_width=True)

        st.subheader(f'📋 Top 50 meilleures opportunités ({len(df_m):,} paires filtrées)')
        st.markdown("""
        <div class="explication">
        <strong>Comment lire ce tableau :</strong><br>
        — <strong>gain_km</strong> : km économisés sur la somme des trajets des deux personnes.<br>
        — <strong>deux_receptifs</strong> : True = les deux ont exprimé un souhait de rapprochement
        (priorité de mise en relation).<br>
        — <strong>score_indiv_a/b</strong> : score individuel de dépendance de chaque personne
        (entre 0 et 1 — plus proche de 1 = plus captive).<br><br>
        <strong>Exemple de lecture :</strong> Une ligne avec gain_km=42, deux_receptifs=True,
        secteur=santé_domicile signifie : deux infirmières libérales, toutes deux favorables
        à un changement, dont l'échange de zone de patientèle économiserait 42 km/jour
        au total, soit environ 4 200 km/an chacune.
        </div>
        """, unsafe_allow_html=True)

        cols_aff = [c for c in [
            'secteur', 'niveau', 'dep_a', 'nom_commune_a', 'nom_commune_b',
            'gain_km', 'deux_receptifs', 'score_indiv_a', 'score_indiv_b'
        ] if c in df_m.columns]
        st.dataframe(
            df_m.nlargest(50, 'gain_km')[cols_aff].round(3),
            use_container_width=True, hide_index=True
        )
    else:
        st.info('Aucune paire ne correspond aux filtres sélectionnés. '
                'Essayez de réduire le gain minimum ou de désactiver le filtre "réceptifs".')


# ══════════════════════════════════════════════════════════════
# ONGLET 4 — EXPORT
# ══════════════════════════════════════════════════════════════
elif onglet == '📋 Export':

    st.title('📋 Export — Documents de travail')

    st.markdown("""
    <div class="explication">
    Cet onglet permet d'exporter les données pour alimenter des notes de travail,
    des présentations ou des analyses complémentaires.
    Tous les exports sont filtrés selon les paramètres sélectionnés dans la barre latérale.
    </div>
    """, unsafe_allow_html=True)

    col_e1, col_e2 = st.columns(2)

    with col_e1:
        st.subheader('📍 Score Cibloscope par commune')
        st.markdown("""
        **Colonnes exportées :**
        - `COMMUNE` — code INSEE 5 chiffres
        - `DEP` — code département
        - `score` — score composite (0 à 1)
        - `segment` — Prioritaire / Secondaire / Hors cible
        - `ica` — Indice de Captivité Automobile
        - `svs` — Score Vitalité Sectorielle
        - `pct_voiture` — % actifs utilisant la voiture
        - `w_total` — nb actifs (poids flux INSEE)
        """)
        cols_exp = [c for c in ['COMMUNE', 'DEP', 'score', 'segment',
                                 'ica', 'svs', 'pct_voiture', 'w_total']
                    if c in df_filtre.columns]
        df_exp = df_filtre[cols_exp].sort_values('score', ascending=False).round(3)
        st.dataframe(df_exp.head(10), use_container_width=True, hide_index=True)
        st.download_button(
            '⬇️ Télécharger CSV communes',
            data=df_exp.to_csv(index=False).encode('utf-8'),
            file_name='cibloscope_communes.csv', mime='text/csv'
        )

    with col_e2:
        st.subheader('🏥 Population vitale par département')
        st.markdown("""
        **Colonnes exportées :**
        - `DEP` — code département
        - `n_vitaux_estimes` — nb de travailleurs vitaux captifs estimés
        - `n_mercato_estimes` — nb de travailleurs réceptifs au mercato
        - `ica_moyen` — captivité automobile moyenne du département
        """)
        dep_sort = dep_vitaux.sort_values('n_vitaux_estimes', ascending=False)
        st.dataframe(dep_sort.head(10), use_container_width=True, hide_index=True)
        st.download_button(
            '⬇️ Télécharger CSV départements',
            data=dep_sort.to_csv(index=False).encode('utf-8'),
            file_name='cibloscope_departements.csv', mime='text/csv'
        )

    st.divider()

    st.subheader('🔄 Opportunités mercato complètes')
    st.markdown("""
    **Colonnes principales :**
    `secteur` · `niveau` (N1/N2) · `dep_a` · `nom_commune_a` · `nom_commune_b` ·
    `gain_km` (gain total) · `deux_receptifs` · `score_indiv_a` · `score_indiv_b`
    """)
    st.dataframe(
        df_mercato.sort_values('gain_km', ascending=False).head(20),
        use_container_width=True, hide_index=True
    )
    st.download_button(
        '⬇️ Télécharger CSV mercato complet',
        data=df_mercato.to_csv(index=False).encode('utf-8'),
        file_name='mercato_complet.csv', mime='text/csv'
    )

    st.divider()
    st.subheader('📝 Fiche synthèse')

    n_prior   = (df_score['segment'] == 'Prioritaire').sum()
    n_vit     = len(df_vitaux) * RATIO_CALIBRATION
    n_merc    = (df_mercato['deux_receptifs'].astype(bool).sum() * RATIO_CALIBRATION
                 if 'deux_receptifs' in df_mercato.columns else 0)
    gain_tot  = df_mercato['gain_km'].sum() * RATIO_CALIBRATION

    synthese = f"""## Cibloscope Mobilité — Fiche synthèse

### Objectif
Identifier et cibler les travailleurs dont la mobilité professionnelle est
structurellement dépendante de la voiture et dont l'emploi est vital pour la société.

### Méthode
Score composite = ICA (Indice de Captivité Automobile) × 45%
                + SVS (Score Vitalité Sectorielle) × 35%
                + CF (Capacité de Financement inversée) × 20%

### Résultats nationaux

| Indicateur | Valeur |
|---|---|
| Communes prioritaires (top {100-seuil_pct}%) | {n_prior:,} |
| Travailleurs vitaux captifs estimés | {n_vit/1e6:.2f}M |
| Opportunités mercato (extrapolé) | {n_merc/1e3:.0f}k paires |
| Km économisés/jour si mercato activé | {gain_tot/1e6:.1f}M km |
| Litres carburant/jour économisés | {gain_tot*0.07/1e6:.1f}M L |

### Sources
INSEE MOBPRO 2022 · GTFS PAN transport.data.gouv.fr · Ameli 2023 ·
Nvidia Nemotron-Personas-France (CC-BY 4.0) · Filosofi 2021 (DGFiP/INSEE)

### Limites
ICA calculé par proxy distance (modèle ENTD 2019) — pas par mesure directe TRANS.
SVS basé sur Ameli département + NLP Nemotron — SIRENE et MSA non intégrés.
Effectifs estimés par calibration statistique (ratio 28M/échantillon).
"""
    st.markdown(synthese)
    st.download_button(
        '⬇️ Télécharger fiche synthèse (Markdown)',
        data=synthese.encode('utf-8'),
        file_name='cibloscope_synthese.md', mime='text/markdown'
    )
