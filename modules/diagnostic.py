# 1/ Module Diagnostic
# Fonctions :
#           Vérifier l’état des services AD / DNS sur les contrôleurs de domaine.
#           Tester le bon fonctionnement de la base de données MYSQL.
#           OK : Permettre de vérifier la version d’OS, l’uptime, l’utilisation des ressources CPU / RAM / Disques pour une machine Windows Server
#           OK : Permettre de vérifier la version d’OS, l’uptime, l’utilisation des ressources CPU / RAM / Disques pour une machine Ubuntu
import os
import json
import datetime
import paramiko
import winrm

# Configuration issue de vos informations
INFRA = {
    "wms-db": {"ip": "192.168.10.21", "user": "wms-db", "pwd": "passroot", "os": "ubuntu"},
    "wms-app": {"ip": "192.168.10.22", "user": "wms-app", "pwd": "passroot", "os": "ubuntu"},
    "DC01": {"ip": "192.168.10.10", "user": "Administrateur", "pwd": "caca3100!", "os": "windows"},
    "DC02": {"ip": "192.168.10.11", "user": "Administrateur", "pwd": "caca3200!", "os": "windows"}
}

def get_timestamp():
    return datetime.datetime.now().isoformat()

def diag_ubuntu(server_key):
    srv = INFRA[server_key]
    print(f"--- Diagnostic Ubuntu: {server_key} ({srv['ip']}) ---")
    
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(srv['ip'], username=srv['user'], password=srv['pwd'], timeout=5)
        
        # Commandes pour ressources et MySQL si c'est le serveur DB
        cmd = "uptime -p && lsb_release -d && free -m && df -h /"
        if server_key == "wms-db":
            cmd += " && systemctl is-active mysql"
            
        stdin, stdout, stderr = ssh.exec_command(cmd)
        res = stdout.read().decode()
        
        report = {
            "timestamp": get_timestamp(),
            "server": server_key,
            "status": "UP",
            "details": res.splitlines()
        }
        ssh.close()
        return report
    except Exception as e:
        return {"timestamp": get_timestamp(), "server": server_key, "status": "DOWN", "error": str(e)}

def diag_windows(server_key):
    srv = INFRA[server_key]
    print(f"--- Diagnostic Windows: {server_key} ({srv['ip']}) ---")
    
    try:
        # Connexion WinRM (doit être activé sur DC01/DC02)
        session = winrm.Session(f"http://{srv['ip']}:5985/wsman", auth=(srv['user'], srv['pwd']))
        
        # Script PowerShell pour AD, DNS et ressources
        ps_script = """
        $os = Get-CimInstance Win32_OperatingSystem | Select-Object Caption, LastBootUpTime
        $cpu = Get-CimInstance Win32_Processor | Select-Object -ExpandProperty LoadPercentage
        $mem = Get-CimInstance Win32_OperatingSystem | Select-Object @{Name="FreeMB";Expression={$_.FreePhysicalMemory/1KB}}
        $ad = Get-Service -Name adws,dns -ErrorAction SilentlyContinue | Select-Object Name, Status
        return "OS:$($os.Caption) | CPU:$($cpu)% | FreeMem:$($mem.FreeMB)MB | AD/DNS:$($ad)"
        """
        
        run = session.run_ps(ps_script)
        
        report = {
            "timestamp": get_timestamp(),
            "server": server_key,
            "status": "UP" if run.status_code == 0 else "ERROR",
            "output": run.std_out.decode().strip()
        }
        return report
    except Exception as e:
        return {"timestamp": get_timestamp(), "server": server_key, "status": "DOWN", "error": str(e)}

def main_menu():
    while True:
        print("\n=== NTL-SysToolbox : Module Diagnostic ===")
        print("1. Vérifier les Contrôleurs de Domaine (DC01/DC02)")
        print("2. Vérifier la Base de Données (WMS-DB)")
        print("3. Diagnostic complet du Siège (Toutes les VM)")
        print("4. Quitter")
        
        choice = input("Choisissez une option : ")
        
        results = []
        if choice == "1":
            results.append(diag_windows("DC01"))
            results.append(diag_windows("DC02"))
        elif choice == "2":
            results.append(diag_ubuntu("wms-db"))
        elif choice == "3":
            for srv in INFRA:
                if INFRA[srv]["os"] == "windows":
                    results.append(diag_windows(srv))
                else:
                    results.append(diag_ubuntu(srv))
        elif choice == "4":
            break
        else:
            print("Option invalide.")
            continue

        # Affichage et Export JSON
        final_json = json.dumps(results, indent=4)
        print(final_json)
        
        with open(f"diag_report_{choice}.json", "w") as f:
            f.write(final_json)
            print(f"\n[INFO] Rapport généré dans diag_report_{choice}.json")

if __name__ == "__main__":
    main_menu()