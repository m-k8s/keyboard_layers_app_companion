#!/usr/bin/env python3
"""
Regenere les images de couches de l'overlay depuis un export Vial.

    ./custom/render-overlay.py ~/Documents/corne-layout-v4.vial

Cible : Corne v4.1 standard, 46 touches (3x6 + 3 pouces + 2 colonnes centrales).
Disposition systeme : Linux fr+latin9.

Options :
    -o DOSSIER     dossier de sortie (defaut : assets/ a la racine du depot)
    --config FICH  met aussi a jour la section [LAYER_IMAGES] de ce config.ini.
                   Un chemin relatif est resolu depuis la racine du depot, pas
                   depuis le repertoire courant.
    --scale N      facteur de taille des images (defaut 1.0)
    --sheet        assemble aussi une planche unique, pour impression A4
                   paysage ou fond d ecran
"""

import argparse
import json
import os
import re
import sys
import unicodedata
from PIL import Image, ImageDraw, ImageFont

# Le script vit dans custom/ : la sortie par defaut est assets/ a la racine du
# depot, et non ./assets, pour ne pas dependre du repertoire courant.
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(REPO, "assets")

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONTB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# ============================================================== apparence
LET, SYM, MOD, NAV, LAY, SYS, DIM = "let sym mod nav lay sys dim".split()
COLORS = {
    LET: ("#e8e6e3", "#2f3439"),
    SYM: ("#f0a848", "#33302b"),
    MOD: ("#8fa3b8", "#2a2f34"),
    NAV: ("#7fc4d8", "#263034"),
    LAY: ("#8fd18f", "#28322a"),
    SYS: ("#c49ad8", "#2f2a35"),
    DIM: ("#4a4f54", "#232629"),
}
BG = "#17191c"
DEAD = "\u25cc"          # cercle pointille : marque les touches mortes

# ====================================================== table fr+latin9
# Par touche : (niveau1, niveau2 = Shift, niveau3 = AltGr, niveau4 = AltGr+Shift)
# Chaine vide = ce niveau ne produit rien.
L = {
    "KC_GRAVE":  ("\u0153", "\u0152", "\u201c", "\u201d"),      # oe OE " "
    "KC_1":      ("&", "1", DEAD + "\u00b4", ""),
    "KC_2":      ("\u00e9", "2", "~", "\u00c9"),
    "KC_3":      ('"', "3", "#", ""),
    "KC_4":      ("'", "4", "{", ""),
    "KC_5":      ("(", "5", "[", ""),
    "KC_6":      ("-", "6", "|", ""),
    "KC_7":      ("\u00e8", "7", DEAD + "`", "\u00c8"),
    "KC_8":      ("_", "8", "\\", ""),
    "KC_9":      ("\u00e7", "9", "^", "\u00c7"),
    "KC_0":      ("\u00e0", "0", "@", "\u00c0"),
    "KC_MINUS":  (")", "\u00b0", "]", ""),
    "KC_EQUAL":  ("=", "+", "}", ""),
    "KC_LBRACKET": (DEAD + "^", DEAD + "\u00a8", DEAD + "~", "'"),
    "KC_RBRACKET": ("$", "\u00a3", "\u00ea", "\u00eb"),
    "KC_SCOLON": ("m", "M", "\u00b9", "\u00ba"),
    "KC_QUOTE":  ("\u00f9", "%", "\u00b2", "\u00d9"),
    "KC_BSLASH": ("*", "\u00b5", "\u00b3", "\u00a5"),
    "KC_NONUS_HASH": ("*", "\u00b5", "\u00b3", "\u00a5"),
    "KC_NONUS_BACKSLASH": ("<", ">", "|", ""),
    "KC_M":      (",", "?", "", ""),
    "KC_COMMA":  (";", ".", "", ""),
    "KC_DOT":    (":", "/", "", ""),
    "KC_SLASH":  ("!", "\u00a7", "", ""),
}
# lettres : position US -> caractere AZERTY, avec les niveaux 3 connus de latin9
_LETTERS = {
    "KC_Q": ("a", "\u00e2"), "KC_W": ("z", "\u00e5"), "KC_E": ("e", "\u20ac"),
    "KC_R": ("r", ""),       "KC_T": ("t", "\u00fe"), "KC_Y": ("y", "\u00fd"),
    "KC_U": ("u", "\u00fb"), "KC_I": ("i", "\u00ee"), "KC_O": ("o", "\u00f4"),
    "KC_P": ("p", "\u00b6"),
    "KC_A": ("q", ""),       "KC_S": ("s", "\u00f8"), "KC_D": ("d", ""),
    "KC_F": ("f", "\u00b1"), "KC_G": ("g", "\u00e6"), "KC_H": ("h", "\u00f0"),
    "KC_J": ("j", ""),       "KC_K": ("k", ""),       "KC_L": ("l", ""),
    "KC_Z": ("w", "\u00ab"), "KC_X": ("x", "\u00bb"), "KC_C": ("c", "\u00a9"),
    "KC_V": ("v", "\u00ae"), "KC_B": ("b", ""),       "KC_N": ("n", "\u00ac"),
}
for _k, (_lo, _a) in _LETTERS.items():
    L[_k] = (_lo, _lo.upper(), _a, _a.upper() if _a else "")
