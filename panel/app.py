import customtkinter as ctk
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import threading
import time
import sys
import os
import io
import contextlib
import requests
from datetime import datetime
from dotenv import load_dotenv

if hasattr(sys, '_MEIPASS'):
    _BASE = os.path.dirname(sys.executable)
    sys.path.insert(0, sys._MEIPASS)
else:
    _BASE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    sys.path.append(_BASE)

load_dotenv(os.path.join(_BASE, ".env"))
from monitor.analizador_alertas import login, obtener_alertas, analizar_alertas, ejecutar_correccion, ACCIONES, CONTENEDORES
from gestor_tickets.cliente_glpi import (login as glpi_login, obtener_tickets_abiertos,
                                          cerrar_tickets_resueltos, logout)
from panel.tema import *

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

def _resource(rel):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, rel)
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", rel))

REFRESCO   = 30
ZABBIX_URL = os.getenv("ZABBIX_URL", "http://localhost:8080/api_jsonrpc.php")
ICON_PATH  = _resource(os.path.join("img", "HealOps Icon.png"))

LOGS = {
    "Alertas reales": "logs/alertas_reales.log",
    "Alertas falsas": "logs/alertas_falsas.log",
    "Corrector":      "logs/corrector.log",
    "Tickets GLPI":   "logs/tickets.log",
}


def obtener_hosts(token):
    return requests.post(ZABBIX_URL, json={
        "jsonrpc": "2.0", "method": "host.get",
        "params": {"output": ["hostid", "host", "status"]},
        "id": 5
    }, headers={"Authorization": f"Bearer {token}"}).json().get("result", [])


# ── Helpers de UI ─────────────────────────────────────────────────────────────

def _card(parent, **kw):
    """Tarjeta blanca con borde sutil y radio grande."""
    defaults = dict(fg_color=BG_CARD, corner_radius=20,
                    border_width=1, border_color=BORDER)
    defaults.update(kw)
    return ctk.CTkFrame(parent, **defaults)


def _label(parent, text, font=None, color=None, **kw):
    return ctk.CTkLabel(parent, text=text,
                        font=font or FONT_BODY,
                        text_color=color or TEXT_MAIN, **kw)



def _pill_btn(parent, text, command, fg=ACCENT, hover=ACCENT_HOVER, width=140, height=36):
    return ctk.CTkButton(parent, text=text, font=FONT_BTN,
                         fg_color=fg, hover_color=hover,
                         text_color="white", corner_radius=100,
                         width=width, height=height, command=command)


def _ghost_btn(parent, text, command, width=130, height=36):
    return ctk.CTkButton(parent, text=text, font=FONT_BTN,
                         fg_color=BG_CARD, hover_color="#F3F3F3",
                         text_color=TEXT_SUB, corner_radius=100,
                         width=width, height=height,
                         border_width=1, border_color=BORDER,
                         command=command)


# ── Ventana de corrección ─────────────────────────────────────────────────────

