# 1/ Module Diagnostic
# Fonctions :
#           Vérifier l’état des services AD / DNS sur les contrôleurs de domaine.
#           Tester le bon fonctionnement de la base de données MYSQL.
#           Permettre de vérifier la version d’OS, l’uptime, l’utilisation des ressources CPU / RAM / Disques pour une machine Windows Server
#           Permettre de vérifier la version d’OS, l’uptime, l’utilisation des ressources CPU / RAM / Disques pour une machine Ubuntu


import psutil
import platform
import time
import json

def check_system_resources():
    """
    Vérifie OS, Uptime, CPU, RAM, Disque.
    Retourne un dictionnaire (compatible JSON).
    """ 
    boot_time = psutil.boot_time()
    uptime_seconds = time.time() - boot_time    
    
    disk_usage = psutil.disk_usage('/') 
    
    data = {
        "os_version": platform.platform(),
        "uptime_hours": round(uptime_seconds / 3600, 2),
        "cpu_percent": psutil.cpu_percent(interval=1),
        "ram_percent": psutil.virtual_memory().percent,
        "disk_percent": disk_usage.percent
    }
    return data


print(check_system_resources())