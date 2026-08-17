#!/usr/bin/env bash
# Flash guide du Corne v4.1 (standard, Vial).
#   ./flash-corne.sh              -> firmware OSD (notification de couche)
#   ./flash-corne.sh --rollback   -> firmware officiel foostan (retour arriere)
# Chaque etape qui demande une action physique s'affiche en grand et attend Entree.

set -uo pipefail

FW_OSD="$HOME/corne/OSD-crkbd_rev4_1_standard_vial.uf2"
FW_ROLLBACK="$HOME/corne/ROLLBACK-officiel-foostan-rev4_1.uf2"
KEYMAP="$HOME/Documents/corne-layout-v3.vial"
VENV_PY="$HOME/.local/share/virtualenvs/companion-Ooe6syD5/bin/python"
VID="4653"; PID="0004"
LABEL="RPI-RP2"

MODE="osd"; FW="$FW_OSD"
if [[ "${1:-}" == "--rollback" ]]; then MODE="rollback"; FW="$FW_ROLLBACK"; fi

B=$'\e[1m'; R=$'\e[0m'; GR=$'\e[32m'; YE=$'\e[33m'; RD=$'\e[31m'; CY=$'\e[36m'; INV=$'\e[7m'
COLS=$(tput cols 2>/dev/null || echo 100)

# ---------------------------------------------------------------- affichage
center() { local s="$1" n=${#1}; printf '%*s%s\n' $(( (COLS - n) / 2 )) '' "$s"; }

D1=("  █  " " ██  " "  █  " "  █  " " ███ ")
D2=("████ " "   █ " " ██  " "█    " "█████")
D3=("████ " "    █" " ███ " "    █" "████ ")
D4=("█   █" "█   █" "█████" "    █" "    █")
D5=("█████" "█    " "████ " "    █" "████ ")
D6=(" ███ " "█    " "████ " "█   █" " ███ ")

big_step() {   # gros numero d'etape 1..6 ; largeur fixe 5, pas de calcul sur ${#}
  local n="$1" pad=$(( (COLS - 5) / 2 )) rows=() i
  case "$n" in
    1) rows=("${D1[@]}");; 2) rows=("${D2[@]}");; 3) rows=("${D3[@]}");;
    4) rows=("${D4[@]}");; 5) rows=("${D5[@]}");; 6) rows=("${D6[@]}");;
  esac
  echo
  for i in "${rows[@]}"; do printf '%*s%s\n' "$pad" '' "${CY}${B}${i}${R}"; done
  echo
}

banner() {
  clear
  local line; line=$(printf '%*s' "$COLS" '' | tr ' ' '=')
  echo "${CY}${line}${R}"
  center "${B}$1${R}"
  echo "${CY}${line}${R}"
}

pause() {  # gros encadre + attente d'Entree
  echo
  local line; line=$(printf '%*s' "$COLS" '' | tr ' ' '-')
  echo "${YE}${line}${R}"
  while IFS= read -r l; do center "${B}${YE}${l}${R}"; done <<< "$1"
  echo "${YE}${line}${R}"
  echo
  center "${INV}${B}  APPUIE SUR ENTREE POUR CONTINUER  ${R}"
  echo
  read -r _ < /dev/tty
}

fail() { echo; center "${RD}${B}!! $1${R}"; echo; exit 1; }
ok()   { center "${GR}${B}[OK] $1${R}"; }

cleanup() {
  echo
  center "${RD}${B}INTERROMPU${R}"
  center "Si une seule moitie a ete flashee, les deux ne communiqueront plus."
  center "Relance le script pour flasher la seconde moitie avec le meme firmware."
  exit 130
}
trap cleanup INT TERM

# ---------------------------------------------------------------- RPI-RP2
find_rp2_dev()  { lsblk -rno PATH,LABEL 2>/dev/null | awk -v l="$LABEL" '$2==l{print $1; exit}'; }
find_rp2_mnt()  { lsblk -rno LABEL,MOUNTPOINT 2>/dev/null | awk -v l="$LABEL" '$1==l && $2!=""{print $2; exit}'; }

