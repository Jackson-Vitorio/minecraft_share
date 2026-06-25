"""
Minecraft Share - Host Manager com Syncthing e Discord Webhook

Gerencia mundo compartilhado via Syncthing com lock por usuário.
Suporte a pastas iguais (cópia desabilitada automaticamente).
Notifica no Discord quando o host é assumido ou liberado,
extraindo domínio do mod e4all do log do Minecraft.
Detecta se o domínio é o mesmo da última vez e avisa.
"""

import json
import re
import shutil
import threading
import time
from pathlib import Path
from tkinter import ttk, messagebox, filedialog, Tk, StringVar

import requests

# ------------------------------------------------------------
# Configuração
# ------------------------------------------------------------
APP_NAME = "Minecraft Share"
CONFIG_DIR = Path.home() / ".minecraft-share"
CONFIG_DIR.mkdir(exist_ok=True)

CONFIG_FILE = CONFIG_DIR / "config.json"
LOCK_FILE = CONFIG_DIR / "lock.json"
LAST_DOMAIN_FILE = CONFIG_DIR / "last_domain.txt"   # Armazena o último domínio enviado

DEFAULT_CONFIG = {
    "username": "",
    "shared_world_path": "",
    "local_saves_dir": "",
    "syncthing_url": "http://127.0.0.1:8384",
    "syncthing_api_key": "",
    "syncthing_folder_id": "",
    "discord_webhook_url": "https://discord.com/api/webhooks/1519798919570264104/gQjqr9sMSaRhpnWsyUcYnqamGBsHSA2PY8o2K3TNFidUJnIO2ISODdbwEZyhG0GA4XFD",
}


def load_config():
    if CONFIG_FILE.exists():
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        for k, v in DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        return cfg
    return DEFAULT_CONFIG.copy()


def save_config(cfg):
    CONFIG_FILE.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def read_lock():
    if LOCK_FILE.exists():
        return json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    return {"host": None}


def write_lock(host):
    LOCK_FILE.write_text(
        json.dumps({"host": host}, indent=2),
        encoding="utf-8"
    )


def clear_lock():
    LOCK_FILE.write_text(
        json.dumps({"host": None}, indent=2),
        encoding="utf-8"
    )


def get_last_domain():
    """Lê o último domínio salvo."""
    if LAST_DOMAIN_FILE.exists():
        return LAST_DOMAIN_FILE.read_text(encoding="utf-8").strip()
    return None


def save_last_domain(domain):
    """Salva o domínio atual."""
    LAST_DOMAIN_FILE.write_text(domain, encoding="utf-8")


# ------------------------------------------------------------
# Discord Webhook
# ------------------------------------------------------------
def send_discord_notification(webhook_url: str, message: str):
    """Envia uma mensagem para o webhook do Discord."""
    if not webhook_url:
        return
    try:
        response = requests.post(webhook_url, json={"content": message}, timeout=5)
        if response.status_code not in (200, 204):
            print(f"Falha ao enviar webhook: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Falha ao enviar webhook: {e}")


def get_e4all_domain(log_path: Path) -> str:
    """Extrai o domínio do mod e4all a partir do log do Minecraft."""
    if not log_path.exists():
        return None
    try:
        with log_path.open("r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        recent = lines[-200:] if len(lines) >= 200 else lines
        for line in reversed(recent):
            if "hospedado no domínio" in line:
                match = re.search(r"domínio\s*\[([^\]]+)\]", line)
                if match:
                    return match.group(1)
    except Exception:
        pass
    return None


# ------------------------------------------------------------
# Syncthing API
# ------------------------------------------------------------
class SyncthingAPI:
    def __init__(self, cfg):
        self.url = cfg.get("syncthing_url", "http://127.0.0.1:8384").rstrip("/")
        self.key = cfg.get("syncthing_api_key", "")
        self.folder_id = cfg.get("syncthing_folder_id", "")

    def _request(self, method, endpoint, **kwargs):
        headers = {"X-API-Key": self.key}
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))
        return requests.request(
            method,
            f"{self.url}{endpoint}",
            headers=headers,
            timeout=30,
            **kwargs
        )

    def test(self):
        try:
            resp = self._request("GET", "/rest/system/ping")
            return resp.ok
        except Exception:
            return False

    def pause(self):
        resp = self._request("POST", "/rest/system/pause")
        return resp.ok

    def resume(self):
        resp = self._request("POST", "/rest/system/resume")
        return resp.ok

    def scan(self):
        resp = self._request(
            "POST",
            f"/rest/db/scan?folder={self.folder_id}"
        )
        return resp.ok

    def completion(self):
        try:
            resp = self._request(
                "GET",
                f"/rest/db/completion?folder={self.folder_id}"
            )
            if resp.ok:
                return resp.json().get("completion", 0)
        except Exception:
            pass
        return 0

    def wait_for_sync(self, progress_callback=None, interval=1.0):
        while True:
            p = self.completion()
            if progress_callback:
                progress_callback(p)
            if p >= 100:
                break
            time.sleep(interval)


