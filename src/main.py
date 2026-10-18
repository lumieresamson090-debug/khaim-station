import csv
import os
import sqlite3
import traceback
from datetime import datetime

import flet as ft

# ==========================================
# CONFIGURATION
# ==========================================
APP_NOM = "K-HAIM KALEMIE"
SOUS_TITRE = "Station-service"
PIN_PAR_DEFAUT = "1234"  # modifiable ensuite dans l'application (Réglages)
CARBURANTS = ["Essence", "Diesel"]
TITRES = ["Ventes", "Stock", "Pompes", "Rapports"]


class Couleurs:
    DARK_BLUE = "#0B1B36"
    YELLOW = "#FFC107"
    WHITE = "#FFFFFF"
    GREEN = "#2E9D5B"
    RED = "#D64545"
    ORANGE = "#F28C28"
    TEXT_GRAY = "#6C757D"
    BG_GRAY = "#F4F6FA"
    GRIS_CLAIR = "#E9ECF2"
    LIGHT_BLUE = "#E0E7FF"
    ALERTE_BG = "#FDECEA"


# (fond, texte) pour chaque carburant
COULEUR_CARBURANT = {
    "Essence": (Couleurs.YELLOW, Couleurs.DARK_BLUE),
    "Diesel": (Couleurs.DARK_BLUE, Couleurs.WHITE),
}


# ==========================================
# OUTILS
# ==========================================
def dossier_donnees():
    """Dossier où la base est conservée (privé à l'app sur Android)."""
    base = os.getenv("FLET_APP_STORAGE_DATA")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".khaim_station")
    os.makedirs(base, exist_ok=True)
    return base


def fmt_nombre(valeur, decimales=0):
    texte = f"{float(valeur):,.{decimales}f}"
    return texte.replace(",", " ").replace(".", ",")


def fmt_fc(valeur):
    return f"{fmt_nombre(valeur, 0)} FC"


def fmt_litres(valeur):
    valeur = float(valeur)
    decimales = 0 if valeur.is_integer() else 1
    return f"{fmt_nombre(valeur, decimales)} L"


def fmt_saisie(valeur):
    valeur = float(valeur)
    return str(int(valeur)) if valeur.is_integer() else str(valeur)


def lire_nombre(texte):
    """Lit un nombre saisi (accepte la virgule). Lève ValueError si invalide."""
    return float((texte or "").strip().replace(" ", "").replace(",", "."))


def date_courte(iso):
    try:
        return datetime.strptime(iso, "%Y-%m-%d %H:%M:%S").strftime("%d/%m %H:%M")
    except (ValueError, TypeError):
        return str(iso)


def date_longue(iso):
    try:
        return datetime.strptime(iso, "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y à %H:%M")
    except (ValueError, TypeError):
        return str(iso)


def texte_rapport(cl, ventes):
    lignes = [
        f"{APP_NOM} - {SOUS_TITRE.upper()}",
        "RAPPORT DE CLOTURE",
        f"Date : {date_longue(cl['date'])}",
        "",
    ]
    for v in ventes:
        _, date, pompe, carburant, litres, prix, montant = v
        lignes.append(f"{date_courte(date)} | {pompe} | {carburant} | {fmt_litres(litres)} x {fmt_nombre(prix)} = {fmt_fc(montant)}")
    lignes += [
        "",
        f"Essence : {fmt_litres(cl['litres_essence'])} - {fmt_fc(cl['recette_essence'])}",
        f"Diesel : {fmt_litres(cl['litres_diesel'])} - {fmt_fc(cl['recette_diesel'])}",
        f"Nombre de ventes : {cl['nb_ventes']}",
        f"RECETTE TOTALE : {fmt_fc(cl['recette'])}",
    ]
    return "\n".join(lignes)


