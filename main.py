import asyncio
from pyodide.ffi import create_proxy
from js import document, window, console, CanvasGradient, Path2D
from card_logic import GameState, Card

try:
    from js import console
except ImportError:
    # Fallback for local testing
    class Console:
        def log(self, *args): print(*args)
    console = Console()

# Setup canvas
canvas = document.getElementById("game-canvas")
ctx = canvas.getContext("2d")

# Game dimensions & constants
COLOR_WHITE = "#ffffff"
COLOR_RED = "#c0392b" # Changed from #d63031
COLOR_BLACK = "#2c3e50" # Changed from #2d3436
COLOR_GOLD = "#f1c40f"
COLOR_GLASS = "rgba(255, 255, 255, 0.1)" # Kept, not in diff but useful
COLOR_PLACEHOLDER = "rgba(0, 0, 0, 0.2)" # Changed from rgba(255, 255, 255, 0.15)
COLOR_FELT = "#2d5a27" # Changed from #27ae60

# Card Dimensions (Proportional to image)
DPR = float(window.devicePixelRatio or 1.0)
CARD_WIDTH = 110 * DPR # Changed from 100 * DPR
CARD_HEIGHT = 160 * DPR # Changed from 145 * DPR
CARD_GAP = 20 * DPR # Changed from 15 * DPR
TABLEAU_OFFSET_Y = 220 * DPR # Changed from 190 * DPR
TABLEAU_CARD_SPACING = 35 * DPR
CORNER_RADIUS = 12 * DPR # Changed from 10 * DPR

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

def draw_suit_icon(ctx, suit, x, y, size, alpha=1.0): # Merged with the later definition
    icons = {
        'copas': '♥',
        'espadas': '♠',
        'ouros': '♦',
        'paus': '♣'
    }
    
    ctx.save()
    if alpha < 1.0: ctx.globalAlpha = alpha
    ctx.font = f"bold {size}px sans-serif" # Changed to sans-serif
    ctx.textAlign = "center"
    ctx.textBaseline = "middle"
    
    ctx.fillStyle = COLOR_RED if suit in ['copas', 'ouros'] else COLOR_BLACK
    ctx.fillText(icons.get(suit, ''), x, y)
    ctx.restore()

def draw_card(ctx, card, x, y, is_dragging=False):
    try:
        console.log(f"Drawing card: {card.value}{card.suit} at ({x}, {y}), face_up={card.face_up}, dragging={is_dragging}")
        if not card.face_up:
            # Classic Blue Back with Border
            draw_rounded_rect(ctx, x, y, CARD_WIDTH, CARD_HEIGHT, CORNER_RADIUS, "#1e3799")
            # Stripe pattern
            ctx.save()
            ctx.beginPath()
            ctx.rect(x + 8*DPR, y + 8*DPR, CARD_WIDTH - 16*DPR, CARD_HEIGHT - 16*DPR)
            ctx.clip()
            ctx.strokeStyle = "rgba(255,255,255,0.1)"
            ctx.lineWidth = 2 * DPR
            for i in range(-500, 500, 15):
                ctx.moveTo(x + i*DPR, y)
                ctx.lineTo(x + (i + 300)*DPR, y + 400*DPR)
            ctx.stroke()
            ctx.restore()
        else:
            # Draw Front
            draw_rounded_rect(ctx, x, y, CARD_WIDTH, CARD_HEIGHT, CORNER_RADIUS, "#ffffff")
            # Border
            ctx.strokeStyle = "rgba(0,0,0,0.1)"
            ctx.lineWidth = 1 * DPR
            ctx.strokeRect(x, y, CARD_WIDTH, CARD_HEIGHT)
            
            color = COLOR_RED if card.is_red else COLOR_BLACK
            ctx.fillStyle = color
            
            # Use standard font for compatibility
            font_main = f"bold {int(20*DPR)}px sans-serif"
            font_small = f"bold {int(14*DPR)}px sans-serif"
            
            # Rank (Top Left)
            ctx.font = font_main
            ctx.textAlign = "left"
            ctx.textBaseline = "top"
            ctx.fillText(card.value, x + 8*DPR, y + 8*DPR)
            
            # Small Suit below rank
            draw_suit_icon_internal(ctx, card.suit, x + 18*DPR, y + 42*DPR, 14 * DPR)
            
            # Center Content
            if card.value in ['K', 'Q', 'J']:
                ctx.font = f"bold {int(60*DPR)}px sans-serif"
                ctx.textAlign = "center"
                ctx.textBaseline = "middle"
                ctx.fillText(card.value, x + CARD_WIDTH/2, y + CARD_HEIGHT/2)
            else:
                draw_suit_icon_internal(ctx, card.suit, x + CARD_WIDTH/2, y + CARD_HEIGHT/2, 48 * DPR)
            
            # Bottom Right (Inverted)
            ctx.save()
            ctx.translate(x + CARD_WIDTH, y + CARD_HEIGHT)
            ctx.rotate(3.14159)
            ctx.font = font_main
            ctx.textAlign = "left"
            ctx.textBaseline = "top"
            ctx.fillText(card.value, 8*DPR, 8*DPR)
            draw_suit_icon_internal(ctx, card.suit, 18*DPR, 42*DPR, 14 * DPR)
            ctx.restore()
    except Exception as e:
        console.log(f"Erro ao desenhar carta: {e}")

