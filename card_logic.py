import random

# Tentar importar console do JS para debug no navegador
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
        self.tableau = [[] for _ in range(7)]
        self.stock = []
        self.waste = []
        self.foundations = [[] for _ in range(4)]
        self.score = 0
        self.moves = 0
        self.start_time = 0.0
        self.reset()

    def reset(self):
        # Criar baralho
        full_deck = [Card(v, s) for s in Card.SUITS for v in Card.VALUES]
        random.shuffle(full_deck)

        # Limpar pilhas/placar
        self.tableau = [[] for _ in range(7)]
        self.stock = []
        self.waste = []
        self.foundations = [[] for _ in range(4)]
        self.score = 0
        self.moves = 0
        self.start_time = 0.0

        # Distribuição no tableau
        for i in range(7):
            for j in range(i + 1):
                card = full_deck.pop()
                if j == i:
                    card.face_up = True
                self.tableau[i].append(card)

        # Restante no estoque
        self.stock = full_deck

    # ---- Regras ----
    def can_move_to_tableau(self, card, target_pile):
        if not target_pile:
            return card.value == 'K'
        top = target_pile[-1]
        if not top.face_up:
            return False
        # Klondike: cor alternada, ordem decrescente
        return card.is_red != top.is_red and card.rank == top.rank - 1

    def can_move_to_foundation(self, card, f_idx):
        if f_idx < 0 or f_idx >= 4:
            return False
        target = self.foundations[f_idx]
        if not target:
            return card.value == 'A'
        top = target[-1]
        return card.suit == top.suit and card.rank == top.rank + 1

    def draw_from_stock(self):
        if not self.stock:
            if not self.waste:
                return
            # recicla waste -> stock
            self.stock = list(reversed(self.waste))
            self.waste = []
            for c in self.stock:
                c.face_up = False
        else:
            card = self.stock.pop()
            card.face_up = True
            self.waste.append(card)
            self.moves += 1

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

    # ---- Heurística de melhor jogada (para o botão Dica) ----
    def best_move(self):
        """
        Retorna um dict descrevendo a melhor jogada disponível, prioridade:
        1) Waste -> Foundation
        2) Tableau -> Foundation
        3) Movimentos que revelem carta virada no tableau (tab->tab_reveal)
        4) Waste -> Tableau
        5) Tableau -> Tableau
        6) Comprar do Stock (draw)
        """
        # 1) Waste -> Foundation
        if self.waste:
            c = self.waste[-1]
            for f in range(4):
                if self.can_move_to_foundation(c, f):
                    return {'type': 'waste_to_f', 'f_idx': f}

        # 2) Tableau -> Foundation
        for i in range(7):
            if self.tableau[i]:
                c = self.tableau[i][-1]
                if c.face_up:
                    for f in range(4):
                        if self.can_move_to_foundation(c, f):
                            return {'type': 'tab_to_f', 'src': i, 'f_idx': f}

        # 3) Movimentos que revelem carta virada
        for src in range(7):
            pile = self.tableau[src]
            if not pile:
                continue
            # há alguma virada logo abaixo do bloco aberto?
            first_up = None
            for k, c in enumerate(pile):
                if c.face_up:
                    first_up = k
                    break
            if first_up is None or first_up == 0:
                continue  # não vai revelar nada
            # tentar mover o bloco aberto (first_up .. fim) para outro tableau
            moving = pile[first_up]
            for dst in range(7):
                if dst == src:
                    continue
                if self.can_move_to_tableau(moving, self.tableau[dst]):
                    return {'type': 'tab_to_tab_reveal', 'src': src, 'dst': dst, 'idx': first_up}

        # 4) Waste -> Tableau
        if self.waste:
            c = self.waste[-1]
            for j in range(7):
                if self.can_move_to_tableau(c, self.tableau[j]):
                    return {'type': 'waste_to_tab', 'dst': j}

        # 5) Tableau -> Tableau (qualquer)
        for i in range(7):
            pile = self.tableau[i]
            if not pile:
                continue
            for k, c in enumerate(pile):
                if not c.face_up:
                    continue
                for j in range(7):
                    if i == j:
                        continue
                    if self.can_move_to_tableau(c, self.tableau[j]):
                        # evitar mover tudo para vazio se não for Rei
                        if not self.tableau[j] and c.value != 'K':
                            continue
                        return {'type': 'tab_to_tab', 'src': i, 'dst': j, 'idx': k}
                break  # só checa a partir do primeiro virado

        # 6) Comprar do stock
        if self.stock or self.waste:
            return {'type': 'draw'}

        return None

    # (Opcional) checar se ainda há jogadas
    def has_any_move(self):
        return self.best_move() is not None