def exporter_csv(cl, ventes):
    """Écrit le rapport en CSV. Retourne le chemin du fichier, ou None en cas d'échec."""
    candidats = []
    if os.path.exists("/storage/emulated/0/Download"):
        candidats.append("/storage/emulated/0/Download/K-HAIM_Rapports")
    telechargements = os.path.join(os.path.expanduser("~"), "Downloads")
    if os.path.isdir(telechargements):
        candidats.append(os.path.join(telechargements, "K-HAIM_Rapports"))
    candidats.append(os.path.join(dossier_donnees(), "exports"))

    try:
        horodatage = datetime.strptime(cl["date"], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d_%H-%M")
    except ValueError:
        horodatage = str(cl["id"])
    nom_fichier = f"K-HAIM_Kalemie_Rapport_{horodatage}.csv"

    for dossier in candidats:
        try:
            os.makedirs(dossier, exist_ok=True)
            chemin = os.path.join(dossier, nom_fichier)
            with open(chemin, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow([f"{APP_NOM} - {SOUS_TITRE.upper()}"])
                w.writerow(["RAPPORT DE CLOTURE"])
                w.writerow([f"Date : {date_longue(cl['date'])}"])
                w.writerow([])
                w.writerow(["Date/Heure", "Pompe", "Carburant", "Litres", "Prix unitaire (FC)", "Montant (FC)"])
                for v in ventes:
                    _, date, pompe, carburant, litres, prix, montant = v
                    w.writerow([date, pompe, carburant, litres, prix, montant])
                w.writerow([])
                w.writerow(["RESUME"])
                w.writerow(["Essence vendue (L)", cl["litres_essence"], "Recette essence (FC)", cl["recette_essence"]])
                w.writerow(["Diesel vendu (L)", cl["litres_diesel"], "Recette diesel (FC)", cl["recette_diesel"]])
                w.writerow(["Nombre de ventes", cl["nb_ventes"]])
                w.writerow(["RECETTE TOTALE (FC)", cl["recette"]])
                w.writerow([])
                w.writerow(["Signature du gérant : ____________________"])
            return chemin
        except OSError:
            continue
    return None


# ==========================================
# BASE DE DONNÉES
# ==========================================
class BaseDeDonnees:
    def __init__(self):
        chemin = os.path.join(dossier_donnees(), "khaim_kalemie.db")
        self.conn = sqlite3.connect(chemin, check_same_thread=False)
        self.cur = self.conn.cursor()
        self.creer_tables()
        self.initialiser()

    def creer_tables(self):
        self.cur.execute(
            """CREATE TABLE IF NOT EXISTS pompes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nom_pompe TEXT NOT NULL,
                type_carburant TEXT NOT NULL,
                statut TEXT DEFAULT 'En service')"""
        )
        self.cur.execute(
            """CREATE TABLE IF NOT EXISTS stock (
                type_carburant TEXT PRIMARY KEY,
                quantite_litres REAL DEFAULT 0)"""
        )
        self.cur.execute(
            """CREATE TABLE IF NOT EXISTS ventes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pompe_id INTEGER,
                type_carburant TEXT,
                litres_vendus REAL,
                prix_unitaire REAL,
                montant_fc REAL,
                date_vente TEXT,
                statut TEXT DEFAULT 'Valide',
                cloture_id INTEGER,
                FOREIGN KEY(pompe_id) REFERENCES pompes(id))"""
        )
        self.cur.execute(
            """CREATE TABLE IF NOT EXISTS mouvements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type_carburant TEXT,
                litres REAL,
                motif TEXT,
                date_mouvement TEXT)"""
        )
        self.cur.execute(
            """CREATE TABLE IF NOT EXISTS clotures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date_cloture TEXT,
                nb_ventes INTEGER,
                litres_essence REAL,
                litres_diesel REAL,
                recette_essence REAL,
                recette_diesel REAL,
                recette_totale REAL)"""
        )
        self.cur.execute("CREATE TABLE IF NOT EXISTS parametres (cle TEXT PRIMARY KEY, valeur TEXT)")
        self.conn.commit()

    def initialiser(self):
        self.cur.execute("SELECT COUNT(*) FROM pompes")
        if self.cur.fetchone()[0] == 0:
            self.cur.executemany(
                "INSERT INTO pompes (nom_pompe, type_carburant, statut) VALUES (?, ?, ?)",
                [
                    ("Pompe 1 - Essence", "Essence", "En service"),
                    ("Pompe 2 - Essence", "Essence", "En service"),
                    ("Pompe 3 - Diesel", "Diesel", "En service"),
                    ("Pompe 4 - Diesel", "Diesel", "En panne"),
                ],
            )
        self.cur.execute("SELECT COUNT(*) FROM stock")
        if self.cur.fetchone()[0] == 0:
            self.cur.executemany(
                "INSERT INTO stock (type_carburant, quantite_litres) VALUES (?, ?)",
                [("Essence", 10000.0), ("Diesel", 10000.0)],
            )
        for cle, valeur in [("prix_Essence", "3000"), ("prix_Diesel", "3000"), ("seuil_stock_bas", "1000")]:
            self.cur.execute("INSERT OR IGNORE INTO parametres (cle, valeur) VALUES (?, ?)", (cle, valeur))
        self.conn.commit()

    # ---- paramètres
    def get_param(self, cle, defaut=None):
        self.cur.execute("SELECT valeur FROM parametres WHERE cle = ?", (cle,))
        ligne = self.cur.fetchone()
        return ligne[0] if ligne else defaut

    def set_param(self, cle, valeur):
        self.cur.execute("INSERT OR REPLACE INTO parametres (cle, valeur) VALUES (?, ?)", (cle, str(valeur)))
        self.conn.commit()

    def get_prix(self):
        return {c: float(self.get_param(f"prix_{c}", "3000")) for c in CARBURANTS}

    def get_seuil(self):
        return float(self.get_param("seuil_stock_bas", "1000"))

    def set_reglages(self, prix, seuil):
        for carburant, valeur in prix.items():
            self.set_param(f"prix_{carburant}", valeur)
        self.set_param("seuil_stock_bas", seuil)

    # ---- stock
    def get_stock(self):
        self.cur.execute("SELECT type_carburant, quantite_litres FROM stock")
        return {c: q for c, q in self.cur.fetchall()}

    def mouvement_stock(self, carburant, litres, motif):
        maintenant = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.cur.execute(
            "UPDATE stock SET quantite_litres = quantite_litres + ? WHERE type_carburant = ?", (litres, carburant)
        )
        self.cur.execute(
            "INSERT INTO mouvements (type_carburant, litres, motif, date_mouvement) VALUES (?, ?, ?, ?)",
            (carburant, litres, motif, maintenant),
        )
        self.conn.commit()

    def ajuster_stock(self, carburant, nouvelle_quantite):
        actuel = self.get_stock().get(carburant, 0.0)
        difference = nouvelle_quantite - actuel
        if difference != 0:
            self.mouvement_stock(carburant, difference, "Ajustement")
        return difference

    def mouvements(self, limite=20):
        self.cur.execute(
            "SELECT date_mouvement, type_carburant, litres, motif FROM mouvements ORDER BY id DESC LIMIT ?",
            (limite,),
        )
        return self.cur.fetchall()

    # ---- pompes
    def get_pompes(self):
        self.cur.execute("SELECT id, nom_pompe, type_carburant, statut FROM pompes ORDER BY id")
        return self.cur.fetchall()

    def ajouter_pompe(self, nom, carburant):
        self.cur.execute(
            "INSERT INTO pompes (nom_pompe, type_carburant, statut) VALUES (?, ?, 'En service')", (nom, carburant)
        )
        self.conn.commit()

    def changer_statut_pompe(self, pompe_id, statut):
        self.cur.execute("UPDATE pompes SET statut = ? WHERE id = ?", (statut, pompe_id))
        self.conn.commit()

    # ---- ventes
    def enregistrer_vente(self, pompe_id, litres, prix):
        if litres <= 0 or prix <= 0:
            return False, 0, "Les litres et le prix doivent être supérieurs à zéro."
        self.cur.execute("SELECT nom_pompe, type_carburant, statut FROM pompes WHERE id = ?", (pompe_id,))
        pompe = self.cur.fetchone()
        if not pompe:
            return False, 0, "Pompe introuvable."
        nom, carburant, statut = pompe
        if statut != "En service":
            return False, 0, f"{nom} est en panne."
        stock = self.get_stock().get(carburant, 0.0)
        if stock < litres:
            return False, 0, f"Stock insuffisant ({fmt_litres(stock)} disponibles)."
        montant = round(litres * prix, 2)
        maintenant = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            self.cur.execute(
                "UPDATE stock SET quantite_litres = quantite_litres - ? WHERE type_carburant = ?", (litres, carburant)
            )
            self.cur.execute(
                """INSERT INTO ventes
                   (pompe_id, type_carburant, litres_vendus, prix_unitaire, montant_fc, date_vente)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (pompe_id, carburant, litres, prix, montant, maintenant),
            )
            self.conn.commit()
        except sqlite3.Error as erreur:
            self.conn.rollback()
            return False, 0, f"Erreur : {erreur}"
        return True, montant, "Vente enregistrée"

    def annuler_vente(self, vente_id):
        self.cur.execute(
            "SELECT type_carburant, litres_vendus FROM ventes WHERE id = ? AND statut = 'Valide' AND cloture_id IS NULL",
            (vente_id,),
        )
        vente = self.cur.fetchone()
        if not vente:
            return False, "Cette vente ne peut plus être annulée."
        carburant, litres = vente
        maintenant = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            self.cur.execute("UPDATE ventes SET statut = 'Annulée' WHERE id = ?", (vente_id,))
            self.cur.execute(
                "UPDATE stock SET quantite_litres = quantite_litres + ? WHERE type_carburant = ?", (litres, carburant)
            )
            self.cur.execute(
                "INSERT INTO mouvements (type_carburant, litres, motif, date_mouvement) VALUES (?, ?, ?, ?)",
                (carburant, litres, "Annulation de vente", maintenant),
            )
            self.conn.commit()
        except sqlite3.Error as erreur:
            self.conn.rollback()
            return False, f"Erreur : {erreur}"
        return True, "Vente annulée, litres remis en stock"

    def ventes_ouvertes(self, limite=15):
        self.cur.execute(
            """SELECT v.id, v.date_vente, p.nom_pompe, v.type_carburant, v.litres_vendus, v.prix_unitaire, v.montant_fc
               FROM ventes v JOIN pompes p ON p.id = v.pompe_id
               WHERE v.cloture_id IS NULL AND v.statut = 'Valide'
               ORDER BY v.id DESC LIMIT ?""",
            (limite,),
        )
        return self.cur.fetchall()

    def ventes_de_cloture(self, cloture_id):
        self.cur.execute(
            """SELECT v.id, v.date_vente, p.nom_pompe, v.type_carburant, v.litres_vendus, v.prix_unitaire, v.montant_fc
               FROM ventes v JOIN pompes p ON p.id = v.pompe_id
               WHERE v.cloture_id = ? AND v.statut = 'Valide'
               ORDER BY v.date_vente""",
            (cloture_id,),
        )
        return self.cur.fetchall()

    def totaux_ouverts(self):
        resultat = {c: {"nb": 0, "litres": 0.0, "montant": 0.0} for c in CARBURANTS}
        self.cur.execute(
            """SELECT type_carburant, COUNT(*), COALESCE(SUM(litres_vendus), 0), COALESCE(SUM(montant_fc), 0)
               FROM ventes WHERE cloture_id IS NULL AND statut = 'Valide' GROUP BY type_carburant"""
        )
        for carburant, nb, litres, montant in self.cur.fetchall():
            resultat[carburant] = {"nb": nb, "litres": litres, "montant": montant}
        return resultat

    # ---- clôtures
    def cloturer(self):
        totaux = self.totaux_ouverts()
        nb = sum(t["nb"] for t in totaux.values())
        if nb == 0:
            return False, "Aucune vente à clôturer.", None
        maintenant = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            self.cur.execute(
                """INSERT INTO clotures
                   (date_cloture, nb_ventes, litres_essence, litres_diesel,
                    recette_essence, recette_diesel, recette_totale)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    maintenant, nb,
                    totaux["Essence"]["litres"], totaux["Diesel"]["litres"],
                    totaux["Essence"]["montant"], totaux["Diesel"]["montant"],
                    sum(t["montant"] for t in totaux.values()),
                ),
            )
            cloture_id = self.cur.lastrowid
            self.cur.execute("UPDATE ventes SET cloture_id = ? WHERE cloture_id IS NULL", (cloture_id,))
            self.conn.commit()
        except sqlite3.Error as erreur:
            self.conn.rollback()
            return False, f"Erreur : {erreur}", None
        return True, "Journée clôturée", cloture_id

    @staticmethod
    def _cloture_dict(ligne):
        return {
            "id": ligne[0], "date": ligne[1], "nb_ventes": ligne[2],
            "litres_essence": ligne[3], "litres_diesel": ligne[4],
            "recette_essence": ligne[5], "recette_diesel": ligne[6], "recette": ligne[7],
        }

    def get_cloture(self, cloture_id):
        self.cur.execute(
            """SELECT id, date_cloture, nb_ventes, litres_essence, litres_diesel,
                      recette_essence, recette_diesel, recette_totale FROM clotures WHERE id = ?""",
            (cloture_id,),
        )
        ligne = self.cur.fetchone()
        return self._cloture_dict(ligne) if ligne else None

    def clotures(self, limite=30):
        self.cur.execute(
            """SELECT id, date_cloture, nb_ventes, litres_essence, litres_diesel,
                      recette_essence, recette_diesel, recette_totale
               FROM clotures ORDER BY id DESC LIMIT ?""",
            (limite,),
        )
        return [self._cloture_dict(l) for l in self.cur.fetchall()]


# ==========================================
# APPLICATION
# ==========================================
def main_app(page: ft.Page):
    page.title = "K-HAIM KALEMIE - Station-service"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = Couleurs.DARK_BLUE
    page.padding = 0

    db = BaseDeDonnees()
    etat = {"onglet": 0}
    ui = {"corps": None, "sous_titre": None}

    def ic(nom):
        """Icône par son nom, avec une icône de secours si le nom n'existe pas."""
        return getattr(ft.Icons, nom, ft.Icons.CIRCLE)

    # ---------- composants communs ----------
    def notifier(message, couleur=Couleurs.GREEN):
        page.open(ft.SnackBar(ft.Text(message), bgcolor=couleur))
        page.update()

    def carte(contenu, **kw):
        return ft.Container(
            content=contenu,
            bgcolor=Couleurs.WHITE,
            border_radius=12,
            padding=14,
            shadow=ft.BoxShadow(blur_radius=6, color=ft.Colors.with_opacity(0.06, "black")),
            **kw,
        )

    def pastille(texte, couleur):
        return ft.Container(
            content=ft.Text(texte, size=10, color=Couleurs.WHITE, weight=ft.FontWeight.BOLD),
            bgcolor=couleur,
            padding=ft.padding.symmetric(horizontal=8, vertical=4),
            border_radius=6,
        )

    def titre_section(texte):
        return ft.Text(texte, size=15, weight=ft.FontWeight.BOLD, color=Couleurs.DARK_BLUE)

    def bouton(texte, icone, couleur, action, texte_sombre=False, **kw):
        return ft.ElevatedButton(
            texte, icon=icone, on_click=action,
            bgcolor=couleur,
            color=Couleurs.DARK_BLUE if texte_sombre else Couleurs.WHITE,
            height=48,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=10),
                text_style=ft.TextStyle(weight=ft.FontWeight.BOLD),
            ),
            **kw,
        )

    def confirmer(titre, message, action, libelle="Confirmer", couleur=Couleurs.RED):
        def oui(e):
            page.close(dlg)
            action()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(titre),
            content=ft.Text(message),
            actions=[
                ft.TextButton("Annuler", on_click=lambda e: page.close(dlg)),
                ft.ElevatedButton(libelle, bgcolor=couleur, color=Couleurs.WHITE, on_click=oui),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.open(dlg)

    def dialogue_export(titre, cl, ventes, chemin):
        def copier(e):
            page.set_clipboard(texte_rapport(cl, ventes))
            notifier("Rapport copié : collez-le dans WhatsApp ou un e-mail")

        contenu = [
            ft.Text(f"Recette : {fmt_fc(cl['recette'])}", size=16, weight=ft.FontWeight.BOLD, color=Couleurs.DARK_BLUE),
            ft.Text(f"{cl['nb_ventes']} vente(s) • {date_longue(cl['date'])}", size=12, color=Couleurs.TEXT_GRAY),
        ]
        if chemin:
            contenu += [
                ft.Text("Fichier enregistré dans :", size=13),
                ft.Container(
                    bgcolor=Couleurs.LIGHT_BLUE, border_radius=8, padding=10,
                    content=ft.Text(chemin, size=11, color=Couleurs.DARK_BLUE, selectable=True),
                ),
            ]
        else:
            contenu.append(ft.Text(
                "Le fichier n'a pas pu être enregistré sur ce téléphone. Utilisez « Copier le rapport ».",
                size=12, color=Couleurs.RED,
            ))
        dlg = ft.AlertDialog(
            title=ft.Text(titre),
            content=ft.Column(contenu, tight=True, spacing=8),
            actions=[
                ft.TextButton("Copier le rapport", on_click=copier),
                ft.ElevatedButton("OK", bgcolor=Couleurs.YELLOW, color=Couleurs.DARK_BLUE, on_click=lambda e: page.close(dlg)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.open(dlg)

    # ==========================================
    # ONGLET 1 : VENTES
    # ==========================================
    def construire_ventes():
        corps = ui["corps"]
        prix = db.get_prix()
        pompes_actives = [p for p in db.get_pompes() if p[3] == "En service"]

        dd_pompe = ft.Dropdown(
            label="Pompe", border_radius=10, bgcolor=Couleurs.WHITE,
            options=[ft.dropdown.Option(key=str(p[0]), text=f"{p[1]}") for p in pompes_actives],
        )
        f_litres = ft.TextField(
            label="Litres vendus", keyboard_type=ft.KeyboardType.NUMBER,
            border_radius=10, bgcolor=Couleurs.WHITE, suffix_text="L",
        )
        f_prix = ft.TextField(
            label="Prix du litre", keyboard_type=ft.KeyboardType.NUMBER,
            border_radius=10, bgcolor=Couleurs.WHITE, suffix_text="FC",
        )
        txt_montant = ft.Text("Montant : 0 FC", size=18, weight=ft.FontWeight.BOLD, color=Couleurs.DARK_BLUE)
        zone_dash = ft.Column(spacing=12)
        zone_hist = ft.Column(spacing=8)

        def maj_montant(e=None):
            try:
                montant = lire_nombre(f_litres.value) * lire_nombre(f_prix.value)
            except ValueError:
                montant = 0
            txt_montant.value = f"Montant : {fmt_fc(montant)}"
            page.update()

        def sur_pompe(e):
            pompe = next((p for p in pompes_actives if str(p[0]) == dd_pompe.value), None)
            if pompe:
                f_prix.value = fmt_saisie(prix[pompe[2]])
            maj_montant()

        dd_pompe.on_change = sur_pompe
        f_litres.on_change = maj_montant
        f_prix.on_change = maj_montant

        def annuler(vente_id):
            ok, message = db.annuler_vente(vente_id)
            maj()
            notifier(message, Couleurs.GREEN if ok else Couleurs.RED)

        def carte_vente(v):
            vente_id, date, pompe, carburant, litres, prix_u, montant = v
            return carte(ft.Row([
                ft.Column(
                    [
                        ft.Text(f"{carburant} • {fmt_litres(litres)}", weight=ft.FontWeight.BOLD, color=Couleurs.DARK_BLUE),
                        ft.Text(f"{pompe} • {date_courte(date)}", size=11, color=Couleurs.TEXT_GRAY),
                        ft.Text(f"{fmt_nombre(prix_u)} FC / litre", size=11, color=Couleurs.TEXT_GRAY),
                    ],
                    spacing=2, expand=True,
                ),
                ft.Text(fmt_fc(montant), weight=ft.FontWeight.BOLD, color=Couleurs.GREEN),
                ft.IconButton(
                    ic("UNDO"), icon_color=Couleurs.RED, tooltip="Annuler la vente",
                    on_click=lambda e, i=vente_id, l=litres, m=montant: confirmer(
                        "Annuler cette vente",
                        f"Annuler la vente de {fmt_litres(l)} ({fmt_fc(m)}) ? Les litres retournent au stock.",
                        lambda: annuler(i), libelle="Annuler la vente",
                    ),
                ),
            ]))

        def maj():
            stock = db.get_stock()
            seuil = db.get_seuil()
            totaux = db.totaux_ouverts()
            bas = [c for c in CARBURANTS if stock.get(c, 0) <= seuil]

            cartes_stock = []
            for c in CARBURANTS:
                fond, texte = COULEUR_CARBURANT[c]
                lignes = [
                    ft.Text(c, color=texte, weight=ft.FontWeight.BOLD),
                    ft.Text(fmt_litres(stock.get(c, 0)), color=texte, size=20, weight=ft.FontWeight.BOLD),
                ]
                if c in bas:
                    lignes.append(ft.Text(
                        "⚠ Stock bas", size=11, weight=ft.FontWeight.BOLD,
                        color=Couleurs.RED if c == "Essence" else Couleurs.ORANGE,
                    ))
                cartes_stock.append(ft.Container(
                    bgcolor=fond, border_radius=10, padding=15, expand=True,
                    content=ft.Column(lignes, spacing=2),
                ))

            total_fc = sum(t["montant"] for t in totaux.values())
            total_l = sum(t["litres"] for t in totaux.values())
            total_nb = sum(t["nb"] for t in totaux.values())
            carte_jour = carte(ft.Column(
                [
                    ft.Text("Journée en cours", size=13, color=Couleurs.TEXT_GRAY),
                    ft.Text(fmt_fc(total_fc), size=26, weight=ft.FontWeight.BOLD, color=Couleurs.DARK_BLUE),
                    ft.Text(f"{fmt_litres(total_l)} • {total_nb} vente(s)", size=12, color=Couleurs.TEXT_GRAY),
                    ft.Divider(height=6),
                    ft.Text(f"Essence : {fmt_litres(totaux['Essence']['litres'])} • {fmt_fc(totaux['Essence']['montant'])}", size=12, color=Couleurs.DARK_BLUE),
                    ft.Text(f"Diesel : {fmt_litres(totaux['Diesel']['litres'])} • {fmt_fc(totaux['Diesel']['montant'])}", size=12, color=Couleurs.DARK_BLUE),
                ],
                spacing=4,
            ))

            controles = []
            if bas:
                controles.append(ft.Container(
                    bgcolor=Couleurs.ALERTE_BG, border_radius=10, padding=10,
                    content=ft.Text(
                        f"⚠ Stock bas : {', '.join(bas)}. Pensez à vous approvisionner.",
                        size=12, color=Couleurs.RED, weight=ft.FontWeight.BOLD,
                    ),
                ))
            controles += [ft.Row(cartes_stock, spacing=10), carte_jour]
            zone_dash.controls = controles

            ventes = db.ventes_ouvertes(15)
            if ventes:
                zone_hist.controls = [carte_vente(v) for v in ventes]
            else:
                zone_hist.controls = [ft.Text("Aucune vente depuis la dernière clôture.", color=Couleurs.TEXT_GRAY)]
            page.update()

        def enregistrer(e):
            if not dd_pompe.value or not f_litres.value or not f_prix.value:
                notifier("Choisissez une pompe, puis saisissez les litres et le prix.", Couleurs.RED)
                return
            try:
                litres = lire_nombre(f_litres.value)
                prix_u = lire_nombre(f_prix.value)
            except ValueError:
                notifier("Nombre invalide.", Couleurs.RED)
                return
            ok, montant, message = db.enregistrer_vente(int(dd_pompe.value), litres, prix_u)
            if not ok:
                notifier(message, Couleurs.RED)
                return
            f_litres.value = ""
            txt_montant.value = "Montant : 0 FC"
            maj()
            notifier(f"Vente enregistrée : {fmt_fc(montant)}")

        if pompes_actives:
            formulaire = ft.Column(
                [
                    titre_section("Nouvelle vente"),
                    dd_pompe, f_litres, f_prix, txt_montant,
                    ft.Row([bouton("Enregistrer la vente", ic("CHECK"), Couleurs.YELLOW, enregistrer, texte_sombre=True, expand=True)]),
                ],
                spacing=10,
            )
        else:
            formulaire = ft.Column([
                titre_section("Nouvelle vente"),
                ft.Text("Aucune pompe en service. Activez une pompe dans l'onglet Pompes.", color=Couleurs.RED),
            ])

        corps.controls.extend([
            zone_dash,
            carte(formulaire),
            titre_section("Dernières ventes"),
            zone_hist,
        ])
        maj()

    # ==========================================
    # ONGLET 2 : STOCK
    # ==========================================
    def ouvrir_livraison(carburant):
        f = ft.TextField(label="Litres reçus", keyboard_type=ft.KeyboardType.NUMBER, suffix_text="L", autofocus=True)

        def valider(e):
            try:
                litres = lire_nombre(f.value)
            except ValueError:
                notifier("Nombre invalide.", Couleurs.RED)
                return
            if litres <= 0:
                notifier("La quantité doit être supérieure à zéro.", Couleurs.RED)
                return
            db.mouvement_stock(carburant, litres, "Livraison")
            page.close(dlg)
            afficher_onglet()
            notifier(f"Stock {carburant} : +{fmt_litres(litres)}")

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Livraison de {carburant}"),
            content=ft.Column([f], tight=True),
            actions=[
                ft.TextButton("Annuler", on_click=lambda e: page.close(dlg)),
                ft.ElevatedButton("Ajouter au stock", bgcolor=Couleurs.YELLOW, color=Couleurs.DARK_BLUE, on_click=valider),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.open(dlg)

    def ouvrir_ajustement(carburant):
        actuel = db.get_stock().get(carburant, 0.0)
        f = ft.TextField(
            label="Quantité réelle mesurée", keyboard_type=ft.KeyboardType.NUMBER,
            suffix_text="L", value=fmt_saisie(actuel), autofocus=True,
        )

        def valider(e):
            try:
                nouvelle = lire_nombre(f.value)
            except ValueError:
                notifier("Nombre invalide.", Couleurs.RED)
                return
            if nouvelle < 0:
                notifier("La quantité ne peut pas être négative.", Couleurs.RED)
                return
            difference = db.ajuster_stock(carburant, nouvelle)
            page.close(dlg)
            afficher_onglet()
            notifier(f"Stock {carburant} ajusté ({'+' if difference > 0 else ''}{fmt_litres(difference)})")

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Ajuster le stock de {carburant}"),
            content=ft.Column(
                [
                    ft.Text(f"Stock actuel : {fmt_litres(actuel)}", size=12, color=Couleurs.TEXT_GRAY),
                    f,
                    ft.Text("Utilisez cette fonction après une mesure de la cuve.", size=11, color=Couleurs.TEXT_GRAY),
                ],
                tight=True, spacing=8,
            ),
            actions=[
                ft.TextButton("Annuler", on_click=lambda e: page.close(dlg)),
                ft.ElevatedButton("Enregistrer", bgcolor=Couleurs.YELLOW, color=Couleurs.DARK_BLUE, on_click=valider),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.open(dlg)

    def construire_stock():
        corps = ui["corps"]
        stock = db.get_stock()
        prix = db.get_prix()
        seuil = db.get_seuil()

        def carte_carburant(c):
            fond, texte = COULEUR_CARBURANT[c]
            quantite = stock.get(c, 0)
            bas = quantite <= seuil
            return carte(ft.Column(
                [
                    ft.Row([
                        ft.Container(
                            content=ft.Icon(ic("WATER_DROP"), color=texte),
                            bgcolor=fond, width=40, height=40, border_radius=20,
                            alignment=ft.alignment.center,
                        ),
                        ft.Column(
                            [
                                ft.Text(c, weight=ft.FontWeight.BOLD, color=Couleurs.DARK_BLUE, size=16),
                                ft.Text(f"{fmt_nombre(prix[c])} FC / litre", size=11, color=Couleurs.TEXT_GRAY),
                            ],
                            spacing=2, expand=True,
                        ),
                        pastille("Stock bas", Couleurs.RED) if bas else pastille("Normal", Couleurs.GREEN),
                    ]),
                    ft.Text(fmt_litres(quantite), size=28, weight=ft.FontWeight.BOLD, color=Couleurs.DARK_BLUE),
                    ft.Text(f"Valeur estimée : {fmt_fc(quantite * prix[c])}", size=11, color=Couleurs.TEXT_GRAY),
                    ft.Row([
                        bouton("Livraison", ic("LOCAL_SHIPPING"), Couleurs.GREEN, lambda e, x=c: ouvrir_livraison(x), expand=True),
                        bouton("Ajuster", ic("TUNE"), Couleurs.DARK_BLUE, lambda e, x=c: ouvrir_ajustement(x), expand=True),
                    ], spacing=10),
                ],
                spacing=8,
            ))

        corps.controls.extend([carte_carburant(c) for c in CARBURANTS])
        corps.controls.append(titre_section("Derniers mouvements de stock"))
        mouvements = db.mouvements(20)
        if mouvements:
            for date, carburant, litres, motif in mouvements:
                couleur = Couleurs.GREEN if litres > 0 else Couleurs.RED
                signe = "+" if litres > 0 else ""
                corps.controls.append(carte(ft.Row([
                    ft.Column(
                        [
                            ft.Text(f"{motif} • {carburant}", size=13, weight=ft.FontWeight.BOLD, color=Couleurs.DARK_BLUE),
                            ft.Text(date_courte(date), size=11, color=Couleurs.TEXT_GRAY),
                        ],
                        spacing=2, expand=True,
                    ),
                    ft.Text(f"{signe}{fmt_litres(litres)}", weight=ft.FontWeight.BOLD, color=couleur),
                ])))
        else:
            corps.controls.append(ft.Text("Aucun mouvement enregistré.", color=Couleurs.TEXT_GRAY))

    # ==========================================
    # ONGLET 3 : POMPES
    # ==========================================
    def ouvrir_ajout_pompe(e=None):
        f_nom = ft.TextField(label="Nom de la pompe", capitalization=ft.TextCapitalization.SENTENCES)
        f_type = ft.Dropdown(label="Carburant", options=[ft.dropdown.Option(c) for c in CARBURANTS])

        def valider(ev):
            nom = (f_nom.value or "").strip()
            if not nom or not f_type.value:
                notifier("Saisissez un nom et choisissez le carburant.", Couleurs.RED)
                return
            db.ajouter_pompe(nom, f_type.value)
            page.close(dlg)
            afficher_onglet()
            notifier("Pompe ajoutée")

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Nouvelle pompe"),
            content=ft.Column([f_nom, f_type], tight=True),
            actions=[
                ft.TextButton("Annuler", on_click=lambda ev: page.close(dlg)),
                ft.ElevatedButton("Ajouter", bgcolor=Couleurs.YELLOW, color=Couleurs.DARK_BLUE, on_click=valider),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.open(dlg)

    def construire_pompes():
        corps = ui["corps"]

        def basculer(pompe_id, en_service):
            db.changer_statut_pompe(pompe_id, "En service" if en_service else "En panne")
            afficher_onglet()

        corps.controls.append(
            bouton("Ajouter une pompe", ic("ADD"), Couleurs.YELLOW, ouvrir_ajout_pompe, texte_sombre=True)
        )
        for pompe_id, nom, carburant, statut in db.get_pompes():
            actif = statut == "En service"
            fond, texte = COULEUR_CARBURANT.get(carburant, (Couleurs.DARK_BLUE, Couleurs.WHITE))
            corps.controls.append(carte(ft.Row([
                ft.Container(
                    content=ft.Icon(ic("LOCAL_GAS_STATION"), color=texte),
                    bgcolor=fond, width=40, height=40, border_radius=20,
                    alignment=ft.alignment.center,
                ),
                ft.Column(
                    [
                        ft.Text(nom, weight=ft.FontWeight.BOLD, color=Couleurs.DARK_BLUE),
                        ft.Row([
                            pastille(carburant, fond if carburant == "Diesel" else Couleurs.ORANGE),
                            pastille(statut, Couleurs.GREEN if actif else Couleurs.RED),
                        ], spacing=6),
                    ],
                    spacing=6, expand=True,
                ),
                ft.Switch(
                    value=actif, active_color=Couleurs.GREEN, tooltip="En service / En panne",
                    on_change=lambda ev, i=pompe_id: basculer(i, ev.control.value),
                ),
            ])))

    # ==========================================
    # ONGLET 4 : RAPPORTS
    # ==========================================
    def construire_rapports():
        corps = ui["corps"]
        totaux = db.totaux_ouverts()
        total_fc = sum(t["montant"] for t in totaux.values())
        total_l = sum(t["litres"] for t in totaux.values())
        total_nb = sum(t["nb"] for t in totaux.values())

        def executer_cloture():
            ok, message, cloture_id = db.cloturer()
            if not ok:
                notifier(message, Couleurs.RED)
                return
            cl = db.get_cloture(cloture_id)
            ventes = db.ventes_de_cloture(cloture_id)
            chemin = exporter_csv(cl, ventes)
            afficher_onglet()
            dialogue_export("Journée clôturée", cl, ventes, chemin)

        def demander_cloture(e):
            if total_nb == 0:
                notifier("Aucune vente à clôturer.", Couleurs.RED)
                return
            confirmer(
                "Clôturer la journée ?",
                f"{total_nb} vente(s) • {fmt_fc(total_fc)}.\n"
                "Les ventes seront archivées et les compteurs remis à zéro. "
                "Le stock n'est pas modifié. Un rapport CSV sera créé.",
                executer_cloture, libelle="Clôturer", couleur=Couleurs.GREEN,
            )

        def exporter(cloture_id):
            cl = db.get_cloture(cloture_id)
            ventes = db.ventes_de_cloture(cloture_id)
            dialogue_export("Rapport exporté", cl, ventes, exporter_csv(cl, ventes))

        def copier(cloture_id):
            cl = db.get_cloture(cloture_id)
            ventes = db.ventes_de_cloture(cloture_id)
            page.set_clipboard(texte_rapport(cl, ventes))
            notifier("Rapport copié : collez-le dans WhatsApp ou un e-mail")

        def carte_cloture(cl):
            return carte(ft.Column(
                [
                    ft.Row([
                        ft.Text(date_longue(cl["date"]), weight=ft.FontWeight.BOLD, color=Couleurs.DARK_BLUE, size=13, expand=True),
                        ft.Text(fmt_fc(cl["recette"]), weight=ft.FontWeight.BOLD, color=Couleurs.GREEN),
                    ]),
                    ft.Text(
                        f"{cl['nb_ventes']} vente(s) • Essence {fmt_litres(cl['litres_essence'])} • Diesel {fmt_litres(cl['litres_diesel'])}",
                        size=11, color=Couleurs.TEXT_GRAY,
                    ),
                    ft.Row([
                        bouton("Exporter", ic("DOWNLOAD"), Couleurs.YELLOW, lambda e, i=cl["id"]: exporter(i), texte_sombre=True, expand=True),
                        bouton("Copier", ic("CONTENT_COPY"), Couleurs.DARK_BLUE, lambda e, i=cl["id"]: copier(i), expand=True),
                    ], spacing=10),
                ],
                spacing=8,
            ))

        corps.controls.append(ft.Container(
            bgcolor=Couleurs.DARK_BLUE, border_radius=12, padding=18, alignment=ft.alignment.center,
            content=ft.Column(
                [
                    ft.Text("JOURNÉE EN COURS", size=12, color=Couleurs.WHITE),
                    ft.Text(fmt_fc(total_fc), size=30, weight=ft.FontWeight.BOLD, color=Couleurs.YELLOW),
                    ft.Text(f"{fmt_litres(total_l)} • {total_nb} vente(s)", size=11, color=Couleurs.WHITE),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4,
            ),
        ))
        corps.controls.append(ft.Row([
            bouton("Clôturer la journée", ic("TASK_ALT"), Couleurs.YELLOW, demander_cloture, texte_sombre=True, expand=True)
        ]))
        corps.controls.append(titre_section("Historique des clôtures"))
        historique = db.clotures(30)
        if historique:
            corps.controls.extend([carte_cloture(cl) for cl in historique])
        else:
            corps.controls.append(ft.Text("Aucune clôture pour le moment.", color=Couleurs.TEXT_GRAY))

    # ==========================================
    # RÉGLAGES ET SÉCURITÉ
    # ==========================================
    def ouvrir_changement_pin():
        f_ancien = ft.TextField(label="Ancien PIN", password=True, can_reveal_password=True, keyboard_type=ft.KeyboardType.NUMBER)
        f_nouveau = ft.TextField(label="Nouveau PIN (4 chiffres minimum)", password=True, can_reveal_password=True, keyboard_type=ft.KeyboardType.NUMBER)
        f_confirm = ft.TextField(label="Confirmer le nouveau PIN", password=True, can_reveal_password=True, keyboard_type=ft.KeyboardType.NUMBER)

        def valider(ev):
            if f_ancien.value != db.get_param("pin", PIN_PAR_DEFAUT):
                notifier("Ancien PIN incorrect.", Couleurs.RED)
                return
            nouveau = f_nouveau.value or ""
            if len(nouveau) < 4 or not nouveau.isdigit():
                notifier("Le nouveau PIN doit contenir au moins 4 chiffres.", Couleurs.RED)
                return
            if nouveau != f_confirm.value:
                notifier("Les deux PIN ne correspondent pas.", Couleurs.RED)
                return
            db.set_param("pin", nouveau)
            page.close(dlg)
            notifier("PIN modifié")

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Changer le PIN"),
            content=ft.Column([f_ancien, f_nouveau, f_confirm], tight=True),
            actions=[
                ft.TextButton("Annuler", on_click=lambda ev: page.close(dlg)),
                ft.ElevatedButton("Valider", bgcolor=Couleurs.YELLOW, color=Couleurs.DARK_BLUE, on_click=valider),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.open(dlg)

    def ouvrir_reglages(e=None):
        prix = db.get_prix()
        f_essence = ft.TextField(label="Prix du litre d'essence (FC)", value=fmt_saisie(prix["Essence"]), keyboard_type=ft.KeyboardType.NUMBER)
        f_diesel = ft.TextField(label="Prix du litre de diesel (FC)", value=fmt_saisie(prix["Diesel"]), keyboard_type=ft.KeyboardType.NUMBER)
        f_seuil = ft.TextField(label="Alerte de stock bas (litres)", value=fmt_saisie(db.get_seuil()), keyboard_type=ft.KeyboardType.NUMBER)

        def enregistrer(ev):
            try:
                p_essence = lire_nombre(f_essence.value)
                p_diesel = lire_nombre(f_diesel.value)
                seuil = lire_nombre(f_seuil.value)
            except ValueError:
                notifier("Nombre invalide.", Couleurs.RED)
                return
            if p_essence <= 0 or p_diesel <= 0 or seuil < 0:
                notifier("Les prix doivent être supérieurs à zéro.", Couleurs.RED)
                return
            db.set_reglages({"Essence": p_essence, "Diesel": p_diesel}, seuil)
            page.close(dlg)
            afficher_onglet()
            notifier("Réglages enregistrés")

        def vers_pin(ev):
            page.close(dlg)
            ouvrir_changement_pin()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Réglages"),
            content=ft.Column(
                [f_essence, f_diesel, f_seuil, ft.TextButton("Changer le PIN", icon=ic("KEY"), on_click=vers_pin)],
                tight=True, scroll=ft.ScrollMode.AUTO,
            ),
            actions=[
                ft.TextButton("Annuler", on_click=lambda ev: page.close(dlg)),
                ft.ElevatedButton("Enregistrer", bgcolor=Couleurs.YELLOW, color=Couleurs.DARK_BLUE, on_click=enregistrer),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.open(dlg)

    # ==========================================
    # NAVIGATION
    # ==========================================
    def afficher_onglet():
        corps = ui["corps"]
        corps.controls.clear()
        ui["sous_titre"].value = f"{SOUS_TITRE} • {TITRES[etat['onglet']]}"
        [construire_ventes, construire_stock, construire_pompes, construire_rapports][etat["onglet"]]()
        corps.controls.append(ft.Container(height=20))
        page.update()

    def changer_onglet(e):
        etat["onglet"] = e.control.selected_index
        afficher_onglet()

    def afficher_app():
        page.clean()
        ui["corps"] = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
        ui["sous_titre"] = ft.Text("", size=12, color=Couleurs.YELLOW)

        entete = ft.Container(
            bgcolor=Couleurs.DARK_BLUE,
            padding=ft.padding.only(left=20, right=4, top=8, bottom=14),
            content=ft.Row([
                ft.Column(
                    [ft.Text(APP_NOM, size=20, weight=ft.FontWeight.BOLD, color=Couleurs.WHITE), ui["sous_titre"]],
                    spacing=2, expand=True,
                ),
                ft.IconButton(ic("SETTINGS"), icon_color=Couleurs.YELLOW, tooltip="Réglages", on_click=ouvrir_reglages),
                ft.IconButton(ic("LOCK"), icon_color=Couleurs.YELLOW, tooltip="Verrouiller", on_click=lambda e: afficher_login()),
            ]),
        )
        page.navigation_bar = ft.NavigationBar(
            selected_index=etat["onglet"],
            bgcolor=Couleurs.WHITE,
            on_change=changer_onglet,
            destinations=[
                ft.NavigationBarDestination(icon=ic("SHOPPING_CART"), label="Ventes"),
                ft.NavigationBarDestination(icon=ic("WATER_DROP"), label="Stock"),
                ft.NavigationBarDestination(icon=ic("LOCAL_GAS_STATION"), label="Pompes"),
                ft.NavigationBarDestination(icon=ic("ASSESSMENT"), label="Rapports"),
            ],
        )
        page.add(
            ft.SafeArea(
                expand=True,
                content=ft.Column(
                    [
                        entete,
                        ft.Container(
                            content=ui["corps"], bgcolor=Couleurs.BG_GRAY, expand=True,
                            padding=ft.padding.only(left=16, right=16, top=14),
                        ),
                    ],
                    spacing=0, expand=True,
                ),
            )
        )
        afficher_onglet()

    def afficher_login():
        page.clean()
        page.navigation_bar = None
        pin = ft.TextField(
            label="Code PIN", password=True, can_reveal_password=True,
            keyboard_type=ft.KeyboardType.NUMBER, width=260, text_align=ft.TextAlign.CENTER,
            border_radius=10, filled=True, bgcolor=Couleurs.WHITE, color=Couleurs.DARK_BLUE,
        )

        def valider(e):
            if pin.value == db.get_param("pin", PIN_PAR_DEFAUT):
                afficher_app()
            else:
                pin.value = ""
                pin.error_text = "Code incorrect"
                page.update()

        pin.on_submit = valider
        page.add(
            ft.SafeArea(
                expand=True,
                content=ft.Column(
                    [
                        ft.Icon(ic("LOCAL_GAS_STATION"), size=72, color=Couleurs.YELLOW),
                        ft.Text(APP_NOM, size=26, weight=ft.FontWeight.BOLD, color=Couleurs.WHITE),
                        ft.Text("Gestion de la station-service", size=13, color=Couleurs.WHITE),
                        ft.Container(height=30),
                        pin,
                        ft.Container(height=10),
                        bouton("Ouvrir", ic("LOCK_OPEN"), Couleurs.YELLOW, valider, texte_sombre=True, width=260),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    expand=True,
                ),
            )
        )
        page.update()

    afficher_login()


def main(page: ft.Page):
    try:
        main_app(page)
    except Exception:
        page.add(ft.Text(traceback.format_exc(), selectable=True, color="red"))
        page.update()


ft.app(target=main)