def draw_suit_icon_internal(ctx, suit, x, y, size, alpha=1.0):
    icons = {'copas': '♥', 'espadas': '♠', 'ouros': '♦', 'paus': '♣'}
    color = COLOR_RED if suit in ['copas', 'ouros'] else COLOR_BLACK
    ctx.save()
    if alpha < 1.0: ctx.globalAlpha = alpha
    ctx.fillStyle = color
    ctx.font = f"bold {int(size)}px sans-serif" # Changed to sans-serif
    ctx.textAlign = "center"
    ctx.textBaseline = "middle"
    ctx.fillText(icons.get(suit, ''), x, y)
    ctx.restore()

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
        target_x = canvas.width - (4 - target_idx) * (CARD_WIDTH + CARD_GAP) - 40*DPR # Adjusted for right alignment
        target_y = 30*DPR
    elif 'tableau' in hint['type']:
        target_idx = hint['target_idx']
        target_x = 40*DPR + target_idx * (CARD_WIDTH + CARD_GAP)
        target_y = TABLEAU_OFFSET_Y + len(state.tableau[target_idx]) * TABLEAU_CARD_SPACING if state.tableau[target_idx] else TABLEAU_OFFSET_Y

    if target_x > 0:
        ctx.strokeStyle = "rgba(251, 191, 36, 0.7)"
        ctx.strokeRect(target_x - 4*DPR, target_y - 4*DPR, CARD_WIDTH + 8*DPR, CARD_HEIGHT + 8*DPR)
    
    ctx.setLineDash([])

def render(elapsed_time):
    try:
        render_internal()
    except Exception as e:
        if not hasattr(render, "_err_logged"):
            console.log(f"Erro render: {e}")
            render._err_logged = True

