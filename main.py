import asyncio
from pyodide.ffi import create_proxy
from js import document, window, console
from card_logic import GameState
import time

# --------- Cores ---------
COLOR_FELT = "#2d5a27"
COLOR_RED = "#d63031"
COLOR_BLACK = "#2d3436"
COLOR_PLACEHOLDER = "rgba(0, 0, 0, 0.20)"
COLOR_HINT = "rgba(241, 196, 15, 0.95)"
COLOR_OVERLAY = "rgba(0,0,0,0.45)"

# --------- Layout Dinâmico ---------
DPR = 1.0
CARD_WIDTH = 110
CARD_HEIGHT = 160
CARD_GAP = 20
TABLEAU_OFFSET_Y = 240
DEFAULT_TABLEAU_SPACING = 35
CORNER_RADIUS = 12

# Por-coluna (atualizado a cada quadro)
tableau_spacings = [DEFAULT_TABLEAU_SPACING]*7

# --------- Estado de Jogo / Render ---------
state = GameState()
selected_cards = []
drag_source = None

mouse_start_x = mouse_start_y = 0
drag_start_x = drag_start_y = 0
current_mouse_x = current_mouse_y = 0

active_hint = None
hint_timer = 0.0
game_won = False
no_moves = False

# Render sob demanda / arrasto
needs_redraw = True
is_dragging = False

# --------- Canvas ---------
canvas = document.getElementById("game-canvas")
ctx = canvas.getContext("2d")

# Guardar proxies para evitar GC
_proxies = []

# --------- Dimensões / Responsividade ---------
def update_dpr():
    global DPR
    DPR = float(window.devicePixelRatio or 1.0)

_last_w = 0
_last_h = 0
def resize_canvas_to_css():
    """Ajusta canvas a partir do CSS * DPR, retorna True se alterou."""
    global _last_w, _last_h
    rect = canvas.getBoundingClientRect()
    target_w = max(1, int(rect.width * DPR))
    target_h = max(1, int(rect.height * DPR))
    if target_w != _last_w or target_h != _last_h:
        canvas.width, canvas.height = target_w, target_h
        _last_w, _last_h = target_w, target_h
        return True
    return False

def recalc_layout():
    """Dimensiona cartas para caberem em 7 colunas com margens fixas."""
    global CARD_WIDTH, CARD_HEIGHT, CARD_GAP, TABLEAU_OFFSET_Y, DEFAULT_TABLEAU_SPACING, CORNER_RADIUS
    margin = 45 * DPR
    CARD_GAP = 20 * DPR
    usable = canvas.width - 2*margin - 6*CARD_GAP
    # Largura alvo por coluna (clamp para não ficar minúsculo ou gigante)
    cw = usable / 7 if usable > 0 else 110*DPR
    cw = max(90*DPR, min(140*DPR, cw))
    CARD_WIDTH = cw
    CARD_HEIGHT = cw * 1.45  # proporção agradável
    TABLEAU_OFFSET_Y = 240 * DPR
    DEFAULT_TABLEAU_SPACING = 35 * DPR
    CORNER_RADIUS = 12 * DPR

# pattern cache para verso
_back_pattern = None
def rebuild_back_pattern():
    from js import document as _doc
    global _back_pattern
    pat = _doc.createElement("canvas")
    pat.width, pat.height = int(60*DPR), int(60*DPR)
    pctx = pat.getContext("2d")
    pctx.fillStyle = "#1e3799"
    pctx.fillRect(0, 0, pat.width, pat.height)
    pctx.strokeStyle = "rgba(255,255,255,0.12)"
    pctx.lineWidth = 3 * DPR
    for i in range(-pat.width, pat.width*2, int(12*DPR)):
        pctx.beginPath()
        pctx.moveTo(i, 0)
        pctx.lineTo(i + pat.width, pat.height)
        pctx.stroke()
    _back_pattern = ctx.createPattern(pat, "repeat")

# --------- Desenho de primitivas ---------
def draw_rounded_rect(x, y, w, h, r, fill, stroke=None):
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
    ctx.fillStyle = fill
    ctx.fill()
    if stroke:
        ctx.strokeStyle = stroke
        ctx.lineWidth = 1 * DPR
        ctx.stroke()

