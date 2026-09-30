#!/usr/bin/env bash
# x52tool – Einmalige Systemkonfiguration
# Führe dieses Skript einmalig mit sudo aus, danach läuft x52tool ohne root.
#
# Was dieses Skript tut:
#   1. Prüft ob libx52 (x52d, x52ctl) installiert ist
#   2. Legt /etc/tmpfiles.d/x52d-access.conf an, damit der Socket
#      /run/x52d.cmd für alle User schreibbar ist
#   3. Aktiviert die Regel sofort (ohne Reboot)
#
# Einmalig ausführen:
#   sudo bash install.sh

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}!${NC} $*"; }
err()  { echo -e "${RED}✗${NC} $*"; exit 1; }

# Root prüfen
if [[ $EUID -ne 0 ]]; then
    err "Bitte mit sudo ausführen: sudo bash install.sh"
fi

echo ""
echo "x52tool – Systemkonfiguration"
echo "=============================="
echo ""

# 1. libx52 prüfen
echo "Prüfe Abhängigkeiten..."

if ! command -v x52d &>/dev/null; then
    err "x52d nicht gefunden. Bitte libx52 installieren:\n   Arch/CachyOS: yay -S libx52\n   Andere: https://github.com/nirenjan/libx52"
fi
ok "x52d gefunden: $(which x52d)"

if ! command -v x52ctl &>/dev/null; then
    err "x52ctl nicht gefunden. Bitte libx52 neu installieren."
fi
ok "x52ctl gefunden: $(which x52ctl)"

# 2. x52d system service prüfen
echo ""
echo "Prüfe x52d service..."

if systemctl is-active --quiet x52d.service; then
    ok "x52d.service läuft"
else
    warn "x52d.service läuft nicht – wird gestartet..."
    systemctl enable --now x52d.service || err "x52d.service konnte nicht gestartet werden"
    ok "x52d.service gestartet"
fi

# 3. tmpfiles.d-Regel anlegen
echo ""
echo "Konfiguriere Socket-Zugriff..."

TMPFILES_CONF="/etc/tmpfiles.d/x52d-access.conf"
cat > "$TMPFILES_CONF" << 'EOF'
# x52tool: Socket des x52d-Daemons für alle User schreibbar machen
# Damit kann x52ctl ohne sudo aufgerufen werden.
z /run/x52d.cmd 0777 root root -
EOF
ok "Regel angelegt: $TMPFILES_CONF"

# 4. Sofort aktivieren
systemd-tmpfiles --create "$TMPFILES_CONF"
ok "Socket-Berechtigungen gesetzt"

# 5. Testen
echo ""
echo "Teste Verbindung zu x52d..."
if x52ctl config set Clock FormatPrimary 24hr &>/dev/null; then
    ok "x52ctl funktioniert – Verbindung zu x52d OK"
else
    warn "x52ctl-Test fehlgeschlagen. Gerät eingesteckt und x52d aktiv?"
fi

echo ""
echo -e "${GREEN}Installation abgeschlossen.${NC}"
echo "x52tool kann jetzt ohne sudo gestartet werden:"
echo "   python3 -m x52tool"
echo ""