class VentanaCorreccion(ctk.CTkToplevel):
    def __init__(self, master, host, nombre_alerta):
        super().__init__(master)
        self.title(f"Corregir — {host}")
        self.geometry("700x520")
        self.resizable(False, False)
        self.configure(fg_color=BG_PAGE)
        self.grab_set()

        comando = next((v for k, v in ACCIONES.items() if k in nombre_alerta.lower()), None)
        contenedor = CONTENEDORES.get(host, host)

        _label(self, nombre_alerta, font=FONT_TITLE).pack(anchor="w", padx=24, pady=(24, 2))
        _label(self, f"Host: {host}", font=FONT_MUTED, color=TEXT_SUB).pack(anchor="w", padx=24)

        _label(self, "ACCIÓN A EJECUTAR", font=FONT_LABEL,
               color=TEXT_LIGHT).pack(anchor="w", padx=24, pady=(20, 6))
        cmd_frame = ctk.CTkFrame(self, fg_color="#1E1E1E", corner_radius=8)
        cmd_frame.pack(fill="x", padx=24)
        ctk.CTkLabel(cmd_frame,
                     text=f"docker exec {contenedor} sh -c \"{comando}\"",
                     font=FONT_MONO, text_color="#D4D4D4",
                     wraplength=630, justify="left").pack(padx=14, pady=10, anchor="w")

        _label(self, "OUTPUT", font=FONT_LABEL,
               color=TEXT_LIGHT).pack(anchor="w", padx=24, pady=(16, 6))
        self.output = ctk.CTkTextbox(self, font=FONT_MONO, fg_color="#1E1E1E",
                                     text_color="#D4D4D4", corner_radius=8,
                                     state="disabled")
        self.output.pack(fill="both", expand=True, padx=24, pady=(0, 16))

        btns = ctk.CTkFrame(self, fg_color=BG_PAGE, corner_radius=0)
        btns.pack(fill="x", padx=24, pady=(0, 24))
        self.btn_run = _pill_btn(btns, "Ejecutar corrección",
                                 command=lambda: self._ejecutar(host, nombre_alerta))
        self.btn_run.pack(side="left")
        _ghost_btn(btns, "Cerrar", command=self.destroy).pack(side="left", padx=(10, 0))

    def _ejecutar(self, host, nombre_alerta):
        self.btn_run.configure(text="Ejecutando…", state="disabled", fg_color=TEXT_LIGHT)
        self._append("Iniciando corrección...\n")

        def run():
            try:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    ok = ejecutar_correccion(host, nombre_alerta)
                salida = buf.getvalue().strip()
                if salida:
                    self.after(0, lambda s=salida: self._append(s + "\n"))
                if ok:
                    self.after(0, lambda: self._append("\nCorrecion exitosa.\n"))
                else:
                    self.after(0, lambda: self._append("\nFallo — ticket creado en GLPI.\n"))
            except Exception as e:
                self.after(0, lambda: self._append(f"\nError: {e}\n"))
            finally:
                self.after(0, lambda: self.btn_run.configure(
                    text="Ejecutar corrección", state="normal", fg_color=ACCENT))

        threading.Thread(target=run, daemon=True).start()

    def _append(self, text):
        self.output.configure(state="normal")
        self.output.insert("end", text)
        self.output.see("end")
        self.output.configure(state="disabled")


# ── Ventana de logs ───────────────────────────────────────────────────────────