wait_rp2() {    # attend l'apparition du volume, le monte si besoin, renvoie le point de montage
  local t=0 dev mnt
  while (( t < 90 )); do
    dev=$(find_rp2_dev)
    if [[ -n "$dev" ]]; then
      mnt=$(find_rp2_mnt)
      if [[ -z "$mnt" ]]; then
        udisksctl mount -b "$dev" --no-user-interaction >/dev/null 2>&1
        sleep 1; mnt=$(find_rp2_mnt)
      fi
      [[ -n "$mnt" ]] && { echo "$mnt"; return 0; }
    fi
    sleep 1; ((t++))
    (( t % 5 == 0 )) && printf '.' >&2
  done
  return 1
}

wait_rp2_gone() {  # la disparition du volume = ecriture terminee
  local t=0
  while (( t < 40 )); do
    [[ -z "$(find_rp2_dev)" ]] && return 0
    sleep 1; ((t++))
  done
  return 1
}

flash_half() {  # $1 = "GAUCHE" ou "DROITE"
  local half="$1" mnt
  printf '%s' "$(center "Attente du volume ${LABEL}")"
  echo
  mnt=$(wait_rp2) || fail "Volume $LABEL introuvable apres 90 s. Le bouton BOOT etait-il bien maintenu ?"
  echo; ok "Volume detecte : $mnt"
  center "Ecriture de $(basename "$FW") ..."
  cp "$FW" "$mnt/" 2>/dev/null || true
  sync 2>/dev/null || true
  if wait_rp2_gone; then
    ok "Moitie $half flashee (le volume a disparu, c'est le signe attendu)"
  else
    fail "Le volume $LABEL est toujours la : l'ecriture a echoue."
  fi
}

# ---------------------------------------------------------------- preflight
banner "FLASH CORNE v4.1  --  mode: $(tr a-z A-Z <<< "$MODE")"
echo
[[ -f "$FW" ]] || fail "Firmware absent : $FW"
ok "Firmware      : $(basename "$FW") ($(stat -c%s "$FW") octets)"
if [[ -f "$KEYMAP" ]]; then ok "Keymap sauve  : $KEYMAP"
else center "${YE}Attention : $KEYMAP introuvable.${R}"; fi
command -v udisksctl >/dev/null || fail "udisksctl absent (paquet udisks2)"
ok "udisksctl     : present"
if lsusb -d "$VID:$PID" >/dev/null 2>&1; then ok "Clavier       : detecte actuellement"
else center "${YE}Clavier non detecte pour l'instant, ce n'est pas bloquant.${R}"; fi
echo
center "Le script va te guider en 6 etapes. Rien n'est ecrit avant l'etape 2."
pause "PRET ? ON COMMENCE."

# ---------------------------------------------------------------- etapes
banner "ETAPE 1/6  --  PREPARATION"; big_step 1
pause "DEBRANCHE LE CABLE USB DU CLAVIER
PUIS SEPARE LES DEUX MOITIES
(retire le cable jack entre elles)

JAMAIS DE JACK BRANCHE OU DEBRANCHE
QUAND L'USB EST CONNECTE"

banner "ETAPE 2/6  --  MOITIE GAUCHE EN BOOTLOADER"; big_step 2
pause "MAINTIENS LA TOUCHE  a  DE LA MOITIE GAUCHE
(la 2e du haut, juste a droite de Tab)
ET BRANCHE SON CABLE USB

GARDE LA TOUCHE APPUYEE 2 SECONDES APRES

CETTE METHODE EFFACE LE KEYMAP,
IL SERA A RECHARGER A LA FIN"
banner "ETAPE 2/6  --  ECRITURE GAUCHE"
flash_half "GAUCHE"

banner "ETAPE 3/6  --  MOITIE DROITE EN BOOTLOADER"; big_step 3
pause "DEBRANCHE LA MOITIE GAUCHE

MAINTIENS LA TOUCHE  p  DE LA MOITIE DROITE
(juste a gauche du retour arriere)
ET BRANCHE SON CABLE USB"
banner "ETAPE 3/6  --  ECRITURE DROITE"
flash_half "DROITE"

banner "ETAPE 4/6  --  REASSEMBLAGE"; big_step 4
pause "DEBRANCHE L'USB

RECONNECTE LE CABLE JACK ENTRE LES MOITIES

PUIS SEULEMENT APRES, REBRANCHE L'USB
(dans l'ordre : jack d'abord, USB ensuite)"