def draw_suit_at(suit, x, y, size, alpha=1.0):
    icons = {'copas': '♥', 'espadas': '♠', 'ouros': '♦', 'paus': '♣'}
    color = COLOR_RED if suit in ['copas', 'ouros'] else COLOR_BLACK
    ctx.save()
    ctx.globalAlpha = alpha
    ctx.fillStyle = color
    ctx.font = f"bold {int(size)}px sans-serif"
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

def draw_card(card, x, y):
    try:
        if not card.face_up:
            # Verso com pattern leve (cache)
            draw_rounded_rect(x, y, CARD_WIDTH, CARD_HEIGHT, CORNER_RADIUS,
                              "#1e3799", "rgba(255,255,255,0.2)")
            if _back_pattern is None:
                rebuild_back_pattern()
            pad = 6 * DPR
            ctx.save()
            ctx.beginPath()
            ctx.rect(x + pad, y + pad, CARD_WIDTH - 2*pad, CARD_HEIGHT - 2*pad)
            ctx.closePath()
            ctx.fillStyle = _back_pattern
            ctx.fill()
            ctx.restore()
        else:
            # Frente
            draw_rounded_rect(x, y, CARD_WIDTH, CARD_HEIGHT, CORNER_RADIUS,
                              "#ffffff", "rgba(0,0,0,0.1)")
            color = COLOR_RED if card.is_red else COLOR_BLACK
            ctx.fillStyle = color

            ctx.font = f"bold {int(22*DPR)}px sans-serif"
            ctx.textAlign = "left"
            ctx.textBaseline = "top"
            ctx.fillText(str(card.value), x + 8*DPR, y + 8*DPR)
            draw_suit_at(card.suit, x + 18*DPR, y + 44*DPR, 16 * DPR)

            if card.value in ['K', 'Q', 'J']:
                emojis = {'K': '👑', 'Q': '👸', 'J': '🫡'}
                ctx.font = f"{int(60*DPR)}px sans-serif"
                ctx.textAlign = "center"
                ctx.textBaseline = "middle"
                ctx.fillText(emojis.get(card.value, card.value), x + CARD_WIDTH/2, y + CARD_HEIGHT/2)
            else:
                draw_suit_at(card.suit, x + CARD_WIDTH/2, y + CARD_HEIGHT/2, 54 * DPR)

            ctx.save()
            ctx.translate(x + CARD_WIDTH, y + CARD_HEIGHT)
            ctx.rotate(3.14159)
            ctx.font = f"bold {int(22*DPR)}px sans-serif"
            ctx.textAlign = "left"
            ctx.textBaseline = "top"
            ctx.fillText(str(card.value), 8*DPR, 8*DPR)
            draw_suit_at(card.suit, 18*DPR, 44*DPR, 16 * DPR)
            ctx.restore()
    except Exception as e:
        console.log(f"Erro renderizando carta: {e}")

def check_victory():
    try:
        return all(len(p) == 13 for p in state.foundations)
    except Exception:
        return False

def compute_spacing_for_column(n_cards):
    """Espaçamento vertical que garante caber no canvas."""
    if n_cards <= 1:
        return DEFAULT_TABLEAU_SPACING
    available = canvas.height - (TABLEAU_OFFSET_Y + 20*DPR) - CARD_HEIGHT  # espaço até o rodapé
    if available <= 0:
        return max(12*DPR, DEFAULT_TABLEAU_SPACING * 0.6)
    spacing = available / (n_cards - 1)
    # clamp para leitura/estética
    spacing = max(14*DPR, min(DEFAULT_TABLEAU_SPACING, spacing))
    return spacing

