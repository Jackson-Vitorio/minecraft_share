import os
import sys
import json
import re
import time
import threading
import subprocess
import shutil
import socket
from datetime import datetime, timedelta

import requests
import PySimpleGUI as sg

# ==================== CONFIGURAÇÕES GLOBAIS ====================
CONFIG_FILE = "mundo_sync_config.json"
LOCK_FILE = "em_uso.lock"
LOCK_DURATION_HOURS = 2

def get_default_minecraft_dir():
    if os.name == 'nt':
        return os.path.join(os.environ['APPDATA'], '.minecraft')
    else:
        return os.path.expanduser('~/.minecraft')

def get_rclone_path():
    rclone_sistema = shutil.which("rclone")
    if rclone_sistema:
        return rclone_sistema
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    nome = "rclone.exe" if os.name == 'nt' else "rclone"
    return os.path.join(base_path, nome)

RCLONE = get_rclone_path()

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

# ==================== FUNÇÕES AUXILIARES ====================
def carregar_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def salvar_config(cfg):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=4)

def primeira_configuracao():
    layout = [
        [sg.Text("Bem-vindo ao MundoSync! Configure os caminhos:")],
        [sg.Text("Seu nome/apelido:"), sg.Input(key='-USERNAME-')],
        [sg.Text("Pasta .minecraft:"), sg.Input(get_default_minecraft_dir(), key='-MINECRAFT_DIR-'), sg.FolderBrowse()],
        [sg.Text("Pasta saves:"), sg.Input(key='-MUNDO_PATH-'), sg.FolderBrowse()],
        [sg.Text("Nome da pasta do mundo:"), sg.Input(key='-MUNDO_NOME-')],
        [sg.Text("Remote do Rclone (ex: gdrive:MinecraftMundo):"), sg.Input(key='-REMOTE-')],
        [sg.Text("Webhook do Discord (opcional):"), sg.Input(key='-WEBHOOK-')],
        [sg.Text("Regex personalizada (deixe em branco para padrão):")],
        [sg.Input(key='-REGEX-')],
        [sg.Button("Salvar"), sg.Button("Cancelar")]
    ]
    window = sg.Window("Configuração Inicial", layout)
    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, "Cancelar"):
            window.close()
            return None
        if event == "Salvar":
            cfg = {
                "username": values['-USERNAME-'],
                "minecraft_dir": values['-MINECRAFT_DIR-'],
                "mundo_path": values['-MUNDO_PATH-'],
                "mundo_nome": values['-MUNDO_NOME-'],
                "remote": values['-REMOTE-'],
                "webhook_url": values['-WEBHOOK-'],
                "regex": values['-REGEX-']
            }
            salvar_config(cfg)
            window.close()
            return cfg
    window.close()

