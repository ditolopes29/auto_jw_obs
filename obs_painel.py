import base64
import ctypes
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

MARGEM_X = 18                # Distância das bordas laterais da tela
MARGEM_Y_INFERIOR = 100      # Distância da borda inferior (acima da barra de tarefas)
MARGEM_Y_SUPERIOR = 18       # Distância da borda superior

CANTOS_VALIDOS = {
    "inferior_direito": "Inferior Direito",
    "inferior_esquerdo": "Inferior Esquerdo",
    "superior_direito": "Superior Direito",
    "superior_esquerdo": "Superior Esquerdo",
}

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
COR_LIVE = "#dc2626"
COR_REC = "#d97706"


def garantir_instancia_unica():
    """Impede que duas janelas do painel abram ao mesmo tempo no Windows."""
    if os.name != "nt":
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    mutex = kernel32.CreateMutexW(None, False, "Local\\OBS_Painel_Compacto_Mutex")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        if mutex:
            kernel32.CloseHandle(mutex)
        return None
    return mutex


def caminho_preferencias() -> str:
    appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
    return os.path.join(appdata, "obs_painel_config.json")


def carregar_preferencias() -> dict:
    padrao = {"canto": "inferior_direito", "opacidade": 1.0}
    try:
        with open(caminho_preferencias(), "r", encoding="utf-8") as f:
            dados = json.load(f)
        canto = dados.get("canto", padrao["canto"])
        opacidade = float(dados.get("opacidade", padrao["opacidade"]))
        if canto not in CANTOS_VALIDOS:
            canto = padrao["canto"]
        if opacidade not in (0.8, 1.0):
            opacidade = 1.0
        return {"canto": canto, "opacidade": opacidade}
    except Exception:
        return padrao


