import os
import json
import datetime
import paramiko
import winrm
import mysql.connector
import csv
import requests
import subprocess
import warnings

# On ignore les avertissements visuels de WinRM pour la console
warnings.filterwarnings("ignore", category=UserWarning)

# --- CONFIGURATION DE L'INFRASTRUCTURE NTL ---
INFRA = {
    "wms-db": {"ip": "192.168.10.21", "user": "wms-db", "pwd": "passroot", "os": "ubuntu"},
    "wms-app": {"ip": "192.168.10.22", "user": "wms-app", "pwd": "passroot", "os": "ubuntu"},
    "DC01": {"ip": "192.168.10.10", "user": "Administrateur@nord-transit.fr", "pwd": "caca31000!", "os": "windows"},
    "DC02": {"ip": "192.168.10.11", "user": "Administrateur@nord-transit.fr", "pwd": "caca31000!", "os": "windows"},
    "IPBX-VM": {"ip": "192.168.10.40", "user": "ipbx", "pwd": "passipbx", "os": "ubuntu"}, 
    "SUPER-01": {"ip": "192.168.10.50", "user": "Administrateur@nord-transit.fr", "pwd": "caca31000!", "os": "windows"},
    "dimitri": {"ip": "192.168.10.27", "user": "dimitri", "pwd": "passroot", "os": "ubuntu"}
    # "eloise": {"ip": "192.168.10.A DEFINIR", "user": "A DEFINIR", "pwd": "caca31000!", "os": "windows"}
}

def get_timestamp():
    return datetime.datetime.now().isoformat()

def save_report(data, prefix):
    os.makedirs('reports', exist_ok=True)
    filename = f"reports/{prefix}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)
    print(f"\n[INFO] Rapport généré : {filename}")

# --- MODULE 1 : DIAGNOSTIC ---
def diag_ubuntu(server_key):
    srv = INFRA[server_key]
    report = {"server": server_key, "status": "UP", "services": {}, "metrics": {}}
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(srv['ip'], username=srv['user'], password=srv['pwd'], timeout=5)
        stdin, stdout, stderr = ssh.exec_command("uptime -p && free -m && lsb_release -d")
        report["metrics"]["raw"] = stdout.read().decode().strip()
        if server_key == "wms-db":
            try:
                db = mysql.connector.connect(host=srv['ip'], user="root", password="TonMotDePasse", database="ntl_wms", connect_timeout=3)
                report["services"]["mysql"] = "OK"
                db.close()
            except: report["services"]["mysql"] = "KO"
        ssh.close()
    except Exception as e: report["status"] = "DOWN"; report["error"] = str(e)
    return report

def diag_windows(server_key):
    srv = INFRA[server_key]
    try:
        session = winrm.Session(f"http://{srv['ip']}:5985/wsman", auth=(srv['user'], srv['pwd']), transport='ntlm')
        ps_script = """
        $os = Get-CimInstance Win32_OperatingSystem
        $cpu = Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average
        $ad = Get-Service -Name "NTDS" -ErrorAction SilentlyContinue
        $dns = Get-Service -Name "DNS" -ErrorAction SilentlyContinue
        @{ OS=$os.Caption; Uptime="$((New-TimeSpan -Start $os.LastBootUpTime).Days) j"; CPU="$($cpu.Average)%"; AD=$ad.Status; DNS=$dns.Status } | ConvertTo-Json
        """
        run = session.run_ps(ps_script)
        return {"server": server_key, "status": "UP", "metrics": json.loads(run.std_out)}
    except Exception as e: return {"server": server_key, "status": "DOWN", "error": str(e)}

def diag_module():
    results = []
    for name, srv in INFRA.items():
        res = diag_windows(name) if srv["os"] == "windows" else diag_ubuntu(name)
        results.append(res)
    print(json.dumps(results, indent=4))
    save_report(results, "diag")

