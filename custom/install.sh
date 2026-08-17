#!/usr/bin/env bash
#
# Installation de l'overlay de couches du Corne v4.1 sur Ubuntu / GNOME.
#
#   ./custom/install.sh                    installation complete
#   ./custom/install.sh --check            verifie sans rien modifier
#   ./custom/install.sh --keymap FICHIER   utilise un autre export .vial
#
# Idempotent : relancable sans dommage.
#
# Ce script N'INSTALLE PAS le firmware ni le keymap. Tous deux vivent dans le
# clavier et le suivent d'une machine a l'autre. Si le clavier est neuf, voir
# custom/README.md et le depot m-k8s/kbd_firmware.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/corne-overlay.service"
UDEV="/etc/udev/rules.d/59-vial.rules"
EXT_UUID="focused-window-dbus@flexagoon.com"
EXT_URL="https://extensions.gnome.org/extension/5592/focused-window-d-bus/"
VID="4653"; PID="0004"
PKGS=(libhidapi-hidraw0 libhidapi-libusb0 x11-utils x11-xserver-utils xdotool pipx)

CHECK_ONLY=0
KEYMAP=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --check)  CHECK_ONLY=1; shift ;;
    --keymap) KEYMAP="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,14p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'; exit 0 ;;
    *) echo "option inconnue : $1"; exit 2 ;;
  esac
done

B=$'\e[1m'; R=$'\e[0m'; GR=$'\e[32m'; YE=$'\e[33m'; RD=$'\e[31m'; CY=$'\e[36m'
step()  { echo; echo "${CY}${B}== $* ==${R}"; }
ok()    { echo "  ${GR}[ok]${R} $*"; }
warn()  { echo "  ${YE}[!]${R}  $*"; WARNINGS+=("$*"); }
die()   { echo; echo "  ${RD}${B}[stop]${R} $*"; echo; exit 1; }
todo()  { MANUAL+=("$*"); }
declare -a WARNINGS=() MANUAL=()

# --------------------------------------------------------------- 1. controles
step "1/7  Controles prealables"

[[ -f "$REPO/Pipfile" && -f "$REPO/libs/gui.py" ]] \
  || die "Ce script doit vivre dans custom/ du depot companion. Racine deduite : $REPO"
ok "depot : $REPO"

command -v apt-get >/dev/null || die "Distribution non basee sur apt, installation manuelle requise."
command -v systemctl >/dev/null || die "systemd absent."

case "${XDG_SESSION_TYPE:-}" in
  wayland) ok "session Wayland" ;;
  x11)     ok "session X11 (le placement et le premier plan y sont plus simples)" ;;
  *)       warn "type de session inconnu (${XDG_SESSION_TYPE:-vide})" ;;
esac

if [[ "${XDG_CURRENT_DESKTOP:-}" == *GNOME* ]]; then
  ok "GNOME : ${XDG_CURRENT_DESKTOP}"
else
  warn "bureau non GNOME (${XDG_CURRENT_DESKTOP:-vide}) : le suivi de la fenetre active ne fonctionnera pas"
fi

if lsusb -d "$VID:$PID" >/dev/null 2>&1; then
  ok "clavier detecte : $(lsusb -d "$VID:$PID" | sed 's/.*: //')"
else
  warn "clavier absent du bus USB : le service demarrera et retentera toutes les 15 s"
fi

# --------------------------------------------------- 2. dependances systeme
step "2/7  Paquets systeme"
MISSING=()
for p in "${PKGS[@]}"; do
  dpkg -s "$p" >/dev/null 2>&1 || MISSING+=("$p")
