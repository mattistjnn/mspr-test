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
from dotenv import load_dotenv
from paramiko import Transport

warnings.filterwarnings("ignore", category=UserWarning)

load_dotenv()

def load_infra_from_env():
    """Reconstruit le dictionnaire INFRA à partir des variables d'environnement."""
    infra_dict = {}
    for key, value in os.environ.items():
        if key.startswith("INFRA_"):
            friendly_name = key.replace("INFRA_", "").lower().replace("_", "-")
            parts = value.split(",")
            if len(parts) == 4:
                infra_dict[friendly_name] = {
                    "ip": parts[0],
                    "user": parts[1],
                    "pwd": parts[2],
                    "os": parts[3]
                }
    return infra_dict

INFRA = load_infra_from_env()
MYSQL_PWD = os.getenv("DB_ROOT_PWD", "default_pass")

# --- OUTILS GÉNÉRIQUES ---
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
                db = mysql.connector.connect(
                    host=srv['ip'], user="root", password=MYSQL_PWD, 
                    database="ntl_wms", connect_timeout=3
                )
                report["services"]["mysql"] = "OK"
                db.close()
            except: 
                report["services"]["mysql"] = "KO"
        ssh.close()
    except Exception as e: 
        report["status"] = "DOWN"
        report["error"] = str(e)
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
    except Exception as e: 
        return {"server": server_key, "status": "DOWN", "error": str(e)}

def diag_module():
    results = []
    for name, srv in INFRA.items():
        res = diag_windows(name) if srv["os"] == "windows" else diag_ubuntu(name)
        results.append(res)
    print(json.dumps(results, indent=4))
    save_report(results, "diag")

# --- MODULE 2 : SAUVEGARDE WMS ---
def backup_module():
    if "wms-db" not in INFRA:
        print("[ERREUR] Configuration wms-db introuvable dans le .env")
        return
    
    srv = INFRA["wms-db"]
    os.makedirs('backups', exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(srv['ip'], username=srv['user'], password=srv['pwd'])

        # Utilisation du mot de passe centralisé
        ssh.exec_command(f"mysqldump -u root -p'{MYSQL_PWD}' ntl_wms > /tmp/backup_{ts}.sql")

        # Tunnel SSH pour que MySQL voie la connexion depuis localhost
        transport = ssh.get_transport()
        channel = transport.open_channel("direct-tcpip", ("127.0.0.1", 3306), ("127.0.0.1", 0))

        db = mysql.connector.connect(host="127.0.0.1", user="root", password=MYSQL_PWD, database="ntl_wms", sock=channel)
        cursor = db.cursor()
        cursor.execute("SELECT * FROM stocks")

        with open(f"backups/stocks_{ts}.csv", "w", newline='') as f:
            writer = csv.writer(f)
            writer.writerow([i[0] for i in cursor.description])
            writer.writerows(cursor.fetchall())

        print("[OK] Sauvegardes terminées.")
        db.close(); ssh.close()
    except Exception as e:
        print(f"[ERREUR] {e}")

# --- MODULE 3 : AUDIT OBSOLESCENCE ---
def get_eol_data(product):
    url = f"https://endoflife.date/api/{product.lower()}.json"
    try:
        resp = requests.get(url, timeout=5)
        return resp.json() if resp.status_code == 200 else None
    except:
        return None

def analyze_obsolescence(version, eol_info):
    if not eol_info or version in ["Version Inconnue", "Access Denied"]:
        return "Inconnu"
    
    match = next((x for x in eol_info if x['cycle'] in version), None)
    if not match:
        return "Version non répertoriée"
    
    eol_date_str = match['eol']
    # Gestion du cas où 'eol' est un booléen (ex: true pour supporté)
    if isinstance(eol_date_str, bool):
        return "OK : Supporté"
        
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
    print("3. Importer un inventaire CSV ")
    
    choix = input("\nVotre choix : ")

    if choix == "1":
        print("Scan du réseau en cours...")
        report = []
        for i in range(10, 56): 
            ip = f"192.168.10.{i}"
            cmd = ["ping", "-c", "1", "-W", "1", ip] if os.name != 'nt' else ["ping", "-n", "1", "-w", "100", ip]
            if subprocess.call(cmd, stdout=subprocess.DEVNULL) == 0:
                os_type = "windows-server" if (i < 20 or i == 50) else "ubuntu"
                if i == 40: os_type = "centos"
                
                version = "Version Détectée" 
                eol_info = get_eol_data(os_type)
                statut = analyze_obsolescence(version, eol_info)
                
                print(f"[FOUND] {ip} | {os_type} | {statut}")
                report.append({"ip": ip, "os": os_type, "status": statut, "at": get_timestamp()})
        save_report(report, "audit_obsolescence_complet")

    elif choix == "2":
        os_name = input("Entrez le nom de l'OS (ex: ubuntu, windows-server) : ")
        data = get_eol_data(os_name)
        if data:
            for cycle in data[:5]:
                print(f"- Version {cycle['cycle']} : EOL {cycle['eol']}")
        else:
            print("OS non trouvé.")

def main():
    if not INFRA:
        print("/!\\ Alerte : Aucun serveur chargé depuis le fichier .env")
        
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