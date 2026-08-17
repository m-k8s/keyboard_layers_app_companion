# Personnalisations Corne v4.1 / fr+latin9

Branche `corne-v4-fr-latin9` du fork de `maatthc/keyboard_layers_app_companion`.

Cible : Corne Cherry v4.1 standard (46 touches), firmware Vial de foostan,
Ubuntu 24.04, GNOME 46 sous Wayland, disposition clavier `fr+latin9`.

---

## Commandes courantes

Faire disparaitre l'overlay immediatement :

    systemctl --user stop corne-overlay

Le remettre, voir son etat, suivre ses traces :

    systemctl --user start corne-overlay
    systemctl --user status corne-overlay
    journalctl --user -u corne-overlay -f

Il demarre tout seul a l'ouverture de session. Si le clavier n'est pas branche,
il echoue et retente toutes les 15 secondes : brancher le clavier suffit, il se
rattache seul.

### Modifier le keymap

    systemctl --user stop corne-overlay        # libere l'endpoint raw HID
    # https://vial.rocks : editer, puis Save layout vers ~/Documents/corne-layout-vN.vial
    cd ~/corne/companion
    ./custom/render-overlay.py ~/Documents/corne-layout-vN.vial --config config.ini --sheet
    systemctl --user start corne-overlay

**Un seul processus peut ouvrir l'endpoint raw HID.** Vial et l'overlay ne
peuvent donc pas fonctionner en meme temps : toujours arreter le service avant
d'ouvrir Vial.

A lancer depuis la racine du depot, `--config` etant un chemin relatif.

`--sheet` assemble en plus `assets/planche-complete.png`, la planche unique de
toutes les couches, a imprimer en A4 paysage ou a mettre en fond d'ecran.

### Reflasher le firmware

    cd ~/corne && ./flash-corne.sh              # firmware OSD (notification de couche)
    cd ~/corne && ./flash-corne.sh --rollback   # binaire officiel de foostan

Le script guide en six etapes et attend Entree a chaque manipulation. Pas besoin
de demonter le clavier : maintenir la touche `a` en branchant la moitie gauche,
`p` pour la moitie droite (bootmagic).

**Tout flash par bootmagic efface l'EEPROM**, donc le keymap. Il faut le
recharger ensuite dans Vial via `Load saved layout`. Test le plus rapide pour
verifier : la touche `a` doit taper `a` et non `q`.

### Reglages de l'overlay

Section `[OVERLAY]` de `config.ini`, puis redemarrer le service.

| Cle | Defaut | Effet |
|---|---|---|
| `scale` | `0.55` | taille par rapport aux PNG de 1488x587 |
| `hide_on_layer` | `0` | couche pour laquelle l'overlay reste masque |
| `anchor` | `top` | `top`, `bottom`, ou `auto` (oppose de la fenetre active) |
| `margin_bottom` | `70` | marge en pixels par rapport au bord ancre |
| `always_on_top` | `1` | passage au premier plan |
| `follow_focus` | `1` | suit l'ecran de la fenetre active ; `0` = ecran fixe |
| `monitor_index` | `0` | ecran a utiliser quand `follow_focus = 0`, ordre `xrandr` |

---

## Diagnostic : caracteres manques ou repetitions parasites

**A verifier dans cet ordre. Le cable jack en premier, toujours.**

1. **Remplacer le cable jack entre les deux moities.** C'est la cause la plus
   probable et la moins chere. Sur un clavier scinde, la moitie maitresse
   interroge l'esclave a chaque cycle de balayage : un contact defaillant
   retarde la boucle principale, le balayage devient irregulier et l'anti-rebond
   part en vrille.
2. **Tester chaque moitie seule**, jack debranche, USB branche directement sur
   la moitie testee. Les deux propres en solo confirment la liaison scindee.
3. **Testeur de matrice de Vial** (service arrete). Une case qui clignote
   plusieurs fois pour un seul appui signe un rebond electrique.
4. **Seulement ensuite**, suspecter le firmware : `./flash-corne.sh --rollback`
   remet le binaire officiel de foostan, bit pour bit.

### Ce qui induit en erreur

- Le symptome ressemble beaucoup a un probleme logiciel. Il ne l'est pas.
- **Les deux moities touchees n'innocentent PAS le cable jack.** La maitresse
  traite le clavier entier : si sa boucle est retardee, ses propres touches
  souffrent autant que celles de l'esclave.
- Reinserer le cable ameliore temporairement les choses, ce qui fait croire a
  une reparation. Un contact qui s'ameliore par reinsertion est un contact
  marginal, pas un contact sain.
- Le probleme suit le clavier d'un ordinateur a l'autre, ce qui semble
  disculper le materiel alors que le cable voyage avec lui.