# ------------------------------------------------------------
# Utilitários de cópia
# ------------------------------------------------------------
def copy_tree_with_progress(src: Path, dst: Path, progress_callback=None):
    if not src.exists():
        raise FileNotFoundError(f"Origem não existe: {src}")

    if dst.exists():
        if dst.is_dir():
            shutil.rmtree(dst)
        else:
            dst.unlink()

    total = sum(1 for _ in src.rglob("*") if _.is_file())
    copied = 0

    def on_copy(src_path, dst_path, *, follow_symlinks=True):
        nonlocal copied
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_path, follow_symlinks=follow_symlinks)
        copied += 1
        if progress_callback:
            progress_callback(copied, total)

    shutil.copytree(
        src,
        dst,
        copy_function=on_copy,
        symlinks=False,
        dirs_exist_ok=True,
    )
    return copied, total


# ------------------------------------------------------------
# Lógica principal
# ------------------------------------------------------------
def assume_host(ui):
    cfg = load_config()
    username = ui.username_var.get().strip()
    if not username:
        messagebox.showerror(APP_NAME, "Informe seu nome.")
        return

    shared_path = Path(cfg["shared_world_path"])
    local_saves = Path(cfg["local_saves_dir"])
    if not shared_path.exists():
        messagebox.showerror(APP_NAME, "Pasta compartilhada não existe.")
        return
    if not local_saves.exists():
        messagebox.showerror(APP_NAME, "Pasta saves local não existe.")
        return

    # Verifica lock
    lock = read_lock()
    if lock.get("host") and lock["host"] != username:
        messagebox.showerror(APP_NAME, f"Mundo em uso por {lock['host']}")
        return

    world_name = shared_path.name
    local_world = local_saves / world_name

    if not local_world.exists():
        messagebox.showerror(APP_NAME, f"Mundo local não encontrado: {local_world}\nEntre no mundo no Minecraft primeiro.")
        return

    # --- Prepara Syncthing ---
    api = SyncthingAPI(cfg)
    if not api.test():
        if not messagebox.askyesno(APP_NAME, "Não foi possível conectar ao Syncthing.\nContinuar mesmo assim?"):
            return

    ui.status_label.config(text="Sincronizando com Syncthing...")
    ui.progress_bar["value"] = 0
    ui.root.update()

    if api.test():
        ui.status_label.config(text="Verificando atualizações...")
        api.scan()
        time.sleep(1)

        ui.status_label.config(text="Aguardando sincronização...")
        sync_done = threading.Event()

        def sync_progress(p):
            ui.progress_bar["value"] = p
            ui.root.update()

        def wait_sync():
            try:
                api.wait_for_sync(progress_callback=sync_progress)
                sync_done.set()
            except Exception as e:
                ui.root.after(0, lambda: messagebox.showerror(APP_NAME, f"Erro na sincronização: {e}"))
                sync_done.set()

        threading.Thread(target=wait_sync, daemon=True).start()
        sync_done.wait(timeout=300)

    ui.status_label.config(text="Pausando Syncthing...")
    ui.root.update()
    if api.test():
        api.pause()
        time.sleep(1)

    # Cópia se necessário
    if shared_path.resolve() == local_world.resolve():
        ui.status_label.config(text="Mundo já está em local saves – cópia ignorada.")
        ui.root.update()
    else:
        ui.status_label.config(text=f"Copiando {world_name} → local...")
        ui.progress_bar["value"] = 0
        ui.root.update()

        def copy_progress(copied, total):
            if total > 0:
                pct = int(copied / total * 100)
                ui.progress_bar["value"] = pct
                ui.status_label.config(text=f"Copiando... {copied}/{total}")
                ui.root.update()

        try:
            copy_tree_with_progress(shared_path, local_world, copy_progress)
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Erro ao copiar: {e}")
            if api.test():
                api.resume()
            return

    write_lock(username)

    # --- Extrai domínio e verifica duplicidade ---
    webhook_url = cfg.get("discord_webhook_url", "")
    log_path = Path.home() / ".minecraft" / "logs" / "latest.log"
    domain = get_e4all_domain(log_path)
    last_domain = get_last_domain()

    # Verifica se o domínio é o mesmo da última vez
    if domain and domain == last_domain:
        # Aviso no Tkinter
        msg_box = (f"⚠️ O domínio é o mesmo do último host assumido ({domain}).\n"
                   "Isso indica que a LAN não foi reaberta ou o mundo não foi atualizado.\n"
                   "Reabra a LAN para gerar um novo domínio antes de assumir o host novamente.")
        messagebox.showwarning(APP_NAME, msg_box)
        # Aviso no Discord (opcional)
        if webhook_url:
            send_discord_notification(webhook_url, f"⚠️ **{username}** assumiu o host, mas o domínio não mudou: {domain}. Reabra a LAN!")
        # Não salvamos o domínio novamente (permanece o mesmo)
    else:
        # Domínio diferente ou primeiro host – salva e notifica normalmente
        if domain:
            save_last_domain(domain)
            # Notificação normal com domínio
            if webhook_url:
                msg = f"📢 **{username}** assumiu o host!\n🌐 **Domínio:** {domain}"
                send_discord_notification(webhook_url, msg)
        else:
            # Sem domínio – notificação genérica
            if webhook_url:
                msg = f"📢 **{username}** assumiu o host!"
                send_discord_notification(webhook_url, msg)

    ui.status_label.config(text="Pronto! Pode jogar.")
    ui.progress_bar["value"] = 100
    messagebox.showinfo(APP_NAME, f"Host assumido.\n\nMundo: {world_name}\nSyncthing pausado.")


