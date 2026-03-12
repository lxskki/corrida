import random

# Tentar importar console do JS para depuração no navegador
try:
    from js import console
except ImportError:
    class ConsoleFallback:
        def log(self, *ms): print(*ms)
    console = ConsoleFallback()


class Card:
    SUITS = ['copas', 'espadas', 'ouros', 'paus']
    VALUES = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']

    def __init__(self, value, suit):
        self.value = value
        self.suit = suit
        self.face_up = False
        self.is_red = suit in ['copas', 'ouros']
        self.rank = self.VALUES.index(value) + 1

    def __repr__(self):
        return f"{self.value} de {self.suit}"


class GameState:
    def __init__(self):
        self.deck = []
        self.tableau = [[] for _ in range(7)]
        self.stock = []
        self.waste = []
        self.foundations = [[] for _ in range(4)]
        self.score = 0
        self.moves = 0
        self.start_time = 0.0
        self.reset()

    def reset(self):
        console.log("Reiniciando lógica do jogo...")
        # Criar baralho completo
        full_deck = []
        for s in Card.SUITS:
            for v in Card.VALUES:
                full_deck.append(Card(v, s))
        random.shuffle(full_deck)

        # Limpar pilhas
        self.tableau = [[] for _ in range(7)]
        self.stock = []
        self.waste = []
        self.foundations = [[] for _ in range(4)]
        self.score = 0
        self.moves = 0
        self.start_time = 0.0

        # Distribuir para o tabuleiro (Tableau)
        for i in range(7):
            for j in range(i + 1):
                if full_deck:
                    card = full_deck.pop()
                    if j == i:
                        card.face_up = True
                    self.tableau[i].append(card)

        # Restante vai para o estoque (Stock)
        self.stock = full_deck
        console.log("Estado do jogo reiniciado com sucesso.")

    def draw_from_stock(self):
        if not self.stock:
            if not self.waste:
                return
            # Reciclar lixo para o estoque
            self.stock = list(reversed(self.waste))
            self.waste = []
            for c in self.stock:
                c.face_up = False
        else:
            card = self.stock.pop()
            card.face_up = True
            self.waste.append(card)
            self.moves += 1

    def can_move_to_tableau(self, card, target_pile):
        if not target_pile:
            return card.value == 'K'
        top = target_pile[-1]
        if not top.face_up: 
            return False
        # Cores alternadas e ordem decrescente
        return card.is_red != top.is_red and card.rank == top.rank - 1

    def can_move_to_foundation(self, card, f_idx):
        if f_idx < 0 or f_idx >= 4: 
            return False
        target = self.foundations[f_idx]
        if not target:
            return card.value == 'A'
        top = target[-1]
        return card.suit == top.suit and card.rank == top.rank + 1

    def try_auto_move(self, card, source_pile):
        for i in range(4):
            if self.can_move_to_foundation(card, i):
                if card in source_pile:
                    source_pile.remove(card)
                self.foundations[i].append(card)
                self.score += 10
                self.moves += 1
                return True
        return False

    def get_hint(self):
        # Hint logic: simple scan
        # 1. Waste to Foundations
        if self.waste:
            c = self.waste[-1]
            for i in range(4):
                if self.can_move_to_foundation(c, i):
                    return {'type': 'waste_to_f', 'f_idx': i}

        # 2. Tableau to Foundations
        for i in range(7):
            if self.tableau[i]:
                c = self.tableau[i][-1]
                if c.face_up:
                    for j in range(4):
                        if self.can_move_to_foundation(c, j):
                            return {'type': 'tab_to_f', 'src': i, 'f_idx': j}

        # 3. Tableau to Tableau
        for i in range(7):
            if not self.tableau[i]: 
                continue
            for k, c in enumerate(self.tableau[i]):
                if c.face_up:
                    for j in range(7):
                        if i == j: 
                            continue
                        if self.can_move_to_tableau(c, self.tableau[j]):
                            if k == 0 and not self.tableau[j]:
                                continue
                            return {'type': 'tab_to_tab', 'src': i, 'target': j, 'card_idx': k}
                    break
        return None