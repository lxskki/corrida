import asyncio
from pyodide.ffi import create_proxy
from js import document, window, console
from card_logic import GameState, Card
import time

# --- Constantes do Visual ---
COLOR_FELT = "#2d5a27"  # Mesa Verde
COLOR_WHITE = "#ffffff"
COLOR_RED = "#d63031"
COLOR_BLACK = "#2d3436"
COLOR_PLACEHOLDER = "rgba(0, 0, 0, 0.2)"
COLOR_GOLD = "#f1c40f"
COLOR_HINT = "rgba(241, 196, 15, 0.9)"
COLOR_OVERLAY = "rgba(0,0,0,0.45)"

# --- Globais de Layout (recalculadas por DPR) ---
DPR = 1.0
CARD_WIDTH = 100
CARD_HEIGHT = 145
CARD_GAP = 15
TABLEAU_OFFSET_Y = 200
TABLEAU_CARD_SPACING = 35
CORNER_RADIUS = 10

# --- Estado de Renderização ---
state = GameState()
selected_cards = []   # Cartas sendo arrastadas (lista)
drag_source = None    # Referência da pilha original (lista)
mouse_start_x = 0
mouse_start_y = 0
drag_start_x = 0
drag_start_y = 0
current_mouse_x = 0
current_mouse_y = 0
hint_timer = 0.0
active_hint = None
game_won = False

# Armazena proxies para evitar GC pelo Pyodide
_proxies = []

# --- Setup do Canvas ---
canvas = document.getElementById("game-canvas")
ctx = canvas.getContext("2d")

def update_dimensions():
    """Atualiza medidas em função do devicePixelRatio (DPR)."""
    global DPR, CARD_WIDTH, CARD_HEIGHT, CARD_GAP, TABLEAU_OFFSET_Y, TABLEAU_CARD_SPACING, CORNER_RADIUS
    DPR = float(window.devicePixelRatio or 1.0)
    CARD_WIDTH = 110 * DPR
    CARD_HEIGHT = 160 * DPR
    CARD_GAP = 20 * DPR
    TABLEAU_OFFSET_Y = 240 * DPR
    TABLEAU_CARD_SPACING = 35 * DPR
    CORNER_RADIUS = 12 * DPR

_last_w = 0
_last_h = 0
def resize_canvas_to_dpr():
    """Ajusta canvas.width/height ao tamanho CSS * DPR (evita borrado)."""
    global _last_w, _last_h
    rect = canvas.getBoundingClientRect()
    target_w = max(1, int(rect.width * DPR))
    target_h = max(1, int(rect.height * DPR))
    if target_w != _last_w or target_h != _last_h:
        canvas.width = target_w
        canvas.height = target_h
        _last_w, _last_h = target_w, target_h

# --- Funções de Desenho ---
def draw_rounded_rect(ctx, x, y, w, h, r, color, stroke=None):
    ctx.beginPath()
    ctx.moveTo(x + r, y)
    ctx.lineTo(x + w - r, y)
    ctx.quadraticCurveTo(x + w, y, x + w, y + r)
    ctx.lineTo(x + w, y + h - r)
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h)
    ctx.lineTo(x + r, y + h)
    ctx.quadraticCurveTo(x, y + h, x, y + h - r)
    ctx.lineTo(x, y + r)
    ctx.quadraticCurveTo(x, y, x + r, y)
    ctx.closePath()
    ctx.fillStyle = color
    ctx.fill()
    if stroke:
        ctx.strokeStyle = stroke
        ctx.lineWidth = 1 * DPR
        ctx.stroke()

