"""
JARVIS Active Defender — Detect & block intruders, remote sessions, unauthorized access.
Runs as background monitor with proactive alerts + forceful countermeasures.
"""
import os, json, time, threading, subprocess, logging, re, socket
from datetime import datetime, timedelta

log = logging.getLogger("jarvis.defender")

_THREAT_LOG = []
_ACTIVE_SESSIONS = {}
_BLOCKED_IPS = set()
_DEFENDER_RUNNING = False
_ALERT_CALLBACK = None

# Remote control software to watch for
_REMOTE_TOOLS = [
    "TeamViewer", "AnyDesk", "VNC", "RealVNC", "TightVNC", "UltraVNC",
    "Remote Desktop", "mstsc", "RDP", "Ammyy", "LogMeIn", "GoToAssist",
    "ScreenConnect", "Splashtop", "RemotePC", "Zoho Assist", "Chrome Remote Desktop",
    " parsec", "RustDesk", "NoMachine", "X2Go", "DWService", "Mosh",
    "Anyplace Control", "Remote Utilities", "AeroAdmin", "DWAgent"
]

_SUSPICIOUS_PROCESS_PATTERNS = [
    "netcat", "nc.exe", "ncat", "socat", "psexec", "wmiexec",
    "Invoke-Mimikatz", "mimikatz", "meterpreter", "cobaltstrike",
    "beacon", "empire", "pwn", "shellter", "havoc",
    "keylog", "keystroke", "hook", "inject", "dump",
    "pypykatz", "lsassy", "kerbrute", "bloodhound", "sharphound"
]


def start_defender(alert_callback=None, interval=5):
    global _DEFENDER_RUNNING, _ALERT_CALLBACK
    _ALERT_CALLBACK = alert_callback
    _DEFENDER_RUNNING = True
    t = threading.Thread(target=_defender_loop, args=(interval,), daemon=True)
    t.start()
    log.info("Active Defender started")
    return {"ok": True, "status": "running"}


def stop_defender():
    global _DEFENDER_RUNNING
    _DEFENDER_RUNNING = False
    log.info("Active Defender stopped")
    return {"ok": True, "status": "stopped"}


def _defender_loop(interval):
    while _DEFENDER_RUNNING:
        try:
            threats = _scan_for_threats()
            for t in threats:
                _handle_threat(t)
        except:
            pass
        time.sleep(interval)