class VisorLogs(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Logs — HealOps")
        self.geometry("880x620")
        self.configure(fg_color=BG_PAGE)
        self.resizable(True, True)

        header = ctk.CTkFrame(self, fg_color=BG_PAGE, corner_radius=0)
        header.pack(fill="x", padx=28, pady=(24, 0))
        _label(header, "Logs del sistema", font=FONT_HERO).pack(side="left")

        tabs = ctk.CTkTabview(self, fg_color=BG_CARD, corner_radius=16,
                               border_width=1, border_color=BORDER,
                               segmented_button_fg_color=BG_CARD,
                               segmented_button_selected_color=ACCENT,
                               segmented_button_selected_hover_color=ACCENT_HOVER,
                               segmented_button_unselected_color=BG_CARD,
                               segmented_button_unselected_hover_color="#F3F3F3",
                               text_color=TEXT_MAIN,
                               text_color_disabled=TEXT_LIGHT)
        tabs.pack(fill="both", expand=True, padx=28, pady=16)

        for nombre, ruta in LOGS.items():
            tabs.add(nombre)
            txt = ctk.CTkTextbox(tabs.tab(nombre), font=FONT_MONO,
                                  fg_color=BG_CARD, text_color=TEXT_MAIN,
                                  corner_radius=0, border_width=0)
            txt.pack(fill="both", expand=True)
            try:
                with open(ruta, encoding="utf-8") as f:
                    lineas = f.readlines()
                contenido = "".join(reversed(lineas[-200:]))
                txt.insert("end", contenido or "Sin registros aún.")
            except FileNotFoundError:
                txt.insert("end", "Archivo no encontrado todavía.")
            txt.configure(state="disabled")


# ── Ventana de administración ─────────────────────────────────────────────────

class VentanaAdmin(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Administración — HealOps")
        self.geometry("740x560")
        self.configure(fg_color=BG_PAGE)
        self.resizable(False, False)
        self._construir()

    def _construir(self):
        pad = dict(padx=28)

        header = ctk.CTkFrame(self, fg_color=BG_PAGE, corner_radius=0)
        header.pack(fill="x", **pad, pady=(24, 4))
        _label(header, "Administración", font=FONT_HERO).pack(anchor="w")
        _label(header, "Aplicar triggers de monitorización a todos los hosts de Zabbix",
               color=TEXT_SUB).pack(anchor="w", pady=(2, 0))

        ctk.CTkFrame(self, fg_color=BORDER, height=1,
                     corner_radius=0).pack(fill="x", **pad, pady=16)

        c = _card(self)
        c.pack(fill="both", expand=True, **pad, pady=(0, 16))

        self.txt = ctk.CTkTextbox(c, font=FONT_MONO, fg_color=BG_CARD,
                                   text_color=TEXT_MAIN, corner_radius=0,
                                   border_width=0)
        self.txt.pack(fill="both", expand=True, padx=16, pady=16)
        self.txt.insert("end", "Pulsa el botón para aplicar los triggers a todos los hosts.\n")
        self.txt.configure(state="disabled")

        self.btn = _pill_btn(self, "Aplicar triggers a todos los hosts",
                              self._ejecutar, width=0, height=40)
        self.btn.pack(**pad, pady=(0, 24), fill="x")

    def _append(self, texto):
        self.txt.configure(state="normal")
        self.txt.insert("end", texto)
        self.txt.see("end")
        self.txt.configure(state="disabled")

    def _ejecutar(self):
        self.btn.configure(text="Aplicando…", state="disabled",
                            fg_color=TEXT_LIGHT, hover_color=TEXT_LIGHT)
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.configure(state="disabled")

        def _run():
            import subprocess
            script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "..", "setup", "setup_zabbix.py")
            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"
            proc = subprocess.Popen([sys.executable, script],
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT,
                                     text=True, encoding="utf-8",
                                     errors="replace", env=env)
            for linea in proc.stdout:
                self.after(0, lambda l=linea: self._append(l))
            proc.wait()
            self.after(0, lambda: self.btn.configure(
                text="Aplicar triggers a todos los hosts",
                state="normal", fg_color=ACCENT, hover_color=ACCENT_HOVER))

        threading.Thread(target=_run, daemon=True).start()


# ── Tarjeta de host (sidebar) ─────────────────────────────────────────────────

class TarjetaHost(ctk.CTkFrame):
    def __init__(self, parent, nombre, on_click):
        super().__init__(parent, fg_color=BG_CARD, corner_radius=16,
                         border_width=1, border_color=BORDER, cursor="hand2")
        self.nombre    = nombre
        self._on_click = on_click
        self.pack(fill="x", pady=4)

        inner = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        inner.pack(fill="x", padx=16, pady=12)

        top = ctk.CTkFrame(inner, fg_color="transparent", corner_radius=0)
        top.pack(fill="x")

        self.dot = ctk.CTkLabel(top, text="●", font=("Inter", 10), text_color=SUCCESS)
        self.dot.pack(side="left", padx=(0, 8))

        _label(top, nombre, font=FONT_TITLE).pack(side="left")

        self.badge = ctk.CTkLabel(top, text="OK", font=FONT_LABEL,
                                   text_color=SUCCESS,
                                   fg_color=SUCCESS_BG, corner_radius=100,
                                   padx=10, pady=2)
        self.badge.pack(side="right")

        self.lbl_sub = _label(inner, "Sin problemas", font=FONT_MUTED, color=TEXT_LIGHT)
        self.lbl_sub.pack(anchor="w", pady=(3, 0))

        for w in [self, inner, top, self.dot, self.lbl_sub, self.badge]:
            w.bind("<Button-1>", lambda _: self._on_click(self.nombre))

    def set_estado(self, n):
        if n > 0:
            self.configure(border_color=ACCENT_BG)
            self.dot.configure(text_color=ACCENT)
            self.badge.configure(text=f"{n} alerta{'s' if n > 1 else ''}",
                                  text_color=ACCENT, fg_color=ACCENT_BG)
            self.lbl_sub.configure(
                text=f"{n} problema{'s' if n > 1 else ''} activo{'s' if n > 1 else ''}",
                text_color=ACCENT)
        else:
            self.configure(border_color=BORDER)
            self.dot.configure(text_color=SUCCESS)
            self.badge.configure(text="OK", text_color=SUCCESS, fg_color=SUCCESS_BG)
            self.lbl_sub.configure(text="Sin problemas", text_color=TEXT_LIGHT)

    def set_selected(self, sel):
        self.configure(fg_color=ACCENT_BG if sel else BG_CARD,
                        border_color=ACCENT if sel else BORDER)


# ── Tarjeta KPI ───────────────────────────────────────────────────────────────

class TarjetaStat(ctk.CTkFrame):
    def __init__(self, parent, titulo, valor, color, badge_ok=None):
        super().__init__(parent, fg_color=BG_CARD, corner_radius=20,
                          border_width=1, border_color=BORDER)
        self._color = color
        self._badge_ok = badge_ok

        _label(self, titulo.upper(), font=FONT_LABEL,
               color=TEXT_LIGHT).pack(anchor="w", padx=20, pady=(18, 4))

        self.lbl = ctk.CTkLabel(self, text=valor, font=FONT_NUM, text_color=color)
        self.lbl.pack(anchor="w", padx=20, pady=(0, 18))

    def set(self, valor, color=None):
        self.lbl.configure(text=str(valor))
        if color:
            self.lbl.configure(text_color=color)


# ── Panel principal ───────────────────────────────────────────────────────────

class HealOpsPanel(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("HealOps")
        self.geometry("1480x860")
        self.configure(fg_color=BG_PAGE)
        self.resizable(True, True)
        try:
            self._icon_img = ImageTk.PhotoImage(Image.open(ICON_PATH))
            self.iconphoto(True, self._icon_img)
        except Exception as e:
            print(f"[Panel] Icono: {e}")
        self._tarjetas_host    = {}
        self._alertas_por_host = {}
        self._host_seleccionado = None
        self._ultimo_token      = None
        self._estilo_tabla()
        self._construir_ui()
        self._iniciar_actualizacion()

    # ── UI ────────────────────────────────────────────────────

    def _construir_ui(self):
        # ── Navbar ────────────────────────────────────────────
        nav = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0,
                            border_width=0)
        nav.pack(fill="x")

        # borde inferior del nav
        ctk.CTkFrame(self, fg_color=BORDER, height=1,
                     corner_radius=0).pack(fill="x")

        inner_nav = ctk.CTkFrame(nav, fg_color="transparent", corner_radius=0)
        inner_nav.pack(fill="x", padx=32, pady=0)

        # Logo + nombre
        logo_row = ctk.CTkFrame(inner_nav, fg_color="transparent", corner_radius=0)
        logo_row.pack(side="left", pady=10)
        try:
            self._logo = ctk.CTkImage(light_image=Image.open(ICON_PATH), size=(300, 120))
            ctk.CTkLabel(logo_row, image=self._logo, text="").pack(side="left")
        except Exception as e:
            print(f"[Panel] Logo: {e}")

        # Botones derecha
        btns = ctk.CTkFrame(inner_nav, fg_color="transparent", corner_radius=0)
        btns.pack(side="right", pady=10)

        self.label_hora = _label(btns, "", font=FONT_MUTED, color=TEXT_LIGHT)
        self.label_hora.pack(side="left", padx=(0, 20))

        self.btn_analizar = _pill_btn(btns, "Analizar ahora", self._analizar_ahora,
                                       width=148, height=36)
        self.btn_analizar.pack(side="left", padx=(0, 8))

        _ghost_btn(btns, "Administración",
                   lambda: VentanaAdmin(self), width=130, height=36).pack(side="left", padx=(0, 8))

        _ghost_btn(btns, "Ver Logs",
                   lambda: VisorLogs(self), width=100, height=36).pack(side="left")

        # ── KPIs ──────────────────────────────────────────────
        kpi_wrap = ctk.CTkFrame(self, fg_color=BG_PAGE, corner_radius=0)
        kpi_wrap.pack(fill="x", padx=32, pady=(24, 0))

        self.stat_reales      = TarjetaStat(kpi_wrap, "Alertas activas",    "—", ACCENT)
        self.stat_tickets     = TarjetaStat(kpi_wrap, "Tickets abiertos",   "—", INFO)
        self.stat_estado      = TarjetaStat(kpi_wrap, "Hosts con problemas","—", SUCCESS)
        self.stat_correcciones= TarjetaStat(kpi_wrap, "Correcciones hoy",   "—", SUCCESS)

        for stat in [self.stat_reales, self.stat_tickets,
                     self.stat_estado, self.stat_correcciones]:
            stat.pack(side="left", fill="x", expand=True,
                      padx=(0, 12), ipadx=4, pady=0)
        # quitar padx del último
        self.stat_correcciones.pack_configure(padx=0)

        # ── Cuerpo master / detail ────────────────────────────
        cuerpo = ctk.CTkFrame(self, fg_color=BG_PAGE, corner_radius=0)
        cuerpo.pack(fill="both", expand=True, padx=32, pady=24)

        # Sidebar (master)
        sidebar = ctk.CTkFrame(cuerpo, fg_color=BG_PAGE, corner_radius=0, width=290)
        sidebar.pack(side="left", fill="y", padx=(0, 20))
        sidebar.pack_propagate(False)

        _label(sidebar, "Servidores", font=FONT_LABEL,
               color=TEXT_LIGHT).pack(anchor="w", pady=(0, 10))

        self.frame_hosts = ctk.CTkScrollableFrame(
            sidebar, fg_color=BG_PAGE, corner_radius=0,
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=TEXT_LIGHT)
        self.frame_hosts.pack(fill="both", expand=True)

        # Detail
        self.detail = ctk.CTkFrame(cuerpo, fg_color=BG_PAGE, corner_radius=0)
        self.detail.pack(side="left", fill="both", expand=True)

        self._construir_detail_vacio()

    def _construir_detail_vacio(self):
        for w in self.detail.winfo_children():
            w.destroy()
        wrap = ctk.CTkFrame(self.detail, fg_color=BG_PAGE, corner_radius=0)
        wrap.pack(expand=True)
        _label(wrap, "Selecciona un servidor", font=FONT_TITLE).pack()
        _label(wrap, "Haz clic en un host del panel izquierdo para ver su detalle",
               color=TEXT_LIGHT).pack(pady=(4, 0))

    def _construir_detail(self, nombre):
        for w in self.detail.winfo_children():
            w.destroy()

        # Título
        cab = ctk.CTkFrame(self.detail, fg_color=BG_PAGE, corner_radius=0)
        cab.pack(fill="x", pady=(0, 16))
        _label(cab, nombre, font=FONT_HERO).pack(side="left")

        # Fila 1: Alertas (ancho completo)
        c_alertas = _card(self.detail)
        c_alertas.pack(fill="x", pady=(0, 12))
        self._seccion(c_alertas, "Alertas activas")
        self.frame_alertas = ctk.CTkScrollableFrame(
            c_alertas, fg_color=BG_CARD, corner_radius=0, height=150,
            scrollbar_button_color=BORDER, scrollbar_button_hover_color=TEXT_LIGHT)
        self.frame_alertas.pack(fill="x", padx=16, pady=(8, 16))

        # Fila 2: Tickets + Corrector
        fila2 = ctk.CTkFrame(self.detail, fg_color=BG_PAGE, corner_radius=0)
        fila2.pack(fill="x", pady=(0, 12))

        c_tickets = _card(fila2)
        c_tickets.pack(side="left", fill="both", expand=True, padx=(0, 12))
        self._seccion(c_tickets, "Tickets GLPI")
        self.detail_tabla_tickets = self._tabla(
            c_tickets, ("#", "Título del ticket", "Estado"), (45, 270, 80), height=4)
        self._añadir_tooltip(self.detail_tabla_tickets)

        c_corrector = _card(fila2)
        c_corrector.pack(side="left", fill="both", expand=True)
        self._seccion(c_corrector, "Corrector")
        self.detail_tabla_corrector = self._tabla(
            c_corrector, ("Hora", "Estado", "Alerta"), (60, 75, 200), height=4)
        self._añadir_tooltip(self.detail_tabla_corrector)

    def _fila_alerta(self, host, alerta):
        nombre_alerta = alerta.get("nombre", "")
        sev = {"4": "High", "5": "Critical"}.get(str(alerta.get("severity", "")), "—")
        tiene_accion = any(k in nombre_alerta.lower() for k in ACCIONES)
        sev_color = ACCENT if sev == "Critical" else WARNING

        fila = ctk.CTkFrame(self.frame_alertas, fg_color="#F9F9F9", corner_radius=8)
        fila.pack(fill="x", pady=3)

        ctk.CTkLabel(fila, text=sev, font=FONT_LABEL, fg_color=sev_color,
                     text_color="white", corner_radius=6, width=64, height=26).pack(
            side="left", padx=(10, 12), pady=10)

        _label(fila, nombre_alerta, font=FONT_BODY).pack(side="left", expand=True, anchor="w")

        if tiene_accion:
            _pill_btn(fila, "Corregir", width=110, height=30,
                      command=lambda h=host, a=nombre_alerta: VentanaCorreccion(self, h, a)
                      ).pack(side="right", padx=10, pady=8)
        else:
            _label(fila, "Sin corrección", color=TEXT_LIGHT,
                   font=FONT_MUTED).pack(side="right", padx=10)

    def _seccion(self, parent, texto):
        ctk.CTkLabel(parent, text=texto.upper(), font=FONT_LABEL,
                     text_color=TEXT_LIGHT).pack(anchor="w", padx=20, pady=(16, 0))

    def _tabla(self, parent, columnas, anchos, height=5):
        t = ttk.Treeview(parent, columns=columnas, show="headings",
                         height=height, style="Healops.Treeview")
        for i, (col, ancho) in enumerate(zip(columnas, anchos)):
            ancho_col = ancho > 90
            t.heading(col, text=col, anchor="w" if ancho_col else "center")
            t.column(col, width=ancho, anchor="w" if ancho_col else "center",
                     stretch=(i == len(anchos) - 1))
        t.pack(fill="both", expand=True, padx=16, pady=(8, 16))
        return t

    def _estilo_tabla(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("Healops.Treeview",
                     background=BG_CARD, foreground=TEXT_MAIN,
                     fieldbackground=BG_CARD, font=("Inter", 12, "normal"),
                     rowheight=40, borderwidth=0, relief="flat")
        s.configure("Healops.Treeview.Heading",
                     background=BG_CARD, foreground=TEXT_LIGHT,
                     font=("Inter", 10, "bold"), borderwidth=0, relief="flat")
        s.map("Healops.Treeview",
              background=[("selected", ACCENT_BG)],
              foreground=[("selected", ACCENT)])

    def _añadir_tooltip(self, tabla):
        tip = tk.Toplevel(self)
        tip.withdraw()
        tip.overrideredirect(True)
        tip.configure(bg="#222222")
        lbl = tk.Label(tip, font=("Inter", 11), bg="#222222", fg="white",
                       padx=12, pady=6, wraplength=500, justify="left")
        lbl.pack()

        def on_motion(e):
            row = tabla.identify_row(e.y)
            col = tabla.identify_column(e.x)
            if not row or not col:
                tip.withdraw()
                return
            idx = int(col.replace("#", "")) - 1
            vals = tabla.item(row, "values")
            if vals and idx < len(vals) and len(str(vals[idx])) > 18:
                lbl.configure(text=str(vals[idx]))
                tip.geometry(f"+{e.x_root + 14}+{e.y_root + 14}")
                tip.deiconify()
                tip.lift()
            else:
                tip.withdraw()

        tabla.bind("<Motion>", on_motion)
        tabla.bind("<Leave>", lambda _: tip.withdraw())

    def _limpiar(self, tabla):
        for row in tabla.get_children():
            tabla.delete(row)

    # ── Selección de host ──────────────────────────────────────

    def _seleccionar_host(self, nombre):
        if self._host_seleccionado == nombre:
            return
        if self._host_seleccionado and self._host_seleccionado in self._tarjetas_host:
            self._tarjetas_host[self._host_seleccionado].set_selected(False)
        self._host_seleccionado = nombre
        self._tarjetas_host[nombre].set_selected(True)
        self._construir_detail(nombre)
        if self._cache:
            self._refrescar_detail()

    # ── Detail refresh ─────────────────────────────────────────

    def _refrescar_detail(self):
        if not self._host_seleccionado:
            return
        nombre = self._host_seleccionado

        for w in self.frame_alertas.winfo_children():
            w.destroy()
        alertas_host = self._alertas_por_host.get(nombre, [])
        if not alertas_host:
            _label(self.frame_alertas, "Sin alertas activas",
                   color=TEXT_LIGHT).pack(pady=20)
        else:
            for alerta in alertas_host:
                self._fila_alerta(nombre, alerta)

        ESTADOS = {1: "Nuevo", 2: "En curso", 3: "En espera", 4: "Resuelto", 5: "Cerrado"}
        self._limpiar(self.detail_tabla_tickets)
        for t in self._cache.get("tickets", []):
            if nombre.lower() in t.get("name", "").lower():
                estado_txt = ESTADOS.get(int(t.get("status", 1)), "Abierto")
                self.detail_tabla_tickets.insert("", "end",
                    values=(t.get("id"), t.get("name", ""), estado_txt))

        self._limpiar(self.detail_tabla_corrector)
        try:
            with open("logs/corrector.log", encoding="utf-8") as f:
                lineas = f.readlines()
            relevantes = [l for l in lineas if nombre.lower() in l.lower()][-10:]
            for linea in reversed(relevantes):
                partes = linea.strip().split("] ", 1)
                hora = partes[0].replace("[", "").split(" ")[-1] if partes else ""
                if len(partes) > 1:
                    campos = partes[1].split(" | ")
                    estado = campos[0] if campos else "?"
                    alerta = campos[2] if len(campos) > 2 else (campos[1] if len(campos) > 1 else "")
                    self.detail_tabla_corrector.insert("", "end",
                        values=(hora, estado, alerta), tags=(estado,))
            self.detail_tabla_corrector.tag_configure("OK",         foreground=SUCCESS)
            self.detail_tabla_corrector.tag_configure("ERROR",      foreground=ACCENT)
            self.detail_tabla_corrector.tag_configure("SIN_ACCION", foreground=WARNING)
        except FileNotFoundError:
            pass

    # ── Botón analizar ahora ───────────────────────────────────

    def _analizar_ahora(self):
        self.btn_analizar.configure(text="Analizando…", state="disabled",
                                     fg_color=TEXT_LIGHT, hover_color=TEXT_LIGHT)
        self.label_hora.configure(text="Analizando…")

        def _run():
            try:
                self._fetch()
                self.after(0, lambda: self._toast("Análisis completado", SUCCESS))
            except Exception as e:
                self.after(0, lambda: self._toast(f"Error: {e}", ACCENT))
            finally:
                self.after(0, lambda: self.btn_analizar.configure(
                    text="Analizar ahora", state="normal",
                    fg_color=ACCENT, hover_color=ACCENT_HOVER))

        threading.Thread(target=_run, daemon=True).start()

    def _toast(self, mensaje, color=SUCCESS):
        """Notificación flotante que desaparece sola."""
        toast = ctk.CTkFrame(self, fg_color=color, corner_radius=12)
        lbl = ctk.CTkLabel(toast, text=mensaje, font=FONT_BTN,
                            text_color="white")
        lbl.pack(padx=20, pady=10)
        toast.place(relx=1.0, rely=1.0, anchor="se", x=-32, y=-32)
        self.after(2500, toast.destroy)

    # ── Ciclo de actualización ─────────────────────────────────
    # Hilo de fondo: solo HTTP. UI: siempre en main thread via after(0,...).

    def _iniciar_actualizacion(self):
        self._cache = {}
        threading.Thread(target=self._bucle, daemon=True).start()

    def _bucle(self):
        while True:
            self._fetch()
            time.sleep(REFRESCO)

    def _fetch(self):
        try:
            import pandas as pd
            try:
                if not self._ultimo_token:
                    self._ultimo_token = login()
                token = self._ultimo_token
                alertas = obtener_alertas(token)
                if "error" in alertas:
                    raise ValueError("token expirado")
            except Exception:
                self._ultimo_token = login()
                token = self._ultimo_token
                alertas = obtener_alertas(token)

            with contextlib.redirect_stdout(io.StringIO()):
                reales = analizar_alertas(alertas)

            df = pd.DataFrame(alertas["result"])
            df["host"] = df["hosts"].apply(lambda x: x[0]["host"] if x else "?")
            df = df.rename(columns={"description": "nombre", "priority": "severity"})

            alertas_por_host = {}
            for _, row in reales.iterrows():
                alertas_por_host.setdefault(row["host"], []).append(row.to_dict())

            hosts = obtener_hosts(token)

            try:
                session = glpi_login()
                tickets = obtener_tickets_abiertos(session)
                logout(session)
            except Exception:
                tickets = []

            self._cache = {
                "n_reales":     len(reales),
                "alertas_host": alertas_por_host,
                "hosts":        hosts,
                "tickets":      tickets,
            }
            self.after(0, self._aplicar_cache)

        except Exception as e:
            print(f"[Panel] Error fetch: {e}")

    def _aplicar_cache(self):
        c = self._cache
        if not c:
            return

        self._alertas_por_host = c["alertas_host"]

        self.stat_reales.set(c["n_reales"],
                              ACCENT if c["n_reales"] > 0 else TEXT_LIGHT)
        self.stat_tickets.set(len(c["tickets"]),
                               INFO if c["tickets"] else TEXT_LIGHT)

        hosts_prob = len([h for h, v in self._alertas_por_host.items() if v])
        self.stat_estado.set(hosts_prob,
                              ACCENT if hosts_prob > 0 else SUCCESS)

        hoy = datetime.now().strftime("%Y-%m-%d")
        try:
            with open("logs/corrector.log", encoding="utf-8") as f:
                ok_hoy = sum(1 for l in f if hoy in l and "| OK |" in l)
        except FileNotFoundError:
            ok_hoy = 0
        self.stat_correcciones.set(ok_hoy, SUCCESS if ok_hoy > 0 else TEXT_LIGHT)

        for h in c["hosts"]:
            nombre = h["host"]
            if nombre not in self._tarjetas_host:
                self._tarjetas_host[nombre] = TarjetaHost(
                    self.frame_hosts, nombre, self._seleccionar_host)
            self._tarjetas_host[nombre].set_estado(
                len(self._alertas_por_host.get(nombre, [])))

        if self._host_seleccionado:
            self._refrescar_detail()

        n = c["n_reales"]
        self.title(f"HealOps — {n} alerta{'s' if n != 1 else ''} activa{'s' if n != 1 else ''}"
                   if n > 0 else "HealOps — Sin alertas")
        self.label_hora.configure(
            text=f"Actualizado {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    app = HealOpsPanel()
    app.mainloop()