Garder un cable **TRS** de rechange. Le v4.1 fonctionne en half duplex et
attend un TRS, 2 anneaux et 3 conducteurs. Le v4.0 utilisait un TRRS, 3 anneaux.

Ne jamais brancher ni debrancher le jack avec l'USB connecte. C'est le seul
geste qui peut reellement abimer le PCB.

---

## Structure

### Fichiers modifies en amont

- `libs/gui.py` : overlay sans decoration, masque sur la couche de base, suivi
  de la fenetre active, ancrage haut ou bas.
- `config.ini` : section `[OVERLAY]` ajoutee.

### Fichiers ajoutes

- `custom/render-overlay.py` : genere les images de couches depuis un export
  Vial, avec les caracteres reellement produits sous `fr+latin9`.
- `custom/keymaps/*.vial` : source de verite du keymap.
- `custom/systemd/corne-overlay.service` : demarrage automatique.
- `custom/flash-corne.sh` : flash guide des deux moities.

Les images de `assets/` sont **generees** et donc ignorees par git.

### Depot lie : le firmware

La personnalisation du firmware n'est **pas** dans ce depot, pour eviter de
maintenir deux copies du meme changement. Elle vit dans :

    git@github.com:m-k8s/kbd_firmware.git    branche corne-v4_1-layer-notify

Le keymap y emet un paquet raw HID a chaque changement de couche, marqueur
`0x90` a l'octet 24, numero de couche a l'octet 25. Voir le `README.custom.md`
de la branche pour la construction et le flash.

### Reinstaller de zero

    git clone -b corne-v4-fr-latin9 git@github.com:m-k8s/keyboard_layers_app_companion.git companion
    cd companion
    sudo apt-get install -y libhidapi-hidraw0 libhidapi-libusb0
    pipx install pipenv && pipenv install
    ./custom/render-overlay.py custom/keymaps/corne-layout-v3.vial --config config.ini --sheet
    cp custom/systemd/corne-overlay.service ~/.config/systemd/user/
    systemctl --user daemon-reload && systemctl --user enable --now corne-overlay

Le chemin du venv est code en dur dans l'unite systemd et depend du chemin du
dossier : verifier `ExecStart` si le projet est deplace.

**Dependance externe** : l'extension GNOME `focused-window-dbus@flexagoon.com`
doit etre installee et activee, sinon `follow_focus` retombe silencieusement
sur `monitor_index`.

---

## Contraintes Wayland rencontrees

Trois voies pour connaitre la fenetre active ou le pointeur, toutes fermees a un
client ordinaire :

- `_NET_ACTIVE_WINDOW` renvoie `0x0`, X11 ne voit pas les fenetres Wayland.
- `xdotool getmouselocation` renvoie une position **gelee** : Xwayland ne recoit
  les mouvements que lorsque le curseur survole une surface X11.
- `org.gnome.Shell.Introspect.GetWindows` repond `AccessDenied`.

D'ou le recours a `focused-window-dbus`, qui tourne dans GNOME Shell et publie
la geometrie de la fenetre active sur le bus de session.

Attention : l'index de moniteur renvoye par Mutter ne correspond pas a l'ordre
de `xrandr`. Le code se fie aux coordonnees, jamais a l'index.

Deux autres points, decouverts a la dure :

- SDL doit etre force sur X11 (`SDL_VIDEODRIVER=x11`, pose dans `gui.py`). En
  client Wayland natif, le placement et `always_on_top` sont ignores en silence.
- La fenetre ne doit **jamais** etre demappee. Chaque `show()` reveille la
  prevention de vol de focus de Mutter, qui affiche « une fenetre est prete » et
  laisse l'overlay en arriere-plan. Pour disparaitre, elle se reduit a 1x1.

Passer la session en X11 reglerait ces contraintes, mais couterait la mise a
l'echelle par ecran (Wayland uniquement), la gestion des frequences de
rafraichissement mixtes, et l'isolation des entrees entre applications. Sans
compter que GNOME a supprime la session X11 dans sa version 49.

---

## Choix ecarte : le clignotement de touche

Une version du firmware emettait la ligne et la colonne a chaque frappe, pour
faire clignoter la touche dans l'overlay. Abandonne pour deux raisons.

Les chiffres et symboles vivant sur les couches 1 et 2, taper un mot de passe
aurait affiche chaque touche a l'ecran, partage de reunion compris. Et le flux
de frappes brut aurait ete lisible par tout processus capable d'ouvrir
l'endpoint raw HID, soit un keylogger materiel.

Techniquement, l'envoi devait de toute facon sortir du chemin de frappe :
`raw_hid_send` bloque jusqu'a 100 ms, `send_report` utilisant `TIME_MS2I(100)`.
Une variante par tampon circulaire vide depuis `housekeeping_task_user` existe
dans l'historique de la branche firmware si le besoin revient.
