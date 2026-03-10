<!-- @import "[TOC]" {cmd="toc" depthFrom=1 depthTo=6 orderedList=false} -->

<!-- code_chunk_output -->

- [Dossier technique et fonctionnel — NTL-SysToolbox](#dossier-technique-et-fonctionnel--ntl-systoolbox)
  - [Table des matières](#table-des-matières)
  - [1. Objectif de l'outil](#1-objectif-de-loutil)
  - [2. Architecture logique](#2-architecture-logique)
    - [2.1 Vue d'ensemble](#21-vue-densemble)
    - [2.2 Organisation du code](#22-organisation-du-code)
  - [3. Répartition par modules](#3-répartition-par-modules)
    - [3.1 Module Diagnostic (`diag_module`)](#31-module-diagnostic-diag_module)
    - [3.2 Module Sauvegarde (`backup_module`)](#32-module-sauvegarde-backup_module)
    - [3.3 Module Audit d'obsolescence (`audit_module`)](#33-module-audit-dobsolescence-audit_module)
  - [4. Configuration et gestion des secrets](#4-configuration-et-gestion-des-secrets)
    - [4.1 Evolution depuis `main.py`](#41-evolution-depuis-mainpy)
    - [4.2 Mécanisme de chargement](#42-mécanisme-de-chargement)
    - [4.3 Gestion des secrets — état actuel et limites](#43-gestion-des-secrets--état-actuel-et-limites)
  - [5. Ergonomie du menu interactif](#5-ergonomie-du-menu-interactif)
    - [5.1 Principe de conception](#51-principe-de-conception)
    - [5.2 Structure de navigation](#52-structure-de-navigation)
    - [5.3 Retour utilisateur](#53-retour-utilisateur)
    - [5.4 Compromis ergonomiques](#54-compromis-ergonomiques)
  - [6. Démarche d'audit d'obsolescence](#6-démarche-daudit-dobsolescence)
    - [6.1 Source de référence : API endoflife.date](#61-source-de-référence--api-endoflifedate)
    - [6.2 Logique de qualification EOL](#62-logique-de-qualification-eol)
    - [6.3 Seuil de 180 jours](#63-seuil-de-180-jours)
    - [6.4 Détection de version OS](#64-détection-de-version-os)
    - [6.5 Classification des types d'OS par plage IP](#65-classification-des-types-dos-par-plage-ip)
  - [7. Choix techniques et compromis](#7-choix-techniques-et-compromis)
    - [7.1 Synthèse des choix techniques](#71-synthèse-des-choix-techniques)
    - [7.2 Compromis architecturaux](#72-compromis-architecturaux)
      - [Architecture monolithique (fichier unique)](#architecture-monolithique-fichier-unique)
      - [`mainENV.py` vs. `main.py`](#mainenvpy-vs-mainpy)
      - [Authentification par mot de passe vs. clé SSH](#authentification-par-mot-de-passe-vs-clé-ssh)
      - [Ping sweep vs. Nmap](#ping-sweep-vs-nmap)
    - [7.3 Limites connues](#73-limites-connues)

<!-- /code_chunk_output -->

# Dossier technique et fonctionnel — NTL-SysToolbox

**Version :** 1.0
**Date :** 15/02/2026
**Projet :** MSPR — Nord-Transit Logistique
**Point d'entrée de référence :** `mainENV.py`

---

## Table des matières

1. [Objectif de l'outil](#1-objectif-de-loutil)
2. [Architecture logique](#2-architecture-logique)
3. [Répartition par modules](#3-répartition-par-modules)
4. [Configuration et gestion des secrets](#4-configuration-et-gestion-des-secrets)
5. [Ergonomie du menu interactif](#5-ergonomie-du-menu-interactif)
6. [Démarche d'audit d'obsolescence](#6-démarche-daudit-dobsolescence)
7. [Choix techniques et compromis](#7-choix-techniques-et-compromis)

---

## 1. Objectif de l'outil

NTL-SysToolbox est un outil CLI Python concu pour la DSI de Nord-Transit Logistique. Il répond à trois besoins opérationnels :

- **Diagnostic** : vérifier la disponibilité et l'état des serveurs de l'infrastructure NTL.
- **Sauvegarde** : exporter la base de données WMS (dump SQL et CSV).
- **Audit d'obsolescence** : évaluer le statut de fin de vie (EOL) des systèmes d'exploitation déployés.

L'outil cible un parc hétérogène de 7 serveurs (4 Ubuntu, 3 Windows Server) sur le sous-réseau `192.168.10.0/24`.

---

## 2. Architecture logique

### 2.1 Vue d'ensemble

```
┌─────────────────────────────────────────────────────┐
│                    mainENV.py                        │
│                  (point d'entrée)                    │
├─────────────┬──────────────┬────────────────────────┤
│  Module 1   │  Module 2    │  Module 3              │
│ Diagnostic  │ Sauvegarde   │ Audit EOL              │
├─────────────┴──────────────┴────────────────────────┤
│              Couche connexion                        │
│     ssh_connect()  /  winrm_session()               │
│     ssh_run()      /  winrm_ps()                    │
├─────────────────────────────────────────────────────┤
│              Couche utilitaire                       │
│     get_timestamp()  /  save_report()               │
├──────────┬──────────────────────┬───────────────────┤
│  .env    │  API endoflife.date  │  Infrastructure   │
│ (config) │  (données EOL)       │  SSH / WinRM      │
└──────────┴──────────────────────┴───────────────────┘
```

### 2.2 Organisation du code

L'architecture retenue est **monolithique** : l'ensemble de la logique métier est contenu dans un fichier unique (`mainENV.py`, 272 lignes). Ce fichier se décompose en quatre sections logiques :

| Section        | Lignes  | Rôle                                                                               |
| -------------- | ------- | ---------------------------------------------------------------------------------- |
| Configuration  | 1-33    | Imports, chargement du `.env`, construction du dictionnaire `INFRA`                |
| Helpers        | 35-66   | Fonctions de connexion (SSH, WinRM), utilitaires (horodatage, export JSON)         |
| Modules métier | 69-248  | Diagnostic, Sauvegarde, Audit — chaque module exposé via une fonction `*_module()` |
| Menu principal | 251-272 | Boucle interactive `main()` avec aiguillage vers les modules                       |

---

## 3. Répartition par modules

### 3.1 Module Diagnostic (`diag_module`)

**Objectif :** collecter l'état de disponibilité et les métriques de chaque serveur déclaré.

**Fonctionnement :**

```
diag_module()
  ├── pour chaque serveur dans INFRA :
  │     ├── si os == "windows" → diag_windows(server_key)
  │     │     └── WinRM → script PowerShell → JSON (OS, Uptime, CPU, AD, DNS)
  │     └── si os == "ubuntu"  → diag_ubuntu(server_key)
  │           ├── SSH → uptime -p && free -m && lsb_release -d
  │           └── si server_key == "wms-db" → test MySQL (SELECT 1)
  ├── affichage JSON dans le terminal
  └── save_report() → reports/diag_<timestamp>.json
```

**Protocoles utilisés :**

| OS cible | Protocole | Bibliothèque | Port | Authentification |
| -------- | --------- | ------------ | ---- | ---------------- |
| Ubuntu   | SSH       | `paramiko`   | 22   | Mot de passe     |
| Windows  | WinRM     | `pywinrm`    | 5985 | NTLM             |

**Métriques collectées :**

- **Ubuntu** : uptime (`uptime -p`), mémoire (`free -m`), version OS (`lsb_release -d`), état MySQL (serveur `wms-db` uniquement).
- **Windows** : version OS (`Win32_OperatingSystem.Caption`), uptime en jours, charge CPU moyenne, état des services Active Directory (`NTDS`) et DNS.

**Timeout :** 5 secondes par connexion SSH. Le timeout WinRM est celui par défaut de `pywinrm` (30 secondes).

### 3.2 Module Sauvegarde (`backup_module`)

**Objectif :** exporter la base de données `ntl_wms` hébergée sur le serveur `wms-db`.

**Fonctionnement :**

```
backup_module()
  ├── vérification de la présence de "wms-db" dans INFRA
  ├── connexion SSH vers wms-db
  ├── mysqldump -u root ntl_wms → backups/backup_<timestamp>.sql
  ├── SELECT * FROM stocks      → backups/stocks_<timestamp>.csv
  └── fermeture de la connexion
```

**Détails techniques :**

- Le dump SQL est réalisé via `mysqldump` exécuté à distance par SSH. Le flux `stdout` de la commande est directement écrit dans un fichier local, sans étape intermédiaire sur le serveur distant.
- L'export CSV de la table `stocks` est réalisé via une requête `SELECT * FROM stocks` exécutée en mode `--batch` (séparateur tabulation), puis convertie en CSV standard côté client.
- Le mot de passe MySQL est lu depuis la variable d'environnement `DB_ROOT_PWD`.

### 3.3 Module Audit d'obsolescence (`audit_module`)

**Objectif :** évaluer le statut de fin de support des OS déployés sur le réseau NTL.

**Trois sous-modes :**

| Mode                 | Description                                | Entrée                                   | Sortie             |
| -------------------- | ------------------------------------------ | ---------------------------------------- | ------------------ |
| 1 — Scan réseau      | Ping sweep + détection de version OS       | Plage IP 192.168.10.10-55                | Rapport JSON       |
| 2 — Consultation EOL | Affichage des cycles de vie d'un OS        | Nom d'OS saisi par l'utilisateur         | Affichage terminal |
| 3 — Import CSV       | Qualification EOL à partir d'un inventaire | Fichier CSV (colonnes : ip, os, version) | Rapport JSON       |

Le fonctionnement détaillé de la démarche d'audit est décrit en section 6.

---

## 4. Configuration et gestion des secrets

### 4.1 Evolution depuis `main.py`

L'outil a connu deux versions de gestion de la configuration :

| Version               | Fichier                   | Méthode                                                                   | Problème de sécurité                                                            |
| --------------------- | ------------------------- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| `main.py` (legacy)    | `conf.json` + code source | Lecture JSON directe ; mot de passe MySQL codé en dur (`"TonMotDePasse"`) | Mots de passe en clair dans le code source et dans un fichier JSON versionnable |
| `mainENV.py` (actuel) | `.env`                    | Chargement via `python-dotenv` ; mot de passe MySQL dans `DB_ROOT_PWD`    | Mots de passe dans le `.env` uniquement, excluable du versionnement             |

**Justification du passage au `.env` :**

- **Séparation code / configuration** : les identifiants ne sont plus dans le code source, ce qui élimine le risque de fuite via le dépôt Git.
- **Compatibilité opérationnelle** : le format `.env` est un standard de l'industrie, lisible sans outillage, et compatible avec Docker, systemd et les plateformes CI/CD.
- **Simplicité** : aucune dépendance lourde (pas de coffre-fort de secrets type Vault), adapté à la taille de l'infrastructure NTL (7 serveurs).

### 4.2 Mécanisme de chargement

La fonction `load_infra_from_env()` (lignes 20-29 de `mainENV.py`) reconstruit le dictionnaire `INFRA` à partir des variables d'environnement préfixées `INFRA_` :

```
Variable d'environnement              →   Clé interne
INFRA_WMS_DB=192.168.10.21,...,ubuntu  →   infra["wms-db"]
INFRA_DC01=192.168.10.10,...,windows   →   infra["dc01"]
```

**Transformation appliquée :** le préfixe `INFRA_` est supprimé, le nom est converti en minuscules et les underscores sont remplacés par des tirets. Ce mécanisme permet d'ajouter ou retirer un serveur en modifiant uniquement le fichier `.env`, sans toucher au code.

### 4.3 Gestion des secrets — état actuel et limites

| Aspect                         | Implémentation                           | Limite identifiée                                                                           |
| ------------------------------ | ---------------------------------------- | ------------------------------------------------------------------------------------------- |
| Stockage des mots de passe     | Fichier `.env` en clair                  | Pas de chiffrement au repos                                                                 |
| Transmission des mots de passe | SSH (chiffré) / WinRM NTLM (chiffré)     | Pas de support clé SSH ou certificat                                                        |
| Mot de passe MySQL             | Variable `DB_ROOT_PWD` dans `.env`       | Transmis en argument de commande (`-p'...'`) — visible dans `ps aux` sur le serveur distant |
| Versionnement                  | Le `.env` doit figurer dans `.gitignore` | Pas de `.gitignore` fourni par défaut                                                       |

**Compromis assumé :** le stockage en clair dans le `.env` est accepté car l'outil est destiné à fonctionner sur un poste d'administration contrôlé, dans un réseau interne. L'intégration d'un coffre-fort de secrets (HashiCorp Vault, Azure Key Vault) ajouterait une complexité disproportionnée pour un parc de 7 machines.

---

## 5. Ergonomie du menu interactif

### 5.1 Principe de conception

L'outil adopte un **menu textuel numéroté** avec boucle infinie (`while True`). Ce choix est motivé par :

- **Contexte d'utilisation** : poste d'administration, accès terminal, pas d'interface graphique requise.
- **Public cible** : techniciens et administrateurs systèmes habitués au terminal.
- **Simplicité de déploiement** : aucune dépendance frontend (pas de serveur web, pas de framework UI).

### 5.2 Structure de navigation

```
Menu principal
├── 1. Diagnostic       → exécution directe (pas de sous-menu)
├── 2. Sauvegarde       → exécution directe (pas de sous-menu)
├── 3. Audit            → sous-menu à 3 choix
│     ├── 1. Scan réseau
│     ├── 2. Consultation EOL par OS
│     └── 3. Import CSV
└── 4. Quitter          → sortie de la boucle
```

**Retour au menu :** après l'exécution d'un module, l'utilisateur revient automatiquement au menu principal. Il n'y a pas de confirmation intermédiaire ni de navigation complexe.

### 5.3 Retour utilisateur

- **Affichage en temps réel** : les résultats du diagnostic et du scan réseau sont affichés ligne par ligne pendant l'exécution.
- **Message de confirmation** : `[OK]` pour les opérations réussies, `[ERREUR]` en cas d'échec.
- **Persistance** : un message `[INFO] Rapport généré : <chemin>` confirme l'écriture du fichier de sortie.
- **Alerte au démarrage** : si aucun serveur n'est chargé depuis le `.env`, un avertissement est affiché avant le menu.

### 5.4 Compromis ergonomiques

| Choix                                  | Justification                                                       | Alternative écartée                                                 |
| -------------------------------------- | ------------------------------------------------------------------- | ------------------------------------------------------------------- |
| Menu texte numéroté                    | Immédiatement compréhensible, pas de dépendance                     | Bibliothèque `curses` ou `click` — complexité inutile               |
| Pas de paramètres en ligne de commande | L'outil est concu pour un usage interactif supervisé                | `argparse` avec sous-commandes — pertinent si automatisation future |
| Sous-menu uniquement pour l'audit      | Le diagnostic et la sauvegarde n'ont qu'un seul comportement        | Sous-menus pour tous les modules — surcharge cognitive inutile      |
| Pas de pagination des résultats        | Les volumes de sortie restent lisibles (7 serveurs, 46 IP scannées) | Pagination — justifiée uniquement pour des parcs plus grands        |

---

## 6. Démarche d'audit d'obsolescence

### 6.1 Source de référence : API endoflife.date

L'audit d'obsolescence s'appuie sur l'API REST publique **endoflife.date** (`https://endoflife.date/api/`).

**Justification du choix :**

| Critère       | endoflife.date                                                      | Alternatives considérées                                                      |
| ------------- | ------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Couverture    | 300+ produits dont Ubuntu, Windows Server, CentOS                   | Sites éditeurs (Microsoft, Canonical) — données dispersées, pas d'API unifiée |
| Format        | JSON structuré, RESTful, sans authentification                      | Scraping de pages HTML — fragile et non maintenable                           |
| Licence       | Données ouvertes, usage libre                                       | Bases propriétaires — coût, licences                                          |
| Fiabilité     | Communauté active, données vérifiées contre les sources officielles | Maintenance manuelle d'une base locale — charge d'entretien                   |
| Disponibilité | API publique, haute disponibilité                                   | Base locale — pas de mise à jour automatique                                  |

**Point d'attention :** l'outil dépend d'un service externe. En cas d'indisponibilité de l'API, le module audit retourne `None` et le statut est classé `Inconnu`. Un timeout de 5 secondes est appliqué pour ne pas bloquer l'exécution.

### 6.2 Logique de qualification EOL

La fonction `analyze_obsolescence()` applique l'algorithme suivant :

```
Entrée : version détectée + données EOL du produit
                    │
          La version est-elle connue ?
           /                    \
         Non                    Oui
          │                      │
    "Inconnu"          Recherche du cycle correspondant
                        (correspondance partielle sur le champ 'cycle')
                                 │
                       Cycle trouvé ?
                      /              \
                    Non              Oui
                     │                │
         "Version non           Le champ 'eol' est-il un booléen ?
          répertoriée"          /                    \
                              Oui                    Non (date)
                               │                      │
                         "OK : Supporté"      Calcul du delta en jours
                                              entre la date EOL et aujourd'hui
                                                    │
                                          ┌─────────┼─────────┐
                                       < 0 j     < 180 j     >= 180 j
                                          │         │            │
                                     CRITIQUE   ATTENTION       OK
```

### 6.3 Seuil de 180 jours

Le seuil de **180 jours** (environ 6 mois) détermine la frontière entre `OK` et `ATTENTION`. Ce seuil correspond à une fenêtre raisonnable pour planifier et exécuter une migration d'OS dans un contexte PME :

- Qualification et test d'un nouvel OS : ~1 mois
- Planification avec les équipes métier : ~1 mois
- Migration progressive des serveurs : ~2-3 mois
- Marge de sécurité : ~1 mois

**Compromis :** ce seuil est codé en dur (ligne 177 de `mainENV.py`). Un seuil configurable via le `.env` aurait été envisageable, mais la valeur de 180 jours est un standard du marché et ne nécessite pas d'ajustement fréquent.

### 6.4 Détection de version OS

Lors du scan réseau (mode 1), l'outil tente de détecter automatiquement la version OS de chaque hôte actif :

| OS      | Méthode            | Commande exécutée                                                                               |
| ------- | ------------------ | ----------------------------------------------------------------------------------------------- |
| Ubuntu  | SSH                | `lsb_release -rs` (fallback : lecture de `/etc/os-release`)                                     |
| Windows | WinRM + PowerShell | `(Get-CimInstance Win32_OperatingSystem).Caption` → extraction de l'année via regex `(20\d{2})` |

**Condition :** la détection n'est possible que si l'IP figure dans le dictionnaire `INFRA` (identifiants connus). Pour les hôtes sans identifiants, le statut est `Version Inconnue`.

### 6.5 Classification des types d'OS par plage IP

Lors du scan réseau, le type d'OS est déduit de l'adresse IP selon une convention propre au réseau NTL :

| Plage IP                      | Type d'OS attribué |
| ----------------------------- | ------------------ |
| 192.168.10.10 – 192.168.10.19 | `windows-server`   |
| 192.168.10.20 – 192.168.10.39 | `ubuntu`           |
| 192.168.10.40                 | `centos` (IPBX)    |
| 192.168.10.41 – 192.168.10.49 | `ubuntu`           |
| 192.168.10.50                 | `windows-server`   |
| 192.168.10.51 – 192.168.10.55 | `ubuntu`           |

**Compromis assumé :** cette heuristique est codée en dur et reflète le plan d'adressage actuel de NTL. Toute réorganisation du sous-réseau nécessiterait une mise à jour du code. Une approche plus robuste (détection dynamique de l'OS via fingerprinting réseau) aurait été plus générique mais disproportionnée pour un réseau de 46 adresses avec un plan d'adressage stable.

---

## 7. Choix techniques et compromis

### 7.1 Synthèse des choix techniques

| Décision            | Choix retenu                     | Justification                                                                                   |
| ------------------- | -------------------------------- | ----------------------------------------------------------------------------------------------- |
| Langage             | Python 3.10+                     | Ecosystème riche pour l'administration système, bibliothèques SSH/WinRM matures                 |
| Architecture        | Fichier unique monolithique      | Adapté à la taille du projet (~270 lignes) ; facilite le déploiement (un seul fichier à copier) |
| Configuration       | Fichier `.env` + `python-dotenv` | Standard industriel, séparation code/config, compatible CI/CD                                   |
| Connexion Linux     | `paramiko` (SSH)                 | Bibliothèque de référence en Python, pure Python, pas de dépendance système                     |
| Connexion Windows   | `pywinrm` (WinRM/NTLM)           | Seule option mature en Python pour l'administration Windows à distance sans agent               |
| Données EOL         | API `endoflife.date`             | Gratuite, complète, structurée, sans authentification                                           |
| Format des rapports | JSON                             | Lisible par un humain, parsable par un outil, compatible avec des traitements ultérieurs        |
| Interface           | CLI interactive (menu texte)     | Aucune dépendance UI, déploiement immédiat                                                      |

### 7.2 Compromis architecturaux

#### Architecture monolithique (fichier unique)

**Choix :** tout le code dans `mainENV.py`.

**Argument :** avec environ 270 lignes, le projet reste suffisamment compact pour tenir dans un fichier unique sans nuire à la lisibilité. Cette approche offre plusieurs avantages concrets :

- **Déploiement simplifié** : un seul fichier Python à copier sur le poste d'administration.
- **Pas de risque de divergence** : aucune duplication de code entre plusieurs fichiers.
- **Navigation directe** : toute la logique est visible et consultable sans naviguer entre fichiers.

**Limite :** pour un projet plus grand, une extraction en modules avec injection de dépendances serait souhaitable.

#### `mainENV.py` vs. `main.py`

| Aspect                              | `main.py` (legacy)                                                               | `mainENV.py` (retenu)                                                       |
| ----------------------------------- | -------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| Configuration                       | `conf.json` lu directement                                                       | `.env` via `python-dotenv`                                                  |
| Mot de passe MySQL                  | Codé en dur (`"TonMotDePasse"`)                                                  | Variable `DB_ROOT_PWD`                                                      |
| Connexion MySQL (diagnostic)        | Connecteur Python `mysql.connector` (port 3306 direct)                           | Commande `mysql` via SSH (pas d'exposition du port MySQL)                   |
| Backup SQL                          | `mysqldump` distant + écriture sur le serveur, puis connecteur MySQL pour le CSV | `mysqldump` via SSH (stdout rapatrié) + requête `mysql --batch` pour le CSV |
| Dépendance `mysql-connector-python` | Requise                                                                          | Non requise                                                                 |

**Justification :** `mainENV.py` élimine la nécessité d'exposer le port MySQL (3306) sur le réseau. Toutes les interactions avec la base passent par le tunnel SSH, ce qui réduit la surface d'attaque.

#### Authentification par mot de passe vs. clé SSH

**Choix :** authentification par mot de passe uniquement.

**Argument :** l'infrastructure NTL est un environnement contrôlé avec des serveurs configurés pour l'authentification par mot de passe. Le passage aux clés SSH nécessiterait un déploiement de clés sur l'ensemble du parc et une modification des procédures d'exploitation existantes. Pour un parc de 4 serveurs Linux, le gain sécuritaire ne justifie pas la charge de migration.

**Recommandation pour l'avenir :** migrer vers l'authentification par clé SSH si le parc s'agrandit ou si les exigences de sécurité évoluent.

#### Ping sweep vs. Nmap

**Choix :** scan réseau par `ping` (ICMP) via `subprocess`.

**Argument :** le ping ICMP est suffisant pour la détection de présence dans un réseau interne sans filtrage. `Nmap` offrirait des capacités avancées (détection d'OS, scan de ports) mais introduirait une dépendance binaire externe, plus lourde à déployer et potentiellement soumise à des restrictions de politique de sécurité.

### 7.3 Limites connues

| Limite                                       | Impact                                                                                             | Piste d'amélioration                                                              |
| -------------------------------------------- | -------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Exécution séquentielle des diagnostics       | Temps d'exécution proportionnel au nombre de serveurs (jusqu'à 30s par serveur Windows en timeout) | Parallélisation via `concurrent.futures.ThreadPoolExecutor`                       |
| Plan d'adressage IP codé en dur dans l'audit | Toute modification du réseau nécessite un changement de code                                       | Externaliser le mapping IP/OS dans le `.env` ou un fichier de configuration dédié |
| Pas de journalisation (`logging`)            | Difficile de diagnostiquer un problème sans relancer l'outil                                       | Ajouter le module `logging` avec rotation de fichiers                             |
| Pas de tests automatisés                     | Risque de régression lors des modifications                                                        | Ajouter des tests unitaires avec `pytest` et des mocks pour SSH/WinRM             |
| `AutoAddPolicy` pour SSH                     | Accepte toute clé hôte sans vérification — vulnérable au MITM                                      | Utiliser `RejectPolicy` avec un fichier `known_hosts` prédéployé                  |

---

_Ce dossier technique et fonctionnel documente l'état actuel de NTL-SysToolbox. Les choix retenus privilégient la simplicité de déploiement et la maintenabilité par une petite équipe, dans le contexte d'un parc de taille modeste. Les limites identifiées constituent des axes d'amélioration pour les versions futures._
