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