# --------- Render principal ---------
def render_frame():
    try:
        # fundo
        ctx.fillStyle = COLOR_FELT
        ctx.fillRect(0, 0, canvas.width, canvas.height)

        y_top = 40 * DPR
        x_stock = 45 * DPR

        # Estoque
        draw_rounded_rect(x_stock, y_top, CARD_WIDTH, CARD_HEIGHT, CORNER_RADIUS, "rgba(0,0,0,0.1)")
        if state.stock:
            draw_card(state.stock[-1], x_stock, y_top)

        # Descarte
        x_waste = x_stock + CARD_WIDTH + CARD_GAP
        if state.waste and not (drag_source is state.waste and selected_cards):
            draw_card(state.waste[-1], x_waste, y_top)

        # Fundações
        f_suits = ['paus', 'copas', 'espadas', 'ouros']
        for i in range(4):
            xf = canvas.width - (4 - i) * (CARD_WIDTH + CARD_GAP) - 45 * DPR
            draw_rounded_rect(xf, y_top, CARD_WIDTH, CARD_HEIGHT, CORNER_RADIUS, COLOR_PLACEHOLDER)
            draw_suit_at(f_suits[i], xf + CARD_WIDTH/2, y_top + CARD_HEIGHT/2, 45*DPR, 0.15)
            if state.foundations[i]:
                draw_card(state.foundations[i][-1], xf, y_top)

        # Spacing por coluna (para caber tudo)
        for i in range(7):
            tableau_spacings[i] = compute_spacing_for_column(len(state.tableau[i]))

        # Tableau
        for i in range(7):
            xt = 45 * DPR + i * (CARD_WIDTH + CARD_GAP)
            draw_rounded_rect(xt, TABLEAU_OFFSET_Y, CARD_WIDTH, CARD_HEIGHT, CORNER_RADIUS, COLOR_PLACEHOLDER)
            pile = state.tableau[i]
            sp = tableau_spacings[i]
            for j, card in enumerate(pile):
                if drag_source is pile and card in selected_cards:
                    continue
                yt = TABLEAU_OFFSET_Y + j * sp
                draw_card(card, xt, yt)

        # Arrasto
        if selected_cards:
            ctx.shadowColor = "rgba(0,0,0,0.3)"
            ctx.shadowBlur = 10 * DPR
            for i, card in enumerate(selected_cards):
                dx = current_mouse_x - (mouse_start_x - drag_start_x)
                dy = current_mouse_y - (mouse_start_y - drag_start_y) + (i * (14*DPR if tableau_spacings and min(tableau_spacings) < 18*DPR else DEFAULT_TABLEAU_SPACING))
                draw_card(card, dx, dy)
            ctx.shadowBlur = 0

        # Dica (realce do alvo)
        if active_hint and (time.time() - hint_timer) <= 1.25:
            t = active_hint
            if t["type"] in ("waste_to_f", "tab_to_f"):
                i = t["f_idx"]
                xf = canvas.width - (4 - i) * (CARD_WIDTH + CARD_GAP) - 45 * DPR
                draw_highlight_rect(xf, y_top, CARD_WIDTH, CARD_HEIGHT)
            elif t["type"] in ("tab_to_tab", "tab_to_tab_reveal"):
                j = t["dst"]
                xt = 45 * DPR + j * (CARD_WIDTH + CARD_GAP)
                draw_highlight_rect(xt, TABLEAU_OFFSET_Y, CARD_WIDTH, CARD_HEIGHT)
            elif t["type"] == "waste_to_tab":
                j = t["dst"]
                xt = 45 * DPR + j * (CARD_WIDTH + CARD_GAP)
                draw_highlight_rect(xt, TABLEAU_OFFSET_Y, CARD_WIDTH, CARD_HEIGHT)

        # Overlays
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

        global needs_redraw
        needs_redraw = False
    except Exception as e:
        console.log(f"CRITICAL RENDER ERROR: {e}")

# --------- Hit test auxiliaries ---------
def column_top_x(i):
    return 45 * DPR + i * (CARD_WIDTH + CARD_GAP)

def column_card_at(i, my):
    """Retorna índice j clicado na coluna i, ou None."""
    pile = state.tableau[i]
    if not pile:
        return None
    sp = tableau_spacings[i]
    # percorre de cima para baixo (ajuste de altura do “degrau”)
    for j in range(len(pile)-1, -1, -1):
        yt = TABLEAU_OFFSET_Y + j * sp
        h = CARD_HEIGHT if j == len(pile)-1 else sp
        if yt <= my <= yt + h:
            return j
    return None

