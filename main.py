import asyncio
from pyodide.ffi import create_proxy
from js import document, window, console, CanvasGradient, Path2D
from card_logic import GameState, Card

# Setup canvas
canvas = document.getElementById("game-canvas")
ctx = canvas.getContext("2d")

# Game dimensions & constants
DPR = window.devicePixelRatio or 1
CARD_WIDTH = 90 * DPR
CARD_HEIGHT = 130 * DPR
CARD_GAP = 30 * DPR
TABLEAU_OFFSET_Y = 180 * DPR
TABLEAU_CARD_SPACING = 30 * DPR
CORNER_RADIUS = 8 * DPR

# Colors (matching style.css)
COLOR_WHITE = "#ffffff"
COLOR_RED = "#e11d48"
COLOR_BLACK = "#0f172a"
COLOR_GOLD = "#fbbf24"
COLOR_GLASS = "rgba(255, 255, 255, 0.1)"

# Game State
state = GameState()
state_history = [] 

active_hint = None
global_timer = { 
    'hint': 0,
    'start_time': 0, # Game logic starts on first move
    'last_tick': 0
}

selected_cards = []  # Cards currently being dragged
drag_source = None
mouse_start_x = 0
mouse_start_y = 0
drag_start_x = 0
drag_start_y = 0
current_mouse_x = 0
current_mouse_y = 0

def draw_rounded_rect(ctx, x, y, width, height, radius, color, shadow=True):
    ctx.beginPath()
    ctx.moveTo(x + radius, y)
    ctx.lineTo(x + width - radius, y)
    ctx.quadraticCurveTo(x + width, y, x + width, y + radius)
    ctx.lineTo(x + width, y + height - radius)
    ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height)
    ctx.lineTo(x + radius, y + height)
    ctx.quadraticCurveTo(x, y + height, x, y + height - radius)
    ctx.lineTo(x, y + radius)
    ctx.quadraticCurveTo(x, y, x + radius, y)
    ctx.closePath()
    
    if shadow:
        ctx.shadowColor = "rgba(0,0,0,0.2)"
        ctx.shadowBlur = 10 * DPR
        ctx.shadowOffsetY = 4 * DPR
        
    ctx.fillStyle = color
    ctx.fill()
    
    # Reset shadow
    ctx.shadowBlur = 0
    ctx.shadowOffsetY = 0

def draw_suit_icon(ctx, suit, x, y, size):
    ctx.font = f"bold {size}px Inter"
    ctx.textAlign = "center"
    ctx.textBaseline = "middle"
    
    icons = {
        'copas': '♥',
        'espadas': '♠',
        'ouros': '♦',
        'paus': '♣'
    }
    
    ctx.fillStyle = COLOR_RED if suit in ['copas', 'ouros'] else COLOR_BLACK
    ctx.fillText(icons.get(suit, ''), x, y)

def draw_card(ctx, card, x, y, is_dragging=False):
    if not card.face_up:
        # Draw Back
        draw_rounded_rect(ctx, x, y, CARD_WIDTH, CARD_HEIGHT, CORNER_RADIUS, "#1e293b")
        # Interior pattern
        ctx.strokeStyle = "rgba(255,255,255,0.05)"
        ctx.lineWidth = 2 * DPR
        ctx.strokeRect(x+5*DPR, y+5*DPR, CARD_WIDTH-10*DPR, CARD_HEIGHT-10*DPR)
    else:
        # Draw Front
        draw_rounded_rect(ctx, x, y, CARD_WIDTH, CARD_HEIGHT, CORNER_RADIUS, COLOR_WHITE)
        
        # Text/Icons
        color = COLOR_RED if card.is_red else COLOR_BLACK
        ctx.fillStyle = color
        ctx.font = f"bold {20*DPR}px Outfit"
        ctx.textAlign = "left"
        
        # Corner Value
        ctx.fillText(card.value, x + 10*DPR, y + 25*DPR)
        draw_suit_icon(ctx, card.suit, x + 15*DPR, y + 45*DPR, 18 * DPR)
        
        # Center Icon
        draw_suit_icon(ctx, card.suit, x + CARD_WIDTH/2, y + CARD_HEIGHT/2, 48 * DPR)