def release_host(ui):
    cfg = load_config()
    username = ui.username_var.get().strip()
    if not username:
        messagebox.showerror(APP_NAME, "Informe seu nome.")
        return

    lock = read_lock()
    if lock.get("host") != username:
        messagebox.showerror(APP_NAME, f"Você não é o host atual. Host: {lock.get('host')}")
        return

    shared_path = Path(cfg["shared_world_path"])
    local_saves = Path(cfg["local_saves_dir"])
    if not shared_path.exists():
        messagebox.showerror(APP_NAME, "Pasta compartilhada não existe.")
        return

    world_name = shared_path.name
    local_world = local_saves / world_name

    if shared_path.resolve() == local_world.resolve():
        ui.status_label.config(text="Mundo já está em shared – cópia ignorada.")
        ui.root.update()
    else:
        if not local_world.exists():
            messagebox.showerror(APP_NAME, f"Mundo local não encontrado: {local_world}")
            return

        ui.status_label.config(text=f"Copiando {world_name} → compartilhado...")
        ui.progress_bar["value"] = 0
        ui.root.update()

        def copy_progress(copied, total):
            if total > 0:
                pct = int(copied / total * 100)
                ui.progress_bar["value"] = pct
                ui.status_label.config(text=f"Copiando... {copied}/{total}")
                ui.root.update()

        try:
            copy_tree_with_progress(local_world, shared_path, copy_progress)
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Erro ao copiar: {e}")
            return

    api = SyncthingAPI(cfg)
    ui.status_label.config(text="Reativando Syncthing...")
    ui.root.update()
    if api.test():
        api.resume()
        time.sleep(1)

    ui.status_label.config(text="Sincronizando com Syncthing...")
    ui.progress_bar["value"] = 0
    ui.root.update()

    if api.test():
        ui.status_label.config(text="Verificando atualizações...")
        api.scan()
        time.sleep(1)

        ui.status_label.config(text="Aguardando sincronização...")
        sync_done = threading.Event()

        def sync_progress(p):
            ui.progress_bar["value"] = p
            ui.root.update()

        def wait_sync():
            try:
                api.wait_for_sync(progress_callback=sync_progress)
                sync_done.set()
            except Exception as e:
                ui.root.after(0, lambda: messagebox.showerror(APP_NAME, f"Erro na sincronização: {e}"))
                sync_done.set()

        threading.Thread(target=wait_sync, daemon=True).start()
        sync_done.wait(timeout=300)

    clear_lock()

    webhook_url = cfg.get("discord_webhook_url", "")
    if webhook_url:
        msg = f"🔓 **{username}** liberou o host. O mundo está livre."
        send_discord_notification(webhook_url, msg)

    ui.status_label.config(text="Pronto! Mundo liberado.")
    ui.progress_bar["value"] = 100
    messagebox.showinfo(APP_NAME, "Host liberado.\n\nSyncthing reativado.")


