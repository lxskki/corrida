import random

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
        self.tableau = []
        self.stock = []
        self.waste = []
        self.foundations = []
        self.score = 0
        self.moves = 0
        self.start_time = None
        self.reset()
        
    def reset(self):
        self.deck = [Card(v, s) for s in Card.SUITS for v in Card.VALUES]
        random.shuffle(self.deck)
        
        self.tableau = [[] for _ in range(7)]
        for i in range(7):
            for j in range(i + 1):
                card = self.deck.pop()
                if j == i:
                    card.face_up = True
                self.tableau[i].append(card)
                
        self.stock = self.deck
        self.waste = []
        self.foundations = [[] for _ in range(4)]
        self.score = 0
        self.moves = 0
        self.start_time = None
        
    def can_move_to_tableau(self, card, target_pile):
        if not target_pile:
            return card.value == 'K'
        
        bottom_card = target_pile[-1]
        if not bottom_card.face_up:
            return False
            
        return card.is_red != bottom_card.is_red and card.rank == bottom_card.rank - 1
        
    def can_move_to_foundation(self, card, foundation_index):
        target_f = self.foundations[foundation_index]
        if not target_f:
            return card.value == 'A'
        
        top_card = target_f[-1]
        return card.suit == top_card.suit and card.rank == top_card.rank + 1

    def draw_from_stock(self):
        if not self.stock:
            # Recycle waste
            self.stock = list(reversed(self.waste))
            self.waste = []
            for c in self.stock:
                c.face_up = False
        else:
            card = self.stock.pop()
            card.face_up = True
            self.waste.append(card)
        self.moves += 1

    def try_auto_move(self, card_ref, source_pile):
        # Logic to move card to foundation automatically
        for i in range(4):
            if self.can_move_to_foundation(card_ref, i):
                source_pile.remove(card_ref)
                self.foundations[i].append(card_ref)
                self.score += 10
                self.moves += 1
                return True
        return False