def draw_suit_at(ctx, suit, x, y, size, alpha=1.0):
    icons = {'copas': '♥', 'espadas': '♠', 'ouros': '♦', 'paus': '♣'}
    color = COLOR_RED if suit in ['copas', 'ouros'] else COLOR_BLACK
    ctx.save()
    ctx.globalAlpha = alpha
    ctx.fillStyle = color
    ctx.font = f"bold {int(size)}px sans-serif"  # fonte padrão para garantir renderização
    ctx.textAlign = "center"
    ctx.textBaseline = "middle"
    ctx.fillText(icons.get(suit, ''), x, y)
    ctx.restore()

def draw_highlight_rect(x, y, w, h):
    ctx.save()
    ctx.lineWidth = 4 * DPR
    ctx.strokeStyle = COLOR_HINT
    ctx.setLineDash([10 * DPR, 8 * DPR])
    ctx.strokeRect(x + 2*DPR, y + 2*DPR, w - 4*DPR, h - 4*DPR)
    ctx.restore()

def draw_card(ctx, card, x, y):
    try:
        if not card.face_up:
            # Verso da carta
            draw_rounded_rect(ctx, x, y, CARD_WIDTH, CARD_HEIGHT, CORNER_RADIUS,
                              "#1e3799", "rgba(255,255,255,0.2)")
            # Padrão interno
            ctx.save()
            ctx.beginPath()
            ctx.rect(x + 6*DPR, y + 6*DPR, CARD_WIDTH - 12*DPR, CARD_HEIGHT - 12*DPR)
            ctx.clip()
            ctx.strokeStyle = "rgba(255,255,255,0.1)"
            ctx.lineWidth = 3 * DPR
            for i in range(-500, 500, 15):
                ctx.moveTo(x + i*DPR, y)
                ctx.lineTo(x + (i + 300)*DPR, y + 400*DPR)
                ctx.stroke()
            ctx.restore()
        else:
            # Frente
            draw_rounded_rect(ctx, x, y, CARD_WIDTH, CARD_HEIGHT, CORNER_RADIUS,
                              "#ffffff", "rgba(0,0,0,0.1)")
            color = COLOR_RED if card.is_red else COLOR_BLACK
            ctx.fillStyle = color

            # Valor no canto superior
            ctx.font = f"bold {int(22*DPR)}px sans-serif"
            ctx.textAlign = "left"
            ctx.textBaseline = "top"
            ctx.fillText(str(card.value), x + 8*DPR, y + 8*DPR)
            # Naipe pequeno
            draw_suit_at(ctx, card.suit, x + 18*DPR, y + 44*DPR, 16 * DPR)

            # Centro
            if card.value in ['K', 'Q', 'J']:
                emojis = {'K': '👑', 'Q': '👸', 'J': '🫡'}
                ctx.font = f"{int(60*DPR)}px sans-serif"
                ctx.textAlign = "center"
                ctx.textBaseline = "middle"
                ctx.fillText(emojis.get(card.value, card.value), x + CARD_WIDTH/2, y + CARD_HEIGHT/2)
            else:
                draw_suit_at(ctx, card.suit, x + CARD_WIDTH/2, y + CARD_HEIGHT/2, 54 * DPR)

            # Valor invertido no canto inferior
            ctx.save()
            ctx.translate(x + CARD_WIDTH, y + CARD_HEIGHT)
            ctx.rotate(3.14159)
            ctx.font = f"bold {int(22*DPR)}px sans-serif"
            ctx.textAlign = "left"
            ctx.textBaseline = "top"
            ctx.fillText(str(card.value), 8*DPR, 8*DPR)
            draw_suit_at(ctx, card.suit, 18*DPR, 44*DPR, 16 * DPR)
            ctx.restore()
    except Exception as e:
        console.log(f"Erro renderizando carta: {e}")

def check_victory():
    """Vitória se as 4 foundations tiverem 13 cartas cada."""
    try:
        return all(len(p) == 13 for p in state.foundations)
    except Exception:
        return False