# le grave litteral de latin9 vit au niveau 4 de la touche p
L["KC_P"] = ("p", "P", "\u00b6", "`")

NAMED = {
    "KC_TAB": ("Tab", NAV), "KC_BSPACE": ("\u232b", NAV),
    "KC_BSPC": ("\u232b", NAV),
    "KC_DELETE": ("Suppr", NAV), "KC_DEL": ("Suppr", NAV),
    "KC_ENTER": ("\u23ce", NAV), "KC_ENT": ("\u23ce", NAV),
    "KC_SPACE": ("Espace", NAV), "KC_SPC": ("Espace", NAV),
    "KC_ESCAPE": ("\u00c9chap", NAV), "KC_ESC": ("\u00c9chap", NAV),
    "KC_HOME": ("D\u00e9but", NAV), "KC_END": ("Fin", NAV),
    "KC_PGUP": ("Pg\u2191", NAV), "KC_PGDOWN": ("Pg\u2193", NAV),
    "KC_PGDN": ("Pg\u2193", NAV),
    "KC_INSERT": ("Inser", NAV), "KC_INS": ("Inser", NAV),
    "KC_PSCREEN": ("Impr", NAV), "KC_PSCR": ("Impr", NAV),
    "KC_CAPSLOCK": ("Verr Maj", NAV), "KC_CAPS": ("Verr Maj", NAV),
    "KC_LEFT": ("\u2190", NAV), "KC_RIGHT": ("\u2192", NAV),
    "KC_UP": ("\u2191", NAV), "KC_DOWN": ("\u2193", NAV),
    "KC_LSHIFT": ("Maj", MOD), "KC_LSFT": ("Maj", MOD),
    "KC_RSHIFT": ("Maj", MOD), "KC_RSFT": ("Maj", MOD),
    "KC_LCTRL": ("Ctrl", MOD), "KC_LCTL": ("Ctrl", MOD),
    "KC_RCTRL": ("Ctrl", MOD), "KC_RCTL": ("Ctrl", MOD),
    "KC_LALT": ("Alt", MOD), "KC_RALT": ("AltGr", MOD),
    "KC_LGUI": ("Super", MOD), "KC_RGUI": ("Super", MOD),
    "KC_MUTE": ("Muet", NAV), "KC_AUDIO_MUTE": ("Muet", NAV),
    "KC_VOLU": ("Vol+", NAV), "KC_AUDIO_VOL_UP": ("Vol+", NAV),
    "KC_VOLD": ("Vol\u2212", NAV), "KC_AUDIO_VOL_DOWN": ("Vol\u2212", NAV),
    "KC_MPLY": ("Play", NAV), "KC_MEDIA_PLAY_PAUSE": ("Play", NAV),
    "KC_MNXT": ("Suiv", NAV), "KC_MEDIA_NEXT_TRACK": ("Suiv", NAV),
    "KC_MPRV": ("Pr\u00e9c", NAV), "KC_MEDIA_PREV_TRACK": ("Pr\u00e9c", NAV),
    "FN_MO13": ("C1 \u00b7 C3", LAY), "FN_MO23": ("C2 \u00b7 C3", LAY),
    # KC_GRAVE porte le keysym Above_Tab, que GNOME utilise pour switch-group
    # (basculer entre les fenetres d une meme application). Sans cette mention
    # on la retire en croyant ne perdre qu un oe, et le raccourci part avec.
    "KC_GRAVE": ("\u0153\nAbove Tab", SYM),
    # Moins et plus du pave numerique. Ctrl plus eux zoome et dezoome dans les
    # navigateurs quelle que soit la disposition, alors que Ctrl plus la touche
    # de la rangee des chiffres est interpretee par position (onglet N).
    "KC_KP_MINUS": ("-\nnum", SYM),
    "KC_KP_PLUS": ("+\nnum", SYM),
    "KC_KP_ASTERISK": ("*\nnum", SYM),
    "KC_KP_SLASH": ("/\nnum", SYM),
    "KC_TRNS": ("\u25bd", DIM), "KC_TRANSPARENT": ("\u25bd", DIM),
    "KC_NO": ("", DIM),
    "QK_BOOT": ("BOOT", SYS), "RESET": ("BOOT", SYS),
    "QK_CLEAR_EEPROM": ("RAZ\nEEPROM", SYS),
    "RGB_TOG": ("RGB", SYS), "RGB_MOD": ("mode", SYS),
    "RGB_RMOD": ("mode\u2212", SYS),
    "RGB_HUI": ("teinte+", SYS), "RGB_HUD": ("teinte\u2212", SYS),
    "RGB_SAI": ("satur+", SYS), "RGB_SAD": ("satur\u2212", SYS),
    "RGB_VAI": ("lumi+", SYS), "RGB_VAD": ("lumi\u2212", SYS),
}
for _i in range(1, 25):
    NAMED[f"KC_F{_i}"] = (f"F{_i}", NAV)

