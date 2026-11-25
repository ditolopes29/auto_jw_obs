obs = obslua

local caminho_painel = ""
local fechar_ao_sair = true
local ja_iniciou = false

local function arquivo_existe(caminho)
    if caminho == nil or caminho == "" then
        return false
    end
    local f = io.open(caminho, "r")
    if f ~= nil then
        io.close(f)
        return true
    end
    return false
end

local function extrair_nome_arquivo(caminho)
    return caminho:match("([^\\/]+)$")
end

local function abrir_painel()
    if not arquivo_existe(caminho_painel) then
        obs.script_log(obs.LOG_WARNING, "[Painel OBS] Arquivo não encontrado: " .. tostring(caminho_painel))
        return
    end

    local ext = caminho_painel:lower():match("%.([^%.]+)$")
    local arg_fechar = fechar_ao_sair and " --fechar-com-obs" or ""
    local comando

    if ext == "py" or ext == "pyw" then
        comando = string.format('start "" pythonw "%s"%s', caminho_painel, arg_fechar)
    else
        comando = string.format('start "" "%s"%s', caminho_painel, arg_fechar)
    end

    obs.script_log(obs.LOG_INFO, "[Painel OBS] Iniciando: " .. caminho_painel)
    os.execute(comando)
end

local function timer_inicializacao()
    obs.remove_current_callback()
    if not ja_iniciou and caminho_painel ~= "" then
        ja_iniciou = true
        abrir_painel()
    end
end

local function ao_clicar_abrir(props, prop)
    abrir_painel()
    return false
end

-- ==========================================
-- FUNÇÕES PADRÃO DO OBS LUA
-- ==========================================
function script_description()
    return [[
<h3>Painel OBS Automático</h3>
<p>Abre a telinha de cenas automaticamente junto com o OBS Studio.</p>
<p>Selecione abaixo o arquivo <b>obs_painel.exe</b> (ou <b>obs_painel.py</b> para testes).</p>
]]
end

function script_properties()
    local props = obs.obs_properties_create()

    obs.obs_properties_add_path(
        props,
        "caminho_painel",
        "Caminho do Painel",
        obs.OBS_PATH_FILE,
        "Executável (*.exe);;Script Python (*.py;*.pyw);;Todos (*.*)",
        nil
    )

    obs.obs_properties_add_bool(
        props,
        "fechar_ao_sair",
        "Fechar o painel quando o OBS fechar"
    )

    obs.obs_properties_add_button(
        props,
        "btn_abrir",
        "Abrir Painel Agora",
        ao_clicar_abrir
    )

    return props
end

function script_defaults(settings)
    obs.obs_data_set_default_bool(settings, "fechar_ao_sair", true)
end

function script_update(settings)
    caminho_painel = obs.obs_data_get_string(settings, "caminho_painel")
    fechar_ao_sair = obs.obs_data_get_bool(settings, "fechar_ao_sair")
end

function script_load(settings)
    script_update(settings)
    ja_iniciou = false
    if caminho_painel ~= "" then
        -- Aguarda 1,5s para o OBS terminar de subir o WebSocket antes de abrir o painel
        obs.timer_add(timer_inicializacao, 1500)
    end
end

function script_unload()
    if fechar_ao_sair and caminho_painel ~= "" then
        local nome = extrair_nome_arquivo(caminho_painel)
        if nome and nome:lower():match("%.exe$") then
            os.execute(string.format('taskkill /F /IM "%s" >nul 2>&1', nome))
        end
    end
end