done
if [[ ${#MISSING[@]} -eq 0 ]]; then
  ok "les ${#PKGS[@]} paquets requis sont deja presents"
elif [[ $CHECK_ONLY -eq 1 ]]; then
  warn "a installer : ${MISSING[*]}"
else
  echo "  installation de : ${MISSING[*]}"
  sudo apt-get install -y "${MISSING[@]}" >/dev/null || die "echec de l'installation des paquets"
  ok "${#MISSING[@]} paquet(s) installe(s)"
fi

# ------------------------------------------------------- 3. regle udev Vial
step "3/7  Regle udev pour Vial"
if [[ -f "$UDEV" ]]; then
  ok "deja en place : $UDEV"
elif [[ $CHECK_ONLY -eq 1 ]]; then
  warn "absente : $UDEV"
else
  # 59- et non 99- : un changement du noyau a modifie l'ordre d'application.
  RULE='KERNEL=="hidraw*", SUBSYSTEM=="hidraw", ATTRS{serial}=="*vial:f64c2b3c*", MODE="0660", GROUP="'"$(id -gn)"'", TAG+="uaccess", TAG+="udev-acl"'
  echo "$RULE" | sudo tee "$UDEV" >/dev/null || die "ecriture de $UDEV impossible"
  sudo udevadm control --reload && sudo udevadm trigger
  ok "creee, rebranche le clavier pour qu'elle prenne effet"
fi

# ----------------------------------------------------- 4. environnement python
step "4/7  Environnement Python"
command -v pipenv >/dev/null || {
  [[ $CHECK_ONLY -eq 1 ]] && warn "pipenv absent" || {
    pipx install pipenv >/dev/null 2>&1 || die "installation de pipenv impossible"
    export PATH="$HOME/.local/bin:$PATH"
  }
}

WANT="$(grep -oP 'python_version\s*=\s*"\K[0-9.]+' "$REPO/Pipfile" 2>/dev/null || echo 3.13)"
PY=""
if command -v "python$WANT" >/dev/null; then
  PY="$(command -v "python$WANT")"
  ok "python$WANT du systeme : $PY"
elif command -v pyenv >/dev/null; then
  FOUND="$(pyenv versions --bare 2>/dev/null | grep -E "^${WANT}\.[0-9]+$" | tail -1)"
  if [[ -z "$FOUND" && $CHECK_ONLY -eq 0 ]]; then
    echo "  compilation de python via pyenv, quelques minutes"
    FOUND="$(pyenv install --list | grep -E "^  ${WANT}\.[0-9]+$" | tail -1 | tr -d ' ')"
    pyenv install -s "$FOUND" || die "pyenv install $FOUND a echoue"
  fi
  [[ -n "$FOUND" ]] && PY="$(pyenv root)/versions/$FOUND/bin/python" && ok "pyenv : $FOUND"
fi
if [[ -z "$PY" ]]; then
  MSG="python $WANT introuvable (demande par le Pipfile). Installe-le : sudo apt-get install python$WANT, ou pyenv install $WANT"
  [[ $CHECK_ONLY -eq 1 ]] && warn "$MSG" || die "$MSG"
fi

if [[ $CHECK_ONLY -eq 0 && -n "$PY" ]]; then
  ( cd "$REPO" && pipenv install --python "$PY" ) || die "pipenv install a echoue"
  ok "dependances installees"
fi

VENV_PY=""
if [[ $CHECK_ONLY -eq 0 && -n "$PY" ]]; then
  VENV="$( cd "$REPO" && pipenv --venv 2>/dev/null )" || die "venv introuvable apres installation"
  VENV_PY="$VENV/bin/python"
  [[ -x "$VENV_PY" ]] || die "interpreteur du venv absent : $VENV_PY"
  ok "venv : $VENV"
  "$VENV_PY" -c "import kivy, hid, zeroconf, aiohttp, tenacity" 2>/dev/null \
    && ok "imports verifies, dont hid qui charge libhidapi" \
    || die "un import a echoue, verifie que libhidapi-hidraw0 est installe"
fi

# ------------------------------------------------------- 5. extension GNOME
step "5/7  Extension GNOME focused-window-dbus"
if gnome-extensions list 2>/dev/null | grep -qx "$EXT_UUID"; then
  if gnome-extensions list --enabled 2>/dev/null | grep -qx "$EXT_UUID"; then
    ok "installee et activee"
  elif [[ $CHECK_ONLY -eq 0 ]]; then
    gnome-extensions enable "$EXT_UUID" && ok "activee" || warn "activation impossible"
  else
    warn "installee mais desactivee"
  fi
else
  warn "absente : le suivi de la fenetre active retombera sur monitor_index"
  todo "Installer l'extension GNOME depuis $EXT_URL puis relancer ce script."
fi

# ---------------------------------------------------- 6. images des couches
step "6/7  Images des couches"
[[ -z "$KEYMAP" ]] && KEYMAP="$(ls -1 "$REPO"/custom/keymaps/*.vial 2>/dev/null | sort -V | tail -1)"
[[ -f "$KEYMAP" ]] || die "aucun export .vial trouve dans $REPO/custom/keymaps/"
ok "keymap source : $(basename "$KEYMAP")"
if [[ $CHECK_ONLY -eq 0 ]]; then
  "$REPO/custom/render-overlay.py" "$KEYMAP" --config config.ini --sheet \
    | sed 's/^/  /' || die "generation des images impossible"
fi

# ---------------------------------------------------------- 7. service systemd
step "7/7  Service systemd"
if [[ $CHECK_ONLY -eq 1 ]]; then
  [[ -f "$UNIT" ]] && ok "unite presente : $UNIT" || warn "unite absente"
else
  mkdir -p "$UNIT_DIR"
  # L'unite est GENEREE et non copiee : le chemin du venv contient un hash
  # derive du chemin du projet, donc il differe d'une machine a l'autre.
  cat > "$UNIT" <<UNITEOF
[Unit]
Description=Corne layer overlay
Documentation=https://github.com/maatthc/keyboard_layers_app_companion
PartOf=graphical-session.target
After=graphical-session.target
# pas de plafond de tentatives : le clavier peut etre branche plus tard
StartLimitIntervalSec=0

[Service]
Type=simple
WorkingDirectory=$REPO
ExecStart=$VENV_PY main.py
# sortie 1 = clavier absent -> on retente ; sortie 0 = Echap -> on laisse tranquille
Restart=on-failure
RestartSec=15
# sans ceci, Python bufferise stdout et le journal reste vide
Environment=PYTHONUNBUFFERED=1
Environment=KIVY_NO_CONSOLELOG=1
Slice=app.slice

[Install]
WantedBy=graphical-session.target
UNITEOF
  ok "unite ecrite avec le venv de cette machine"
  systemctl --user daemon-reload
  systemctl --user enable corne-overlay >/dev/null 2>&1
  systemctl --user restart corne-overlay
  sleep 5
  if systemctl --user is-active --quiet corne-overlay; then
    ok "service actif et active au demarrage de session"
    journalctl --user -u corne-overlay --since "15 sec ago" -o cat --no-pager \
      | grep -E "^\[overlay\]|Product:" | sed 's/^/      /'
  else
    warn "service inactif, voir : journalctl --user -u corne-overlay -n 30"
  fi
fi

# -------------------------------------------------------------------- bilan
echo
echo "${CY}${B}== Bilan ==${R}"
if [[ ${#WARNINGS[@]} -eq 0 ]]; then
  echo "  ${GR}${B}Aucun avertissement.${R}"
else
  echo "  ${YE}${#WARNINGS[@]} avertissement(s) :${R}"
  for w in "${WARNINGS[@]}"; do echo "    - $w"; done
fi
if [[ ${#MANUAL[@]} -gt 0 ]]; then
  echo
  echo "  ${B}A faire a la main :${R}"
  for m in "${MANUAL[@]}"; do echo "    - $m"; done
fi
echo
echo "  ${B}Rappels${R}"
echo "    Le firmware et le keymap vivent dans le clavier, rien a installer ici."
echo "    Vial et l'overlay ne peuvent pas ouvrir l'endpoint raw HID en meme temps :"
echo "      systemctl --user stop corne-overlay   avant d'ouvrir vial.rocks"
echo "    Reglages : section [OVERLAY] de $REPO/config.ini"
echo "    Documentation complete : $REPO/custom/README.md"
echo