# --------- Input: Mouse/Touch ---------
def on_mousedown_like(mx, my):
    global mouse_start_x, mouse_start_y, selected_cards, drag_source, drag_start_x, drag_start_y, is_dragging, needs_redraw

    mouse_start_x, mouse_start_y = mx, my

    if not state.start_time:
        state.start_time = time.time()

    # 1) Stock
    x_stock, y_top = 45 * DPR, 40 * DPR
    if x_stock <= mx <= x_stock + CARD_WIDTH and y_top <= my <= y_top + CARD_HEIGHT:
        state.draw_from_stock()
        update_stats()
        needs_redraw = True
        return

    # 2) Waste
    x_waste = x_stock + CARD_WIDTH + CARD_GAP
    if x_waste <= mx <= x_waste + CARD_WIDTH and y_top <= my <= y_top + CARD_HEIGHT:
        if state.waste:
            selected_cards = [state.waste[-1]]
            drag_source = state.waste
            drag_start_x, drag_start_y = x_waste, y_top
            is_dragging = True
            needs_redraw = True
            return

    # 3) Tableau
    for i in range(7):
        xt = column_top_x(i)
        if xt <= mx <= xt + CARD_WIDTH:
            j = column_card_at(i, my)
            if j is None:
                continue
            pile = state.tableau[i]
            if pile[j].face_up:
                selected_cards = pile[j:]
                drag_source = pile
                sp = tableau_spacings[i]
                drag_start_x, drag_start_y = xt, (TABLEAU_OFFSET_Y + j * sp)
                is_dragging = True
                needs_redraw = True
                return
            elif j == len(pile)-1:
                pile[j].face_up = True
                state.moves += 1
                update_stats()
                needs_redraw = True
                return

def on_mousedown(ev):
    rect = canvas.getBoundingClientRect()
    mx = (ev.clientX - rect.left) * DPR
    my = (ev.clientY - rect.top) * DPR
    on_mousedown_like(mx, my)

def on_mousemove(ev):
    global current_mouse_x, current_mouse_y, needs_redraw
    rect = canvas.getBoundingClientRect()
    current_mouse_x = (ev.clientX - rect.left) * DPR
    current_mouse_y = (ev.clientY - rect.top) * DPR
    if selected_cards:
        needs_redraw = True

def on_mouseup(ev):
    rect = canvas.getBoundingClientRect()
    mx = (ev.clientX - rect.left) * DPR
    my = (ev.clientY - rect.top) * DPR
    finish_drop(mx, my)

# ---- Touch (mobile) ----
def on_touchstart(ev):
    try:
        t = ev.touches[0]
    except Exception:
        return
    ev.preventDefault()
    rect = canvas.getBoundingClientRect()
    mx = (t.clientX - rect.left) * DPR
    my = (t.clientY - rect.top) * DPR
    on_mousedown_like(mx, my)

def on_touchmove(ev):
    global current_mouse_x, current_mouse_y, needs_redraw
    try:
        t = ev.touches[0]
    except Exception:
        return
    ev.preventDefault()
    rect = canvas.getBoundingClientRect()
    current_mouse_x = (t.clientX - rect.left) * DPR
    current_mouse_y = (t.clientY - rect.top) * DPR
    if selected_cards:
        needs_redraw = True

def on_touchend(ev):
    ev.preventDefault()
    # usa o último current_mouse_* como posição do drop
    finish_drop(current_mouse_x, current_mouse_y)

# --------- Drop / regras pós-movimento ---------
def finish_drop(mx, my):
    global selected_cards, drag_source, is_dragging, needs_redraw, game_won, no_moves

    if not selected_cards:
        return
    moved = False

    # Tenta soltar no Tableau
    for i in range(7):
        xt = column_top_x(i)
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

    # Virar carta exposta (se foi do tableau)
    if moved and drag_source in state.tableau:
        if drag_source and len(drag_source) > 0 and not drag_source[-1].face_up:
            drag_source[-1].face_up = True
            state.score += 5

    selected_cards = []
    drag_source = None
    is_dragging = False
    update_stats()
    needs_redraw = True

    # Vitória / sem jogadas
    if not game_won and check_victory():
        game_won = True
    no_moves = (not game_won) and (not state.has_any_move())

# --------- Stats ---------
def update_stats():
    try:
        s = document.getElementById("score");  m = document.getElementById("moves");  t = document.getElementById("timer")
        if s: s.innerText = str(state.score)
        if m: m.innerText = str(state.moves)
        if t:
            if state.start_time:
                elapsed = int(time.time() - state.start_time)
                mm, ss = divmod(elapsed, 60)
                t.innerText = f"{mm:02d}:{ss:02d}"
            else:
                t.innerText = "00:00"
    except Exception as e:
        console.log(f"Erro UI: {e}")

def clear_hint():
    global active_hint, hint_timer
    active_hint = None
    hint_timer = 0.0

