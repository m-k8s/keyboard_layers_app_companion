import os
import re
import json
import asyncio
import configparser
import struct
import subprocess
from libs.config import Config

# Config._config_file est un attribut de classe et Config._config un singleton
# charge au premier appel. Le reaffecter ici, au niveau module, redirige la
# configuration de TOUTE l application, y compris keyboard_hid et webserver,
# sans modifier ces fichiers. main.py importe libs.gui avant d instancier quoi
# que ce soit, l ordre est donc garanti.
#
# Repli sur ./config.ini si le fichier externe n existe pas : le comportement
# d origine du projet est preserve.
_EXT_CONFIG = os.environ.get(
    "CORNE_OVERLAY_CONFIG",
    os.path.expanduser("~/.config/corne-overlay/config.ini"),
)
if os.path.isfile(_EXT_CONFIG):
    Config._config_file = _EXT_CONFIG

os.environ["KIVY_NO_ARGS"] = "1"

# Sous Wayland, un client natif ne peut ni se positionner lui-même ni passer
# au premier plan : le protocole ne le permet pas. On force donc SDL sur X11
# pour tourner via Xwayland, ou le placement et _NET_WM_STATE_ABOVE marchent.
os.environ.setdefault("SDL_VIDEODRIVER", "x11")

# --------------------------------------------------------------------------
# A poser AVANT l'import de kivy.core.window : cet import cree la fenêtre.
# --------------------------------------------------------------------------
from kivy.config import Config as KivyConfig  # noqa: E402

KivyConfig.set("graphics", "borderless", "1")
KivyConfig.set("graphics", "resizable", "0")
KivyConfig.set("graphics", "position", "custom")
KivyConfig.set("graphics", "always_on_top", "1")
# Cette app n affiche qu une image : aucun fournisseur d entree n est utile.
# probesysfs balaie /dev/input, appelle xinput pour chaque périphérique et
# inonde le journal. On ne garde que la souris.
try:
    for _name, _ in list(KivyConfig.items("input")):
        if _name != "mouse":
            KivyConfig.remove_option("input", _name)
except Exception as _e:
    print(f"[overlay] section input inchangee ({_e})")
KivyConfig.set("input", "mouse", "mouse,disable_multitouch")

from kivy.app import App  # noqa: E402,F401
from kivy.core.window import Window  # noqa: E402
from kivy.uix.image import Image  # noqa: E402,F401


DEFAULTS = {
    "scale": 0.55,
    "hide_on_layer": 0,
    "margin_bottom": 70,
    "always_on_top": 1,
    "follow_focus": 1,       # 0 = écran fixe via monitor_index
    "anchor": "bottom",      # bottom | top | auto
    "monitor_index": 0,
    "assets_dir": "",        # vide = ./assets/ a cote de main.py
}


def _read_overlay_conf():
    conf = dict(DEFAULTS)
    try:
        cp = configparser.ConfigParser()
        cp.read(Config._config_file)   # le même fichier que le reste de l app
        if "OVERLAY" in cp:
            s = cp["OVERLAY"]
            conf["scale"] = s.getfloat("scale", DEFAULTS["scale"])
            for k in ("hide_on_layer", "margin_bottom", "always_on_top",
                      "follow_focus", "monitor_index"):
                conf[k] = s.getint(k, DEFAULTS[k])
            conf["anchor"] = s.get("anchor", DEFAULTS["anchor"]).strip().lower()
            conf["assets_dir"] = os.path.expanduser(
                s.get("assets_dir", DEFAULTS["assets_dir"]).strip())
    except Exception as e:
        print(f"[overlay] section OVERLAY ignorée ({e}), valeurs par défaut")
    return conf


def _png_size(path, fallback=(1488, 587)):
    """Dimensions depuis l'en-tete PNG, sans OpenGL ni PIL."""
    try:
        with open(path, "rb") as f:
            head = f.read(24)
        if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
            return fallback
        return struct.unpack(">II", head[16:24])
    except Exception as e:
        print(f"[overlay] taille de {path} illisible ({e})")
        return fallback


_GEOM_RE = re.compile(r"^(\d+)x(\d+)\+(\d+)\+(\d+)$")


def _monitors():
    """[(x, y, w, h, est_primaire)] depuis xrandr, [] si indisponible."""
    mons = []
    try:
        out = subprocess.run(
            ["xrandr", "--current"], capture_output=True, text=True, timeout=3
        ).stdout
        for line in out.splitlines():
            if " connected" not in line:
                continue
            for tok in line.split():
                m = _GEOM_RE.fullmatch(tok)
                if m:
                    w, h, x, y = (int(v) for v in m.groups())
                    mons.append((x, y, w, h, "primary" in line))
                    break
    except Exception as e:
        print(f"[overlay] xrandr indisponible ({e})")
    return mons


