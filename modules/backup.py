#2/ Module de sauvegarde WMS
# Fonctions :
#       Permettre une sauvegarde de la base de données au format SQL
#       Permettre un export d’une table au format CSV

import subprocess
INFRA = {
    "wms-db": {"ip": "192.168.10.21", "user": "wms-db", "pwd": "passroot", "os": "ubuntu"},
    "wms-app": {"ip": "192.168.10.22", "user": "wms-app", "pwd": "passroot", "os": "ubuntu"},
    "DC01": {"ip": "192.168.10.10", "user": "Administrateur@nord-transit.fr", "pwd": "caca31000!", "os": "windows"},
    "DC02": {"ip": "192.168.10.11", "user": "Administrateur@nord-transit.fr", "pwd": "caca31000!", "os": "windows"}
}

def backup_wms():
    srv = INFRA["wms-db"]
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    print(f"\n--- Lancement de la sauvegarde WMS ({timestamp}) ---")
    
    try:
        # 1. Export SQL complet via SSH (mysqldump)
        # On utilise l'utilisateur 'root' et le mot de passe configuré
        sql_file = f"backup_ntl_wms_{timestamp}.sql"
        dump_cmd = f"mysqldump -u root -p'{srv['pwd']}' ntl_wms > /tmp/{sql_file}"
        
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(srv['ip'], username=srv['user'], password=srv['pwd'])
        
        ssh.exec_command(dump_cmd)
        
        # Récupération du fichier sur la machine locale (le script)
        sftp = ssh.open_sftp()
        sftp.get(f"/tmp/{sql_file}", f"./backups/{sql_file}")
        
        # 2. Export CSV de la table 'stocks' 
        csv_file = f"extract_stocks_{timestamp}.csv"
        csv_cmd = f"mysql -u root -p'{srv['pwd']}' -e 'SELECT * FROM stocks' ntl_wms | sed 's/\\t/,/g' > /tmp/{csv_file}"
        ssh.exec_command(csv_cmd)
        sftp.get(f"/tmp/{csv_file}", f"./backups/{csv_file}")
        
        print(f"[OK] Sauvegarde SQL et Export CSV terminés dans le dossier ./backups/")
        sftp.close()
        ssh.close()
        
    except Exception as e:
        print(f"[ERREUR] Échec de la sauvegarde : {str(e)}")

# Pensez à créer le dossier 'backups' avant de lancer : os.makedirs('backups', exist_ok=True)