def draw_hint_highlight(hint):
    if not hint: return
    
    ctx.strokeStyle = COLOR_GOLD
    ctx.lineWidth = 4 * DPR
    ctx.setLineDash([10 * DPR, 5 * DPR])
    
    # Highlight Source
    source_x, source_y = -100, -100
    if hint['type'] == 'waste_to_foundations' or hint['type'] == 'waste_to_tableau':
        source_x = 40*DPR + CARD_WIDTH + CARD_GAP
        source_y = 30*DPR
    elif hint['type'] == 'tableau_to_foundations' or hint['type'] == 'tableau_to_tableau':
        source_idx = hint['source_idx']
        source_x = 40*DPR + source_idx * (CARD_WIDTH + CARD_GAP)
        if hint['type'] == 'tableau_to_tableau':
            source_y = TABLEAU_OFFSET_Y + hint['card_idx'] * TABLEAU_CARD_SPACING
        else:
            source_y = TABLEAU_OFFSET_Y + (len(state.tableau[source_idx]) - 1) * TABLEAU_CARD_SPACING
            
    if source_x > 0:
        ctx.strokeRect(source_x - 4*DPR, source_y - 4*DPR, CARD_WIDTH + 8*DPR, CARD_HEIGHT + 8*DPR)
        
    # Highlight Target
    target_x, target_y = -100, -100
    if 'foundations' in hint['type']:
        target_idx = hint['target_idx']
        target_x = canvas.width - (4 - target_idx) * (CARD_WIDTH + CARD_GAP)
        target_y = 30*DPR
    elif 'tableau' in hint['type']:
        target_idx = hint['target_idx']
        target_x = 40*DPR + target_idx * (CARD_WIDTH + CARD_GAP)
        target_y = TABLEAU_OFFSET_Y + len(state.tableau[target_idx]) * TABLEAU_CARD_SPACING if state.tableau[target_idx] else TABLEAU_OFFSET_Y

    if target_x > 0:
        ctx.strokeStyle = "rgba(251, 191, 36, 0.5)"
        ctx.strokeRect(target_x - 4*DPR, target_y - 4*DPR, CARD_WIDTH + 8*DPR, CARD_HEIGHT + 8*DPR)
    
    ctx.setLineDash([])

def render(elapsed_time):
    # Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    
    # Draw Hint Highlight
    if active_hint and global_timer['hint'] > 0:
        draw_hint_highlight(active_hint)
        global_timer['hint'] -= 1
    
    # Draw Stock Pile Area
    draw_rounded_rect(ctx, 40*DPR, 30*DPR, CARD_WIDTH, CARD_HEIGHT, CORNER_RADIUS, "rgba(255,255,255,0.03)", False)
    if state.stock:
        draw_card(ctx, state.stock[-1], 40*DPR, 30*DPR)
    
    # Draw Waste Pile
    if state.waste:
        # Avoid drawing waste card if it's currently being dragged
        is_dragging_waste = (drag_source is state.waste and state.waste[-1] in selected_cards)
        if not is_dragging_waste:
            draw_card(ctx, state.waste[-1], 40*DPR + CARD_WIDTH + CARD_GAP, 30*DPR)
        
    # Draw foundations
    for i in range(4):
        x = canvas.width - (4-i)*(CARD_WIDTH + CARD_GAP)
        draw_rounded_rect(ctx, x, 30*DPR, CARD_WIDTH, CARD_HEIGHT, CORNER_RADIUS, "rgba(255,255,255,0.03)", False)
        if state.foundations[i]:
            draw_card(ctx, state.foundations[i][-1], x, 30*DPR)
            
    # Draw Tableau columns
    for i in range(7):
        x = 40*DPR + i*(CARD_WIDTH + CARD_GAP)
        y_base = TABLEAU_OFFSET_Y
        
        # Empty placeholder
        draw_rounded_rect(ctx, x, y_base, CARD_WIDTH, CARD_HEIGHT, CORNER_RADIUS, "rgba(255,255,255,0.02)", False)
        
        for j, card in enumerate(state.tableau[i]):
            # Skip drawing if card is being dragged
            is_dragging = (drag_source is state.tableau[i] and card in selected_cards)
            if is_dragging:
                continue
                
            card_y = y_base + (j * TABLEAU_CARD_SPACING)
            draw_card(ctx, card, x, card_y)
            
    # Draw Dragged Cards last to keep them on top
    if selected_cards:
        for i, card in enumerate(selected_cards):
            drag_x = current_mouse_x - (mouse_start_x - drag_start_x)
            drag_y = current_mouse_y - (mouse_start_y - drag_start_y) + i * TABLEAU_CARD_SPACING
            draw_card(ctx, card, drag_x, drag_y, True)

