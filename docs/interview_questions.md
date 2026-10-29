# Cinq questions d'entretien sur ce projet

Préparez une réponse de 2 minutes à chacune, en citant le code.

**1. Comment garantissez-vous qu'un rechargement ne crée pas de doublons ?**
Clé de provenance `(dataset, sha256 du fichier, feuille, ligne)` en clé primaire ; `ON CONFLICT DO NOTHING`
sur raw, upsert sur staging ; `meta.dataset_current` pour qu'une nouvelle version remplace l'ancienne dans
les marts. À compléter : pourquoi une clé métier (facture + produit) ne fonctionne pas ici (vrais doublons
exacts dans la source). Preuve : `test_reloading_same_file_is_idempotent`, `test_new_file_version_…`.

**2. Pourquoi ne supprimez-vous pas les lignes invalides ?**
Traçabilité et réversibilité : chaque exclusion est un filtre explicite (`is_valid_sale`), auditable dans
`marts.data_quality`. Une règle mal calibrée se corrige en rejouant le nettoyage, sans relire la source.
Relance probable : « et le coût en stockage ? » → négligeable à ce volume, et la couche raw est de toute
façon nécessaire à l'audit.

**3. Le nombre de clients mensuels additionné sur 12 mois donne-t-il le nombre de clients annuels ?**
Non : un `COUNT(DISTINCT)` n'est pas additif, un client actif plusieurs mois serait compté plusieurs fois.
C'est pourquoi `daily_country_sales` ne stocke pas de clients et que le dashboard les recalcule depuis
`fct_sales` avec les filtres. Même raisonnement pour un panier moyen : on ne fait pas la moyenne des moyennes.

**4. Comment savez-vous que les chiffres du dashboard sont justes ?**
Cinq vérifications qui doivent concorder : calcul à la main sur 10 lignes, référence Pandas, SQL filtrable,
mart pré-calculé, somme de chaque mart. Le dashboard lui-même est exécuté dans les tests
(`streamlit.testing`) et comparé à la base. Aucune valeur n'est codée en dur.

**5. Que changeriez-vous pour passer d'un fichier statique à un flux quotidien ?**
Chargement incrémental (filigrane sur `invoice_date` ou fichiers journaliers), orchestration (Airflow /
Dagster) avec reprises, marts incrémentaux (dbt `incremental`), alertes sur le rapport qualité (ex. hausse
soudaine des lignes `invalid`), CI avec un PostgreSQL de test. Expliquer aussi ce qu'on garderait :
la séparation raw / staging / marts et la clé de provenance.