MODS = {"LSFT": "s", "RSFT": "s", "LCTL": "c", "RCTL": "c",
        "LALT": "a", "RALT": "g", "LGUI": "w", "RGUI": "w",
        "S": "s", "C": "c", "A": "a", "G": "g"}
MOD_LABEL = {"s": "Maj", "c": "Ctrl", "a": "Alt", "g": "AltGr", "w": "Super"}

# Unicode classe "\u00b2" comme un chiffre et "\u00b5" comme une lettre, ce qui
# fausse le code couleur. On s'appuie sur les categories reelles, avec une
# exception pour les lettres qui sont des symboles a l'usage.
_SYM_LETTERS = {"\u00b5", "\u00ba", "\u00aa"}


def char_category(ch):
    if len(ch) != 1 or ch in _SYM_LETTERS:
        return SYM
    cat = unicodedata.category(ch)
    return LET if (cat.startswith("L") or cat == "Nd") else SYM


UNRESOLVED = set()


def peel(kc):
    """Deballe les enveloppes de modificateurs. -> (set de mods, base)"""
    mods, cur = set(), kc
    while True:
        m = re.fullmatch(r"([A-Z]+)\((.+)\)", cur)
        if not m or m.group(1) not in MODS:
            return mods, cur
        mods.add(MODS[m.group(1)])
        cur = m.group(2)


def resolve(kc):
    """-> (libelle, indice Shift ou None, categorie) ; None si touche absente."""
    if kc == -1 or kc is None:
        return None
    if not isinstance(kc, str):
        return (str(kc), None, DIM)

    if kc in NAMED:
        lab, cat = NAMED[kc]
        return (lab, None, cat)

    # couches et macros
    m = re.fullmatch(r"(MO|TO|TG|TT|DF|OSL)\((\d+)\)", kc)
    if m:
        return (f"{m.group(1)}\nC{m.group(2)}", None, LAY)
    m = re.fullmatch(r"LT(\d+)\((.+)\)", kc) or re.fullmatch(r"LT\((\d+),\s*(.+)\)", kc)
    if m:
        inner = resolve(m.group(2))
        return (f"C{m.group(1)} /\n{inner[0] if inner else '?'}", None, LAY)
    m = re.fullmatch(r"M(\d+)", kc)
    if m:
        return (f"Macro\n{m.group(1)}", None, SYS)
    m = re.fullmatch(r"TD\((\d+)\)", kc)
    if m:
        return (f"TapD\n{m.group(1)}", None, SYS)
    m = re.fullmatch(r"([LR]?(?:SFT|CTL|ALT|GUI))_T\((.+)\)", kc)
    if m:
        base = resolve(m.group(2))
        key = m.group(1)
        code = MODS.get(key) or MODS.get("L" + key) or ""
        short = MOD_LABEL.get(code, key)
        return (f"{short} /\n{base[0] if base else '?'}", None, MOD)

    mods, base = peel(kc)
    if base in L:
        lv = L[base]
        shift, altgr = "s" in mods, "g" in mods
        idx = 3 if (shift and altgr) else 2 if altgr else 1 if shift else 0
        ch = lv[idx]
        other = {m for m in mods if m not in ("s", "g")}
        if ch and not other:
            cat = char_category(ch)
            hint = lv[1] if idx == 0 and lv[1] and lv[1] != lv[0].upper() else None
            return (ch, hint, cat)
        # combinaison sans caractere propre : on montre modificateurs + base
        pre = "+".join(MOD_LABEL[m] for m in sorted(mods))
        return (f"{pre}\n{lv[0]}", None, MOD)

    if mods and base in NAMED:
        pre = "+".join(MOD_LABEL[m] for m in sorted(mods))
        return (f"{pre}\n{NAMED[base][0]}", None, MOD)

    UNRESOLVED.add(kc)
    return (re.sub(r"^(KC_|QK_)", "", kc).replace("_", "\n"), None, DIM)


