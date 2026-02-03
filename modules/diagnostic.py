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