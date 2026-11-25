import base64
import json
import os
import sys
import threading
import time
import tkinter as tk
from io import BytesIO

import obsws_python as obs
from PIL import Image, ImageTk

# ==========================================
# CONFIGURAÇÕES (FALLBACK CASO NÃO ENCONTRE O OBS)
# ==========================================
OBS_HOST = "localhost"
OBS_PORT_PADRAO = 4455
OBS_PASSWORD_PADRAO = "123456"

PREVIEW_LARGURA = 160
PREVIEW_ALTURA = 90
PREVIEW_INTERVALO_MS = 150   # ~6-7 FPS (bem mais fluido sem pesar na CPU)
PREVIEW_QUALIDADE_JPEG = 70  # 1-100 (JPEG é muito mais rápido que PNG)
RECONEXAO_SEGUNDOS = 2.0
MARGEM_X = 18                # Distância da borda direita da tela
MARGEM_Y = 100               # Distância da borda inferior (mais acima da barra de tarefas)

# Cores da interface
COR_FUNDO = "#18181b"
COR_PREVIEW_BG = "#09090b"
COR_BOTAO = "#27272a"
COR_BOTAO_HOVER = "#3f3f46"
COR_BOTAO_ATIVO = "#16a34a"
COR_BOTAO_ATIVO_HOVER = "#15803d"
COR_TEXTO = "#f4f4f5"
COR_TEXTO_MUTED = "#a1a1aa"
COR_STATUS_OFFLINE = "#ef4444"


def carregar_config_obs() -> tuple[str, int, str, bool]:
    """Lê porta e senha diretamente do config.json do obs-websocket no Windows."""
    appdata = os.environ.get("APPDATA", "")
    caminho_cfg = os.path.join(
        appdata, "obs-studio", "plugin_config", "obs-websocket", "config.json"
    )
    if os.path.isfile(caminho_cfg):
        try:
            with open(caminho_cfg, "r", encoding="utf-8") as f:
                dados = json.load(f)
            habilitado = bool(dados.get("server_enabled", True))
            porta = int(dados.get("server_port", OBS_PORT_PADRAO))
            exige_auth = bool(dados.get("auth_required", True))
            senha = str(dados.get("server_password", "")) if exige_auth else ""
            return OBS_HOST, porta, senha, habilitado
        except Exception:
            pass
    return OBS_HOST, OBS_PORT_PADRAO, OBS_PASSWORD_PADRAO, True


