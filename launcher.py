#!/usr/bin/env python3
"""
Launcher para Minecraft Share (Windows/Linux)
- Verifica/instala Python (Windows)
- Instala dependências Python (requests)
- Verifica/instala Syncthing
- Inicia Syncthing em background
- Executa o programa principal minecraft_share.py
"""

import os
import sys
import subprocess
import shutil
import time
import platform
import urllib.request
import zipfile
import tarfile
import json
from pathlib import Path

# ------------------------------------------------------------
# Configuração
# ------------------------------------------------------------
PROGRAM_NAME = "minecraft_share.py"
SYNCTHING_DIR = Path(__file__).parent / "syncthing_bin"
SYNCTHING_EXE = SYNCTHING_DIR / ("syncthing.exe" if sys.platform == "win32" else "syncthing")
SYNCTHING_CMD = str(SYNCTHING_EXE) if SYNCTHING_EXE.exists() else "syncthing"


def print_header():
    print("\n" + "="*50)
    print("  Minecraft Share - Launcher")
    print("  Sistema: " + platform.system())
    print("="*50 + "\n")


# ------------------------------------------------------------
# Funções para Windows
# ------------------------------------------------------------
def is_python_installed_windows():
    """Verifica se o Python está instalado no Windows."""
    try:
        subprocess.run([sys.executable, "--version"], capture_output=True, check=True)
        return True
    except:
        return False


def download_file(url, dest):
    """Baixa um arquivo com progresso."""
    print(f"Baixando {url}...")
    urllib.request.urlretrieve(url, dest)
    print("Download concluído.")


def install_python_windows():
    """Baixa e instala o Python no Windows."""
    print("\n[ATENÇÃO] Python não encontrado no sistema.")
    print("O Minecraft Share precisa do Python 3.8 ou superior.")
    resp = input("Deseja baixar e instalar o Python agora? (s/N): ").strip().lower()
    if resp != "s":
        print("Instalação cancelada. Instale o Python manualmente de https://www.python.org/downloads/")
        return False

    # Baixa o instalador do Python (versão mais recente 3.12)
    python_url = "https://www.python.org/ftp/python/3.12.2/python-3.12.2-amd64.exe"
    installer = Path(__file__).parent / "python_installer.exe"
    try:
        download_file(python_url, installer)
    except Exception as e:
        print(f"[ERRO] Falha ao baixar Python: {e}")
        return False

    print("Executando instalador do Python...")
    try:
        # Instala silenciosamente, adiciona ao PATH e instala pip
        subprocess.run([str(installer), "/quiet", "InstallAllUsers=1", "PrependPath=1"], check=True)
        print("[OK] Python instalado com sucesso!")
        installer.unlink()
        return True
    except subprocess.CalledProcessError:
        print("[ERRO] Falha na instalação do Python.")
        print("Tente executar o instalador manualmente.")
        return False


# ------------------------------------------------------------
# Instalação do Syncthing (Windows e Linux)
# ------------------------------------------------------------
def get_syncthing_asset_url():
    """Obtém a URL do asset do Syncthing mais recente para o sistema."""
    system = platform.system().lower()
    arch = "amd64" if system == "windows" else "amd64"
    if system == "windows":
        asset_pattern = "windows-amd64"
    elif system == "linux":
        asset_pattern = "linux-amd64"
    else:
        print(f"[ERRO] Sistema não suportado: {system}")
        return None

    url = "https://api.github.com/repos/syncthing/syncthing/releases/latest"
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode())
            for asset in data.get("assets", []):
                if asset_pattern in asset["name"] and asset["name"].endswith((".zip", ".tar.gz")):
                    return asset["browser_download_url"]
        return None
    except Exception as e:
        print(f"[ERRO] Falha ao obter URL do Syncthing: {e}")
        return None