# --- Loop de Renderização ---
def render_frame():
    try:
        # fundo (feltro)
        ctx.fillStyle = COLOR_FELT
        ctx.fillRect(0, 0, canvas.width, canvas.height)

        # Linha superior
        y_top = 40 * DPR
        x_stock = 45 * DPR
        draw_rounded_rect(ctx, x_stock, y_top, CARD_WIDTH, CARD_HEIGHT, CORNER_RADIUS, "rgba(0,0,0,0.1)")
        if state.stock:
            draw_card(ctx, state.stock[-1], x_stock, y_top)

        x_waste = x_stock + CARD_WIDTH + CARD_GAP
        if state.waste:
            is_dragging_waste = (drag_source is state.waste)
            if not is_dragging_waste:
                draw_card(ctx, state.waste[-1], x_waste, y_top)

        f_suits = ['paus', 'copas', 'espadas', 'ouros']
        for i in range(4):
            xf = canvas.width - (4 - i) * (CARD_WIDTH + CARD_GAP) - 45 * DPR
            draw_rounded_rect(ctx, xf, y_top, CARD_WIDTH, CARD_HEIGHT, CORNER_RADIUS, COLOR_PLACEHOLDER)
            draw_suit_at(ctx, f_suits[i], xf + CARD_WIDTH/2, y_top + CARD_HEIGHT/2, 45*DPR, 0.15)
            if i < len(state.foundations) and state.foundations[i]:
                draw_card(ctx, state.foundations[i][-1], xf, y_top)

        # Tableau (7 colunas)
        for i in range(7):
            xt = 45 * DPR + i * (CARD_WIDTH + CARD_GAP)
            draw_rounded_rect(ctx, xt, TABLEAU_OFFSET_Y, CARD_WIDTH, CARD_HEIGHT, CORNER_RADIUS, COLOR_PLACEHOLDER)
            if i < len(state.tableau):
                pile = state.tableau[i]
                for j, card in enumerate(pile):
                    if drag_source is pile and card in selected_cards:
                        continue
                    yt = TABLEAU_OFFSET_Y + (j * TABLEAU_CARD_SPACING)
                    draw_card(ctx, card, xt, yt)

        # Cartas arrastadas (por cima)
        if selected_cards:
            ctx.shadowColor = "rgba(0,0,0,0.3)"
            ctx.shadowBlur = 10 * DPR
            for i, card in enumerate(selected_cards):
                dx = current_mouse_x - (mouse_start_x - drag_start_x)
                dy = current_mouse_y - (mouse_start_y - drag_start_y) + (i * TABLEAU_CARD_SPACING)
                draw_card(ctx, card, dx, dy)
            ctx.shadowBlur = 0

        # Dica visual por ~1.25s
        if active_hint:
            if (time.time() - hint_timer) <= 1.25:
                t = active_hint
                if t["type"] in ("waste_to_f", "tab_to_f"):
                    i = t["f_idx"]
                    xf = canvas.width - (4 - i) * (CARD_WIDTH + CARD_GAP) - 45 * DPR
                    draw_highlight_rect(xf, y_top, CARD_WIDTH, CARD_HEIGHT)
                elif t["type"] == "tab_to_tab":
                    j = t["target"]
                    xt = 45 * DPR + j * (CARD_WIDTH + CARD_GAP)
                    draw_highlight_rect(xt, TABLEAU_OFFSET_Y, CARD_WIDTH, CARD_HEIGHT)
            else:
                _clear_hint()

        # Overlay de vitória
        if game_won:
            ctx.save()
            ctx.fillStyle = COLOR_OVERLAY
            ctx.fillRect(0, 0, canvas.width, canvas.height)
            ctx.fillStyle = "#fff"
            ctx.font = f"bold {int(48*DPR)}px sans-serif"
            ctx.textAlign = "center"
            ctx.textBaseline = "middle"
            ctx.fillText("Vitória! 🎉", canvas.width/2, canvas.height/2 - 20*DPR)
            ctx.font = f"{int(20*DPR)}px sans-serif"
            ctx.fillText("Clique em Novo Jogo para recomeçar.", canvas.width/2, canvas.height/2 + 20*DPR)
            ctx.restore()

    except Exception as e:
        console.log(f"CRITICAL RENDER ERROR: {e}")

