# 1/ Module Diagnostic
# Fonctions :
#           Vérifier l’état des services AD / DNS sur les contrôleurs de domaine.
#           Tester le bon fonctionnement de la base de données MYSQL.
#           OK : Permettre de vérifier la version d’OS, l’uptime, l’utilisation des ressources CPU / RAM / Disques pour une machine Windows Server
#           OK : Permettre de vérifier la version d’OS, l’uptime, l’utilisation des ressources CPU / RAM / Disques pour une machine Ubuntu
import paramiko
import os

# --- INVENTAIRE DE L'INFRA ---
INFRA = {
    "wms-db": {"ip": "192.168.10.21", "user": "wms-db", "pwd": "passroot", "os": "ubuntu"},
    "wms-app": {"ip": "192.168.10.22", "user": "wms-app", "pwd": "passroot", "os": "ubuntu"},
    "DC01": {"ip": "192.168.10.10", "user": "Administrateur", "pwd": "caca3100!", "os": "windows"},
    "DC02": {"ip": "192.168.10.11", "user": "Administrateur", "pwd": "caca3200!", "os": "windows"}
}

def get_ssh_client(ip, user, pwd):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(ip, username=user, password=pwd, timeout=5)
        return client
    except Exception as e:
        print(f"Erreur connexion {ip}: {e}")
        return None

def diag_linux(name, config):
    print(f"\n--- Diagnostic {name.upper()} ({config['os']}) ---")
    client = get_ssh_client(config['ip'], config['user'], config['pwd'])
    if not client: return

    # Commandes Version, Uptime, CPU, RAM, Disque
    cmds = {
        "Version": "lsb_release -d | cut -f2",
        "Uptime": "uptime -p",
        "CPU Load": "top -bn1 | grep 'Cpu(s)' | awk '{print $2}'",
        "RAM Free": "free -m | awk '/Mem:/ {print $4\"MB\"}'",
        "Disk Root": "df -h / | awk 'NR==2 {print $5}'"
    }
    
    for label, cmd in cmds.items():
        stdin, stdout, stderr = client.exec_command(cmd)
        print(f"{label}: {stdout.read().decode().strip()}")

    # Test spécifique BDD si c'est wms-db
    if name == "wms-db":
        db_cmd = "mysql -u root -ppassroot -e 'USE ntl_wms; SELECT COUNT(*) FROM stocks;' 2>/dev/null"
        stdin, stdout, stderr = client.exec_command(db_cmd)
        res = stdout.read().decode().strip()
        status = "OK (Données accessibles)" if res else "ERREUR (BDD ou Table inaccessible)"
        print(f"Service MySQL: {status}")

    client.close()

def diag_windows(name, config):
    print(f"\n--- Diagnostic {name.upper()} ({config['os']}) ---")
    # Note : Nécessite que SSH soit activé sur Windows Server ou utilisation de WinRM
    client = get_ssh_client(config['ip'], config['user'], config['pwd'])
    if not client: return

    cmds = {
        "Version": "powershell [System.Environment]::OSVersion.VersionString",
        "Uptime": "powershell (get-date) - (gcim Win32_OperatingSystem).LastBootUpTime",
        "Services AD/DNS": "powershell Get-Service adws,dns -ErrorAction SilentlyContinue | Select-Object Name, Status | Out-String"
    }

    for label, cmd in cmds.items():
        stdin, stdout, stderr = client.exec_command(cmd)
        print(f"{label}:\n{stdout.read().decode().strip()}")

    client.close()

# --- EXÉCUTION DU MODULE ---
if __name__ == "__main__":
    # Test Briques Critiques (DB et AD)
    diag_linux("wms-db", INFRA["wms-db"])
    diag_windows("DC01", INFRA["DC01"])
    # Test Ressources
    diag_linux("wms-app", INFRA["wms-app"])