def show_status(ui):
    lock = read_lock()
    cfg = load_config()
    api = SyncthingAPI(cfg)

    lines = []
    if lock.get("host"):
        lines.append(f"👤 Host: {lock['host']}")
    else:
        lines.append("🔓 Livre")

    if api.test():
        p = api.completion()
        lines.append(f"🔄 Sincronização: {p:.0f}%")
        lines.append("✅ Syncthing conectado")
    else:
        lines.append("❌ Syncthing não conectado")

    shared = Path(cfg["shared_world_path"])
    if shared.exists():
        lines.append(f"📁 Mundo: {shared.name}")
    else:
        lines.append("⚠️ Pasta compartilhada não configurada")

    local = Path(cfg["local_saves_dir"])
    world_name = shared.name
    local_world = local / world_name
    if shared.resolve() == local_world.resolve():
        lines.append("ℹ️  Mundo está dentro da pasta de saves – cópias desabilitadas")
    else:
        lines.append("ℹ️  Pastas separadas – cópias serão realizadas")

    # Exibe o último domínio salvo
    last_domain = get_last_domain()
    if last_domain:
        lines.append(f"📌 Último domínio: {last_domain}")

    messagebox.showinfo(APP_NAME, "\n".join(lines))


# ------------------------------------------------------------
# Interface Tkinter
# ------------------------------------------------------------
class App:
    def __init__(self, root):
        self.root = root
        root.title(APP_NAME)
        root.geometry("540x540")
        root.minsize(480, 480)

        self.cfg = load_config()

        self.username_var = StringVar(value=self.cfg.get("username", ""))
        self.shared_path_var = StringVar(value=self.cfg.get("shared_world_path", ""))
        self.local_saves_var = StringVar(value=self.cfg.get("local_saves_dir", ""))
        self.st_url_var = StringVar(value=self.cfg.get("syncthing_url", "http://127.0.0.1:8384"))
        self.st_key_var = StringVar(value=self.cfg.get("syncthing_api_key", ""))
        self.st_folder_var = StringVar(value=self.cfg.get("syncthing_folder_id", ""))
        self.webhook_var = StringVar(value=self.cfg.get("discord_webhook_url", ""))

        self.username_var.trace_add("write", self._save_username)
        self._build_ui()

        self.progress_bar["value"] = 0
        self.status_label.config(text="Pronto.")

    def _save_username(self, *args):
        cfg = load_config()
        cfg["username"] = self.username_var.get()
        save_config(cfg)

    def _save_all_config(self):
        cfg = {
            "username": self.username_var.get(),
            "shared_world_path": self.shared_path_var.get(),
            "local_saves_dir": self.local_saves_var.get(),
            "syncthing_url": self.st_url_var.get(),
            "syncthing_api_key": self.st_key_var.get(),
            "syncthing_folder_id": self.st_folder_var.get(),
            "discord_webhook_url": self.webhook_var.get(),
        }
        save_config(cfg)
        return cfg

    def _browse_shared(self):
        d = filedialog.askdirectory(title="Selecione a pasta compartilhada do mundo")
        if d:
            self.shared_path_var.set(d)
            self._save_all_config()

    def _browse_local(self):
        d = filedialog.askdirectory(title="Selecione a pasta saves do Minecraft")
        if d:
            self.local_saves_var.set(d)
            self._save_all_config()

    def _build_ui(self):
        main_frame = ttk.Frame(self.root, padding=12)
        main_frame.pack(fill="both", expand=True)

        # Usuário
        ttk.Label(main_frame, text="Seu nome", font=("", 10, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 2)
        )
        ttk.Entry(main_frame, textvariable=self.username_var).grid(
            row=1, column=0, columnspan=3, sticky="ew", pady=(0, 10)
        )

        # Pastas
        ttk.Label(main_frame, text="Pastas", font=("", 10, "bold")).grid(
            row=2, column=0, sticky="w", pady=(0, 2)
        )

        ttk.Label(main_frame, text="Compartilhada:").grid(
            row=3, column=0, sticky="w"
        )
        ttk.Entry(main_frame, textvariable=self.shared_path_var).grid(
            row=3, column=1, sticky="ew", padx=(5, 5)
        )
        ttk.Button(main_frame, text="📁", width=4, command=self._browse_shared).grid(
            row=3, column=2, sticky="e"
        )

        ttk.Label(main_frame, text="Saves local:").grid(
            row=4, column=0, sticky="w", pady=(5, 0)
        )
        ttk.Entry(main_frame, textvariable=self.local_saves_var).grid(
            row=4, column=1, sticky="ew", padx=(5, 5), pady=(5, 0)
        )
        ttk.Button(main_frame, text="📁", width=4, command=self._browse_local).grid(
            row=4, column=2, sticky="e", pady=(5, 0)
        )

        # Syncthing
        ttk.Label(main_frame, text="Syncthing", font=("", 10, "bold")).grid(
            row=5, column=0, sticky="w", pady=(15, 2)
        )

        ttk.Label(main_frame, text="URL:").grid(
            row=6, column=0, sticky="w"
        )
        ttk.Entry(main_frame, textvariable=self.st_url_var).grid(
            row=6, column=1, columnspan=2, sticky="ew", padx=(5, 0)
        )

        ttk.Label(main_frame, text="API Key:").grid(
            row=7, column=0, sticky="w", pady=(5, 0)
        )
        ttk.Entry(main_frame, textvariable=self.st_key_var, show="•").grid(
            row=7, column=1, columnspan=2, sticky="ew", padx=(5, 0), pady=(5, 0)
        )

        ttk.Label(main_frame, text="Folder ID:").grid(
            row=8, column=0, sticky="w", pady=(5, 0)
        )
        ttk.Entry(main_frame, textvariable=self.st_folder_var).grid(
            row=8, column=1, columnspan=2, sticky="ew", padx=(5, 0), pady=(5, 0)
        )

        # Discord Webhook
        ttk.Label(main_frame, text="Discord Webhook (URL)", font=("", 10, "bold")).grid(
            row=9, column=0, sticky="w", pady=(15, 2)
        )
        ttk.Entry(main_frame, textvariable=self.webhook_var).grid(
            row=10, column=0, columnspan=3, sticky="ew", padx=(0, 0), pady=(0, 5)
        )

        # Progresso
        ttk.Label(main_frame, text="Progresso", font=("", 10, "bold")).grid(
            row=11, column=0, sticky="w", pady=(15, 2)
        )
        self.progress_bar = ttk.Progressbar(
            main_frame, orient="horizontal", length=400, mode="determinate"
        )
        self.progress_bar.grid(row=12, column=0, columnspan=3, sticky="ew", pady=(0, 5))

        self.status_label = ttk.Label(main_frame, text="Pronto.")
        self.status_label.grid(row=13, column=0, columnspan=3, sticky="w")

        # Botões
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=14, column=0, columnspan=3, pady=(15, 0), sticky="ew")

        ttk.Button(
            btn_frame,
            text="✅ Assumir Host",
            command=lambda: self._run_in_thread(assume_host, self)
        ).pack(side="left", padx=(0, 8), fill="x", expand=True)

        ttk.Button(
            btn_frame,
            text="🔄 Liberar Host",
            command=lambda: self._run_in_thread(release_host, self)
        ).pack(side="left", padx=(0, 8), fill="x", expand=True)

        ttk.Button(
            btn_frame,
            text="📊 Status",
            command=lambda: show_status(self)
        ).pack(side="left", padx=(0, 8), fill="x", expand=True)

        ttk.Button(
            btn_frame,
            text="💾 Salvar Config",
            command=self._save_all_config
        ).pack(side="left", fill="x", expand=True)

        main_frame.columnconfigure(1, weight=1)

    def _run_in_thread(self, func, *args):
        def wrapper():
            try:
                func(*args)
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror(APP_NAME, f"Erro: {e}"))
                self.root.after(0, lambda: self.status_label.config(text="Erro."))
                self.root.after(0, lambda: self.progress_bar.config(value=0))
            finally:
                self.root.after(0, lambda: self.status_label.config(text="Pronto."))

        threading.Thread(target=wrapper, daemon=True).start()


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
if __name__ == "__main__":
    root = Tk()
    app = App(root)
    root.mainloop()