# --- Entrada do Usuário ---
def on_mousedown(event):
    global mouse_start_x, mouse_start_y, selected_cards, drag_source, drag_start_x, drag_start_y
    rect = canvas.getBoundingClientRect()
    mx = (event.clientX - rect.left) * DPR
    my = (event.clientY - rect.top) * DPR
    mouse_start_x = mx
    mouse_start_y = my

    if not state.start_time:
        state.start_time = time.time()
        console.log("Tempo iniciado!")

    # 1) Estoque
    x_stock = 45 * DPR
    y_top = 40 * DPR
    if x_stock <= mx <= x_stock + CARD_WIDTH and y_top <= my <= y_top + CARD_HEIGHT:
        state.draw_from_stock()
        update_stats()
        return

    # 2) Descarte
    x_waste = x_stock + CARD_WIDTH + CARD_GAP
    if x_waste <= mx <= x_waste + CARD_WIDTH and y_top <= my <= y_top + CARD_HEIGHT:
        if state.waste:
            selected_cards = [state.waste[-1]]
            drag_source = state.waste
            drag_start_x, drag_start_y = x_waste, y_top
            return

    # 3) Tableau
    for i in range(7):
        xt = 45 * DPR + i * (CARD_WIDTH + CARD_GAP)
        if xt <= mx <= xt + CARD_WIDTH:
            pile = state.tableau[i]
            # Percorre de trás para frente
            for j in range(len(pile)-1, -1, -1):
                yt = TABLEAU_OFFSET_Y + j * TABLEAU_CARD_SPACING
                h = CARD_HEIGHT if j == len(pile)-1 else TABLEAU_CARD_SPACING
                if yt <= my <= yt + h:
                    if pile[j].face_up:
                        selected_cards = pile[j:]
                        drag_source = pile
                        drag_start_x, drag_start_y = xt, yt
                        return
                    elif j == len(pile)-1:  # Clicou na carta fechada do topo
                        pile[j].face_up = True
                        state.moves += 1
                        update_stats()
                        return

def on_mousemove(event):
    global current_mouse_x, current_mouse_y
    rect = canvas.getBoundingClientRect()
    current_mouse_x = (event.clientX - rect.left) * DPR
    current_mouse_y = (event.clientY - rect.top) * DPR

def on_mouseup(event):
    global selected_cards, drag_source, game_won
    if not selected_cards:
        return
    rect = canvas.getBoundingClientRect()
    mx = (event.clientX - rect.left) * DPR
    my = (event.clientY - rect.top) * DPR
    moved = False

    # Tenta soltar no Tableau
    for i in range(7):
        xt = 45 * DPR + i * (CARD_WIDTH + CARD_GAP)
        if xt <= mx <= xt + CARD_WIDTH and my > TABLEAU_OFFSET_Y - 50*DPR:
            if state.can_move_to_tableau(selected_cards[0], state.tableau[i]):
                for c in selected_cards:
                    drag_source.remove(c)
                    state.tableau[i].append(c)
                state.moves += 1
                state.score += 5
                moved = True
                break

    # Tenta soltar nas Fundações
    if not moved and len(selected_cards) == 1:
        for i in range(4):
            xf = canvas.width - (4 - i) * (CARD_WIDTH + CARD_GAP) - 45 * DPR
            if xf <= mx <= xf + CARD_WIDTH and 40*DPR <= my <= 40*DPR + CARD_HEIGHT:
                if state.can_move_to_foundation(selected_cards[0], i):
                    target = selected_cards[0]
                    drag_source.remove(target)
                    state.foundations[i].append(target)
                    state.moves += 1
                    state.score += 10
                    moved = True
                    break

    # Se moveu a partir de um tableau, vira a carta exposta (se existir)
    if moved and drag_source in state.tableau:
        if drag_source and len(drag_source) > 0 and not drag_source[-1].face_up:
            drag_source[-1].face_up = True
            state.score += 5

    selected_cards = []
    drag_source = None
    update_stats()

    # Checa vitória
    if not game_won and check_victory():
        game_won = True

