# 🎯 Cibloscope Mobilité

**Outil de ciblage des travailleurs en dépendance vitale à la voiture**

Contexte : crise Ormuz 2026 — pétrole à 150$/baril — identification des ~1,8M de travailleurs français dont la mobilité est structurellement irremplaçable par les transports en commun.

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://cibloscope-dashboard.streamlit.app)

---

## Pourquoi ce projet

Lors de la guerre en Ukraine, 8 milliards d'euros de chèques carburant ont été versés sans ciblage — capturés en grande partie par des ménages qui n'en avaient pas besoin. Face à un nouveau choc pétrolier, l'État ne peut plus se permettre ce saupoudrage.

Cibloscope répond à une question simple : **qui, précisément, ne peut pas se passer de sa voiture pour exercer un emploi vital ?**

---

## Ce que fait l'application

Le dashboard comporte 4 onglets :

- **Tableau de bord** — KPIs nationaux, distribution ICA par commune, secteurs vitaux estimés, top départements exposés
- **Carte Cibloscope** — choroplèthe interactive France entière, filtrable par département et par indicateur
- **Mercato** — algorithme d'échanges de postes entre travailleurs vitaux pour réduire les distances domicile-travail
- **Export** — CSV prêts pour notes ministérielles, synthèse Markdown téléchargeable

---

## Architecture des données

Le score Cibloscope est un composite de trois dimensions :

```
SCORE = ICA × 0.45  +  SVS × 0.35  +  CF × 0.20
```

| Dimension | Signification | Source |
|---|---|---|
| **ICA** — Indice de Captivité Automobile | % voiture × absence TC réelle | INSEE MOBPRO 2022 + GTFS PAN |
| **SVS** — Score Vitalité Sectorielle | Densité d'emplois vitaux dans la commune | Ameli 2023 + Nemotron NLP |
| **CF** — Capacité de Financement (inversée) | Faiblesse des revenus = besoin d'aide plus fort | Filosofi 2021 |

### Sources open data utilisées

| Source | Données | Lien |
|---|---|---|
| INSEE MOBPRO 2022 | Flux domicile-travail par commune | [insee.fr](https://www.insee.fr/fr/statistiques/8582949) |
| GTFS PAN | Arrêts transport en commun nationaux | [transport.data.gouv.fr](https://transport.data.gouv.fr/datasets/arrets-de-transport-en-france) |
| Ameli 2023 | Auxiliaires médicaux libéraux par département | [data.ameli.fr](https://data.ameli.fr/explore/dataset/demographie-effectifs-et-les-densites/) |
| Filosofi 2021 | Revenus médians par commune | [data.gouv.fr](https://www.data.gouv.fr/datasets/revenu-des-francais-a-la-commune) |
| Nvidia Nemotron-Personas-France | Population synthétique 1M personas | [HuggingFace](https://huggingface.co/datasets/nvidia/Nemotron-Personas-France) |
| france-geojson | Géométries communes simplifiées | [GitHub](https://github.com/gregoiredavid/france-geojson) |

---

## Algorithme Mercato

Le mercato identifie les échanges de postes entre travailleurs vitaux qui réduisent la somme des distances domicile-travail des deux parties.

**Niveau 1 — intra-employeur** : deux personnes dans le même secteur × département, dont l'échange de commune de travail réduit les trajets de chacun.

**Niveau 2 — inter-départemental** : deux personnes dans des départements voisins (< 80 km entre centroïdes), travaillant de l'autre côté de la frontière départementale.

Pour chaque paire, on calcule :

```
Gain = (dist_A→site_actuel_A + dist_B→site_actuel_B)
     - (dist_A→site_B + dist_B→site_A)
```

Un signal NLP sur `career_goals_and_ambitions` (Nemotron) identifie les personnes exprimant un souhait de rapprochement domicile/travail — ces paires sont prioritaires.

---

## Structure du repo

```
cibloscope-dashboard/
├── app.py                                  # Dashboard Streamlit
├── requirements.txt                        # Dépendances Python
├── .python-version                         # Force Python 3.11
├── README.md                               # Ce fichier
├── df_score_final.parquet                  # Score Cibloscope par commune
├── df_vitaux_n2.parquet                    # Travailleurs vitaux (Nemotron)
├── cibloscope_dep_population_vitale.csv    # Estimations par département
├── mercato_checkpoint.parquet             # Paires mercato viables
└── mercato_synthese.csv                    # Export mercato complet
```

---

## Installation locale

```bash
git clone https://github.com/votre-compte/cibloscope-dashboard
cd cibloscope-dashboard
pip install -r requirements.txt
streamlit run app.py
```

---

## Limites et prochaines étapes

**Limites actuelles**

- ICA calculé par proxy distance (ENTD) — pas par mesure directe TRANS (fichier détail MOBPRO non disponible en téléchargement programmatique)
- SVS basé sur NLP Nemotron + Ameli département — SIRENE et MSA non encore intégrés
- Nemotron utilisé en échantillon 200k (limite RAM Colab gratuit) au lieu de 1M
- Granularité commune (35 000 mailles) au lieu d'IRIS (50 000 mailles)

**V2 prioritaire**

- Intégration SIRENE — vrais employeurs vitaux géolocalisés par code NAF
- Intégration MSA — salariés agricoles par département (pendant Ameli pour l'agriculture)
- Fichier détail MOBPRO individuel — variable TRANS directe pour ICA exact
- Passage à l'échelle IRIS pour ciblage infra-communal

---

## Contexte politique

Ce projet a été initié dans le cadre de la réponse à l'instruction du Premier Ministre du 1er avril 2026 demandant un plan d'électrification d'urgence des mobilités, avec pour priorité explicite :

> *"Mettre en place, dans les prochaines semaines, une offre de location de véhicules électriques dédiée à certaines professions ciblées ayant de longs trajets quotidiens, par exemple les infirmiers libéraux ou les aides-soignants."*

Le Cibloscope est l'outil de ciblage qui permet d'identifier ces professions et de prioriser les communes d'intervention.

---

## Licence

Données sources : Licence Ouverte Etalab v2.0 / CC-BY 4.0 selon les sources.
Code : MIT.

---

*Construit avec Python · Streamlit · Folium · Plotly · données open data françaises*