def on_mousedown(event):
    global selected_cards, drag_source, mouse_start_x, mouse_start_y, drag_start_x, drag_start_y
    rect = canvas.getBoundingClientRect()
    mouse_x = (event.clientX - rect.left) * DPR
    mouse_y = (event.clientY - rect.top) * DPR
    
    # Initialize global start time on first interaction
    if not state.start_time or state.start_time == 0.0:
        import time
        state.start_time = time.time()
        console.log("Timer iniciado!")
    
    mouse_start_x = mouse_x
    mouse_start_y = mouse_y
    
    # Check Stock Pile
    if 40*DPR <= mouse_x <= 40*DPR + CARD_WIDTH and 30*DPR <= mouse_y <= 30*DPR + CARD_HEIGHT:
        state.draw_from_stock()
        update_stats()
        return

    # Check Tableau Piles (from top to bottom for correct selection)
    for i in range(7):
        x_start = 40*DPR + i*(CARD_WIDTH + CARD_GAP)
        if x_start <= mouse_x <= x_start + CARD_WIDTH:
            pile = state.tableau[i]
            for j in range(len(pile)-1, -1, -1):
                card_y = TABLEAU_OFFSET_Y + j * TABLEAU_CARD_SPACING
                if card_y <= mouse_y <= card_y + (CARD_HEIGHT if j == len(pile)-1 else TABLEAU_CARD_SPACING):
                    if pile[j].face_up:
                        selected_cards = pile[j:]
                        drag_source = pile
                        drag_start_x = x_start
                        drag_start_y = card_y
                        return
                    elif j == len(pile)-1: # Flip top card if face down
                        pile[j].face_up = True
                        return

    # Check Waste Pile (can only move top card)
    x_waste = 40*DPR + CARD_WIDTH + CARD_GAP
    if x_waste <= mouse_x <= x_waste + CARD_WIDTH and 30*DPR <= mouse_y <= 30*DPR + CARD_HEIGHT:
        if state.waste:
            selected_cards = [state.waste[-1]]
            drag_source = state.waste
            drag_start_x = x_waste
            drag_start_y = 30*DPR
            return

def on_mousemove(event):
    global current_mouse_x, current_mouse_y
    rect = canvas.getBoundingClientRect()
    current_mouse_x = (event.clientX - rect.left) * DPR
    current_mouse_y = (event.clientY - rect.top) * DPR