def on_dblclick(event):
    rect = canvas.getBoundingClientRect()
    mx = (event.clientX - rect.left) * DPR
    my = (event.clientY - rect.top) * DPR

    # Tableau → Foundation (auto)
    for i in range(7):
        xt = 45 * DPR + i * (CARD_WIDTH + CARD_GAP)
        if xt <= mx <= xt + CARD_WIDTH:
            p = state.tableau[i]
            if p and p[-1].face_up:
                yt = TABLEAU_OFFSET_Y + (len(p)-1)*TABLEAU_CARD_SPACING
                if yt <= my <= yt + CARD_HEIGHT:
                    if state.try_auto_move(p[-1], p):
                        update_stats()
                        return

    # Waste → Foundation (auto)
    x_w = 45*DPR + CARD_WIDTH + CARD_GAP
    if x_w <= mx <= x_w + CARD_WIDTH and 40*DPR <= my <= 40*DPR + CARD_HEIGHT:
        if state.waste and state.try_auto_move(state.waste[-1], state.waste):
            update_stats()

def update_stats():
    try:
        score_elem = document.getElementById("score")
        moves_elem = document.getElementById("moves")
        timer_elem = document.getElementById("timer")
        if score_elem: score_elem.innerText = str(state.score)
        if moves_elem: moves_elem.innerText = str(state.moves)
        if timer_elem:
            if state.start_time:
                elapsed = int(time.time() - state.start_time)
                m, s = divmod(elapsed, 60)
                timer_elem.innerText = f"{m:02d}:{s:02d}"
            else:
                timer_elem.innerText = "00:00"
    except Exception as e:
        console.log(f"Erro atualizando texto UI: {e}")

def _clear_hint():
    global active_hint, hint_timer
    active_hint = None
    hint_timer = 0.0

# --- Inicialização e Loop ---
async def run_game():
    console.log("Iniciando motor gráfico...")
    setup_events()
    while True:
        update_dimensions()
        resize_canvas_to_dpr()
        render_frame()
        update_stats()
        await asyncio.sleep(0.016)  # ~60 FPS

def setup_events():
    # Eventos de mouse (guardar proxies para evitar GC)
    for ev, fn in [
        ("mousedown", on_mousedown),
        ("mousemove", on_mousemove),
        ("mouseup",   on_mouseup),
        ("dblclick",  on_dblclick),
    ]:
        p = create_proxy(fn)
        window.addEventListener(ev, p)
        _proxies.append(p)

    # Botões do cabeçalho
    def handle_reset(ev):
        global selected_cards, drag_source, active_hint, hint_timer, game_won
        state.reset()
        selected_cards = []
        drag_source = None
        active_hint = None
        hint_timer = 0.0
        game_won = False
        update_stats()

    def handle_hint(ev):
        global active_hint, hint_timer
        h = state.get_hint()
        if h:
            active_hint = h
            hint_timer = time.time()
        else:
            console.log("Nenhuma jogada disponível.")

    btn_new = document.getElementById("new-game-btn")
    if btn_new:
        p = create_proxy(handle_reset)
        btn_new.addEventListener("click", p)
        _proxies.append(p)

    btn_hint = document.getElementById("hint-btn")
    if btn_hint:
        p = create_proxy(handle_hint)
        btn_hint.addEventListener("click", p)
        _proxies.append(p)

# Iniciar tudo
asyncio.ensure_future(run_game())
console.log("Antigravity Solitaire 2D: Pronto para jogar!")