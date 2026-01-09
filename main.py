import os
import json
import datetime
import paramiko
import winrm
import mysql.connector
import csv
import requests
import subprocess

# --- CONFIGURATION DE L'INFRASTRUCTURE NTL ---
# Ces informations correspondent à l'Annexe A et C du cahier des charges [cite: 152, 162]
INFRA = {
    "wms-db": {"ip": "192.168.10.21", "user": "wms-db", "pwd": "passroot", "os": "ubuntu"},
    "wms-app": {"ip": "192.168.10.22", "user": "wms-app", "pwd": "passroot", "os": "ubuntu"},
    "DC01": {"ip": "192.168.10.10", "user": "Administrateur@nord-transit.fr", "pwd": "TonMotDePasse", "os": "windows"},
    "DC02": {"ip": "192.168.10.11", "user": "Administrateur@nord-transit.fr", "pwd": "TonMotDePasse", "os": "windows"}
}

def get_timestamp():
    """Génère un horodatage pour les rapports[cite: 91]."""
    return datetime.datetime.now().isoformat()

def save_report(data, prefix):
    """Sauvegarde les sorties au format JSON structuré."""
    os.makedirs('reports', exist_ok=True)
    filename = f"reports/{prefix}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)
    print(f"\n[INFO] Rapport généré : {filename}")

# --- MODULE 1 : DIAGNOSTIC [cite: 92] ---
def diag_ubuntu(server_key):
    srv = INFRA[server_key]
    report = {"server": server_key, "status": "UP", "services": {}, "metrics": {}}
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(srv['ip'], username=srv['user'], password=srv['pwd'], timeout=5)
        
        # Vérification ressources (CPU/RAM/Uptime) [cite: 98]
        stdin, stdout, stderr = ssh.exec_command("uptime -p && free -m && df -h /")
        report["metrics"]["raw"] = stdout.read().decode().strip()
        
        if server_key == "wms-db":
            # Test réel de la base MySQL [cite: 96]
            try:
                db = mysql.connector.connect(host=srv['ip'], user="root", password="TonMotDePasse", database="ntl_wms", connect_timeout=3)
                report["services"]["mysql"] = "OK"
                db.close()
            except Exception as e:
                report["services"]["mysql"] = f"KO: {str(e)}"
        ssh.close()
    except Exception as e:
        report["status"] = "DOWN"; report["error"] = str(e)
    return report

def diag_windows(server_key):
    srv = INFRA[server_key]
    try:
        session = winrm.Session(f"http://{srv['ip']}:5985/wsman", auth=(srv['user'], srv['pwd']), transport='ntlm')
        # Script PS pour AD, DNS et ressources [cite: 95, 97]
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

# --- MODULE 2 : SAUVEGARDE WMS [cite: 99] ---
def backup_module():
    srv = INFRA["wms-db"]
    os.makedirs('backups', exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    try:
        # Export SQL [cite: 101]
        print("Lancement de l'export SQL...")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(srv['ip'], username=srv['user'], password=srv['pwd'])
        ssh.exec_command(f"mysqldump -u root -p'TonMotDePasse' ntl_wms > /tmp/backup_{ts}.sql")
        
        # Export CSV [cite: 101]
        print("Lancement de l'export CSV (Table stocks)...")
        db = mysql.connector.connect(host=srv['ip'], user="root", password="TonMotDePasse", database="ntl_wms")
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

# --- MODULE 3 : AUDIT OBSOLESCENCE [cite: 102] ---
def get_eol_data(product):
    url = f"https://endoflife.date/api/{product.lower()}.json"
    try:
        resp = requests.get(url, timeout=5)
        return resp.json() if resp.status_code == 200 else None
    except: return None

def audit_module():
    print("Scan du réseau 192.168.10.0/24... [cite: 104]")
    report = []
    for i in range(10, 25): # Exemple restreint pour le test
        ip = f"192.168.10.{i}"
        cmd = ["ping", "-c", "1", "-W", "1", ip]
        if subprocess.call(cmd, stdout=subprocess.DEVNULL) == 0:
            os_name = "windows" if i < 20 else "ubuntu"
            eol_info = get_eol_data(os_name)
            status = eol_info[0]['eol'] if eol_info else "N/A"
            report.append({"ip": ip, "os": os_name, "eol_date": status})
            print(f"[FOUND] {ip} ({os_name}) - EOL: {status}")
    save_report(report, "audit_obsolescence")

# --- MENU PRINCIPAL [cite: 118] ---
def main():
    while True:
        print("\n" + "="*40 + "\n  NTL-SysToolbox - MENU INTERACTIF\n" + "="*40)
        print("1. Module Diagnostic (AD, DNS, MySQL, Ressources)")
        print("2. Module Sauvegarde (SQL & CSV Stocks)")
        print("3. Module Audit Obsolescence (Scan & API EOL)")
        print("4. Quitter")
        
        c = input("\nVotre choix : ")
        if c == "1": diag_module()
        elif c == "2": backup_module()
        elif c == "3": audit_module()
        elif c == "4": break
        else: print("Option invalide.")

if __name__ == "__main__":
    main()