# --------- Loop principal ---------
async def run_game():
    console.log("Iniciando...")
    setup_events()

    # primeiro layout
    update_dpr()
    resize_canvas_to_css()
    recalc_layout()
    rebuild_back_pattern()

    while True:
        if is_dragging or needs_redraw:
            render_frame()
            update_stats()
            await asyncio.sleep(0.016)  # ~60 FPS enquanto arrasta
        else:
            await asyncio.sleep(0.05)

# --------- Eventos / Botões ---------
def setup_events():
    # Mouse
    p = create_proxy(on_mousedown); window.addEventListener("mousedown", p); _proxies.append(p)
    p = create_proxy(on_mousemove); window.addEventListener("mousemove", p); _proxies.append(p)
    p = create_proxy(on_mouseup);   window.addEventListener("mouseup",   p); _proxies.append(p)
    p = create_proxy(on_touchstart); canvas.addEventListener("touchstart", p); _proxies.append(p)
    p = create_proxy(on_touchmove);  canvas.addEventListener("touchmove",  p); _proxies.append(p)
    p = create_proxy(on_touchend);   canvas.addEventListener("touchend",   p); _proxies.append(p)

    # Resize (recalcula DPR e tamanhos)
    def on_resize(ev):
        update_dpr()
        if resize_canvas_to_css():
            recalc_layout()
            rebuild_back_pattern()
        global needs_redraw
        needs_redraw = True
    p = create_proxy(on_resize); window.addEventListener("resize", p); _proxies.append(p)

    # Botões
    def handle_reset(ev):
        global selected_cards, drag_source, active_hint, hint_timer, game_won, no_moves, needs_redraw
        state.reset()
        selected_cards, drag_source = [], None
        active_hint, hint_timer = None, 0.0
        game_won = False
        no_moves = False
        update_stats()
        needs_redraw = True
    p = create_proxy(handle_reset)
    btn_new = document.getElementById("new-game-btn")
    if btn_new: btn_new.addEventListener("click", p); _proxies.append(p)

    def handle_hint(ev):
        """Executa uma jogada automática inteligente (melhor que só 'sugerir')."""
        global active_hint, hint_timer, needs_redraw, game_won, no_moves
        mv = state.best_move()
        if not mv:
            console.log("Nenhuma jogada disponível.")
            return

        t = mv["type"]
        # 1) Stock
        if t == 'draw':
            state.draw_from_stock()
        # 2) Waste -> Foundation
        elif t == 'waste_to_f':
            c = state.waste[-1]
            state.waste.pop()
            state.foundations[mv['f_idx']].append(c)
            state.moves += 1; state.score += 10
        # 3) Tab -> Foundation
        elif t == 'tab_to_f':
            src = mv['src']; c = state.tableau[src].pop()
            state.foundations[mv['f_idx']].append(c)
            state.moves += 1; state.score += 10
            # vira exposta
            if state.tableau[src] and not state.tableau[src][-1].face_up:
                state.tableau[src][-1].face_up = True
                state.score += 5
        # 4) Waste -> Tableau
        elif t == 'waste_to_tab':
            c = state.waste[-1]; state.waste.pop()
            state.tableau[mv['dst']].append(c)
            state.moves += 1; state.score += 5
        # 5) Tableau -> Tableau (com ou sem revelar)
        elif t in ('tab_to_tab', 'tab_to_tab_reveal'):
            src, dst, idx = mv['src'], mv['dst'], mv['idx']
            moving = state.tableau[src][idx:]
            del state.tableau[src][idx:]
            state.tableau[dst].extend(moving)
            state.moves += 1; state.score += 5
            if state.tableau[src] and not state.tableau[src][-1].face_up:
                state.tableau[src][-1].face_up = True
                state.score += 5

        # feedback visual do alvo
        active_hint = mv
        hint_timer = time.time()

        update_stats()
        needs_redraw = True

        if not game_won and check_victory():
            game_won = True
        no_moves = (not game_won) and (not state.has_any_move())

    p = create_proxy(handle_hint)
    btn_hint = document.getElementById("hint-btn")
    if btn_hint: btn_hint.addEventListener("click", p); _proxies.append(p)

# Inicia o jogo
asyncio.ensure_future(run_game())
console.log("Antigravity Solitaire 2D: pronto!")