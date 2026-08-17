# Personnalisations Corne v4.1 / fr+latin9

Branche `corne-v4-fr-latin9` du fork de `maatthc/keyboard_layers_app_companion`.

Cible : Corne Cherry v4.1 standard (46 touches), firmware Vial de foostan,
Ubuntu 24.04, GNOME 46 sous Wayland, disposition clavier `fr+latin9`.

## Fichiers modifies en amont

- `libs/gui.py` : overlay sans decoration, masque sur la couche de base,
  suivi de la fenetre active, ancrage haut ou bas.
- `config.ini` : section `[OVERLAY]` ajoutee.

## Fichiers ajoutes

- `render-overlay.py` : genere les images de couches depuis un export Vial,
  avec les caracteres reellement produits sous `fr+latin9`.
- `custom/keymaps/*.vial` : source de verite du keymap.
- `custom/systemd/corne-overlay.service` : demarrage automatique.
- `custom/flash-corne.sh` : flash guide des deux moities.

## Depot lie : le firmware

La personnalisation du firmware n'est **pas** dans ce depot, pour eviter de
maintenir deux copies du meme changement. Elle vit dans :

    git@github.com:m-k8s/kbd_firmware.git    branche corne-v4_1-layer-notify

Le keymap y emet un paquet raw HID a chaque changement de couche, marqueur
`0x90` a l'octet 24, numero de couche a l'octet 25. Voir le
`README.custom.md` de la branche pour la construction et le flash.

Les images de `assets/` sont **generees** et donc ignorees par git.

## Cycle de travail

    systemctl --user stop corne-overlay        # libere l endpoint raw HID
    # edition dans vial.rocks, puis Save layout
    ./render-overlay.py ~/Documents/corne-layout-vN.vial --config config.ini
    systemctl --user start corne-overlay

Ajouter `--sheet` pour assembler en plus une planche unique de toutes les
couches, `assets/planche-complete.png`, a imprimer en A4 paysage ou a mettre
en fond d'ecran.

Un seul processus peut ouvrir l endpoint raw HID : Vial et l overlay ne peuvent
pas fonctionner en meme temps.

## Contraintes Wayland rencontrees

Trois voies pour connaitre la fenetre active ou le pointeur, toutes fermees a
un client ordinaire :

- `_NET_ACTIVE_WINDOW` renvoie `0x0`, X11 ne voit pas les fenetres Wayland.
- `xdotool getmouselocation` renvoie une position **gelee** : Xwayland ne recoit
  les mouvements que lorsque le curseur survole une surface X11.
- `org.gnome.Shell.Introspect.GetWindows` repond `AccessDenied`.

La solution retenue est l extension GNOME **`focused-window-dbus@flexagoon.com`**,
qui publie la geometrie de la fenetre active sur le bus de session. Elle est
donc une **dependance** de cette configuration.

Attention : l index de moniteur renvoye par Mutter ne correspond pas a l ordre
de `xrandr`. Le code se fie aux coordonnees, jamais a l index.

Deux autres points, decouverts a la dure :

- SDL doit etre force sur X11 (`SDL_VIDEODRIVER=x11`). En client Wayland natif,
  le placement et `always_on_top` sont ignores en silence.
- La fenetre ne doit **jamais** etre demappee. Chaque `show()` reveille la
  prevention de vol de focus de Mutter. Pour disparaitre, elle se reduit a 1x1.

## Choix ecarte : le clignotement de touche

Une version du firmware emettait ligne et colonne a chaque frappe, pour faire
clignoter la touche dans l overlay. Abandonne : les chiffres et symboles etant
sur les couches 1 et 2, taper un mot de passe aurait affiche chaque touche a
l ecran, en reunion partagee comprise. Et le flux de frappes brut aurait ete
lisible par tout processus capable d ouvrir l endpoint raw HID.
