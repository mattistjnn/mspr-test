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
    "DC01": {"ip": "192.168.10.10", "user": "Administrateur@nord-transit.fr", "pwd": "caca31000!", "os": "windows"},
    "DC02": {"ip": "192.168.10.11", "user": "Administrateur@nord-transit.fr", "pwd": "caca31000!", "os": "windows"}
}

import os
import json
import datetime
import paramiko
import winrm
import mysql.connector
import csv
import requests
import subprocess

# --- CONFIGURATION ---
INFRA = {
    "wms-db": {"ip": "192.168.10.21", "user": "wms-db", "pwd": "passroot", "os": "ubuntu"},
    "wms-app": {"ip": "192.168.10.22", "user": "wms-app", "pwd": "passroot", "os": "ubuntu"},
    "DC01": {"ip": "192.168.10.10", "user": "Administrateur@nord-transit.fr", "pwd": "TonMotDePasse", "os": "windows"},
    "DC02": {"ip": "192.168.10.11", "user": "Administrateur@nord-transit.fr", "pwd": "TonMotDePasse", "os": "windows"}
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

# --- MODULE 3 : AUDIT OBSOLESCENCE (AMÉLIORÉ) ---
def get_eol_data(product):
    url = f"https://endoflife.date/api/{product.lower()}.json"
    try:
        resp = requests.get(url, timeout=5)
        return resp.json() if resp.status_code == 200 else None
    except: return None

def get_precise_version(ip, os_type):
    """Se connecte à la machine pour obtenir la version exacte."""
    try:
        # On cherche dans INFRA si on a les credentials pour cette IP
        srv_key = next((k for k, v in INFRA.items() if v["ip"] == ip), None)
        if not srv_key: return "Unknown Version"
        
        srv = INFRA[srv_key]
        if os_type == "ubuntu":
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(ip, username=srv['user'], password=srv['pwd'], timeout=3)
            stdin, stdout, stderr = ssh.exec_command("lsb_release -rs")
            version = stdout.read().decode().strip()
            ssh.close()
            return version
        else: # windows
            session = winrm.Session(f"http://{ip}:5985/wsman", auth=(srv['user'], srv['pwd']), transport='ntlm')
            run = session.run_ps("(Get-CimInstance Win32_OperatingSystem).Caption")
            # Nettoyage pour l'API (ex: extraire '2019' de 'Microsoft Windows Server 2019 Standard')
            raw_v = run.std_out.decode().strip()
            for year in ["2012", "2016", "2019", "2022"]:
                if year in raw_v: return year
            return raw_v
    except: return "Access Denied"

def audit_module():
    print("Scan réseau et Audit d'obsolescence en cours...")
    report = []
    # Scan de la plage définie au siège [cite: 152, 153]
    for i in range(10, 25): 
        ip = f"192.168.10.{i}"
        cmd = ["ping", "-c", "1", "-W", "1", ip] if os.name != 'nt' else ["ping", "-n", "1", "-w", "100", ip]
        if subprocess.call(cmd, stdout=subprocess.DEVNULL) == 0:
            os_type = "windows" if i < 20 else "ubuntu"
            version = get_precise_version(ip, os_type)
            
            # Récupération EOL via API
            eol_info = get_eol_data(os_type)
            eol_date = "Unknown"
            if eol_info and version != "Unknown Version":
                # On cherche le cycle correspondant à notre version (ex: 22.04 ou 2019)
                match = next((x for x in eol_info if x['cycle'] in version), None)
                if match: eol_date = match['eol']

            print(f"[FOUND] {ip} | OS: {os_type} | Version: {version} | EOL: {eol_date}")
            report.append({
                "ip": ip, "os": os_type, "version": version, 
                "eol_date": eol_date, "timestamp": get_timestamp()
            })
    save_report(report, "audit_obsolescence_detaille")

# --- MENU PRINCIPAL ---
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