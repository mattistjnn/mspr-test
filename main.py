import os
import json
import datetime
import re
import csv
import subprocess
import warnings
import paramiko
import winrm
import requests
from dotenv import load_dotenv

warnings.filterwarnings("ignore", category=UserWarning)
load_dotenv()


#  CONFIGURATION


def load_infra_from_env():
    """Reconstruit le dictionnaire INFRA à partir des variables INFRA_* du .env."""
    infra = {}
    for key, value in os.environ.items():
        if key.startswith("INFRA_"):
            name = key.replace("INFRA_", "").lower().replace("_", "-")
            parts = value.split(",")
            if len(parts) == 4:
                infra[name] = {"ip": parts[0], "user": parts[1], "pwd": parts[2], "os": parts[3]}
    return infra

INFRA = load_infra_from_env()
MYSQL_PWD = os.getenv("DB_ROOT_PWD", "default_pass")


#  HELPERS : CONNEXIONS & UTILITAIRES


def ssh_connect(ip, user, pwd):
    """Ouvre et retourne une connexion SSH."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ip, username=user, password=pwd, timeout=5)
    return ssh

def ssh_run(ssh, cmd):
    """Exécute une commande SSH et retourne la sortie stdout."""
    _, stdout, _ = ssh.exec_command(cmd)
    return stdout.read().decode().strip()

def winrm_session(ip, user, pwd):
    """Ouvre et retourne une session WinRM."""
    return winrm.Session(f"http://{ip}:5985/wsman", auth=(user, pwd), transport='ntlm')

def winrm_ps(session, script):
    """Exécute un script PowerShell et retourne la sortie stdout."""
    return session.run_ps(script).std_out.decode().strip()

def get_timestamp():
    return datetime.datetime.now().isoformat()

def save_report(data, prefix):
    os.makedirs('reports', exist_ok=True)
    filename = f"reports/{prefix}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)
    print(f"\n[INFO] Rapport généré : {filename}")


#  MODULE 1 : DIAGNOSTIC


def diag_ubuntu(server_key):
    srv = INFRA[server_key]
    report = {"server": server_key, "status": "UP", "services": {}, "metrics": {}}
    try:
        ssh = ssh_connect(srv['ip'], srv['user'], srv['pwd'])
        report["metrics"]["raw"] = ssh_run(ssh, "uptime -p && free -m && lsb_release -d")

        if server_key == "wms-db":
            try:
                result = ssh_run(ssh, f"mysql -u root -p'{MYSQL_PWD}' -e 'SELECT 1' ntl_wms")
                report["services"]["mysql"] = "OK" if result else "KO"
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
        session = winrm_session(srv['ip'], srv['user'], srv['pwd'])
        ps_script = """
        $os = Get-CimInstance Win32_OperatingSystem
        $cpu = Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average
        $ad = Get-Service -Name "NTDS" -ErrorAction SilentlyContinue
        $dns = Get-Service -Name "DNS" -ErrorAction SilentlyContinue
        @{ OS=$os.Caption; Uptime="$((New-TimeSpan -Start $os.LastBootUpTime).Days) j"; CPU="$($cpu.Average)%"; AD=$ad.Status; DNS=$dns.Status } | ConvertTo-Json
        """
        return {"server": server_key, "status": "UP", "metrics": json.loads(winrm_ps(session, ps_script))}
    except Exception as e:
        return {"server": server_key, "status": "DOWN", "error": str(e)}

def diag_module():
    results = []
    for name, srv in INFRA.items():
        res = diag_windows(name) if srv["os"] == "windows" else diag_ubuntu(name)
        results.append(res)
    print(json.dumps(results, indent=4))
    save_report(results, "diag")


#  MODULE 2 : SAUVEGARDE WMS


def backup_module():
    if "wms-db" not in INFRA:
        print("[ERREUR] Configuration wms-db introuvable dans le .env")
        return

    srv = INFRA["wms-db"]
    os.makedirs('backups', exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        ssh = ssh_connect(srv['ip'], srv['user'], srv['pwd'])

        # Dump SQL complet
        _, stdout, _ = ssh.exec_command(f"mysqldump -u root -p'{MYSQL_PWD}' ntl_wms")
        with open(f"backups/backup_{ts}.sql", "wb") as f:
            f.write(stdout.read())

        # Export CSV de TOUTES les tables
        tables_str = ssh_run(ssh, f"mysql -u root -p'{MYSQL_PWD}' ntl_wms -e 'SHOW TABLES;' --batch --skip-column-names")
        if tables_str:
            for table in tables_str.split("\n"):
                table = table.strip()
                if not table:
                    continue
                output = ssh_run(ssh, f"mysql -u root -p'{MYSQL_PWD}' ntl_wms -e 'SELECT * FROM {table}' --batch")
                if output:
                    with open(f"backups/{table}_{ts}.csv", "w", newline='') as f:
                        writer = csv.writer(f)
                        for line in output.split("\n"):
                            writer.writerow(line.split("\t"))

        print("[OK] Sauvegardes terminées.")
        ssh.close()
    except Exception as e:
        print(f"[ERREUR] {e}")


#  MODULE 3 : AUDIT OBSOLESCENCE


def get_eol_data(product):
    """Interroge l'API endoflife.date pour un produit donné."""
    try:
        resp = requests.get(f"https://endoflife.date/api/{product.lower()}.json", timeout=5)
        return resp.json() if resp.status_code == 200 else None
    except:
        return None

