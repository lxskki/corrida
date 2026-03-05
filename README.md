# Antigravity Solitaire 2D

Um jogo de cartas Solitaire (Klondike) moderno, construído com lógica Python rodando no navegador via PyScript.

## 🚀 Como Jogar
1. Certifique-se de ter o Python instalado.
2. Abra um terminal na pasta do projeto.
3. Inicie um servidor local:
   ```bash
   python -m http.server 8000
   ```
4. Abra o navegador em `http://localhost:8000`.

## 🎮 Controles
- **Arrastar e Soltar**: Mova cartas individuais ou pilhas válidas.
- **Clique Duplo**: Envia automaticamente uma carta para as fundações, se o movimento for legal.
- **Clique no Estoque**: Compra uma nova carta.
- **Novo Jogo**: Reinicia a partida.

## 🛠️ Tecnologias
- **Lógica**: Python 3 (executado no cliente).
- **Interface**: Canvas 2D + HTML5/CSS3.
- **Engine**: PyScript (Pyodide).
- **Aesthetics**: Design premium com HSL, glassmorphism e tipografia moderna.

## 📂 Estrutura de Arquivos
- `index.html`: Interface e carregamento do PyScript.
- `style.css`: Sistema de design e estilização global.
- `main.py`: Loop de renderização e controle de entrada.
- `card_logic.py`: Regras do jogo e motor de lógica Klondike.
- `pyscript.toml`: Configuração do ambiente Python.
