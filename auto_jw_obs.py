import time
from pynput import mouse, keyboard
import win32gui
import obsws_python as obs

# ==========================================
# CONFIGURAÇÕES DO OBS
# ==========================================
OBS_HOST = "localhost"
OBS_PORT = 4455
OBS_PASSWORD = "123456" 
NOME_CENA_JW = "JW"

ctrl_pressionado = False
cena_anterior = None  # Variável para guardar de onde viemos

# ==========================================
# CONEXÃO COM O OBS
# ==========================================
try:
    print("Tentando conectar ao OBS Studio...")
    cl = obs.ReqClient(host=OBS_HOST, port=OBS_PORT, password=OBS_PASSWORD)
    print("Conectado ao OBS com sucesso!")
except Exception as e:
    print(f"Erro ao conectar no OBS. Verifique as configurações.\nErro: {e}")
    exit()

# ==========================================
# LÓGICA DO TECLADO (Monitorar CTRL e ESC)
# ==========================================
def on_press(key):
    global ctrl_pressionado, cena_anterior
    
    if key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
        ctrl_pressionado = True
        
    # Lógica de RETORNO: Se apertar ESC, volta para a cena salva
    if key == keyboard.Key.esc:
        if cena_anterior:
            print(f">>> ESC pressionado! Retornando para a cena: {cena_anterior}")
            try:
                cl.set_current_program_scene(cena_anterior)
                cena_anterior = None  # Limpa a memória após voltar
            except Exception as e:
                print(f"Erro ao voltar cena: {e}")

def on_release(key):
    global ctrl_pressionado
    if key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
        ctrl_pressionado = False

# ==========================================
# LÓGICA DO MOUSE (CTRL + Clique)
# ==========================================
def on_click(x, y, button, pressed):
    global ctrl_pressionado, cena_anterior
    
    if pressed and button == mouse.Button.left:
        hwnd = win32gui.GetForegroundWindow()
        titulo_janela = win32gui.GetWindowText(hwnd)
        
        if ctrl_pressionado and "JW Library" in titulo_janela:
            try:
                # 1. Pega a cena atual ANTES de mudar
                resp = cl.get_current_program_scene()
                cena_atual = resp.current_program_scene_name
                
                # Só salva se não estivermos já na cena JW (evita loop na memória)
                if cena_atual != NOME_CENA_JW:
                    cena_anterior = cena_atual
                    print(f"[MEMÓRIA] Cena original '{cena_anterior}' salva.")
                
                # 2. Muda para o JW
                print(f">>> Mídia acionada! Mudando para: {NOME_CENA_JW}")
                cl.set_current_program_scene(NOME_CENA_JW)
                
            except Exception as e:
                print(f"Erro na comunicação com o OBS: {e}")

print("\n=== AUTOMATIZAÇÃO JW + OBS ATIVADA ===")
print("1. Segure CTRL + Clique na mídia para enviar pro telão.")
print("2. Pressione ESC para interromper/finalizar a mídia e voltar para a câmera.")
print("Pressione Ctrl+C no terminal para encerrar.")

# ==========================================
# INICIAR LISTENERS
# ==========================================
listener_teclado = keyboard.Listener(on_press=on_press, on_release=on_release)
listener_mouse = mouse.Listener(on_click=on_click)

listener_teclado.start()
listener_mouse.start()
listener_teclado.join()
listener_mouse.join()