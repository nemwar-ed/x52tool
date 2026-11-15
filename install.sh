#!/usr/bin/env bash
# x52tool – Einmalige Systemkonfiguration
# Führe dieses Skript einmalig mit sudo aus, danach läuft x52tool ohne root.
#
# Was dieses Skript tut:
#   1. Prüft ob libx52 (x52d, x52ctl) installiert ist
#   2. Legt ein systemd-Drop-in für x52d.service an, das den Socket
#      /run/x52d.cmd nach jedem Start für alle User schreibbar macht
#   3. Entfernt die alte (wirkungslose) tmpfiles.d-Regel aus v0.0.2-beta
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

# 3. Socket-Zugriff per systemd-Drop-in
#    x52d legt /run/x52d.cmd bei jedem Start neu an (nur root-schreibbar).
#    Eine tmpfiles.d-Regel greift nur beim Booten – also bevor der Socket
#    existiert. Deshalb: nach jedem Start warten, bis der Socket da ist, dann chmod.
echo ""
echo "Konfiguriere Socket-Zugriff..."

DROPIN_DIR="/etc/systemd/system/x52d.service.d"
DROPIN_CONF="$DROPIN_DIR/x52tool-socket.conf"
mkdir -p "$DROPIN_DIR"
cat > "$DROPIN_CONF" << 'DROPIN'
# x52tool: Socket des x52d-Daemons für alle User schreibbar machen,
# damit x52ctl ohne sudo funktioniert.
[Service]
ExecStartPost=/bin/sh -c 'for i in $(seq 50); do if [ -S /run/x52d.cmd ]; then exec chmod 0666 /run/x52d.cmd; fi; sleep 0.1; done; echo "x52d.cmd nicht gefunden" >&2'
DROPIN
ok "Drop-in angelegt: $DROPIN_CONF"

# Alte, wirkungslose Regel aus v0.0.2-beta entfernen
OLD_TMPFILES="/etc/tmpfiles.d/x52d-access.conf"
if [[ -f "$OLD_TMPFILES" ]]; then
    rm -f "$OLD_TMPFILES"
    ok "Alte Regel entfernt: $OLD_TMPFILES"
fi

# 4. Sofort aktivieren
systemctl daemon-reload
systemctl restart x52d.service
sleep 1
if [[ "$(stat -c %a /run/x52d.cmd 2>/dev/null)" == "666" ]]; then
    ok "Socket-Berechtigungen gesetzt"
else
    warn "Socket /run/x52d.cmd hat nicht die erwarteten Rechte (666)"
fi

# 5. Testen (als aufrufender User, nicht als root)
echo ""
echo "Teste Verbindung zu x52d..."
if sudo -u "${SUDO_USER:-root}" x52ctl config get Clock FormatPrimary &>/dev/null; then
    ok "x52ctl funktioniert – Verbindung zu x52d OK"
else
    warn "x52ctl-Test fehlgeschlagen. Gerät eingesteckt und x52d aktiv?"
fi

echo ""
echo -e "${GREEN}Installation abgeschlossen.${NC}"
echo "x52tool kann jetzt ohne sudo gestartet werden:"
echo "   python3 -m x52tool"
echo ""