def install_syncthing():
    """Instala o Syncthing na pasta local do programa."""
    print("\nVerificando Syncthing...")
    SYNCTHING_DIR.mkdir(exist_ok=True)

    if SYNCTHING_EXE.exists():
        print(f"[OK] Syncthing já está em: {SYNCTHING_EXE}")
        return True

    print("[ATENÇÃO] Syncthing não encontrado.")
    system = platform.system().lower()
    if system == "linux":
        # Tenta via gerenciador de pacotes primeiro
        if shutil.which("apt"):
            print("Detectado apt. Tentando instalar via pacote...")
            resp = input("Deseja instalar Syncthing via apt? (s/N): ").strip().lower()
            if resp == "s":
                try:
                    subprocess.run(["sudo", "apt", "install", "-y", "syncthing"], check=True)
                    print("[OK] Syncthing instalado via apt.")
                    return True
                except:
                    print("Falha na instalação via apt. Tentando download...")
        elif shutil.which("dnf"):
            print("Detectado dnf. Tentando instalar via pacote...")
            resp = input("Deseja instalar Syncthing via dnf? (s/N): ").strip().lower()
            if resp == "s":
                try:
                    subprocess.run(["sudo", "dnf", "install", "-y", "syncthing"], check=True)
                    print("[OK] Syncthing instalado via dnf.")
                    return True
                except:
                    print("Falha na instalação via dnf. Tentando download...")
        elif shutil.which("pacman"):
            print("Detectado pacman. Tentando instalar via pacote...")
            resp = input("Deseja instalar Syncthing via pacman? (s/N): ").strip().lower()
            if resp == "s":
                try:
                    subprocess.run(["sudo", "pacman", "-S", "--noconfirm", "syncthing"], check=True)
                    print("[OK] Syncthing instalado via pacman.")
                    return True
                except:
                    print("Falha na instalação via pacman. Tentando download...")
        # Se não deu certo, download manual
        print("Baixando Syncthing para instalação local...")
    else:
        print("Baixando Syncthing para instalação local...")

    # Download do Syncthing
    asset_url = get_syncthing_asset_url()
    if not asset_url:
        print("[ERRO] Não foi possível obter URL do Syncthing.")
        return False

    download_path = SYNCTHING_DIR / "syncthing_download"
    try:
        download_file(asset_url, download_path)
    except Exception as e:
        print(f"[ERRO] Falha no download: {e}")
        return False

    # Extrai
    print("Extraindo...")
    try:
        if system == "windows":
            with zipfile.ZipFile(download_path, 'r') as zip_ref:
                zip_ref.extractall(SYNCTHING_DIR)
        else:
            with tarfile.open(download_path, "r:gz") as tar:
                tar.extractall(SYNCTHING_DIR)
    except Exception as e:
        print(f"[ERRO] Falha na extração: {e}")
        download_path.unlink()
        return False

    download_path.unlink()

    # Procura o executável extraído
    for item in SYNCTHING_DIR.iterdir():
        if item.is_dir() and ("syncthing" in item.name.lower()):
            for file in item.rglob("*"):
                if file.name.lower() == "syncthing" or file.name.lower() == "syncthing.exe":
                    file.chmod(0o755)
                    file.rename(SYNCTHING_EXE)
                    print(f"[OK] Syncthing instalado em: {SYNCTHING_EXE}")
                    # Remove a pasta extraída
                    shutil.rmtree(item, ignore_errors=True)
                    return True

    print("[ERRO] Executável não encontrado após extração.")
    return False


# ------------------------------------------------------------
# Inicialização do Syncthing
# ------------------------------------------------------------
def start_syncthing():
    """Inicia o Syncthing em segundo plano se não estiver rodando."""
    print("\nVerificando Syncthing em execução...")
    # Verifica se já está rodando (por nome do processo)
    try:
        if sys.platform == "win32":
            result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq syncthing.exe"], capture_output=True, text=True)
            if "syncthing.exe" in result.stdout:
                print("[OK] Syncthing já está em execução.")
                return True
        else:
            result = subprocess.run(["pgrep", "-f", "syncthing"], capture_output=True, text=True)
            if result.stdout.strip():
                print("[OK] Syncthing já está em execução (PID: {})".format(result.stdout.strip().split()[0]))
                return True
    except Exception:
        pass

    print("Iniciando Syncthing em segundo plano...")
    try:
        if sys.platform == "win32":
            subprocess.Popen([str(SYNCTHING_EXE), "--no-browser"], creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            subprocess.Popen([str(SYNCTHING_EXE), "--no-browser"],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,
                           start_new_session=True)
        time.sleep(2)
        print("[OK] Syncthing iniciado.")
        return True
    except Exception as e:
        print(f"[ERRO] Falha ao iniciar Syncthing: {e}")
        return False


# ------------------------------------------------------------
# Dependências Python
# ------------------------------------------------------------
def check_python_dependencies():
    """Verifica e instala requests se necessário."""
    print("Verificando dependências Python...")
    try:
        import requests
        print("[OK] requests já instalado.")
        return True
    except ImportError:
        print("[ATENÇÃO] requests não encontrado. Instalando...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "requests"], check=True)
            print("[OK] requests instalado com sucesso.")
            return True
        except subprocess.CalledProcessError:
            print("[ERRO] Falha ao instalar requests. Instale manualmente: pip install requests")
            return False


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
def main():
    """Função principal do launcher."""
    print_header()

    # 1. Verifica Python (especial no Windows)
    if sys.platform == "win32":
        if not is_python_installed_windows():
            if not install_python_windows():
                sys.exit(1)
            # Após instalação, reinicia o script para usar o novo Python
            print("Python instalado. Reiniciando o launcher...")
            subprocess.run([sys.executable, __file__] + sys.argv[1:])
            sys.exit(0)

    # 2. Dependências Python
    if not check_python_dependencies():
        sys.exit(1)

    # 3. Syncthing
    if not install_syncthing():
        print("\n[ERRO] O Syncthing é obrigatório.")
        sys.exit(1)

    # 4. Inicia Syncthing
    if not start_syncthing():
        print("\n[AVISO] Não foi possível iniciar o Syncthing automaticamente.")
        resp = input("Continuar mesmo assim? (s/N): ").strip().lower()
        if resp != "s":
            sys.exit(1)

    # 5. Executa o programa principal
    program_path = Path(__file__).parent / PROGRAM_NAME
    if not program_path.exists():
        print(f"\n[ERRO] Arquivo '{PROGRAM_NAME}' não encontrado.")
        sys.exit(1)

    print(f"\nIniciando {PROGRAM_NAME}...")
    print("="*50 + "\n")

    try:
        subprocess.run([sys.executable, str(program_path)], check=True)
    except KeyboardInterrupt:
        print("\nPrograma interrompido pelo usuário.")
    except subprocess.CalledProcessError as e:
        print(f"\n[ERRO] O programa principal falhou com código: {e.returncode}")
        sys.exit(e.returncode)


if __name__ == "__main__":
    main()