class PainelOBS:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("OBS")
        self.root.attributes("-topmost", True)
        self.root.attributes("-toolwindow", True)
        self.root.configure(bg=COR_FUNDO)
        self.root.resizable(False, False)

        self._executando = True
        self._conectado = False
        self._ja_conectou = False
        self._fechar_ao_desconectar = "--fechar-com-obs" in sys.argv
        self._cl_preview: obs.ReqClient | None = None
        self._cl_comando: obs.ReqClient | None = None
        self._lock_comando = threading.Lock()

        self._botoes_cenas: dict[str, tk.Button] = {}
        self._ordem_cenas: list[str] = []
        self._cena_ativa: str | None = None
        self._primeiro_frame = True

        # Controle de frame mais recente (evita acúmulo na fila da UI)
        self._lock_frame = threading.Lock()
        self._ultimo_frame_pil: Image.Image | None = None
        self._frame_atualizado = False

        # ==========================================
        # INTERFACE GRÁFICA COMPACTA
        # ==========================================
        self.lbl_preview = tk.Label(
            root,
            text="Conectando...",
            bg=COR_PREVIEW_BG,
            fg=COR_TEXTO_MUTED,
            font=("Segoe UI", 8),
            width=22,
            height=5,
        )
        self.lbl_preview.pack(padx=3, pady=(3, 2))

        self.frame_botoes = tk.Frame(root, bg=COR_FUNDO)
        self.frame_botoes.pack(fill=tk.BOTH, expand=True, padx=3, pady=(0, 3))

        self.root.protocol("WM_DELETE_WINDOW", self.ao_fechar)

        # Inicia workers em segundo plano e loop de renderização da UI
        threading.Thread(target=self._loop_obs, daemon=True).start()
        self._posicionar_canto_inferior_direito()
        self._loop_render_ui()

    def _posicionar_canto_inferior_direito(self):
        """Posiciona o painel no canto inferior direito, com folga acima da barra de tarefas."""
        self.root.update_idletasks()
        largura_janela = max(self.root.winfo_width(), self.root.winfo_reqwidth())
        altura_janela = max(self.root.winfo_height(), self.root.winfo_reqheight()) + 30
        largura_tela = self.root.winfo_screenwidth()
        altura_tela = self.root.winfo_screenheight()

        pos_x = max(0, largura_tela - largura_janela - MARGEM_X)
        pos_y = max(0, altura_tela - altura_janela - MARGEM_Y)
        self.root.geometry(f"+{pos_x}+{pos_y}")

    def _conectar_obs(self) -> tuple[bool, bool]:
        """Tenta estabelecer conexões separadas para preview e comandos.
        Retorna (conectado, websocket_habilitado).
        """
        self._desconectar_obs()
        host, porta, senha, habilitado = carregar_config_obs()
        if not habilitado:
            return False, False

        kwargs = {"host": host, "port": porta, "timeout": 3}
        if senha:
            kwargs["password"] = senha

        try:
            cl_prev = obs.ReqClient(**kwargs)
            cl_cmd = obs.ReqClient(**kwargs)
            self._cl_preview = cl_prev
            self._cl_comando = cl_cmd
            self._conectado = True
            return True, True
        except Exception:
            self._desconectar_obs()
            return False, True

    def _desconectar_obs(self):
        self._conectado = False
        for attr in ("_cl_preview", "_cl_comando"):
            cliente = getattr(self, attr, None)
            if cliente is not None:
                try:
                    cliente.disconnect()
                except Exception:
                    pass
                setattr(self, attr, None)

    def _loop_obs(self):
        """Thread em segundo plano: conecta, atualiza cenas e busca frames do preview."""
        ultima_checagem_cenas = 0.0
        intervalo_s = PREVIEW_INTERVALO_MS / 1000.0

        while self._executando:
            if not self._conectado:
                self._agendar_ui(lambda: self._mostrar_status("Conectando ao OBS...", COR_TEXTO_MUTED))
                conectado, ws_habilitado = self._conectar_obs()
                if not conectado:
                    if self._fechar_ao_desconectar and self._ja_conectou:
                        self._agendar_ui(self.ao_fechar)
                        return
                    msg = (
                        "OBS offline"
                        if ws_habilitado
                        else "Ative o WebSocket\nno OBS (Ferramentas)"
                    )
                    self._agendar_ui(lambda m=msg: self._mostrar_status(m, COR_STATUS_OFFLINE))
                    time.sleep(RECONEXAO_SEGUNDOS)
                    continue
                self._ja_conectou = True
                ultima_checagem_cenas = 0.0

            inicio_ciclo = time.monotonic()
            try:
                # 1. Descobre a cena ativa
                cena_atual = self._cl_preview.get_current_program_scene().current_program_scene_name

                # 2. Atualiza lista de cenas a cada 3s ou quando surgir cena nova
                agora = time.monotonic()
                if (agora - ultima_checagem_cenas >= 3.0) or (cena_atual not in self._ordem_cenas):
                    resp_cenas = self._cl_preview.get_scene_list()
                    nomes_cenas = [c["sceneName"] for c in reversed(resp_cenas.scenes)]
                    if nomes_cenas != self._ordem_cenas:
                        self._ordem_cenas = nomes_cenas
                        self._agendar_ui(lambda c=list(nomes_cenas): self._reconstruir_botoes(c))
                    ultima_checagem_cenas = agora

                if cena_atual != self._cena_ativa:
                    self._cena_ativa = cena_atual
                    self._agendar_ui(lambda c=cena_atual: self._destacar_cena_ativa(c))

                # 3. Captura screenshot em JPEG (muito mais leve que PNG)
                resp_img = self._cl_preview.get_source_screenshot(
                    cena_atual,
                    "jpeg",
                    PREVIEW_LARGURA,
                    PREVIEW_ALTURA,
                    PREVIEW_QUALIDADE_JPEG,
                )
                dados_b64 = resp_img.image_data.split(",", 1)[1]
                img_bytes = base64.b64decode(dados_b64)
                img_pil = Image.open(BytesIO(img_bytes))
                img_pil.load()

                with self._lock_frame:
                    self._ultimo_frame_pil = img_pil
                    self._frame_atualizado = True

            except Exception:
                self._desconectar_obs()
                if self._fechar_ao_desconectar and self._ja_conectou:
                    time.sleep(0.8)
                    conectado, _ = self._conectar_obs()
                    if not conectado:
                        self._agendar_ui(self.ao_fechar)
                        return
                continue

            decorrido = time.monotonic() - inicio_ciclo
            restante = intervalo_s - decorrido
            if restante > 0:
                time.sleep(restante)

    def _agendar_ui(self, fn):
        if self._executando:
            try:
                self.root.after(0, fn)
            except tk.TclError:
                pass

    def _loop_render_ui(self):
        """Aplica o frame mais recente na UI sem bloquear o loop de eventos."""
        if not self._executando:
            return

        img_para_exibir = None
        with self._lock_frame:
            if self._frame_atualizado and self._ultimo_frame_pil is not None:
                img_para_exibir = self._ultimo_frame_pil
                self._frame_atualizado = False

        if img_para_exibir is not None:
            img_tk = ImageTk.PhotoImage(img_para_exibir)
            self.lbl_preview.config(
                image=img_tk,
                text="",
                width=PREVIEW_LARGURA,
                height=PREVIEW_ALTURA,
            )
            self.lbl_preview.image = img_tk
            if self._primeiro_frame:
                self._primeiro_frame = False
                self._posicionar_canto_inferior_direito()

        self.root.after(30, self._loop_render_ui)

    def _mostrar_status(self, texto: str, cor: str):
        self.lbl_preview.config(
            image="",
            text=texto,
            fg=cor,
            width=22,
            height=5,
        )
        self.lbl_preview.image = None

    def _reconstruir_botoes(self, nomes_cenas: list[str]):
        for widget in self.frame_botoes.winfo_children():
            widget.destroy()
        self._botoes_cenas.clear()

        for nome_cena in nomes_cenas:
            btn = tk.Button(
                self.frame_botoes,
                text=nome_cena,
                command=lambda c=nome_cena: self.mudar_cena(c),
                bg=COR_BOTAO,
                fg=COR_TEXTO,
                activebackground=COR_BOTAO_HOVER,
                activeforeground=COR_TEXTO,
                font=("Segoe UI", 8),
                relief=tk.FLAT,
                bd=0,
                padx=6,
                pady=3,
                cursor="hand2",
                anchor="w",
            )
            btn.bind("<Enter>", lambda e, c=nome_cena: self._ao_entrar_botao(c))
            btn.bind("<Leave>", lambda e, c=nome_cena: self._ao_sair_botao(c))
            btn.pack(fill=tk.X, pady=1)
            self._botoes_cenas[nome_cena] = btn

        if self._cena_ativa:
            self._destacar_cena_ativa(self._cena_ativa)

        self._posicionar_canto_inferior_direito()

    def _destacar_cena_ativa(self, cena_ativa: str):
        for nome, btn in self._botoes_cenas.items():
            if nome == cena_ativa:
                btn.config(bg=COR_BOTAO_ATIVO, font=("Segoe UI", 8, "bold"))
            else:
                btn.config(bg=COR_BOTAO, font=("Segoe UI", 8))

    def _ao_entrar_botao(self, nome_cena: str):
        btn = self._botoes_cenas.get(nome_cena)
        if not btn:
            return
        cor = COR_BOTAO_ATIVO_HOVER if nome_cena == self._cena_ativa else COR_BOTAO_HOVER
        btn.config(bg=cor)

    def _ao_sair_botao(self, nome_cena: str):
        btn = self._botoes_cenas.get(nome_cena)
        if not btn:
            return
        cor = COR_BOTAO_ATIVO if nome_cena == self._cena_ativa else COR_BOTAO
        btn.config(bg=cor)

    def mudar_cena(self, nome_cena: str):
        """Dispara a troca de cena em segundo plano para nunca travar a UI."""
        self._cena_ativa = nome_cena
        self._destacar_cena_ativa(nome_cena)

        def _enviar():
            with self._lock_comando:
                if not self._cl_comando:
                    return
                try:
                    self._cl_comando.set_current_program_scene(nome_cena)
                except Exception as e:
                    print(f"Erro ao mudar de cena: {e}")

        threading.Thread(target=_enviar, daemon=True).start()

    def ao_fechar(self):
        self._executando = False
        self._desconectar_obs()
        self.root.destroy()


# ==========================================
# INICIALIZAÇÃO DO APLICATIVO
# ==========================================
if __name__ == "__main__":
    app_root = tk.Tk()
    app = PainelOBS(app_root)
    app_root.mainloop()