def verificar_rclone():
    try:
        subprocess.run([RCLONE, "version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False

# ==================== CONFIGURAÇÃO AUTOMÁTICA DO GOOGLE DRIVE ====================
def configurar_google_drive(window):
    """
    Cria o remote 'gdrive' automaticamente, usando as credenciais padrão do Rclone.
    Após a criação, testa a conexão e atualiza o campo REMOTE no config.
    """
    # Verifica se o remote já existe
    try:
        subprocess.run([RCLONE, "lsd", "gdrive:"], capture_output=True, check=True)
        atualizar_log(window, "✅ Remote 'gdrive' já está configurado e funcionando.")
        return True
    except subprocess.CalledProcessError:
        pass  # Remote não existe ou não está autenticado

    # Exibe instruções
    sg.popup_ok(
        "Agora vamos configurar o Google Drive.\n\n"
        "1. Uma janela do navegador será aberta.\n"
        "2. Faça login na sua conta Google.\n"
        "3. Autorize o aplicativo 'rclone'.\n"
        "4. Volte aqui e clique em OK.",
        title="Configurar Google Drive"
    )

    try:
        # Cria o remote com auto-config (abre navegador)
        resultado = subprocess.run(
            [RCLONE, "config", "create", "gdrive", "drive", "config_is_local=false"],
            capture_output=True,
            text=True,
            check=False
        )
        if resultado.returncode != 0:
            sg.popup_error(
                "Falha ao abrir o navegador automaticamente.\n"
                "Você pode configurar manualmente executando 'rclone config' no terminal.\n"
                "Ou tente novamente mais tarde.",
                title="Erro"
            )
            return False

        # Testa a conexão
        subprocess.run([RCLONE, "lsd", "gdrive:"], capture_output=True, check=True)
        atualizar_log(window, "✅ Google Drive configurado com sucesso!")
        sg.popup_ok("Configuração concluída! Seu Google Drive está conectado.", title="Sucesso")
        return True
    except Exception as e:
        sg.popup_error(f"Erro na configuração: {str(e)}", title="Erro")
        return False

# ==================== SINCRONIZAÇÃO COM RCLONE ====================
class RcloneThread(threading.Thread):
    def __init__(self, comando, window, ok_value=None):
        super().__init__(daemon=True)
        self.comando = comando
        self.window = window
        self.ok_value = ok_value
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        try:
            proc = subprocess.Popen(
                self.comando,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            for line in iter(proc.stdout.readline, ''):
                if self._stop_event.is_set():
                    proc.terminate()
                    break
                self._parse_progress(line)
            proc.wait()
            if proc.returncode == 0 and not self._stop_event.is_set():
                self.window.write_event_value('-RCLONE-OK-', self.ok_value)
            else:
                self.window.write_event_value('-RCLONE-ERRO-', f"Código: {proc.returncode}")
        except Exception as e:
            self.window.write_event_value('-RCLONE-ERRO-', str(e))

    def _parse_progress(self, line):
        match = re.search(r'Transferred:\s+([\d.]+)\s*(\w+)\s*/\s*([\d.]+)\s*(\w+),\s*(\d+)%', line)
        if match:
            percent = int(match.group(5))
            self.window.write_event_value('-PROGRESS-', percent)

# ==================== LEITURA DO LOG (IP) ====================
def obter_endereco_log(caminho_minecraft_dir, regex_personalizada=None):
    log_path = os.path.join(caminho_minecraft_dir, "logs", "latest.log")
    if not os.path.exists(log_path):
        return None
    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            linhas = f.readlines()
    except Exception:
        return None
    recentes = linhas[-200:] if len(linhas) >= 200 else linhas

    if regex_personalizada:
        try:
            padrao_dominio = re.compile(regex_personalizada)
            padrao_ip = None
        except re.error:
            padrao_dominio = None
            padrao_ip = None
    else:
        padrao_dominio = re.compile(r'Jogo local hospedado no domínio\s*\[([^\]]+)\]', re.IGNORECASE)
        padrao_ip = re.compile(
            r'(?:e4all|e4mc|Servidor local iniciado no endereço|Local server started on)\s*:?\s*/?(\d+\.\d+\.\d+\.\d+:\d+)',
            re.IGNORECASE
        )

    endereco = None
    for linha in reversed(recentes):
        if padrao_dominio:
            m = padrao_dominio.search(linha)
            if m:
                endereco = m.group(1)
                break
        if not endereco and padrao_ip:
            m = padrao_ip.search(linha)
            if m:
                ip_port = m.group(1)
                if ip_port.startswith("0.0.0.0:"):
                    port = ip_port.split(":")[1]
                    ip = get_local_ip()
                    ip_port = f"{ip}:{port}"
                endereco = ip_port
                break
    return endereco

# ==================== WEBHOOK DISCORD ====================
def enviar_discord(webhook_url, mensagem):
    if not webhook_url:
        return
    try:
        requests.post(webhook_url, json={"content": mensagem}, timeout=5)
    except Exception as e:
        print(f"Erro ao enviar webhook: {e}")

# ==================== GERENCIAMENTO DO LOCK ====================
def _criar_lock_metadata(username):
    agora = datetime.now()
    expira = agora + timedelta(hours=LOCK_DURATION_HOURS)
    return {
        "host": username,
        "timestamp": agora.isoformat(),
        "expira_em": expira.isoformat()
    }

def _subir_lock(config):
    lock_local = os.path.join(config['mundo_path'], config['mundo_nome'], LOCK_FILE)
    metadata = _criar_lock_metadata(config.get('username', 'desconhecido'))
    with open(lock_local, 'w', encoding='utf-8') as f:
        json.dump(metadata, f)
    subprocess.run(
        [RCLONE, "copyto", lock_local, f"{config['remote']}/{LOCK_FILE}"],
        check=True
    )

def _remover_lock_remoto(config):
    try:
        subprocess.run(
            [RCLONE, "deletefile", f"{config['remote']}/{LOCK_FILE}"],
            check=True
        )
    except:
        pass

def _remover_lock_local(config):
    lock_path = os.path.join(config['mundo_path'], config['mundo_nome'], LOCK_FILE)
    if os.path.exists(lock_path):
        os.remove(lock_path)

def _ler_lock_remoto(config):
    try:
        proc = subprocess.run(
            [RCLONE, "cat", f"{config['remote']}/{LOCK_FILE}"],
            capture_output=True, text=True, check=True
        )
        return json.loads(proc.stdout)
    except:
        return None

def _lock_expirado(metadata):
    if not metadata:
        return True
    try:
        expira = datetime.fromisoformat(metadata['expira_em'])
        return datetime.now() > expira
    except:
        return True

def _lock_ativo(config):
    meta = _ler_lock_remoto(config)
    if meta and not _lock_expirado(meta):
        return True, meta.get('host', 'desconhecido')
    return False, None

# ==================== INTERFACE PRINCIPAL ====================
def criar_janela_principal(config):
    sg.theme('DarkBlue3')
    layout = [
        [sg.Text("🌍 MundoSync", font=('Helvetica', 16))],
        [sg.Text("Status: Aguardando", key='-STATUS-', size=(50, 1))],
        [sg.ProgressBar(100, orientation='h', size=(50, 20), key='-PROGRESS-')],
        [sg.Multiline(size=(70, 8), key='-LOG-', autoscroll=True, disabled=True)],
        [sg.Text("Endereço detectado:"), sg.Input(key='-IP-', readonly=True, size=(35,1)),
         sg.Button("Copiar IP"), sg.Button("🎮 Detectar e Enviar IP", key='-DETECTAR-')],
        [sg.Button("⬇️ Baixar Mundo", size=(14,1)), sg.Button("⬆️ Enviar Mundo", size=(14,1)),
         sg.Button("🔍 Status Lock", size=(14,1)), sg.Button("📂 Conectar Google Drive", size=(20,1))],
        [sg.Button("⚙️ Configurações", size=(14,1)), sg.Button("Sair", size=(14,1))]
    ]
    return sg.Window("MundoSync", layout, finalize=True)

def atualizar_log(window, mensagem):
    window['-LOG-'].print(mensagem)

def atualizar_status(window, texto):
    window['-STATUS-'].update(texto)

def atualizar_progresso(window, valor):
    window['-PROGRESS-'].update(valor)

# ==================== FLUXO PRINCIPAL ====================
class MundoSyncApp:
    def __init__(self):
        self.config = carregar_config()
        self.window = None
        self.rclone_thread = None

    def iniciar(self):
        if not self.config:
            self.config = primeira_configuracao()
            if not self.config:
                sg.popup_error("Configuração obrigatória. Encerrando.")
                sys.exit(0)
        if not verificar_rclone():
            sg.popup_error(f"Rclone não encontrado em: {RCLONE}\nVerifique a instalação ou ajuste a configuração.", title="Erro")
            sys.exit(1)

        self.window = criar_janela_principal(self.config)

        while True:
            event, values = self.window.read()
            if event in (sg.WIN_CLOSED, "Sair"):
                self.encerrar()
                break
            elif event == "⬇️ Baixar Mundo":
                self.executar_sync("download")
            elif event == "⬆️ Enviar Mundo":
                self.executar_sync("upload")
            elif event == "-DETECTAR-":
                self.detectar_e_enviar_ip()
            elif event == "Copiar IP":
                ip = values['-IP-']
                if ip:
                    sg.clipboard_set(ip)
                    sg.popup_quick_message("IP copiado!", auto_close_duration=1)
            elif event == "🔍 Status Lock":
                self.mostrar_status_lock()
            elif event == "📂 Conectar Google Drive":
                sucesso = configurar_google_drive(self.window)
                if sucesso:
                    self.config['remote'] = "gdrive:MinecraftMundo"
                    salvar_config(self.config)
                    atualizar_log(self.window, "Remote atualizado para 'gdrive:MinecraftMundo'.")
            elif event == "⚙️ Configurações":
                self.abrir_configuracoes()
            elif event == '-RCLONE-OK-':
                remover_lock = values[event] if isinstance(values[event], bool) else False
                self.finalizar_sync(erro=False, remover_lock=remover_lock)
            elif event == '-RCLONE-ERRO-':
                atualizar_log(self.window, f"Erro Rclone: {values[event]}")
                self.finalizar_sync(erro=True)
            elif event == '-PROGRESS-':
                atualizar_progresso(self.window, values[event])

    def detectar_e_enviar_ip(self):
        minecraft_dir = self.config.get('minecraft_dir')
        if not minecraft_dir:
            atualizar_log(self.window, "Configure a pasta .minecraft primeiro.")
            return

        endereco = obter_endereco_log(minecraft_dir, self.config.get('regex', ''))
        if not endereco:
            atualizar_log(self.window, "Nenhum endereço de LAN encontrado. Abra o mundo para LAN primeiro.")
            sg.popup_quick_message("Nenhum endereço detectado.", auto_close_duration=2)
            return

        self.window['-IP-'].update(endereco)
        atualizar_log(self.window, f"🔥 Endereço detectado: {endereco}")

        # Verificar lock existente
        ativo, host = _lock_ativo(self.config)
        username = self.config.get('username', 'desconhecido')
        if ativo and host != username:
            resp = sg.popup_yes_no(
                f"O lock atual pertence a '{host}' e ainda não expirou.\n"
                "Deseja forçar a posse do lock? (pode corromper o save)",
                title="Lock ativo"
            )
            if resp != "Yes":
                atualizar_log(self.window, "Envio cancelado pelo usuário.")
                return

        # Criar lock e enviar webhook
        _subir_lock(self.config)
        atualizar_log(self.window, f"Lock criado para '{username}'.")

        webhook = self.config.get('webhook_url', '')
        if webhook:
            mundo = self.config.get('mundo_nome', 'desconhecido')
            mensagem = f"🎮 Servidor LAN aberto por **{username}**!\nMundo: **{mundo}**\nEndereço: `{endereco}`"
            enviar_discord(webhook, mensagem)
            atualizar_log(self.window, "Endereço enviado para Discord.")

    def mostrar_status_lock(self):
        ativo, host = _lock_ativo(self.config)
        if ativo:
            meta = _ler_lock_remoto(self.config)
            expira = "desconhecida"
            if meta and 'expira_em' in meta:
                try:
                    dt = datetime.fromisoformat(meta['expira_em'])
                    expira = dt.strftime("%d/%m/%Y %H:%M:%S")
                except:
                    pass
            mensagem = f"🔒 Lock ativo\nHost: {host}\nExpira em: {expira}"
        else:
            mensagem = "🔓 Nenhum lock ativo."
        sg.popup(mensagem, title="Status do Lock")

    def executar_sync(self, direcao):
        ativo, host = _lock_ativo(self.config)
        username = self.config.get('username', '')
        if ativo and host != username:
            resp = sg.popup_yes_no(
                f"O lock está em posse de '{host}'.\n"
                "Deseja continuar mesmo assim? (pode gerar conflitos)",
                title="Lock ativo"
            )
            if resp != "Yes":
                return

        if direcao == "download":
            origem = self.config['remote']
            destino = os.path.join(self.config['mundo_path'], self.config['mundo_nome'])
            mensagem = "Baixando mundo..."
            remover_lock = False
        else:
            origem = os.path.join(self.config['mundo_path'], self.config['mundo_nome'])
            destino = self.config['remote']
            mensagem = "Enviando mundo..."
            # Só remove o lock se ele pertencer ao usuário atual
            remover_lock = ativo and host == username

        atualizar_status(self.window, mensagem)
        atualizar_progresso(self.window, 0)
        comando = [
            RCLONE, "sync",
            origem, destino,
            "--progress",
            "--stats=1s",
            "--create-empty-src-dirs",
            "--exclude", LOCK_FILE
        ]
        self.rclone_thread = RcloneThread(comando, self.window, ok_value=remover_lock)
        self.rclone_thread.start()

    def finalizar_sync(self, erro=False, remover_lock=False):
        if erro:
            atualizar_status(self.window, "Erro na sincronização")
        else:
            atualizar_status(self.window, "Sincronização concluída")
            if remover_lock:
                _remover_lock_remoto(self.config)
                _remover_lock_local(self.config)
                atualizar_log(self.window, "Lock removido após envio.")
                webhook = self.config.get('webhook_url', '')
                if webhook:
                    username = self.config.get('username', 'desconhecido')
                    mundo = self.config.get('mundo_nome', 'desconhecido')
                    mensagem = f"🔓 **{username}** liberou o host.\nMundo: **{mundo}** foi salvo na nuvem."
                    enviar_discord(webhook, mensagem)
                    atualizar_log(self.window, "Notificação de liberação enviada ao Discord.")
        atualizar_progresso(self.window, 0)

    def abrir_configuracoes(self):
        nova_config = primeira_configuracao()
        if nova_config:
            self.config = nova_config

    def encerrar(self):
        if self.rclone_thread and self.rclone_thread.is_alive():
            self.rclone_thread.stop()
        self.window.close()

# ==================== PONTO DE ENTRADA ====================
if __name__ == "__main__":
    app = MundoSyncApp()
    app.iniciar()