def salvar_preferencias(prefs: dict):
    try:
        with open(caminho_preferencias(), "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=2)
    except Exception:
        pass


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
            porta = int(data_port) if (data_port := dados.get("server_port")) is not None else OBS_PORT_PADRAO
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

        self._prefs = carregar_preferencias()
        self.root.attributes("-alpha", self._prefs["opacidade"])

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
        self._forcar_atualizacao_cenas = False
        self._estado_midia = (False, False)  # (ao_vivo, gravando)

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

        # Indicador discreto sobreposto ao canto do preview (sem aumentar a janela)
        self.lbl_status_midia = tk.Label(
            self.lbl_preview,
            text="",
            bg=COR_LIVE,
            fg="#ffffff",
            font=("Segoe UI", 7, "bold"),
            padx=4,
            pady=0,
        )

        self.frame_botoes = tk.Frame(root, bg=COR_FUNDO)
        self.frame_botoes.pack(fill=tk.BOTH, expand=True, padx=3, pady=(0, 3))

        self._criar_menu_contexto()
        self._vincular_menu_contexto(self.root)
        self._vincular_menu_contexto(self.lbl_preview)
        self._vincular_menu_contexto(self.lbl_status_midia)
        self._vincular_menu_contexto(self.frame_botoes)

        self.root.protocol("WM_DELETE_WINDOW", self.ao_fechar)

        # Inicia workers em segundo plano e loop de renderização da UI
        threading.Thread(target=self._loop_obs, daemon=True).start()
        self._posicionar_na_tela()
        self._loop_render_ui()

    # ==========================================
    # MENU DE CONTEXTO (BOTÃO DIREITO) E POSIÇÃO
    # ==========================================
    def _criar_menu_contexto(self):
        self._menu = tk.Menu(self.root, tearoff=0, bg=COR_BOTAO, fg=COR_TEXTO)

        self._menu_cantos = tk.Menu(self._menu, tearoff=0, bg=COR_BOTAO, fg=COR_TEXTO)
        self._var_canto = tk.StringVar(value=self._prefs["canto"])
        for chave, rotulo in CANTOS_VALIDOS.items():
            self._menu_cantos.add_radiobutton(
                label=rotulo,
                variable=self._var_canto,
                value=chave,
                command=lambda c=chave: self._definir_canto(c),
            )

        self._var_transparencia = tk.BooleanVar(value=self._prefs["opacidade"] < 1.0)

        self._menu.add_cascade(label="Canto da tela", menu=self._menu_cantos)
        self._menu.add_checkbutton(
            label="Semitransparente (80%)",
            variable=self._var_transparencia,
            command=self._alternar_transparencia,
        )
        self._menu.add_command(label="Voltar ao canto padrão", command=self._posicionar_na_tela)
        self._menu.add_command(label="Recarregar cenas", command=self._solicitar_recarregar_cenas)
        self._menu.add_separator()
        self._menu.add_command(label="Fechar", command=self.ao_fechar)

    def _vincular_menu_contexto(self, widget):
        widget.bind("<Button-3>", self._abrir_menu_contexto)

    def _abrir_menu_contexto(self, event):
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()

    def _definir_canto(self, canto: str):
        self._prefs["canto"] = canto
        salvar_preferencias(self._prefs)
        self._posicionar_na_tela()

    def _alternar_transparencia(self):
        opacidade = 0.8 if self._var_transparencia.get() else 1.0
        self._prefs["opacidade"] = opacidade
        salvar_preferencias(self._prefs)
        self.root.attributes("-alpha", opacidade)

    def _solicitar_recarregar_cenas(self):
        self._forcar_atualizacao_cenas = True

    def _posicionar_na_tela(self):
        """Posiciona o painel no canto escolhido sem cobrir a barra de tarefas."""
        self.root.update_idletasks()
        largura_janela = max(self.root.winfo_width(), self.root.winfo_reqwidth())
        altura_janela = max(self.root.winfo_height(), self.root.winfo_reqheight()) + 30
        largura_tela = self.root.winfo_screenwidth()
        altura_tela = self.root.winfo_screenheight()

        canto = self._prefs.get("canto", "inferior_direito")
        if "esquerdo" in canto:
            pos_x = MARGEM_X
        else:
            pos_x = max(0, largura_tela - largura_janela - MARGEM_X)

        if "superior" in canto:
            pos_y = MARGEM_Y_SUPERIOR
        else:
            pos_y = max(0, altura_tela - altura_janela - MARGEM_Y_INFERIOR)

        self.root.geometry(f"+{pos_x}+{pos_y}")

    # ==========================================
    # CONEXÃO E LOOP DO OBS
    # ==========================================
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
        """Thread em segundo plano: conecta, atualiza cenas, status e preview."""
        ultima_checagem_cenas = 0.0
        ultima_checagem_midia = 0.0
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
                ultima_checagem_midia = 0.0

            inicio_ciclo = time.monotonic()
            try:
                # 1. Descobre a cena ativa
                cena_atual = self._cl_preview.get_current_program_scene().current_program_scene_name

                # 2. Atualiza lista de cenas a cada 3s, quando solicitado ou surgir cena nova
                agora = time.monotonic()
                if (
                    self._forcar_atualizacao_cenas
                    or (agora - ultima_checagem_cenas >= 3.0)
                    or (cena_atual not in self._ordem_cenas)
                ):
                    resp_cenas = self._cl_preview.get_scene_list()
                    nomes_cenas = [c["sceneName"] for c in reversed(resp_cenas.scenes)]
                    if nomes_cenas != self._ordem_cenas or self._forcar_atualizacao_cenas:
                        self._ordem_cenas = nomes_cenas
                        self._agendar_ui(lambda c=list(nomes_cenas): self._reconstruir_botoes(c))
                    self._forcar_atualizacao_cenas = False
                    ultima_checagem_cenas = agora

                if cena_atual != self._cena_ativa:
                    self._cena_ativa = cena_atual
                    self._agendar_ui(lambda c=cena_atual: self._destacar_cena_ativa(c))

                # 3. Checa status LIVE / REC a cada 1s
                if agora - ultima_checagem_midia >= 1.0:
                    ao_vivo = bool(self._cl_preview.get_stream_status().output_active)
                    gravando = bool(self._cl_preview.get_record_status().output_active)
                    if (ao_vivo, gravando) != self._estado_midia:
                        self._estado_midia = (ao_vivo, gravando)
                        self._agendar_ui(
                            lambda lv=ao_vivo, rc=gravando: self._atualizar_badge_midia(lv, rc)
                        )
                    ultima_checagem_midia = agora

                # 4. Captura screenshot em JPEG (muito mais leve que PNG)
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
                self._estado_midia = (False, False)
                self._agendar_ui(lambda: self._atualizar_badge_midia(False, False))
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

    # ==========================================
    # RENDERIZAÇÃO DA INTERFACE
    # ==========================================
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
                self._posicionar_na_tela()

        self.root.after(30, self._loop_render_ui)

    def _atualizar_badge_midia(self, ao_vivo: bool, gravando: bool):
        if not ao_vivo and not gravando:
            self.lbl_status_midia.place_forget()
            return

        partes = []
        if ao_vivo:
            partes.append("● LIVE")
        if gravando:
            partes.append("● REC")
        cor = COR_LIVE if ao_vivo else COR_REC
        self.lbl_status_midia.config(text="  ".join(partes), bg=cor)
        self.lbl_status_midia.place(relx=0.03, rely=0.05, anchor="nw")

    def _mostrar_status(self, texto: str, cor: str):
        self.lbl_status_midia.place_forget()
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
            self._vincular_menu_contexto(btn)
            btn.pack(fill=tk.X, pady=1)
            self._botoes_cenas[nome_cena] = btn

        if self._cena_ativa:
            self._destacar_cena_ativa(self._cena_ativa)

        self._posicionar_na_tela()

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
    _mutex_instancia = garantir_instancia_unica()
    if os.name == "nt" and _mutex_instancia is None:
        sys.exit(0)

    app_root = tk.Tk()
    app = PainelOBS(app_root)
    app_root.mainloop()
