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