# ============================================================== geometrie
U, KS = 96, 86
STAG_L = [0.32, 0.32, 0.16, 0.00, 0.10, 0.22, 0.22]
STAG_R = [0.22, 0.22, 0.10, 0.00, 0.16, 0.32, 0.32]
GAP, MX, MY = 0.55, 46, 84
COLMAP = [("L", i) for i in range(7)] + [("R", i) for i in [6, 5, 4, 3, 2, 1, 0]]
THUMBS_L = [(3, 3), (4, 4), (5, 5)]
THUMBS_R = [(8, 5), (9, 4), (10, 3)]


def col_x(c):
    return MX + c * U + (GAP * U if c >= 7 else 0)


def col_y(c, r):
    stag = STAG_L[c] if c < 7 else STAG_R[c - 7]
    return MY + (r + stag) * U


def thumb_pos(c, side):
    if side == "L":
        return col_x(c) + 26, col_y(c, 3) + 14 + (c - 3) * 13
    return col_x(c) - 26, col_y(c, 3) + 14 + (10 - c) * 13


# ================================================================== rendu
def draw_key(dr, x, y, entry, fonts):
    lab, hint, cat = entry
    fg, bg = COLORS[cat]
    dr.rounded_rectangle([x, y, x + KS, y + KS], radius=11, fill=bg,
                         outline="#3c4147", width=2)
    if not lab:
        return
    lines = lab.split("\n")
    if len(lines) == 1 and len(lines[0]) <= 2 and DEAD not in lab:
        f = fonts["big"]
    elif max(len(s) for s in lines) <= 5 and len(lines) <= 2:
        f = fonts["mid"]
    else:
        f = fonts["small"]
    total = len(lines) * (f.size + 2) - 2
    cy = y + (KS - total) / 2
    for ln in lines:
        w = dr.textlength(ln, font=f)
        dr.text((x + (KS - w) / 2, cy), ln, font=f, fill=fg)
        cy += f.size + 2
    if hint:
        hw = dr.textlength(hint, font=fonts["hint"])
        dr.text((x + KS - hw - 5, y + 5), hint, font=fonts["hint"], fill="#6f7378")


def render(layer, title, subtitle, path, scale=1.0):
    W = int(MX * 2 + 14 * U + GAP * U)
    H = int(MY + 4.6 * U + 62)
    img = Image.new("RGB", (W, H), BG)
    dr = ImageDraw.Draw(img)
    fonts = {
        "big": ImageFont.truetype(FONTB, 42),
        "mid": ImageFont.truetype(FONTB, 22),
        "small": ImageFont.truetype(FONT, 16),
        "hint": ImageFont.truetype(FONT, 17),
        "title": ImageFont.truetype(FONTB, 34),
        "sub": ImageFont.truetype(FONT, 20),
    }
    dr.text((MX, 22), title, font=fonts["title"], fill="#e8e6e3")
    tw = dr.textlength(title, font=fonts["title"])
    dr.text((MX + tw + 18, 31), subtitle, font=fonts["sub"], fill="#7f858b")

    for c, (half, idx) in enumerate(COLMAP):
        base = 0 if half == "L" else 4
        for r in range(3):
            e = resolve(layer[base + r][idx])
            if e:
                draw_key(dr, col_x(c), col_y(c, r), e, fonts)
    for c, idx in THUMBS_L:
        e = resolve(layer[3][idx])
        if e:
            draw_key(dr, *thumb_pos(c, "L"), e, fonts)
    for c, idx in THUMBS_R:
        e = resolve(layer[7][idx])
        if e:
            draw_key(dr, *thumb_pos(c, "R"), e, fonts)

    if scale != 1.0:
        img = img.resize((int(W * scale), int(H * scale)), Image.LANCZOS)
    img.save(path)
    return img.size


