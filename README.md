# NDN SCHOOL MANAGER

Prototype scolaire local pour le Collège Catholique Bilingue Notre-Dame des Nations, avec une direction artistique camerounaise inspirée du secondaire à Douala : bleu ciel dominant, bleu institutionnel, blanc et touches orange. Une illustration vectorielle originale représente des élèves et un campus ; elle ne prétend pas être une photo réelle du collège. Les données livrées sont fictives.

## Périmètre fonctionnel

- Connexion Flask-Login, mots de passe hachés, rôles contrôlés côté serveur (`admin`, `enseignant`, `direction`), formulaires protégés contre les requêtes CSRF et migrations Flask-Migrate.
- Tableau de bord accueillant calculé depuis SQLite, catalogue démonstration de classes francophones (6e à Terminale) et anglophones (Form 1 à Upper Sixth), création de classes à la demande, association de matières/coefficient et gestion des élèves.
- Date de naissance des élèves vérifiée entre 2009 et 2028. Connexion nominative par identifiant ou courriel, avec une page personnelle pour modifier son identité, son identifiant, son courriel et son mot de passe.
- Personnalisation possible du logo depuis **Paramètres**, avec aperçu immédiat du fichier choisi. Seul un administrateur peut téléverser une image PNG/JPG/WEBP ; elle est validée puis convertie localement en PNG. Le logo officiel n’ayant pas pu être identifié avec certitude dans les résultats publics en ligne, l’emblème NDN reste affiché par défaut.
- Création des comptes enseignants, affectations aux classes/matières et création d’évaluations depuis les affectations autorisées. Les enseignants peuvent aussi proposer des matières et les associer à leurs classes, sans gérer les affectations.
- Saisie des notes par fiche, brouillons, soumission, contrôle par la direction, refus avec motif, états distincts pour note manquante, absence et dispense.
- Calcul serveur des moyennes normalisées sur 20, pondération configurable des évaluations et des matières, classement des résultats complets validés. Les moyennes élèves et classe s’affichent automatiquement sur les écrans de suivi et sont consultables par trimestre.
- Téléchargement des bulletins PDF A4 pour les résultats complets et validés.
- Affichage responsive testé sur téléphone : navigation latérale avec fond de fermeture et touche Échap, contrôles tactiles agrandis, formulaires lisibles sans zoom automatique et tableaux défilant horizontalement. Les fichiers statiques et polices système fonctionnent sans accès Internet.
- Progressive Web App installable avec consultation hors ligne en lecture seule. Après une connexion en ligne réussie, une copie minimale limitée au rôle (classes, élèves inscrits, matières, évaluations et notes) est chiffrée avec AES-GCM dans IndexedDB ; le mot de passe du compte sert à dériver la clé via PBKDF2 et est demandé pour déverrouiller la copie. Le service worker ne met en cache ni pages de données ni réponses API. Aucune modification hors ligne n’est enregistrée ou synchronisée. La sécurité du chiffrement dépend de la robustesse du mot de passe : le compte de démonstration `admin23` / `admin000` est trop faible pour conserver une copie sur un appareil partagé. Supprimez la copie dans l’écran hors ligne ou effacez les données du site dans le navigateur.

Ce prototype n’est pas un déploiement de production. La gestion complète des années/périodes, le transfert et l’archivage des inscriptions, les utilisateurs direction et les paramètres institutionnels avancés restent à compléter. Ne lui confiez pas de données scolaires réelles sans audit, configuration de sécurité dédiée et procédure de sauvegarde validée.

## Installation (Linux/macOS)

Python 3.10 ou plus récent est recommandé.

