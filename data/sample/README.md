# Échantillon SYNTHÉTIQUE

`online_retail_sample.csv` est **inventé** : il ne provient pas du dataset UCI et ne décrit aucune
entreprise réelle. Il reprend le schéma d'Online Retail II (mêmes noms de colonnes) pour permettre de
faire tourner et de tester le pipeline sans accès Internet.

- Généré par `python -m retail_analytics.cli generate-sample` (graine 42, résultat identique à chaque fois).
- Période 2024–2025 (le vrai dataset couvre 2009–2011), produits et clients fictifs (`700xx`, `20001+`).
- Anomalies injectées en quantités connues : 40 doublons exacts, 30 annulations, 12 ajustements de stock,
  8 prix nuls, 3 lignes illisibles, 1 ajustement `A`, des frais de port et ~20 % de commandes sans client.
- Chargé en base sous le nom de dataset `synthetic_sample`.
