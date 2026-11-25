# Painel Compacto OBS (`auto_jw_obs`)

Mini painel flutuante para **OBS Studio** no Windows: exibe um preview em tempo real da cena ativa e botões rápidos para trocar de cena sem ocupar espaço na tela, abrindo e fechando automaticamente junto com o OBS.

## Arquivos do projeto

- **`obs_painel.py`** — Painel compacto (*always on top*) com preview em tempo real, destaque da cena ativa, reconexão automática e leitura automática de porta/senha do OBS WebSocket.
- **`obs_abrir_painel.lua`** — Script Lua para o OBS Studio que abre o painel automaticamente ao iniciar o OBS e o encerra quando o OBS é fechado.
- **`auto_jw_obs.py`** — Automação complementar para alternar para a cena `JW` com `Ctrl + Clique` no JW Library e retornar com `Esc`.

---

## Requisitos

- **Windows**
- **OBS Studio 28 ou superior** (já vem com OBS WebSocket embutido)
- **Python 3.10+** instalado

---

## Como instalar em um novo computador

### 1. Instalar as dependências do Python

Abra o terminal (PowerShell ou CMD) e execute:

```bash
pip install obsws-python pillow
```

*(Caso também utilize o `auto_jw_obs.py`, instale também `pip install pynput pywin32`.)*

### 2. Ativar o WebSocket no OBS Studio

1. Abra o **OBS Studio**.
2. Vá em **Ferramentas → Configurações do servidor WebSocket**.
3. Marque a opção **Habilitar servidor WebSocket** e clique em **OK**.

> **Nota:** Não é necessário configurar porta nem senha no código. O `obs_painel.py` lê automaticamente o arquivo de configuração local do OBS (`%APPDATA%\obs-studio\plugin_config\obs-websocket\config.json`).

### 3. Configurar a abertura automática no OBS

1. No OBS Studio, vá em **Ferramentas → Scripts**.
2. Clique no botão **`+`** e selecione o arquivo `obs_abrir_painel.lua`.
3. Em **Caminho do Painel**, clique em **Procurar** e selecione `obs_painel.py` (ou `.exe`, caso gere um executável no futuro).
4. Deixe marcada a opção **Fechar o painel quando o OBS fechar**.
5. Clique em **Abrir Painel Agora** para testar na hora.

A partir daí, toda vez que você abrir o OBS Studio, a telinha abrirá automaticamente no canto inferior direito e fechará junto com o OBS.

---

## Ajustes rápidos (`obs_painel.py`)

No topo do arquivo `obs_painel.py`, você pode personalizar:

- `PREVIEW_LARGURA` e `PREVIEW_ALTURA` — Tamanho do mini preview (padrão: `160x90`).
- `PREVIEW_INTERVALO_MS` — Velocidade de atualização do preview em milissegundos (padrão: `150`, cerca de 6–7 FPS).
- `MARGEM_X` e `MARGEM_Y` — Distância da borda direita e da parte inferior da tela (padrão: `18` e `100`). Aumente `MARGEM_Y` se quiser a telinha ainda mais alta.

---

## Solução de problemas

- **Aparece `"Ative o WebSocket no OBS (Ferramentas)"`:** O servidor WebSocket está desativado no OBS. Ative conforme o **Passo 2**.
- **O painel abre manualmente, mas não abre com o OBS:** Verifique se o `pythonw` está acessível no PATH do Windows (testando `pythonw obs_painel.py` no terminal) e se o caminho selecionado em **Ferramentas → Scripts** está correto.