def on_mouseup(event):
    global selected_cards, drag_source
    if not selected_cards:
        return
        
    rect = canvas.getBoundingClientRect()
    mouse_x = (event.clientX - rect.left) * DPR
    mouse_y = (event.clientY - rect.top) * DPR
    
    moved = False
    
    # Try move to Tableau
    for i in range(7):
        x_target = 40*DPR + i*(CARD_WIDTH + CARD_GAP)
        if x_target <= mouse_x <= x_target + CARD_WIDTH:
            if state.can_move_to_tableau(selected_cards[0], state.tableau[i]):
                # Execute move
                for card in selected_cards:
                    if drag_source is not None:
                        drag_source.remove(card)
                    state.tableau[i].append(card)
                moved = True
                state.moves += 1
                state.score += 5
                break
                
    # Try move to Foundation (only single card)
    if not moved and len(selected_cards) == 1:
        for i in range(4):
            x_f = canvas.width - (4-i)*(CARD_WIDTH + CARD_GAP)
            if x_f <= mouse_x <= x_f + CARD_WIDTH and 30*DPR <= mouse_y <= 30*DPR + CARD_HEIGHT:
                if state.can_move_to_foundation(selected_cards[0], i):
                    target_card = selected_cards[0]
                    if drag_source is not None and target_card in drag_source:
                        drag_source.remove(target_card)
                    state.foundations[i].append(target_card)
                    moved = True
                    state.score += 10
                    state.moves += 1
                    break

    selected_cards = []
    drag_source = None
    update_stats()

def on_dblclick(event):
    rect = canvas.getBoundingClientRect()
    mouse_x = (event.clientX - rect.left) * DPR
    mouse_y = (event.clientY - rect.top) * DPR
    
    # Check Tableau Piles for top cards
    for i in range(7):
        x_start = 40*DPR + i*(CARD_WIDTH + CARD_GAP)
        if x_start <= mouse_x <= x_start + CARD_WIDTH:
            pile = state.tableau[i]
            if pile:
                last_card_y = TABLEAU_OFFSET_Y + (len(pile)-1) * TABLEAU_CARD_SPACING
                if last_card_y <= mouse_y <= last_card_y + CARD_HEIGHT:
                    # Move top card if possible
                    if state.try_auto_move(pile[-1], pile):
                        update_stats()
                        return

    # Check Waste Pile
    if state.waste:
        x_waste = 40*DPR + CARD_WIDTH + CARD_GAP
        if x_waste <= mouse_x <= x_waste + CARD_WIDTH and 30*DPR <= mouse_y <= 30*DPR + CARD_HEIGHT:
            if state.try_auto_move(state.waste[-1], state.waste):
                update_stats()
                return

def update_stats():
    document.getElementById("score").innerHTML = str(state.score)
    document.getElementById("moves").innerHTML = str(state.moves)
    
    # Timer logic
    if state.start_time:
        import time
        elapsed = int(time.time() - state.start_time)
        mins = elapsed // 60
        secs = elapsed % 60
        document.getElementById("timer").innerHTML = f"{mins:02d}:{secs:02d}"

async def game_loop():
    while True:
        render(0)
        update_stats()
        await asyncio.sleep(0.016) # ~60 FPS

# Event bindings
canvas.addEventListener("mousedown", create_proxy(on_mousedown))
window.addEventListener("mousemove", create_proxy(on_mousemove))
canvas.addEventListener("dblclick", create_proxy(on_dblclick))
window.addEventListener("mouseup", create_proxy(on_mouseup))

def start_new_game(event):
    state.reset()
    document.getElementById("timer").innerHTML = "00:00"
    update_stats()

def on_hint_click(event):
    global active_hint
    console.log("Buscando dica...")
    active_hint = state.get_hint()
    if active_hint:
        console.log(f"Dica encontrada: {active_hint['type']}")
        global_timer['hint'] = 180 # 3 seconds
    else:
        console.log("Nenhum movimento óbvio encontrado. Tente comprar uma carta!")

document.getElementById("new-game-btn").onclick = create_proxy(start_new_game)
document.getElementById("hint-btn").onclick = create_proxy(on_hint_click)
# Dica: Botão de desfazer pode ser implementado salvando cópias do estado, mas vamos focar na dica primeiro.

# Kickoff
asyncio.ensure_future(game_loop())
console.log("Antigravity Solitaire 2D Initialized")
