# Constats — Online Retail II

Interprétation des chiffres de [analysis_uci.md](analysis_uci.md), rapport généré depuis les marts
(run du 2026-10-20, 1 067 371 lignes). Chaque chiffre cité ici figure dans ce rapport ou dans les
requêtes de vérification indiquées. Les hypothèses sont signalées comme telles.

## 1. Deux commandes annulées faussent le CA brut

Les deux plus grosses lignes de vente du dataset ont été annulées en totalité :

- 09/12/2011 : 80 995 × `PAPER CRAFT , LITTLE BIRDIE` (facture 581483, annulée par C581484), £168 470 ;
- 18/01/2011 : 74 215 × `MEDIUM CERAMIC TOP STORAGE JAR` (541431, annulée par C541433), £77 184.

Conséquences visibles dans les marts :
- ces produits sont 4e et 8e au **CA brut**, mais sortent du top 10 au **CA net** ;
- le 09/12/2011 est le jour le plus atypique (£198 095 de CA brut) ;
- les annulations de décembre 2011 (£174 091) et de janvier 2011 (£91 525) sont des pics.

**Décision :** le dashboard et le rapport proposent un classement au CA net. Les lignes ne sont **pas**
supprimées : elles restent valides comme ventes, et l'annulation est comptée à part.

## 2. Saisonnalité forte, croissance faible

- Le CA brut culmine chaque année en novembre (£1,43 M en 2010, £1,45 M en 2011), après une montée
  de septembre à novembre.
- À périmètre égal (janvier–novembre), le CA brut progresse de **+3,0 %** entre 2010 et 2011,
  alors que le nombre de commandes **baisse de 3,7 %** : la hausse vient d'un panier plus élevé, pas de plus
  de commandes.
- Décembre 2011 est **partiel** (données jusqu'au 9) : il ne doit pas être comparé tel quel à décembre 2010.
- Quasiment aucune commande le samedi (30 sur 39 516) ; le jeudi est le jour le plus actif.

## 3. Un marché très concentré

- Le Royaume-Uni réalise **85,5 %** du CA (43 pays au total).
- L'Irlande (EIRE) est 2e avec 3,2 % du CA, mais **3 clients identifiés seulement** : deux d'entre eux
  pèsent £575 000. C'est cohérent avec la description du dataset (« beaucoup de clients sont des grossistes »),
  mais un tel classement par pays mesure ici quelques comptes, pas un marché.
- Les 20 % de produits les plus vendus réalisent **78,1 %** du CA brut (loi de Pareto).

## 4. Une clientèle fidèle

- 5 852 clients identifiés, dont **72,4 %** ont passé au moins deux commandes, avec 6,25 commandes en moyenne.
- 13,1 % du CA provient de ventes sans `Customer ID`. Ces ventes sont gardées dans le CA, mais exclues
  des indicateurs clients, qui sont donc des minorants.

## 5. Qualité : ce qui a été détecté

| Constat | Volume |
|---|---|
| Doublons exacts | 34 335 lignes |
| Lignes d'annulation | 19 494 (8 292 factures « C ») |
| Lignes sans client | 243 007 |
| Lignes sans description | 4 382 (aucune parmi les ventes valides) |
| Codes non produits (port, frais…) | 4 715 lignes |
| Ajustements de stock / prix nuls | 3 457 / 2 695 |
| Codes produit à plusieurs libellés | 596 |
| Valeurs illisibles | 0 |

Au total, 94,0 % des lignes sont des ventes valides.

## Pistes d'analyse suivantes

1. Segmentation RFM des 5 852 clients identifiés (récence, fréquence, montant).
2. Cohortes mensuelles de rétention, en partant des premières commandes de décembre 2009.
3. Distinguer B2B et B2C par la taille des commandes. C'est une hypothèse à valider : le dataset ne contient pas le type de client.
4. Rapprocher annulations et ventes d'origine par (client, produit, quantité) pour estimer un CA net par commande.

## Limites

- Les annulations sont valorisées au mois et au produit où elles ont lieu, sans lien avec la vente d'origine.
- Le fichier analysé est la copie redistribuée par le package R `onlineretail2` (même contenu annoncé :
  1 067 371 lignes, même période). La source officielle UCI n'était pas joignable depuis l'environnement.
- Aucun coût n'étant disponible, aucune marge ni rentabilité n'est calculée.