# --- MODULE 2 : SAUVEGARDE WMS ---
def backup_module():
    srv = INFRA["wms-db"]
    os.makedirs('backups', exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(srv['ip'], username=srv['user'], password=srv['pwd'])
        ssh.exec_command(f"mysqldump -u root -p'TonMotDePasse' ntl_wms > /tmp/backup_{ts}.sql")
        db = mysql.connector.connect(host=srv['ip'], user="root", password="TonMotDePasse", database="ntl_wms")
        cursor = db.cursor()
        cursor.execute("SELECT * FROM stocks")
        with open(f"backups/stocks_{ts}.csv", "w", newline='') as f:
            writer = csv.writer(f)
            writer.writerow([i[0] for i in cursor.description])
            writer.writerows(cursor.fetchall())
        print("[OK] Sauvegardes terminées.")
        db.close(); ssh.close()
    except Exception as e: print(f"[ERREUR] {e}")

# --- MODULE 3 : AUDIT OBSOLESCENCE ---
# --- MODULE 3 : AUDIT OBSOLESCENCE ---
def get_eol_data(product):
    """Interroge l'API endoflife.date pour un produit donné."""
    url = f"https://endoflife.date/api/{product.lower()}.json"
    try:
        resp = requests.get(url, timeout=5)
        return resp.json() if resp.status_code == 200 else None
    except:
        return None

def analyze_obsolescence(version, eol_info):
    """Qualifie le statut de support basé sur la date EOL."""
    if not eol_info or version in ["Version Inconnue", "Access Denied"]:
        return "Inconnu"
    
    # Recherche du cycle correspondant
    match = next((x for x in eol_info if x['cycle'] in version), None)
    if not match:
        return "Version non répertoriée"
    
    eol_date_str = match['eol']
    eol_date = datetime.datetime.strptime(eol_date_str, "%Y-%m-%d")
    now = datetime.datetime.now()
    
    if eol_date < now:
        return f"CRITIQUE : Obsolète depuis le {eol_date_str}"
    elif (eol_date - now).days < 180:
        return f"ATTENTION : Fin de vie proche ({eol_date_str})"
    else:
        return f"OK : Supporté jusqu'au {eol_date_str}"

def audit_module():
    print("\n--- Module 3 : Audit d'obsolescence ---")
    print("1. Scan réseau complet (192.168.10.x) ")
    print("2. Lister cycles de vie pour un OS spécifique ")
    print("3. Importer un inventaire CSV et lister les EOL ")
    
    choix = input("\nVotre choix : ")

    if choix == "1":
        # Fonction 1 : Lister composants et déterminer l'OS 
        print("Scan du réseau en cours...")
        report = []
        for i in range(10, 56): 
            ip = f"192.168.10.{i}"
            cmd = ["ping", "-c", "1", "-W", "1", ip] if os.name != 'nt' else ["ping", "-n", "1", "-w", "100", ip]
            if subprocess.call(cmd, stdout=subprocess.DEVNULL) == 0:
                os_type = "windows-server" if (i < 20 or i == 50) else "ubuntu"
                if i == 40: os_type = "centos" # IPBX spécifié en CentOS 
                
                version = get_precise_version(ip, "windows" if os_type == "windows-server" else "ubuntu")
                eol_info = get_eol_data(os_type)
                statut = analyze_obsolescence(version, eol_info)
                
                print(f"[FOUND] {ip} | {os_type} {version} | {statut}")
                report.append({"ip": ip, "os": os_type, "version": version, "status": statut, "at": get_timestamp()})
        save_report(report, "audit_obsolescence_complet")

    elif choix == "2":
        # Fonction 2 : Lister versions et EOL pour un OS donné 
        os_name = input("Entrez le nom de l'OS (ex: ubuntu, windows-server, debian) : ")
        data = get_eol_data(os_name)
        if data:
            print(f"\nCycles de vie pour {os_name} :")
            for cycle in data[:5]: # Top 5 versions
                print(f"- Version {cycle['cycle']} : Fin de vie le {cycle['eol']}")
        else:
            print("OS non trouvé sur l'API.")

    elif choix == "3":
        # Fonction 3 : Lecture CSV et qualification EOL
        csv_path = input("Entrez le chemin du fichier CSV (format: ip,os,version) : ")
        if os.path.exists(csv_path):
            report = []
            with open(csv_path, mode='r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    eol_info = get_eol_data(row['os'])
                    statut = analyze_obsolescence(row['version'], eol_info)
                    print(f"Composant {row['ip']} ({row['os']}) -> {statut}")
                    report.append({**row, "status": statut})
            save_report(report, "audit_csv")
        else:
            print("Fichier introuvable.")

# --- MENU ---
def main():
    while True:
        print("\n" + "="*45 + "\n  NTL-SysToolbox - GESTION D'EXPLOITATION\n" + "="*45)
        print("1. [Diagnostic] Disponibilité & Ressources")
        print("2. [Sauvegarde] Export SQL & CSV (WMS)")
        print("3. [Audit] Inventaire & Obsolescence (EOL)")
        print("4. Quitter")
        c = input("\nChoix : ")
        if c == "1": diag_module()
        elif c == "2": backup_module()
        elif c == "3": audit_module()
        elif c == "4": break

if __name__ == "__main__":
    main()