def _scan_for_threats():
    threats = []
    # 1. Remote desktop / RDP sessions
    try:
        r = subprocess.run(["powershell", "-Command",
            "query user /server:localhost 2>$null | Select-Object -Skip 1"],
            capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            for line in r.stdout.strip().split("\n"):
                parts = line.strip().split()
                if len(parts) >= 3:
                    username = parts[0]
                    session_state = parts[-1] if parts[-1] in ["Active", "Disc", "Conn"] else parts[-2]
                    session_id = parts[2] if parts[2].isdigit() else "?"
                    if "Active" in session_state.lower() or "conn" in session_state.lower():
                        threats.append({
                            "type": "remote_session",
                            "source": "RDP",
                            "username": username,
                            "session_id": session_id,
                            "detail": f"Active RDP session: {username} (ID: {session_id})"
                        })
    except:
        pass

    # 2. Remote control tool processes
    try:
        r = subprocess.run(["powershell", "-Command",
            "Get-Process | Select-Object Name, Id, StartTime | ConvertTo-Json"],
            capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and len(r.stdout.strip()) > 5:
            procs = json.loads(r.stdout.strip())
            if isinstance(procs, dict):
                procs = [procs]
            for p in procs:
                pname = (p.get("Name") or "").lower()
                for tool in _REMOTE_TOOLS:
                    if tool.lower() in pname:
                        threats.append({
                            "type": "remote_tool",
                            "source": p.get("Name"),
                            "pid": p.get("Id"),
                            "username": p.get("StartTime"),
                            "detail": f"Remote tool running: {p.get('Name')} (PID: {p.get('Id')})"
                        })
                        break
    except:
        pass

    # 3. Suspicious network connections (listening ports that shouldn't be)
    try:
        r = subprocess.run(["powershell", "-Command",
            "Get-NetTCPConnection -State Listen, Established -ErrorAction SilentlyContinue | Select-Object LocalAddress, LocalPort, RemoteAddress, RemotePort, OwningProcess, State | ConvertTo-Json"],
            capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and len(r.stdout.strip()) > 5:
            conns = json.loads(r.stdout.strip())
            if isinstance(conns, dict):
                conns = [conns]
            for c in conns:
                local = c.get("LocalAddress", "")
                remote = c.get("RemoteAddress", "")
                state = c.get("State", "")
                lport = c.get("LocalPort", 0)
                if remote and remote not in ["::", "0.0.0.0", "127.0.0.1", "::1", ""] and state == "Established":
                    try:
                        rport = int(c.get("RemotePort", 0))
                    except:
                        rport = 0
                    if rport in [3389, 5900, 5901, 5902, 5800, 5500, 7070]:  # Remote access ports
                        pid = c.get("OwningProcess", "?")
                        threats.append({
                            "type": "suspicious_connection",
                            "source": f"{remote}:{rport}",
                            "local_port": lport,
                            "remote": remote,
                            "detail": f"Suspicious connection to {remote}:{rport} from PID {pid}"
                        })
    except:
        pass

    # 4. Recent failed login attempts
    try:
        end = datetime.now()
        start = end - timedelta(minutes=5)
        r = subprocess.run(["powershell", "-Command",
            f"Get-WinEvent -FilterHashtable @{{LogName='Security';Id=4625;StartTime='{start:yyyy-MM-ddTHH:mm:ss}'}} -MaxEvents 10 -ErrorAction SilentlyContinue | ForEach-Object {{ [PSCustomObject]@{{Time=$_.TimeCreated;User=$_.Properties[5].Value;Ip=$_.Properties[18].Value}} }} | ConvertTo-Json"],
            capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and len(r.stdout.strip()) > 5:
            attempts = json.loads(r.stdout.strip())
            if isinstance(attempts, dict):
                attempts = [attempts]
            for a in attempts:
                ip = a.get("Ip", "?")
                user = a.get("User", "?")
                if ip and ip != "?":  # External login attempt
                    threats.append({
                        "type": "failed_login",
                        "source": ip,
                        "username": user,
                        "detail": f"Failed login attempt for '{user}' from {ip}"
                    })
    except:
        pass

    # 5. Suspicious processes (potential malware/backdoor)
    try:
        r = subprocess.run(["powershell", "-Command",
            "Get-Process | Select-Object Name, Id, Path | ConvertTo-Json"],
            capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and len(r.stdout.strip()) > 5:
            procs = json.loads(r.stdout.strip())
            if isinstance(procs, dict):
                procs = [procs]
            for p in procs:
                pname = (p.get("Name") or "").lower()
                ppath = (p.get("Path") or "").lower()
                for pat in _SUSPICIOUS_PROCESS_PATTERNS:
                    if pat.lower() in pname or pat.lower() in ppath:
                        threats.append({
                            "type": "suspicious_process",
                            "source": p.get("Name"),
                            "pid": p.get("Id"),
                            "detail": f"Suspicious process: {p.get('Name')} (PID: {p.get('Id')})"
                        })
                        break
    except:
        pass

    return threats


def _handle_threat(threat):
    global _THREAT_LOG
    threat["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _THREAT_LOG.append(threat)
    if len(_THREAT_LOG) > 200:
        _THREAT_LOG = _THREAT_LOG[-200:]
    log.warning(f"Threat detected: {threat['detail']}")
    if _ALERT_CALLBACK:
        try:
            _ALERT_CALLBACK(threat)
        except:
            pass


def get_threat_log(count=50):
    return _THREAT_LOG[-count:]


def get_status():
    """Return current defender status."""
    rdp_count = sum(1 for t in _THREAT_LOG if t["type"] == "remote_session")
    tool_count = sum(1 for t in _THREAT_LOG if t.get("type") == "remote_tool")
    login_count = sum(1 for t in _THREAT_LOG if t.get("type") == "failed_login")
    return {
        "running": _DEFENDER_RUNNING,
        "threats_logged": len(_THREAT_LOG),
        "rdp_sessions_detected": rdp_count,
        "remote_tools_detected": tool_count,
        "failed_logins_detected": login_count,
        "blocked_ips": list(_BLOCKED_IPS),
        "last_threat": _THREAT_LOG[-1] if _THREAT_LOG else None,
    }


# ── Countermeasures ──

def force_logoff(session_id=None):
    """Force logoff all or specific remote sessions."""
    try:
        if session_id:
            cmd = f"logoff {session_id} /server:localhost"
        else:
            # Get all active remote sessions
            r = subprocess.run(["powershell", "-Command",
                "query user /server:localhost 2>$null | Select-Object -Skip 1"],
                capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                for line in r.stdout.strip().split("\n"):
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        sid = parts[2] if parts[2].isdigit() else None
                        if sid:
                            subprocess.run(f"logoff {sid} /server:localhost",
                                shell=True, capture_output=True, timeout=5)
        return {"ok": True, "action": "force_logoff"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def kill_remote_tools():
    """Kill all known remote control processes."""
    killed = []
    try:
        r = subprocess.run(["powershell", "-Command",
            "Get-Process | Select-Object Name, Id | ConvertTo-Json"],
            capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and len(r.stdout.strip()) > 5:
            procs = json.loads(r.stdout.strip())
            if isinstance(procs, dict):
                procs = [procs]
            for p in procs:
                pname = (p.get("Name") or "").lower()
                pid = p.get("Id")
                for tool in _REMOTE_TOOLS:
                    if tool.lower() in pname:
                        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                            capture_output=True, timeout=5)
                        killed.append(f"{pname} (PID {pid})")
                        break
    except:
        pass
    return {"ok": True, "killed": killed, "count": len(killed)}


def block_ip(ip):
    """Block an IP via Windows Firewall."""
    try:
        rule_name = f"JARVIS_Block_{ip.replace('.','_').replace(':','_')}"
        # Check if already exists
        r = subprocess.run(["powershell", "-Command",
            f"Get-NetFirewallRule -DisplayName '{rule_name}' -ErrorAction SilentlyContinue"],
            capture_output=True, text=True, timeout=5)
        if r.stdout.strip():
            return {"ok": True, "already_blocked": ip}
        subprocess.run(["powershell", "-Command",
            f"New-NetFirewallRule -DisplayName '{rule_name}' -Direction Inbound -RemoteAddress '{ip}' -Action Block | Out-Null"],
            capture_output=True, timeout=10)
        _BLOCKED_IPS.add(ip)
        return {"ok": True, "blocked": ip, "rule": rule_name}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def unblock_ip(ip):
    """Remove an IP block from Windows Firewall."""
    try:
        rule_name = f"JARVIS_Block_{ip.replace('.','_').replace(':','_')}"
        subprocess.run(["powershell", "-Command",
            f"Remove-NetFirewallRule -DisplayName '{rule_name}' -ErrorAction SilentlyContinue"],
            capture_output=True, timeout=10)
        _BLOCKED_IPS.discard(ip)
        return {"ok": True, "unblocked": ip}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def lock_workstation():
    """Immediately lock the workstation."""
    try:
        subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], timeout=5)
        return {"ok": True, "action": "workstation_locked"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def enable_defender_scan():
    """Trigger Windows Defender quick scan."""
    try:
        subprocess.run(["powershell", "-Command",
            "Start-MpScan -ScanType QuickScan"],
            capture_output=True, timeout=120)
        return {"ok": True, "action": "defender_quick_scan"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── PC Control ──

def list_processes(sort_by="cpu"):
    """List running processes with CPU/RAM usage."""
    try:
        cmd = "Get-Process | Select-Object Name, Id, @{N='CPU';E={[math]::Round($_.CPU,1)}}, @{N='RAM_MB';E={[math]::Round($_.WorkingSet/1MB,1)}}, StartTime | Sort-Object "
        if sort_by == "ram":
            cmd += "WorkingSet -Descending"
        else:
            cmd += "CPU -Descending"
        cmd += " -First 50 | ConvertTo-Json"
        r = subprocess.run(["powershell", "-Command", cmd],
            capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and len(r.stdout.strip()) > 5:
            procs = json.loads(r.stdout.strip())
            if isinstance(procs, dict):
                procs = [procs]
            return procs[:50]
        return []
    except:
        return []


def kill_process(name_or_pid):
    """Kill a process by name or PID."""
    try:
        cmd = f"Stop-Process -Name '{name_or_pid}' -Force -ErrorAction SilentlyContinue"
        r = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True, timeout=10)
        if r.returncode == 0 or "not found" not in r.stderr.lower():
            # Try PID
            cmd2 = f"Stop-Process -Id {name_or_pid} -Force -ErrorAction SilentlyContinue"
            subprocess.run(["powershell", "-Command", cmd2], capture_output=True, timeout=5)
        return {"ok": True, "target": name_or_pid}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_system_performance():
    """Get detailed system performance metrics."""
    result = {}
    try:
        r = subprocess.run(["powershell", "-Command",
            r"$cpu=(Get-CimInstance Win32_Processor).LoadPercentage; $rt=[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB,1); $rf=[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,1); $d=Get-PSDrive C | Select-Object @{N='F';E={[math]::Round($_.Free/1GB,1)}},@{N='U';E={[math]::Round(($_.Used/1GB),1)}}; @{CPU=$cpu;RAM_Total=$rt;RAM_Free=$rf;Disk_GB=$d} | ConvertTo-Json"],
            capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and len(r.stdout.strip()) > 5:
            result = json.loads(r.stdout.strip())
    except:
        pass
    return result or {"error": "Could not read performance"}


def get_network_connections():
    """List all active network connections."""
    try:
        r = subprocess.run(["powershell", "-Command",
            "Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue | Select-Object LocalAddress, LocalPort, RemoteAddress, RemotePort, OwningProcess, State | ConvertTo-Json"],
            capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and len(r.stdout.strip()) > 5:
            conns = json.loads(r.stdout.strip())
            if isinstance(conns, dict):
                conns = [conns]
            return conns
        return []
    except:
        return []


def get_services(status="running"):
    """List Windows services."""
    try:
        r = subprocess.run(["powershell", "-Command",
            f"Get-Service | Where-Object {{ $_.Status -eq '{status}' }} | Select-Object Name, DisplayName, Status, StartType | ConvertTo-Json"],
            capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and len(r.stdout.strip()) > 5:
            svcs = json.loads(r.stdout.strip())
            if isinstance(svcs, dict):
                svcs = [svcs]
            return svcs
        return []
    except:
        return []


def restart_service(name):
    """Restart a Windows service."""
    try:
        subprocess.run(["powershell", "-Command",
            f"Restart-Service -Name '{name}' -Force -ErrorAction SilentlyContinue"],
            capture_output=True, timeout=30)
        return {"ok": True, "service": name}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_startup_programs():
    """List startup programs."""
    try:
        r = subprocess.run(["powershell", "-Command",
            "Get-CimInstance Win32_StartupCommand | Select-Object Name, Command, Location, User | ConvertTo-Json"],
            capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and len(r.stdout.strip()) > 5:
            items = json.loads(r.stdout.strip())
            if isinstance(items, dict):
                items = [items]
            return items
        return []
    except:
        return []


def get_scheduled_tasks():
    """List scheduled tasks."""
    try:
        r = subprocess.run(["powershell", "-Command",
            "Get-ScheduledTask -TaskPath '\\' | Where-Object State -ne 'Disabled' | Select-Object TaskName, TaskPath, State, @{N='NextRun';E={$_.NextRunTime}} | ConvertTo-Json"],
            capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and len(r.stdout.strip()) > 5:
            tasks = json.loads(r.stdout.strip())
            if isinstance(tasks, dict):
                tasks = [tasks]
            return tasks[:50]
        return []
    except:
        return []


def toggle_wifi(on=True):
    """Enable or disable WiFi."""
    try:
        state = "Enabled" if on else "Disabled"
        subprocess.run(["powershell", "-Command",
            f"Get-NetAdapter -Name '*Wi-Fi*','*Wireless*' -ErrorAction SilentlyContinue | Where-Object {{$_.Status -ne '{state}'}} | ForEach-Object {{$_ | Disable-NetAdapter -Confirm:$false -ErrorAction SilentlyContinue; if ('{state}' -eq 'Enabled') {{$_ | Enable-NetAdapter -Confirm:$false -ErrorAction SilentlyContinue}}}}"],
            capture_output=True, timeout=15)
        return {"ok": True, "wifi": "enabled" if on else "disabled"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def execute_command(cmd):
    """Execute an arbitrary PowerShell command and return output."""
    try:
        r = subprocess.run(["powershell", "-Command", cmd],
            capture_output=True, text=True, timeout=30)
        return {"ok": True, "stdout": r.stdout.strip()[:2000], "stderr": r.stderr.strip()[:500]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Quick test ──
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=== JARVIS Active Defender ===")
    threats = _scan_for_threats()
    print(f"Immediate threats: {len(threats)}")
    for t in threats:
        print(f"  [{t['type']}] {t['detail']}")
    print(f"\nSystem performance: {get_system_performance()}")
