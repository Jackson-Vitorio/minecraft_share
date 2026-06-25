Minecraft Share

Gerencie seu mundo compartilhado do Minecraft com Syncthing e Discord

https://img.shields.io/badge/Minecraft-Share-blue https://img.shields.io/badge/Python-3.8%252B-green https://img.shields.io/badge/Syncthing-1.0%252B-orange https://img.shields.io/badge/Discord-Webhook-purple
📖 Sobre o projeto

Minecraft Share é uma ferramenta que permite que vários jogadores compartilhem o mesmo mundo do Minecraft usando Syncthing para sincronização. Ela gerencia o acesso com um sistema de lock por usuário, evitando conflitos de edição, e envia notificações para o Discord quando alguém assume ou libera o host, incluindo o domínio gerado pelo mod e4all para conexão via LAN.
✨ Funcionalidades

    🔒 Lock por usuário: apenas uma pessoa pode ser host por vez.

    🔄 Integração com Syncthing: pausa/retoma a sincronização automaticamente.

    📁 Pastas iguais ou separadas: se a pasta compartilhada for a mesma que a de saves, a cópia é desabilitada automaticamente.

    🗣️ Notificações Discord: avisa quando o host é assumido ou liberado, com o domínio e4all.

    🖥️ Interface gráfica simples (Tkinter) para configuração.

    🚀 Launcher automático: instala dependências e Syncthing (Linux/Windows).

📦 Pré‑requisitos

    Python 3.8+ (com pip e tkinter)

    Syncthing (instalado via launcher ou manualmente)

    Minecraft Java Edition (com mod e4all para conexão via domínio)

    Discord (opcional, para webhook)

🚀 Instalação
1. Baixe os arquivos

Coloque na mesma pasta:

    minecraft_share.py – programa principal

    launcher.py – instalador/executor automático

2. Execute o launcher
   
O launcher vai:

    Verificar se o Python está instalado.

    Instalar a biblioteca requests (se faltar).

    Verificar se o Syncthing está instalado; se não, perguntar se deseja instalá‑lo (Linux via apt/dnf/pacman; Windows via download automático).

    Iniciar o Syncthing em segundo plano.

    Abrir a interface do Minecraft Share.

    💡 Dica: No Windows, se o launcher não conseguir baixar o Syncthing, baixe manualmente em syncthing.net e coloque o syncthing.exe em uma pasta do PATH ou na mesma pasta do programa.

⚙️ Configuração
Preencha os campos:
Campo	Descrição
Seu nome (será usado no lock e nas notificações).
Compartilhada	Pasta onde o mundo fica sincronizado pelo Syncthing (ex: ~/Sync/Mundo).
Saves local	Pasta de saves do Minecraft (ex: ~/.minecraft/saves). Se for a mesma que a compartilhada, a cópia é ignorada.
Syncthing URL	Endereço da API do Syncthing (padrão: http://127.0.0.1:8384).
API Key	Chave de API do Syncthing (gerada em ~/.config/syncthing/config.xml).
Folder ID	ID da pasta compartilhada no Syncthing (ex: 9e7va-yzsup).
Discord Webhook	URL do webhook do Discord (opcional).
Como obter as informações do Syncthing

    Abra o Syncthing no navegador (http://127.0.0.1:8384).

    Clique em Ações → Configurações → API.

    Copie a API Key.

    Na lista de pastas, clique em Editar na pasta compartilhada.

    O Folder ID está no campo ID da Pasta.

🎮 Como usar
Fluxo de uso

    Abra o Minecraft e entre no mundo.

    Abra a LAN: pressione ESC → Abrir para LAN → o mod e4all gerará um domínio (ex: plywood-kilogram.cl.e4mc.link) e exibirá no chat.

    Clique em "Assumir Host" no Minecraft Share.

        O programa sincroniza com o Syncthing, pausa a sincronização, copia o mundo (se necessário) e grava o lock.

        Se o webhook estiver configurado, uma mensagem será enviada ao Discord com o domínio.

    Jogue normalmente – o Syncthing fica pausado até você liberar.

    Quando terminar, clique em "Liberar Host".

        O programa copia o mundo de volta (se necessário), retoma o Syncthing, sincroniza e remove o lock.

        Uma notificação de liberação é enviada ao Discord.

Comandos na interface
Botão	Função
Assumir Host	Torna‑se o host do mundo.
Liberar Host	Libera o host para outro jogador.
Status	Mostra quem está com o host e o estado do Syncthing.
Salvar Config	Grava as configurações atuais.
🧩 Integração com Discord (Webhook)

Preencha o campo Discord Webhook com a URL gerada no servidor:

    No Discord, vá em Configurações do canal → Integrações → Webhooks.

    Crie um webhook e copie a URL.

    Cole no campo correspondente no programa.

Mensagens enviadas:

    Host assumido: 📢 {nome} assumiu o host! 🌐 Domínio: {dominio}

    Host liberado: 🔓 {nome} liberou o host. O mundo está livre.

    O domínio é extraído do arquivo logs/latest.log do Minecraft (últimas 200 linhas).

🛠️ Solução de problemas
Erro: urllib.error.HTTPError: HTTP Error 404

Causa: O launcher não encontrou a URL de download do Syncthing.

Solução:

    Instale o Syncthing manualmente pelo gerenciador de pacotes (sudo apt install syncthing no Ubuntu) ou baixe de syncthing.net.

    No Windows, baixe o syncthing.exe e coloque na mesma pasta do programa.

Erro: Falha ao enviar webhook: Expecting value...

Causa: URL do webhook inválida ou o Discord retornou erro.

Solução:

    Verifique se a URL está correta.

    Certifique‑se de que o botão "Salvar Config" foi pressionado.

O programa não detecta o domínio do e4all

Causa: O log do Minecraft não está em português ou o mod não escreveu a mensagem.

Solução:

    Certifique‑se de que o mod e4all está instalado.

    Abra a LAN antes de clicar em "Assumir Host".

    Verifique se o arquivo ~/.minecraft/logs/latest.log contém a linha com hospedado no domínio.

O lock não é liberado

Solução:

    Se o programa travou, delete manualmente o arquivo ~/.minecraft-share/lock.json e reinicie o Syncthing.

📁 Estrutura de arquivos
text

.minecraft-share/
├── config.json          # Configurações (pastas, Syncthing, webhook)
└── lock.json            # Lock atual (host ativo)

.minecraft/
├── saves/
│   └── Mundo/           # Seu mundo (local ou compartilhado)
└── logs/
    └── latest.log       # Log do Minecraft (para extrair domínio e4all)

🤝 Contribuindo
Sinta‑se à vontade para abrir issues ou pull requests no repositório.

👏 Agradecimentos

    Syncthing – sincronização peer‑to‑peer.

    mod e4all – geração de domínios para LAN.

    Discord – webhooks para notificações.

Divirta‑se compartilhando mundos! 🎮
