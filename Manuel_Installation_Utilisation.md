# Manuel d'installation et d'utilisation — NTL-SysToolbox

**Version :** 1.0
**Date :** 15/02/2026
**Destinataire :** Direction des Systèmes d'Information — Nord-Transit Logistique
**Point d'entrée :** `main.py`

---

## Table des matières

1. [Prérequis](#1-prérequis)
2. [Installation](#2-installation)
3. [Paramétrage du fichier de configuration `.env`](#3-paramétrage-du-fichier-de-configuration-env)
4. [Lancement de l'outil en mode interactif](#4-lancement-de-loutil-en-mode-interactif)
5. [Description des modules](#5-description-des-modules)
6. [Emplacement des artefacts produits](#6-emplacement-des-artefacts-produits)
7. [Dépannage](#7-dépannage)

---

## 1. Prérequis

### Machine cible

| Élément                | Exigence                                                      |
| ---------------------- | ------------------------------------------------------------- |
| Système d'exploitation | Windows 10/11, Ubuntu 22.04+, ou macOS 13+                    |
| Python                 | Version 3.10 ou supérieure                                    |
| pip                    | Inclus avec Python (vérifier avec `pip --version`)            |
| Réseau                 | Accès au sous-réseau **192.168.10.0/24** (infrastructure NTL) |
| Accès Internet         | Requis pour le module Audit (API `endoflife.date`)            |

### Prérequis réseau sur les serveurs cibles

- **Serveurs Ubuntu** : service SSH activé (port 22).
- **Serveurs Windows** : service WinRM activé (port 5985, transport NTLM).
- **Serveur wms-db** : MySQL installé et accessible en local avec le compte `root`.

---

## 2. Installation

### 2.1 Récupérer le projet

Copier l'intégralité du dossier `MSPR-NTL-CODE/` sur la machine de déploiement. La structure attendue est :

```
MSPR-NTL-CODE/
├── main.py               # Point d'entrée principal
├── requirements.txt      # Dépendances Python
├── .env                  # Fichier de configuration (à créer)
├── reports/              # Rapports générés (créé automatiquement)
└── backups/              # Sauvegardes générées (créé automatiquement)
```

### 2.2 Créer l'environnement virtuel Python

Ouvrir un terminal dans le dossier `MSPR-NTL-CODE/` et exécuter :

```bash
python3 -m venv venv
```

### 2.3 Activer l'environnement virtuel

**Linux / macOS :**

```bash
source venv/bin/activate
```

**Windows (cmd) :**

```cmd
venv\Scripts\activate.bat
```

**Windows (PowerShell) :**

```powershell
.\venv\Scripts\Activate.ps1
```

> Le prompt du terminal doit afficher `(venv)` en préfixe, confirmant l'activation.

### 2.4 Installer les dépendances

```bash
pip install -r requirements.txt
```

Les principales dépendances installées sont :

| Paquet                  | Rôle                                      |
| ----------------------- | ----------------------------------------- |
| `paramiko`              | Connexion SSH vers les serveurs Ubuntu    |
| `pywinrm` (via `winrm`) | Connexion WinRM vers les serveurs Windows |
| `requests`              | Appels HTTP vers l'API endoflife.date     |
| `python-dotenv`         | Lecture du fichier `.env`                 |

---

## 3. Paramétrage du fichier de configuration `.env`

Le fichier `.env` centralise les identifiants de connexion aux serveurs et le mot de passe MySQL. Il doit être créé **à la racine du dossier `MSPR-NTL-CODE/`**.

### 3.1 Format des variables serveur

Chaque serveur est déclaré par une variable au format :

```
INFRA_<NOM_SERVEUR>=<ip>,<utilisateur>,<mot_de_passe>,<os>
```

| Champ          | Description                                      | Valeurs possibles                        |
| -------------- | ------------------------------------------------ | ---------------------------------------- |
| `NOM_SERVEUR`  | Identifiant du serveur (majuscules, underscores) | Libre                                    |
| `ip`           | Adresse IP du serveur                            | Ex : `192.168.10.21`                     |
| `utilisateur`  | Compte de connexion SSH ou WinRM                 | Ex : `root`, `Administrateur@domaine.fr` |
| `mot_de_passe` | Mot de passe du compte                           | —                                        |
| `os`           | Système d'exploitation                           | `ubuntu` ou `windows`                    |

> **Convention de nommage :** le préfixe `INFRA_` est supprimé au chargement, les underscores `_` sont convertis en tirets `-` et le nom passe en minuscules. Ainsi `INFRA_WMS_DB` devient la clé interne `wms-db`.

### 3.2 Variable du mot de passe MySQL

```
DB_ROOT_PWD=<mot_de_passe_root_mysql>
```

Cette variable est utilisée par les modules Diagnostic (test de connexion MySQL) et Sauvegarde (mysqldump).

### 3.3 Exemple complet de fichier `.env`

```env
# Serveurs Ubuntu (SSH, port 22)
INFRA_WMS_DB=192.168.10.21,wms-db,motdepasse1,ubuntu
INFRA_WMS_APP=192.168.10.22,wms-app,motdepasse2,ubuntu
INFRA_IPBX_VM=192.168.10.40,ipbx,motdepasse3,ubuntu
INFRA_DIMITRI=192.168.10.36,dimitri,motdepasse4,ubuntu

# Serveurs Windows (WinRM, port 5985)
INFRA_DC01=192.168.10.10,Administrateur@nord-transit.fr,motdepasse5,windows
INFRA_DC02=192.168.10.11,Administrateur@nord-transit.fr,motdepasse5,windows
INFRA_SUPER_01=192.168.10.50,Administrateur@nord-transit.fr,motdepasse5,windows

# Mot de passe root MySQL (serveur wms-db)
DB_ROOT_PWD=motdepasse_mysql
```

> **Sécurité :** le fichier `.env` contient des mots de passe en clair. Il ne doit **jamais** être versionné (l'ajouter dans `.gitignore`) et ses permissions doivent être restreintes (`chmod 600 .env` sous Linux/macOS).

### 3.4 Ajouter ou retirer un serveur

- **Ajouter :** ajouter une ligne `INFRA_<NOM>=...` dans le `.env`, puis relancer l'outil.
- **Retirer :** supprimer ou commenter (préfixe `#`) la ligne correspondante.
- Aucune modification du code source n'est nécessaire.

---

## 4. Lancement de l'outil en mode interactif

### 4.1 Démarrage

Depuis le dossier `MSPR-NTL-CODE/`, avec l'environnement virtuel activé :

```bash
python main.py
```

### 4.2 Menu principal

L'outil affiche le menu suivant :

```
=============================================
  NTL-SysToolbox - GESTION D'EXPLOITATION
=============================================
1. [Diagnostic] Disponibilité & Ressources
2. [Sauvegarde] Export SQL & CSV (WMS)
3. [Audit] Inventaire & Obsolescence (EOL)
4. Quitter

Choix :
```

Saisir le numéro du module souhaité puis appuyer sur `Entrée`.

### 4.3 Alerte au démarrage

Si le message suivant apparaît :

```
/!\ Alerte : Aucun serveur chargé depuis le fichier .env
```

Cela signifie que le fichier `.env` est absent, vide, ou ne contient aucune variable `INFRA_*` valide. Vérifier le fichier (cf. section 3).

---

## 5. Description des modules

### 5.1 Module 1 — Diagnostic (choix `1`)

**Fonction :** interroge chaque serveur déclaré dans le `.env` pour collecter son état.

| Type de serveur   | Protocole | Informations collectées                        |
| ----------------- | --------- | ---------------------------------------------- |
| Ubuntu            | SSH       | Uptime, mémoire libre, version OS              |
| Ubuntu (`wms-db`) | SSH       | Idem + test de connexion MySQL                 |
| Windows           | WinRM     | Version OS, uptime, charge CPU, état AD et DNS |

**Déroulement :**

1. L'outil parcourt tous les serveurs du `.env`.
2. Pour chaque serveur, il tente une connexion (timeout : 5 secondes).
3. Les résultats sont affichés en JSON dans le terminal.
4. Un rapport JSON horodaté est enregistré dans `reports/`.

**Statuts possibles :**

- `UP` : le serveur a répondu.
- `DOWN` : connexion impossible (timeout, mauvais identifiants, service arrêté).

### 5.2 Module 2 — Sauvegarde (choix `2`)

**Fonction :** se connecte en SSH au serveur `wms-db` et exporte la base de données `ntl_wms`.

**Opérations réalisées :**

1. **Dump SQL complet** : exécute `mysqldump` sur la base `ntl_wms` et enregistre le fichier `.sql`.
2. **Export CSV** : exécute une requête `SELECT * FROM stocks` et enregistre le résultat en `.csv`.

**Prérequis spécifique :** la variable `INFRA_WMS_DB` doit exister dans le `.env`. En son absence, le message suivant s'affiche :

```
[ERREUR] Configuration wms-db introuvable dans le .env
```

### 5.3 Module 3 — Audit d'obsolescence (choix `3`)

**Fonction :** évalue le statut de fin de vie (EOL) des systèmes d'exploitation via l'API publique `endoflife.date`.

Un sous-menu propose trois modes :

```
1. Scan réseau complet (192.168.10.x)
2. Lister cycles de vie pour un OS spécifique
3. Importer un inventaire CSV
```

#### Mode 1 — Scan réseau complet

- Effectue un ping sweep sur la plage `192.168.10.10` à `192.168.10.55`.
- Pour chaque hôte qui répond, tente de détecter la version OS (SSH ou WinRM si les identifiants sont connus).
- Interroge l'API `endoflife.date` pour déterminer le statut EOL.
- Enregistre un rapport JSON dans `reports/` et l'exporte aussi en fichier CSV dans `reports/`.

#### Mode 2 — Consultation EOL par OS

- L'utilisateur saisit un nom d'OS (ex : `ubuntu`, `windows-server`).
- L'outil affiche les 5 derniers cycles de vie connus.

#### Mode 3 — Import CSV

- Permet d'importer un inventaire au format CSV pour évaluer l'obsolescence.

**Classification EOL :**

| Statut      | Signification                      |
| ----------- | ---------------------------------- |
| `OK`        | Supporté, fin de vie > 180 jours   |
| `ATTENTION` | Fin de vie dans moins de 180 jours |
| `CRITIQUE`  | Fin de support dépassée            |

---

## 6. Emplacement des artefacts produits

Tous les artefacts sont générés dans des sous-dossiers du répertoire `MSPR-NTL-CODE/`. Ces dossiers sont créés automatiquement au premier usage.

### 6.1 Rapports — `reports/`

| Module       | Préfixe du fichier            | Format | Exemple                                                   |
| ------------ | ----------------------------- | ------ | --------------------------------------------------------- |
| Diagnostic   | `diag_`                       | JSON   | `reports/diag_20260215_143022.json`                       |
| Audit (scan) | `audit_obsolescence_complet_` | JSON   | `reports/audit_obsolescence_complet_20260215_150000.json` |
| Audit (scan) | `audit_obsolescence_complet_` | CSV    | `reports/audit_obsolescence_complet_20260215_150000.csv`  |

**Convention de nommage :** `<préfixe>_<AAAAMMJJ>_<HHMMSS>.json`

### 6.2 Sauvegardes — `backups/`

| Type          | Préfixe du fichier | Format | Exemple                              |
| ------------- | ------------------ | ------ | ------------------------------------ |
| Dump SQL      | `backup_`          | SQL    | `backups/backup_20260215_143022.sql` |
| Export stocks | `stocks_`          | CSV    | `backups/stocks_20260215_143022.csv` |

**Convention de nommage :** `<préfixe>_<AAAAMMJJ>_<HHMMSS>.<ext>`

### 6.3 Arborescence complète après utilisation

```
MSPR-NTL-CODE/
├── main.py
├── .env
├── requirements.txt
├── venv/
├── reports/
│   ├── diag_20260215_143022.json
│   └── audit_obsolescence_complet_20260215_150000.json
└── backups/
    ├── backup_20260215_143022.sql
    └── stocks_20260215_143022.csv
```

---

## 7. Dépannage

| Problème                                      | Cause probable                                | Solution                                                                       |
| --------------------------------------------- | --------------------------------------------- | ------------------------------------------------------------------------------ |
| `Aucun serveur chargé depuis le fichier .env` | Fichier `.env` absent ou mal formaté          | Vérifier la présence et le contenu du fichier (cf. section 3)                  |
| `timed out` sur un serveur Ubuntu             | SSH inaccessible ou IP incorrecte             | Vérifier que le service SSH est actif et que l'IP est correcte                 |
| `Max retries exceeded` sur un serveur Windows | WinRM non activé ou port 5985 bloqué          | Activer WinRM sur le serveur (`winrm quickconfig`) et ouvrir le port           |
| `Configuration wms-db introuvable`            | Variable `INFRA_WMS_DB` absente du `.env`     | Ajouter la ligne `INFRA_WMS_DB=...` dans le fichier `.env`                     |
| `ModuleNotFoundError` au lancement            | Dépendances non installées ou venv non activé | Activer le venv puis exécuter `pip install -r requirements.txt`                |
| Erreur MySQL `Access denied`                  | Mot de passe `DB_ROOT_PWD` incorrect          | Vérifier la valeur de `DB_ROOT_PWD` dans le `.env`                             |
| Audit : `OS non trouvé`                       | Nom d'OS mal orthographié                     | Utiliser les noms exacts de l'API : `ubuntu`, `windows-server`, `centos`, etc. |

---

_Ce manuel permet à la DSI de déployer et utiliser NTL-SysToolbox de manière autonome. Pour toute évolution (ajout de serveurs, changement de sous-réseau), seul le fichier `.env` est à modifier._