def render_internal():
    console.log("Rendering frame...")
    # Fill background
    ctx.fillStyle = COLOR_FELT
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    
    # Initialization Check
    if not state.stock and not any(state.tableau) and not any(state.foundations) and not state.waste:
        console.log("Initial game state detected as empty, resetting...")
        state.reset()
        console.log(f"After initial reset: Stock={len(state.stock)}, Tableau piles={len(state.tableau)}, First tableau pile cards={len(state.tableau[0]) if state.tableau else 0}")
        
    y_row1 = 30 * DPR
    
    # 1. Stock (Top Left)
    console.log("Drawing Stock pile...")
    x_stock = 40 * DPR
    draw_rounded_rect(ctx, x_stock, y_row1, CARD_WIDTH, CARD_HEIGHT, CORNER_RADIUS, COLOR_PLACEHOLDER, False)
    if state.stock:
        draw_card(ctx, state.stock[-1], x_stock, y_row1)
        
    # 2. Waste
    console.log("Drawing Waste pile...")
    x_waste = x_stock + CARD_WIDTH + CARD_GAP
    draw_rounded_rect(ctx, x_waste, y_row1, CARD_WIDTH, CARD_HEIGHT, CORNER_RADIUS, COLOR_PLACEHOLDER, False) # Draw placeholder for waste
    if state.waste:
        # Don't draw if top card is being dragged from waste
        already_dragging = (drag_source is state.waste and state.waste[-1] in selected_cards)
        if not already_dragging:
            draw_card(ctx, state.waste[-1], x_waste, y_row1)

    # 3. Foundations (Top Right)
    console.log("Drawing Foundations...")
    f_suits = ['paus', 'copas', 'espadas', 'ouros']
    for i in range(4):
        xf = canvas.width - (4-i)*(CARD_WIDTH + CARD_GAP) - 40*DPR
        draw_rounded_rect(ctx, xf, y_row1, CARD_WIDTH, CARD_HEIGHT, CORNER_RADIUS, COLOR_PLACEHOLDER, False)
        # Suit Watermark
        draw_suit_icon_internal(ctx, f_suits[i], xf + CARD_WIDTH/2, y_row1 + CARD_HEIGHT/2, 45*DPR, 0.2)
        if i < len(state.foundations) and state.foundations[i]:
            draw_card(ctx, state.foundations[i][-1], xf, y_row1)
            
    # 4. Tableau (Below Row 1)
    console.log("Drawing Tableau piles...")
    for i in range(7):
        xt = 40*DPR + i*(CARD_WIDTH + CARD_GAP)
        # Empty slot rect
        draw_rounded_rect(ctx, xt, TABLEAU_OFFSET_Y, CARD_WIDTH, CARD_HEIGHT, CORNER_RADIUS, COLOR_PLACEHOLDER, False)
        
        if i < len(state.tableau):
            pile = state.tableau[i]
            for j, card in enumerate(pile):
                # Skip if dragging
                if drag_source is pile and card in selected_cards:
                    continue
                
                yt = TABLEAU_OFFSET_Y + (j * TABLEAU_CARD_SPACING)
                draw_card(ctx, card, xt, yt)
    
    # 5. Dragged Cards (Last)
    console.log("Drawing dragged cards...")
    if selected_cards:
        for i, card in enumerate(selected_cards):
            dx = current_mouse_x - (mouse_start_x - drag_start_x)
            dy = current_mouse_y - (mouse_start_y - drag_start_y) + (i * TABLEAU_CARD_SPACING)
            draw_card(ctx, card, dx, dy, True)
            
    # 6. Hint Highlight
    console.log("Drawing hint highlight...")
    if active_hint and global_timer['hint'] > 0:
        draw_hint_highlight(active_hint)
        global_timer['hint'] -= 1


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
    x_stock = 40 * DPR
    y_row1 = 30 * DPR
    if x_stock <= mouse_x <= x_stock + CARD_WIDTH and y_row1 <= mouse_y <= y_row1 + CARD_HEIGHT:
        state.draw_from_stock()
        update_stats()
        return

    # Check Tableau Piles (from top to bottom for correct selection)
    for i in range(7):
        x_start = 40*DPR + i*(CARD_WIDTH + CARD_GAP)
        if x_start <= mouse_x <= x_start + CARD_WIDTH:
            pile = state.tableau[i]
            # Check if clicking on an empty tableau pile placeholder
            if not pile and TABLEAU_OFFSET_Y <= mouse_y <= TABLEAU_OFFSET_Y + CARD_HEIGHT:
                # No card to select, but it's a valid click on a pile area
                return
            
            for j in range(len(pile)-1, -1, -1):
                card_y = TABLEAU_OFFSET_Y + j * TABLEAU_CARD_SPACING
                card_h = CARD_HEIGHT if j == len(pile)-1 else TABLEAU_CARD_SPACING
                if card_y <= mouse_y <= card_y + card_h:
                    if pile[j].face_up:
                        selected_cards = pile[j:]
                        drag_source = pile
                        drag_start_x = x_start
                        drag_start_y = card_y
                        return
                    elif j == len(pile)-1: # Flip top card if face down
                        pile[j].face_up = True
                        update_stats()
                        return

    # Check Waste Pile (can only move top card)
    x_waste = 40*DPR + CARD_WIDTH + CARD_GAP
    y_row1 = 30 * DPR
    if x_waste <= mouse_x <= x_waste + CARD_WIDTH and y_row1 <= mouse_y <= y_row1 + CARD_HEIGHT:
        if state.waste:
            selected_cards = [state.waste[-1]]
            drag_source = state.waste
            drag_start_x = x_waste
            drag_start_y = y_row1
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
        # Check if mouse is over the target tableau pile area
        if x_target <= mouse_x <= x_target + CARD_WIDTH and TABLEAU_OFFSET_Y <= mouse_y: # Check entire column height
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
            x_f = canvas.width - (4-i)*(CARD_WIDTH + CARD_GAP) - 40*DPR
            y_row1 = 30 * DPR
            if x_f <= mouse_x <= x_f + CARD_WIDTH and y_row1 <= mouse_y <= y_row1 + CARD_HEIGHT:
                if state.can_move_to_foundation(selected_cards[0], i):
                    target_card = selected_cards[0]
                    if drag_source is not None:
                        try:
                            drag_source.remove(target_card)
                        except ValueError: # Card might not be in drag_source if it was already moved
                            pass
                                
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