SUBTITLES = {
    0: "base \u00b7 aucun pouce de couche maintenu",
    1: "pouce gauche maintenu",
    2: "pouce droit maintenu",
    3: "les deux pouces maintenus",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("vial", help="export .vial depuis Vial (Save layout)")
    ap.add_argument("-o", "--out", default=ASSETS)
    ap.add_argument("--config", default=None,
                    help="config.ini a mettre a jour (section LAYER_IMAGES) ; "
                         "un chemin relatif est resolu depuis la racine du depot")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--sheet", action="store_true",
                    help="assemble une planche unique de toutes les couches")
    a = ap.parse_args()

    # Resolu depuis la racine du depot et non depuis le repertoire courant :
    # le script est appelable de n importe ou, y compris via un alias.
    if a.config and not os.path.isabs(a.config):
        a.config = os.path.join(REPO, a.config)

    try:
        with open(a.vial) as f:
            data = json.load(f)
        layers = data["layout"]
    except Exception as e:
        sys.exit(f"Lecture de {a.vial} impossible : {e}")

    if not layers or len(layers[0]) < 8:
        sys.exit("Ce fichier ne ressemble pas a un Corne v4 (matrice 8x7 attendue).")

    os.makedirs(a.out, exist_ok=True)
    names = []
    for i, layer in enumerate(layers):
        flat = [k for row in layer for k in row if isinstance(k, str)]
        if i > 0 and all(k in ("KC_TRNS", "KC_TRANSPARENT", "KC_NO") for k in flat):
            print(f"couche {i} : entierement transparente, ignoree")
            names.append(None)
            continue
        fn = "base.png" if i == 0 else f"layer{i}.png"
        size = render(layer, f"Couche {i}",
                      SUBTITLES.get(i, f"couche {i}"),
                      os.path.join(a.out, fn), a.scale)
        print(f"couche {i} -> {fn}  {size[0]}x{size[1]}")
        names.append(fn)

    if a.sheet:
        rendus = [os.path.join(a.out, n) for n in names if n]
        try:
            ims = [Image.open(f) for f in rendus]
            larg = max(i.width for i in ims)
            haut = sum(i.height for i in ims)
            planche = Image.new("RGB", (larg, haut), BG)
            y = 0
            for i in ims:
                planche.paste(i, (0, y))
                y += i.height
            sp = os.path.join(a.out, "planche-complete.png")
            planche.save(sp)
            print(f"planche -> {sp}  {larg}x{haut}  ({len(ims)} couches)")
        except Exception as e:
            print(f"planche non assemblee : {e}")

    if a.config:
        try:
            import configparser
            cp = configparser.ConfigParser()
            cp.read(a.config)
            if "LAYER_IMAGES" not in cp:
                cp["LAYER_IMAGES"] = {}
            cp["LAYER_IMAGES"].clear()
            for i, fn in enumerate(names):
                cp["LAYER_IMAGES"][f"layer_{i}"] = fn or "base.png"
            with open(a.config, "w") as f:
                cp.write(f)
            print(f"config mis a jour -> {a.config}")
        except Exception as e:
            print(f"config.ini non modifie : {e}")

    if UNRESOLVED:
        print("\nKeycodes non reconnus, affiches en brut :")
        for k in sorted(UNRESOLVED):
            print(f"   {k}")
        print("Signale-les pour que je les ajoute a la table.")
    else:
        print("\nTous les keycodes ont ete resolus.")
    print("\nRedemarre l'overlay pour recharger les images.")


if __name__ == "__main__":
    main()