banner "ETAPE 5/6  --  VERIFICATION USB"; big_step 5
echo
for i in $(seq 1 20); do
  lsusb -d "$VID:$PID" >/dev/null 2>&1 && break
  sleep 1; printf '.'
done
echo
lsusb -d "$VID:$PID" >/dev/null 2>&1 || fail "Clavier non detecte. Verifie le cable USB."
ok "Clavier detecte : $(lsusb -d "$VID:$PID")"
n=$(ls /dev/hidraw* 2>/dev/null | wc -l); ok "$n peripheriques hidraw presents"
echo
center "Tape quelques lettres sur ${B}CHAQUE${R} moitie pour verifier"
center "qu'elles communiquent bien toutes les deux."
pause "LES DEUX MOITIES REPONDENT ?
SI UNE SEULE FONCTIONNE, LE JACK EST MAL BRANCHE
OU LA REVISION DU FIRMWARE NE CORRESPOND PAS"

# ---------------------------------------------------------------- etape 6
banner "ETAPE 6/6  --  TEST DES NOTIFICATIONS DE COUCHE"; big_step 6
if [[ "$MODE" == "rollback" ]]; then
  echo
  center "Mode rollback : le firmware officiel ne notifie pas les couches."
  center "Cette etape est sans objet, elle est ignoree."
else
  if [[ ! -x "$VENV_PY" ]]; then
    center "${YE}venv de l'app introuvable, test automatique ignore.${R}"
  else
    echo
    center "Je vais ecouter l'endpoint raw HID pendant 20 secondes."
    pause "MAINTIENS ET RELACHE PLUSIEURS FOIS
TES DEUX POUCES DE COUCHE
PENDANT LE TEST QUI VA SUIVRE"
    "$VENV_PY" - <<'PYEOF'
import sys, time
try:
    import hid
except Exception as e:
    print("  module hid indisponible :", e); sys.exit(2)
VID, PID = 0x4653, 0x0004
UP, US = 0xFF60, 0x61
MARK, BEGIN = 0x90, 24
paths = []
for d in hid.enumerate(VID, PID):
    if d.get("usage_page") == UP and d.get("usage") == US:
        paths.append(d["path"])
if not paths:
    print("  Aucune interface raw HID (0xFF60/0x61) trouvee.")
    print("  Ferme Vial s'il est ouvert, il monopolise cet endpoint.")
    sys.exit(1)
seen, end = set(), time.time() + 20
try:
    dev = hid.Device(path=paths[0])
except Exception as e:
    print("  Ouverture impossible :", e)
    print("  Ferme Vial s'il est ouvert.")
    sys.exit(1)
print("  Ecoute en cours, change de couche ...")
while time.time() < end:
    try:
        data = dev.read(32, 500)
    except Exception:
        continue
    if data and len(data) > BEGIN + 1 and data[BEGIN] == MARK:
        lay = data[BEGIN + 1]
        if lay not in seen:
            seen.add(lay)
            print(f"  couche {lay} signalee par le clavier")
dev.close()
if seen:
    print(f"\n  RESULTAT : patch fonctionnel, couches vues = {sorted(seen)}")
    sys.exit(0)
print("\n  RESULTAT : aucun paquet recu. Le patch n'est pas actif,")
print("  ou Vial est ouvert et capte les paquets a ma place.")
sys.exit(1)
PYEOF
    rc=$?
    echo
    if [[ $rc -eq 0 ]]; then ok "Notifications de couche confirmees"
    else center "${YE}Test non concluant, voir le message ci-dessus.${R}"; fi
  fi
fi

# ---------------------------------------------------------------- fin
echo
banner "TERMINE"
echo
if [[ "$MODE" == "osd" ]]; then
  center "Il reste 2 choses a faire a la main :"
  echo
  center "1. Recharger ton keymap dans Vial"
  center "   vial.rocks  ->  Load saved layout  ->  $KEYMAP"
  echo
  center "2. Lancer l'OSD :"
  center "   cd ~/corne/companion && pipenv run python main.py"
  echo
  center "En cas de probleme : ./flash-corne.sh --rollback"
else
  center "Firmware officiel restaure."
  center "Recharge ton keymap : vial.rocks -> Load saved layout"
  center "$KEYMAP"
fi
echo