```bash
cd /home/deathgun/Desktop/College
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Définissez `SECRET_KEY` avec une valeur aléatoire longue dans `.env` avant tout accès partagé. Pour le développement local, les variables peuvent aussi être exportées dans le terminal :

```bash
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export FLASK_APP=run.py
flask --app run.py db upgrade
flask --app run.py init-db
flask --app run.py run
```

Ouvrir ensuite <http://127.0.0.1:5000>. La base SQLite et les sauvegardes se trouvent dans `instance/`. Une base existante n’est pas réinitialisée ni écrasée par `init-db`. Pour le développement local, ce serveur doit rester lancé dans le terminal ; il n’est pas le serveur de production. En production sur Vercel, les déploiements remplacent le serveur local et se déclenchent automatiquement après chaque push sur la branche connectée.

La PWA est installable depuis un navigateur compatible sur `localhost` ou une origine HTTPS. Sur iPhone/iPad, ouvrez le site dans Safari puis choisissez **Partager → Sur l’écran d’accueil**. Pour préparer l’accès hors ligne, connectez-vous une première fois depuis l’appareil et le navigateur à utiliser. Ensuite, si le serveur devient inaccessible, ouvrez l’application ; saisissez l’identifiant et le mot de passe utilisés lors de la synchronisation pour consulter la copie chiffrée. Il s’agit d’un instantané de la dernière connexion, pas d’une synchronisation en temps réel ; les saisies et changements hors ligne ne sont pas conservés.

## Déploiement Vercel et Supabase

Le dépôt contient un point d’entrée Flask pour Vercel (`index.py`) et une étape de build qui copie les ressources PWA vers `public/static/`, servies par le CDN Vercel. Vercel exécute Flask dans une fonction sans serveur persistant : le système de fichiers local n’est pas durable. Les téléversements de logo sont donc désactivés sur Vercel jusqu’à l’ajout d’un stockage persistant tel que Supabase Storage. La commande locale de sauvegarde SQLite ne s’applique pas à Supabase.

1. Créez un projet Supabase et récupérez l’URI PostgreSQL dans **Connect**. Pour les fonctions Vercel, choisissez le **Transaction pooler** (port généralement 6543), et ajoutez `sslmode=require`. L’application adapte automatiquement l’URI au pilote `psycopg`, désactive les requêtes préparées pour le pooler et évite de garder un pool de connexions dans les fonctions serverless.
2. Dans Supabase, appliquez le schéma avec Flask-Migrate avant de rendre le site accessible. Depuis un terminal local configuré vers l’URI du pooler approprié :

   ```bash
   export DATABASE_URL='postgresql://postgres.PROJECT_REF:PASSWORD@POOLER_HOST:6543/postgres?sslmode=require'
   export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
   flask --app run.py db upgrade
   flask --app run.py create-admin
   ```

   La commande interactive `create-admin` crée le premier administrateur avec un mot de passe d’au moins 12 caractères. N’exécutez pas `init-db` sur la base de production : elle charge les comptes et les données fictives de démonstration.
3. Importez `mabsagency/ndn-school` dans Vercel, gardez `main` comme branche de production et ajoutez, dans **Project → Settings → Environment Variables**, `DATABASE_URL` (URI de transaction Supabase complète) et `SECRET_KEY` (secret aléatoire différent de celui des exemples). N’ajoutez ni `SUPABASE_SERVICE_ROLE_KEY` ni clé de base de données au code frontend.
4. Déployez une première fois depuis Vercel. Les prochains commits envoyés sur `main` déclencheront automatiquement les déploiements et mises à jour du site ; les pull requests peuvent générer des prévisualisations selon la configuration Git Vercel. Utilisez l’URL HTTPS Vercel pour installer et synchroniser la PWA. Modifiez les variables d’environnement dans Vercel et redéployez après leur changement.

Le processus d’application des migrations à Supabase est manuel et doit précéder tout déploiement qui modifie le schéma. Vercel ne lance pas `flask db upgrade` automatiquement à chaque démarrage de fonction, et le projet n’a pas besoin de laisser un serveur Flask local ouvert après le déploiement. Pour exécuter des migrations depuis un réseau qui ne prend pas en charge IPv6, utilisez l’URI Supabase du **Session pooler** pour la commande CLI, puis conservez le **Transaction pooler** dans Vercel.

## Comptes de démonstration

| Rôle | Identifiant | Mot de passe temporaire |
|---|---|---|
| Administrateur | `admin23` | `admin000` |
| Direction | `direction` | `NDN-Direction-2026!` |
| Enseignante | `enseignant` | `NDN-Prof-2026!` |

Ces mots de passe publics sont réservés à la démonstration locale. `admin000` est volontairement faible pour faciliter la présentation ; changez-le avant toute utilisation sur un réseau.

## Démonstration

1. Connectez-vous avec le compte `admin23` et le mot de passe `admin000` ou utilisez l’adresse électronique du compte.
2. Ouvrez **Mon identité** pour modifier vos informations personnelles et votre mot de passe.
3. Facultatif : téléversez le fichier vérifié du logo officiel dans **Paramètres**.
4. Créez une classe dans **Classes** ; associez au besoin les matières, leurs coefficients et les enseignants déjà créés.
5. Créez une matière dans **Matières** si nécessaire. Les enseignants peuvent également proposer une matière pour leurs classes ; l’administration gère toujours les affectations.
6. Créez une évaluation dans **Nouvelle évaluation** ou connectez-vous comme enseignant pour le faire dans ses affectations.
7. Saisissez les notes, soumettez la fiche, puis connectez-vous avec **direction** pour valider ou refuser.
8. Consultez les moyennes par élève et par classe, les classements, rapports et bulletins PDF téléchargeables ; les données de démonstration préchargées illustrent aussi des résultats incomplets.

Le jeu de démonstration comprend 24 élèves, 18 classes francophones et anglophones, quatre matières et des évaluations fictives. Les classes proposées sont un catalogue de départ modifiable ; l’administrateur peut aussi créer une classe à la demande.

## Tests

```bash
python -m pytest -q
```

Les tests couvrent l’authentification et les permissions, le rendu des pages, l’inscription d’un élève, les calculs incomplets et pondérés, le rejet d’une note hors barème, le cycle de validation, l’historique de correction et le PDF.

## Sauvegarde et restauration

Créer une sauvegarde cohérente de SQLite :

```bash
flask --app run.py backup-db
```

La commande écrit un fichier daté dans `instance/`. Pour restaurer, arrêtez le serveur, conservez la base actuelle comme copie de sécurité, puis placez la sauvegarde choisie sous `instance/ndn_school.db`. La restauration n’est pas une commande destructive automatique.

## Configuration et limites connues

- La moyenne d’une matière convertit chaque note sur 20 puis applique le coefficient de son évaluation. La moyenne générale pondère par le coefficient matière configuré pour la classe et l’année.
- Les évaluations de même matière et trimestre sont pondérées par leurs coefficients ; le barème de chaque évaluation est conservé.
- Une moyenne définitive n’est présentée que si chaque matière a des évaluations validées et si le résultat de l’élève est complet. Les absences ne sont pas transformées en zéro ; les dispenses sont exclues du calcul de la matière.
- Le refus remet une fiche en brouillon et requiert un motif. Une fiche validée est verrouillée ; sa correction explicite par la direction ou l’administration exige une justification et apparaît dans l’historique.
- Les bulletins PDF sont calculés à la demande. Le prototype ne stocke pas de version publiée immuable : une procédure de publication et d’archivage versionné est nécessaire avant un usage officiel.
- Les imports Excel/CSV, l’export tableur et l’archivage/versionnement persistant des bulletins restent à développer.
- Pour utiliser PostgreSQL/Supabase, définissez `DATABASE_URL` avec l’URI PostgreSQL fournie par Supabase ; la dépendance `psycopg` est incluse. La sauvegarde `backup-db` est réservée à SQLite.
- Après une modification du schéma, créez une migration avec `flask --app run.py db migrate -m "description"`, vérifiez le script généré, puis appliquez-le avec `flask --app run.py db upgrade`.
- Pour un serveur de réseau local, utilisez un serveur WSGI, HTTPS si possible, un `SECRET_KEY` secret, une politique de sauvegarde testée, des comptes propres à l’établissement et une revue de sécurité. Ne lancez pas le serveur de développement Flask en production.
