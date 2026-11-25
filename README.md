# Painel Compacto OBS (`auto_jw_obs`)

Mini painel flutuante para **OBS Studio** no Windows: exibe um preview em tempo real da cena ativa e botões rápidos para trocar de cena sem ocupar espaço na tela, abrindo e fechando automaticamente junto com o OBS.

## Arquivos do projeto

- **`dist/obs_painel.exe`** — Executável pronto do painel (*não precisa instalar Python* nos outros computadores).
- **`obs_abrir_painel.lua`** — Script Lua para o OBS Studio que abre o painel automaticamente ao iniciar o OBS e o encerra quando o OBS é fechado.
- **`obs_painel.py`** — Código-fonte do painel (preview em tempo real, destaque da cena ativa, reconexão automática e leitura automática de porta/senha do OBS WebSocket).
- **`auto_jw_obs.py`** — Automação complementar (em Python) para alternar para a cena `JW` com `Ctrl + Clique` no JW Library e retornar com `Esc`.

---

## Requisitos

- **Windows**
- **OBS Studio 28 ou superior** (já vem com OBS WebSocket embutido)

*(Não é necessário instalar Python para usar o `obs_painel.exe`.)*

---

## Como usar em um novo computador

Você só precisa de **2 arquivos** no outro computador: `dist/obs_painel.exe` e `obs_abrir_painel.lua` (ou da pasta completa do repositório).

### 1. Ativar o WebSocket no OBS Studio

1. Abra o **OBS Studio**.
2. Vá em **Ferramentas → Configurações do servidor WebSocket**.
3. Marque a opção **Habilitar servidor WebSocket** e clique em **OK**.

> **Nota:** Não é necessário configurar porta nem senha no código. O `obs_painel.exe` lê automaticamente o arquivo de configuração local do OBS (`%APPDATA%\obs-studio\plugin_config\obs-websocket\config.json`).

### 2. Configurar a abertura automática no OBS

1. No OBS Studio, vá em **Ferramentas → Scripts**.
2. Clique no botão **`+`** e selecione o arquivo `obs_abrir_painel.lua`.
3. Em **Caminho do Painel**, clique em **Procurar** e selecione `dist/obs_painel.exe`.
4. Deixe marcada a opção **Fechar o painel quando o OBS fechar**.
5. Clique em **Abrir Painel Agora** para testar na hora.

A partir daí, toda vez que você abrir o OBS Studio, a telinha abrirá automaticamente no canto inferior direito e fechará junto com o OBS.

---

## Para desenvolvedores (rodar ou editar o código-fonte)

Se quiser modificar o `obs_painel.py` e gerar um novo `.exe`:

```bash
pip install obsws-python pillow pyinstaller
python -m PyInstaller --onefile --windowed --noconfirm --clean --name obs_painel obs_painel.py
```

No topo do `obs_painel.py`, você pode ajustar:
- `PREVIEW_LARGURA` e `PREVIEW_ALTURA` — Tamanho do mini preview (padrão: `160x90`).
- `PREVIEW_INTERVALO_MS` — Velocidade de atualização do preview em milissegundos (padrão: `150`, cerca de 6–7 FPS).
- `MARGEM_X` e `MARGEM_Y` — Distância da borda direita e da parte inferior da tela (padrão: `18` e `100`).

---

## Solução de problemas

- **Aparece `"Ative o WebSocket no OBS (Ferramentas)"`:** O servidor WebSocket está desativado no OBS. Ative conforme o **Passo 1**.
- **Aviso do Windows Defender / SmartScreen na primeira execução:** Clique em **Mais informações → Executar assim mesmo** (ocorre porque o `.exe` não possui assinatura digital comercial).