def analyze_obsolescence(version, eol_info):
    """Qualifie le statut EOL : OK / ATTENTION / CRITIQUE."""
    if not eol_info or version in ["Version Inconnue", "Access Denied"]:
        return "Inconnu"

    match = next((x for x in eol_info if x['cycle'] in version or version in x['cycle']), None)
    if not match:
        return "Version non répertoriée"

    eol_date_str = match['eol']
    if isinstance(eol_date_str, bool):
        return "OK : Supporté"

    eol_date = datetime.datetime.strptime(eol_date_str, "%Y-%m-%d")
    jours_restants = (eol_date - datetime.datetime.now()).days

    if jours_restants < 0:
        return f"CRITIQUE : Obsolète depuis le {eol_date_str}"
    elif jours_restants < 180:
        return f"ATTENTION : Fin de vie proche ({eol_date_str})"
    else:
        return f"OK : Supporté jusqu'au {eol_date_str}"

def get_version_ssh(ip, user, pwd):
    """Récupère la version OS via SSH (ex: '22.04')."""
    try:
        ssh = ssh_connect(ip, user, pwd)
        version = ssh_run(ssh, "lsb_release -rs 2>/dev/null || cat /etc/os-release | grep VERSION_ID | cut -d'\"' -f2")
        ssh.close()
        return version if version else "Version Inconnue"
    except:
        return "Version Inconnue"

def get_version_winrm(ip, user, pwd):
    """Récupère la version Windows via WinRM (ex: '2022')."""
    try:
        session = winrm_session(ip, user, pwd)
        caption = winrm_ps(session, "(Get-CimInstance Win32_OperatingSystem).Caption")
        m = re.search(r'(20\d{2})', caption)
        return m.group(1) if m else "Version Inconnue"
    except:
        return "Version Inconnue"

def detect_version(ip, ip_to_infra):
    """Détecte la version OS d'une IP si ses credentials sont connus."""
    if ip not in ip_to_infra:
        return "Version Inconnue"
    srv = ip_to_infra[ip]
    if srv["os"] == "windows":
        return get_version_winrm(ip, srv["user"], srv["pwd"])
    return get_version_ssh(ip, srv["user"], srv["pwd"])

def audit_module():
    print("\n--- Module 3 : Audit d'obsolescence ---")
    print("1. Scan réseau complet (192.168.10.x)")
    print("2. Lister cycles de vie pour un OS spécifique")
    print("3. Importer un inventaire CSV")

    choix = input("\nVotre choix : ")

    if choix == "1":
        print("Scan du réseau en cours...")
        ip_to_infra = {srv["ip"]: srv for srv in INFRA.values()}
        report = []
        for i in range(10, 56):
            ip = f"192.168.10.{i}"
            cmd = ["ping", "-c", "1", "-W", "1", ip] if os.name != 'nt' else ["ping", "-n", "1", "-w", "100", ip]
            try:
                if subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3) == 0:
                    os_type = "windows-server" if (i < 20 or i == 50) else "ubuntu"
                    if i == 40: os_type = "centos"

                    version = detect_version(ip, ip_to_infra)
                    eol_info = get_eol_data(os_type)
                    statut = analyze_obsolescence(version, eol_info)

                    print(f"[FOUND] {ip} | {os_type} {version} | {statut}")
                    report.append({"ip": ip, "os": os_type, "version": version, "status": statut, "at": get_timestamp()})
            except subprocess.TimeoutExpired:
                continue
        save_report(report, "audit_obsolescence_complet")
        
        # Sauvegarde en CSV du rapport d'audit
        if report:
            os.makedirs('reports', exist_ok=True)
            csv_filename = f"reports/audit_obsolescence_complet_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            keys = report[0].keys()
            with open(csv_filename, 'w', newline='') as f:
                dict_writer = csv.DictWriter(f, fieldnames=keys)
                dict_writer.writeheader()
                dict_writer.writerows(report)
            print(f"[INFO] Rapport CSV généré : {csv_filename}")

    elif choix == "2":
        os_name = input("Entrez le nom de l'OS (ex: ubuntu, windows-server) : ")
        data = get_eol_data(os_name)
        if data:
            for cycle in data[:5]:
                print(f"- Version {cycle['cycle']} : EOL {cycle['eol']}")
        else:
            print("OS non trouvé.")


#  MENU PRINCIPAL


def main():
    if not INFRA:
        print("/!\\ Alerte : Aucun serveur chargé depuis le fichier .env")

    while True:
        print(r"""
 _   _ _   _        _____           _              _ 
| \ | | | | |      /  ___|         | |            | |
|  \| | |_| |______\ `--. _   _ ___| |_ ___   ___ | |
| . ` | __| |______|`--. \ | | / __| __/ _ \ / _ \| |
| |\  | |_| |      /\__/ / |_| \__ \ || (_) | (_) | |
\_| \_/\__|_|      \____/ \__, |___/\__\___/ \___/|_|
                           __/ |                     
                          |___/                      
        """)
        print("="*65)
        print("1. [Diagnostic] Disponibilité & Ressources")
        print("2. [Sauvegarde] Export SQL & CSV (WMS)")
        print("3. [Audit] Inventaire & Obsolescence (EOL)")
        print("4. Quitter")

        choix = input("\nChoix : ")
        if   choix == "1": diag_module()
        elif choix == "2": backup_module()
        elif choix == "3": audit_module()
        elif choix == "4": break

if __name__ == "__main__":
    main()
