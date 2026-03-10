# NTL-SysToolbox

NTL-SysToolbox est un outil en ligne de commande Python conçu pour simplifier la gestion et l'exploitation d'une infrastructure de serveurs (Windows et Linux). 

## 🚀 Fonctionnalités Principales

Le script lance un menu interactif qui donne accès à 3 modules :

1. **Diagnostic (Disponibilité & Ressources)** :
   - Vérifie l'état des serveurs de la topologie (via SSH pour Linux et WinRM pour Windows).
   - Récupère les métriques essentielles (Uptime, CPU, RAM) ainsi que le statut des services critiques (Active Directory, DNS, MySQL).
   
2. **Sauvegarde Automatisée (Base de données WMS)** :
   - Cible le serveur de base de données `wms-db`.
   - Effectue un dump SQL complet (`ntl_wms`).
   - Exporte individuellement le contenu de toutes les tables au format CSV.

3. **Audit d'Obsolescence (EOL - End of Life)** :
   - Effectue un scan réseau sur la plage `192.168.10.x` pour détecter les machines.
   - Identifie la version de l'OS (Ubuntu, Windows Server, CentOS).
   - Interroge l'API officielle `endoflife.date` pour informer si le système est supporté, en fin de vie proche ou critique.
   - Exporte les résultats dans des rapports JSON et CSV exploitables.

## ⚙️ Prérequis et Installation

1. **Python 3** doit être installé.
2. Installez les dépendances du projet :
   ```bash
   pip install -r requirements.txt
   ```
3. Créez un fichier **`.env`** à la racine pour y configurer votre infrastructure (le script charge dynamiquement les variables commençant par `INFRA_`) :
   ```env
   # Format --> INFRA_[NOM_SERVEUR]=[IP],[UTILISATEUR],[MOT_DE_PASSE],[OS]
   INFRA_AD=192.168.10.10,Administrator,MonMotDePasse,windows
   INFRA_WMS_DB=192.168.10.30,admin,MonMotDePasse,ubuntu
   
   # Mot de passe pour la base de données MySQL
   DB_ROOT_PWD=MotDePasseRootSQL
   ```

## 🛠️ Utilisation

Démarrez simplement le script principal :

```bash
python main.py
```

Laissez-vous guider par le menu interactif. Les différents rapports et sauvegardes sont automatiquement générés dans les dossiers `reports/` et `backups/`.