def _focused_window():
    """(x, y, largeur, hauteur) de la fenêtre active, ou None.

    Passe par l extension GNOME focused-window-dbus. C est la seule source
    fiable sous Wayland : _NET_ACTIVE_WINDOW vaut 0x0, la position du pointeur
    vue par Xwayland est gelee des que le curseur survole une fenêtre native,
    et org.gnome.Shell.Introspect.GetWindows est refuse aux appelants ordinaires.
    """
    try:
        out = subprocess.run(
            ["gdbus", "call", "--session", "-d", "org.gnome.Shell",
             "-o", "/org/gnome/shell/extensions/FocusedWindow",
             "-m", "org.gnome.shell.extensions.FocusedWindow.Get"],
            capture_output=True, text=True, timeout=3).stdout
        m = re.search(r"\('(.*)',\)", out, re.S)
        if not m:
            return None
        d = json.loads(m.group(1))
        return int(d["x"]), int(d["y"]), int(d["width"]), int(d["height"])
    except Exception as e:
        print(f"[overlay] fenêtre active indetectable ({e})")
        return None


class Gui(App):
    def __init__(self, listener, **kwargs):
        super().__init__(**kwargs)
        self.conf = Config()
        self.listener = listener
        self.ov = _read_overlay_conf()
        self._visible = False
        self._size = (0, 0)
        self._img_size = (1488, 587)
        self._monitors = []

    def _image(self, layer):
        """Chemin de l image d une couche, dans assets_dir ou a défaut ./assets/."""
        d = self.ov["assets_dir"] or os.path.join(os.getcwd(), "assets")
        return os.path.join(d, self.conf.layers[layer])

    def _pick_monitor(self):
        """(écran, rectangle de la fenêtre active ou None).

        L écran est celui qui contient le centre de la fenêtre active. On se fie
        aux coordonnees et jamais a l index renvoye par Mutter : son ordre ne
        correspond pas a celui de xrandr.
        """
        if not self._monitors:
            self._monitors = _monitors()
        mons = self._monitors
        if not mons:
            return None, None

        win = None
        if self.ov["follow_focus"]:
            win = _focused_window()
            if win:
                cx, cy = win[0] + win[2] // 2, win[1] + win[3] // 2
                for attempt in (0, 1):
                    for m in mons:
                        x, y, w, h, _ = m
                        if x <= cx < x + w and y <= cy < y + h:
                            return m, win
                    if attempt == 0:      # ecrans peut-être reconfigures
                        self._monitors = _monitors() or mons
                        mons = self._monitors

        idx = self.ov["monitor_index"]
        if 0 <= idx < len(mons):
            return mons[idx], win
        for m in mons:
            if m[4]:
                return m, win
        return mons[0], win

    def _place(self):
        iw, ih = self._img_size
        w = max(200, int(iw * self.ov["scale"]))
        h = max(100, int(ih * self.ov["scale"]))
        mon, win = self._pick_monitor()
        if not mon:
            self._size = (w, h)
            Window.size = (w, h)
            Window.left, Window.top = 80, 80
            print(f"[overlay] {w}x{h} en (80,80), écran non détecté")
            return

        mx, my, mw, mh, _ = mon
        margin = self.ov["margin_bottom"]
        left = mx + max(0, (mw - w) // 2)
        top_pos = my + margin
        bottom_pos = my + max(0, mh - h - margin)

        anchor = self.ov["anchor"]
        if anchor == "auto":
            # On se place a l oppose du centre vertical de la fenêtre active :
            # si elle occupe le bas de l écran, l overlay monte, et inversement.
            anchor = "bottom"
            if win:
                wcy = win[1] + win[3] // 2
                if wcy > my + mh // 2:
                    anchor = "top"
        top = top_pos if anchor == "top" else bottom_pos

        self._size = (w, h)
        Window.size = (w, h)
        Window.left = left
        Window.top = top
        print(f"[overlay] {w}x{h} en ({left},{top}) ancre={anchor} "
              f"écran {mw}x{mh}+{mx}+{my}")

    # ------------------------------------------------------------------- kivy
    def build(self):
        self.title = "Corne layer overlay"
        self._img_size = _png_size(self._image(0), self._img_size)
        self.img = Image(source=self._image(0), allow_stretch=True)
        self._place()
        return self.img

    def on_start(self):
        self._hide(force=True)
        asyncio.create_task(self.updateLayer())

    # -------------------------------------------------------------- affichage
    def _hide(self, force=False):
        if not self._visible and not force:
            return
        try:
            Window.size = (1, 1)
        except Exception as e:
            print(f"[overlay] reduction impossible ({e})")
        self._visible = False

    def _show(self):
        if self._visible:
            return
        try:
            self._place()      # le WM a pu repositionner, et l'écran a pu changer
        except Exception as e:
            print(f"[overlay] agrandissement impossible ({e})")
        self._visible = True

    def _apply_layer(self, layer):
        if layer == self.ov["hide_on_layer"]:
            self._hide()
            return
        if layer < 0 or layer >= len(self.conf.layers):
            print(f"[overlay] couche {layer} absente de config.ini, ignorée")
            return
        self.img.source = self._image(layer)
        self._show()

    # ------------------------------------------------------------------ boucle
    async def updateLayer(self, dt=None):
        while True:
            try:
                layer = self.listener.notify_changes()
                if layer is not None:
                    self._apply_layer(layer)
                await asyncio.sleep(0.05)
            except Exception as e:
                print(f"Error: {e}")
                await asyncio.sleep(0.5)

    def on_stop(self, **kwargs):
        print("App closing..")
        super().on_stop(**kwargs)

    async def start(self):
        await super().async_run()
